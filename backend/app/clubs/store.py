"""Club data: every query the club routes need, in one place. Multi-step changes (joining by invite,
handing over ownership) run in one transaction, with the rows they depend on locked."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from ..db import Club, ClubInvite, Database, Membership, User, aware
from . import policy
from .policy import PolicyError


@dataclass(frozen=True)
class MemberRow:
    user_id: int
    username: str
    role: str
    joined_at: datetime


class ClubStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- reading -----------------------------------------------------------------------------------------
    async def by_slug(self, slug: str) -> Club | None:
        if not isinstance(slug, str) or len(slug) > 48:
            return None
        async with self.db.sessions() as s:
            return (await s.execute(select(Club).where(Club.slug == slug))).scalar_one_or_none()

    async def by_id(self, club_id: int) -> Club | None:
        async with self.db.sessions() as s:
            return await s.get(Club, club_id)

    async def membership(self, club_id: int, user_id: int) -> Membership | None:
        async with self.db.sessions() as s:
            return await s.get(Membership, (club_id, user_id))

    async def mine(self, user_id: int) -> list[tuple[Club, str, int]]:
        """(club, your role, members) for every club you're in, newest first."""
        async with self.db.sessions() as s:
            counts = (
                select(Membership.club_id, func.count().label("n"))
                .where(Membership.banned.is_(False))
                .group_by(Membership.club_id)
                .subquery()
            )
            rows = await s.execute(
                select(Club, Membership.role, counts.c.n)
                .join(Membership, Membership.club_id == Club.id)
                .join(counts, counts.c.club_id == Club.id)
                .where(Membership.user_id == user_id, Membership.banned.is_(False))
                .order_by(Membership.joined_at.desc())
            )
            return [(club, role, int(n)) for club, role, n in rows.all()]

    async def members(self, club_id: int) -> list[MemberRow]:
        async with self.db.sessions() as s:
            rows = await s.execute(
                select(Membership.user_id, User.username, Membership.role, Membership.joined_at)
                .join(User, User.id == Membership.user_id)
                .where(Membership.club_id == club_id, Membership.banned.is_(False))
                .order_by(Membership.joined_at)
            )
            return [MemberRow(*r) for r in rows.all()]

    async def count_owned(self, user_id: int) -> int:
        async with self.db.sessions() as s:
            return int(
                await s.scalar(
                    select(func.count()).where(Membership.user_id == user_id, Membership.role == "owner")
                )
                or 0
            )

    async def invites(self, club_id: int) -> list[ClubInvite]:
        """Live invite links (codes aren't kept: only when they run out and how many uses are left)."""
        now = datetime.now(UTC)
        async with self.db.sessions() as s:
            rows = (await s.execute(select(ClubInvite).where(ClubInvite.club_id == club_id))).scalars().all()
        return [i for i in rows if i.uses_left > 0 and aware(i.expires_at) > now]

    # -- changing ----------------------------------------------------------------------------------------
    async def create(self, owner_id: int, name: str, about: str, rules: dict[str, Any]) -> Club:
        for _ in range(5):  # a slug clash is vanishingly rare: try a fresh random tail
            try:
                async with self.db.sessions() as s:
                    club = Club(
                        slug=policy.slug_for(name), name=name, about=about, rules=rules, created_by=owner_id
                    )
                    s.add(club)
                    await s.flush()
                    s.add(Membership(club_id=club.id, user_id=owner_id, role="owner", banned=False))
                    await s.commit()
                    return club
            except IntegrityError:
                continue
        raise PolicyError("busy", "Couldn't make that club just now. Try again", 503)

    async def update(self, club_id: int, values: dict[str, Any]) -> None:
        async with self.db.sessions() as s:
            await s.execute(update(Club).where(Club.id == club_id).values(**values))
            await s.commit()

    async def add_invite(self, club_id: int, by: int, code_hash: str, uses: int, days: int) -> ClubInvite:
        async with self.db.sessions() as s:
            invite = ClubInvite(
                club_id=club_id,
                code_hash=code_hash,
                created_by=by,
                uses_left=uses,
                expires_at=datetime.now(UTC) + timedelta(days=days),
            )
            s.add(invite)
            await s.commit()
            return invite

    async def revoke_invite(self, club_id: int, invite_id: int) -> bool:
        async with self.db.sessions() as s:
            done = await s.execute(
                delete(ClubInvite).where(ClubInvite.club_id == club_id, ClubInvite.id == invite_id)
            )
            await s.commit()
            return bool(done.rowcount)

    async def redeem(self, code_hash: str, user_id: int) -> Club:
        """Join the club an invite is for. The invite row is locked while it's checked and spent."""
        async with self.db.sessions() as s:
            invite = (
                await s.execute(select(ClubInvite).where(ClubInvite.code_hash == code_hash).with_for_update())
            ).scalar_one_or_none()
            if invite is None or invite.uses_left <= 0 or aware(invite.expires_at) <= datetime.now(UTC):
                raise PolicyError("bad_invite", "That invite has expired or doesn't exist", 404)
            club = await s.get(Club, invite.club_id)
            existing = await s.get(Membership, (invite.club_id, user_id))
            if club is None:
                raise PolicyError("bad_invite", "That invite has expired or doesn't exist", 404)
            if existing is not None:
                if existing.banned:
                    raise PolicyError("banned", "You can't rejoin this club", 403)
                return club  # already in: nothing to spend
            members = await s.scalar(
                select(func.count()).where(Membership.club_id == club.id, Membership.banned.is_(False))
            )
            if (members or 0) >= policy.MAX_MEMBERS:
                raise PolicyError("club_full", "This club is full", 409)
            joined = await s.scalar(
                select(func.count()).where(Membership.user_id == user_id, Membership.banned.is_(False))
            )
            if (joined or 0) >= policy.MAX_JOINED:
                raise PolicyError("too_many_clubs", f"You're in {policy.MAX_JOINED} clubs already", 409)
            s.add(Membership(club_id=club.id, user_id=user_id, role="member", banned=False))
            invite.uses_left -= 1
            await s.commit()
            return club

    async def set_role(self, club_id: int, user_id: int, role: str) -> None:
        async with self.db.sessions() as s:
            await s.execute(
                update(Membership)
                .where(Membership.club_id == club_id, Membership.user_id == user_id)
                .values(role=role)
            )
            await s.commit()

    async def remove(self, club_id: int, user_id: int, ban: bool) -> None:
        """Out of the club. A ban keeps a row so the same account can't come back by invite."""
        async with self.db.sessions() as s:
            if ban:
                await s.execute(
                    update(Membership)
                    .where(Membership.club_id == club_id, Membership.user_id == user_id)
                    .values(banned=True, role="member")
                )
            else:
                await s.execute(
                    delete(Membership).where(Membership.club_id == club_id, Membership.user_id == user_id)
                )
            await s.commit()

    async def transfer(self, club_id: int, owner_id: int, new_owner_id: int) -> None:
        """The owner hands the club over and stays on as an admin: one transaction, both rows locked."""
        async with self.db.sessions() as s:
            rows = (
                (
                    await s.execute(
                        select(Membership)
                        .where(
                            Membership.club_id == club_id, Membership.user_id.in_([owner_id, new_owner_id])
                        )
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            by_user = {m.user_id: m for m in rows}
            old, new = by_user.get(owner_id), by_user.get(new_owner_id)
            if old is None or old.role != "owner" or new is None or new.banned:
                raise PolicyError("bad_target", "Hand the club to a member", 400)
            old.role, new.role = "admin", "owner"
            await s.commit()

    async def delete(self, club_id: int) -> None:
        async with self.db.sessions() as s:
            await s.execute(delete(ClubInvite).where(ClubInvite.club_id == club_id))
            await s.execute(delete(Membership).where(Membership.club_id == club_id))
            await s.execute(delete(Club).where(Club.id == club_id))
            await s.commit()
