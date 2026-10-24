"""Who's around, and "Up for a game". In memory: it only matters while people are here.

- Online: the app pings while it's open (the inbox poll), so "online" means seen in the last
  ONLINE_FOR seconds.
- Up for a game: a member says they're free in a club for 30, 60 or 120 minutes, for any game or one
  pick. When MATCH_AT members of the same club are up within MATCH_WINDOW, for a game they all
  accept, a match forms: everyone is told, and the first to tap through opens the room and hosts it
  (so there is never an empty room). Nobody comes: the signals quietly run out.

A restart forgets all of this, which is fine: people say they're up again. Pure: the clock is injected.
"""

from __future__ import annotations

import secrets
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

ONLINE_FOR = 150.0
UP_MINUTES = (30, 60, 120)
MATCH_AT = 3
MATCH_WINDOW = 15 * 60.0
MATCH_LIFE = 30 * 60.0  # a match (and its room link) stays open this long
MAX_TRACKED = 50_000  # memory bound on "last seen" entries


@dataclass
class Up:
    user_id: int
    club_id: int
    game: str | None  # None: any game
    since: float
    until: float


@dataclass
class Match:
    id: str
    club_id: int
    game: str | None
    members: list[int]
    created: float
    until: float
    room: str | None = None  # set by the first member to tap through
    told: set[int] = field(default_factory=set)  # who has been notified


class Presence:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self.seen: dict[int, float] = {}
        self.ups: dict[int, Up] = {}  # one signal per person
        self.matches: dict[int, Match] = {}  # one open match per club

    # -- online ------------------------------------------------------------------------------------
    def touch(self, user_id: int) -> None:
        if len(self.seen) >= MAX_TRACKED:
            cutoff = self.clock() - ONLINE_FOR
            self.seen = {k: v for k, v in self.seen.items() if v > cutoff}
        self.seen[user_id] = self.clock()

    def online(self, user_id: int) -> bool:
        return self.clock() - self.seen.get(user_id, -1e18) < ONLINE_FOR

    # -- up for a game -------------------------------------------------------------------------------
    def up(self, user_id: int, club_id: int, game: str | None, minutes: int) -> Match | None:
        """Say you're up. Returns a match if this signal completed one (to notify), else None. Joining
        a club that already has an open match for your game adds you to it instead."""
        now = self.clock()
        if minutes not in UP_MINUTES:
            raise ValueError("minutes")
        self.ups[user_id] = Up(user_id, club_id, game, now, now + minutes * 60)
        self.touch(user_id)
        open_match = self.match_for(club_id)
        if open_match is not None and (open_match.game is None or game in (None, open_match.game)):
            if user_id not in open_match.members:
                open_match.members.append(user_id)
            return None
        return self._try_match(club_id)

    def down(self, user_id: int) -> None:
        self.ups.pop(user_id, None)

    def up_of(self, user_id: int) -> Up | None:
        u = self.ups.get(user_id)
        if u is not None and u.until <= self.clock():
            del self.ups[user_id]
            return None
        return u

    def club_ups(self, club_id: int) -> list[Up]:
        return [u for uid in list(self.ups) if (u := self.up_of(uid)) is not None and u.club_id == club_id]

    def match_for(self, club_id: int) -> Match | None:
        m = self.matches.get(club_id)
        if m is not None and m.until <= self.clock():
            del self.matches[club_id]
            return None
        return m

    def _try_match(self, club_id: int) -> Match | None:
        now = self.clock()
        fresh = [u for u in self.club_ups(club_id) if now - u.since <= MATCH_WINDOW]
        anyone = [u for u in fresh if u.game is None]
        picks = Counter(u.game for u in fresh if u.game is not None)
        # The game with the most takers (counting the "any game" people); ties go to the earliest pick.
        best_game, best = None, len(anyone)
        for game, n in picks.most_common():
            if n + len(anyone) > best:
                best_game, best = game, n + len(anyone)
        if best < MATCH_AT:
            return None
        members = [u.user_id for u in fresh if u.game in (None, best_game)]
        match = Match(secrets.token_urlsafe(8), club_id, best_game, members, now, now + MATCH_LIFE)
        self.matches[club_id] = match
        return match

    def take_room(self, club_id: int, user_id: int) -> tuple[Match, bool] | None:
        """A member taps through: (the match, True if they should open the room) or None."""
        m = self.match_for(club_id)
        if m is None or user_id not in m.members:
            return None
        return m, m.room is None

    def leave_club(self, club_id: int, user_id: int) -> None:
        """Someone left the club (or was removed): their signal and their place in a match go."""
        up = self.ups.get(user_id)
        if up is not None and up.club_id == club_id:
            del self.ups[user_id]
        match = self.matches.get(club_id)
        if match is not None and user_id in match.members:
            match.members.remove(user_id)

    def forget_club(self, club_id: int) -> None:
        """The club closed: nothing about it may carry over (a new club could even get its id)."""
        self.matches.pop(club_id, None)
        for uid in [uid for uid, up in self.ups.items() if up.club_id == club_id]:
            del self.ups[uid]

    def forget_user(self, user_id: int, closed_clubs: list[int]) -> None:
        """An account was deleted: drop it everywhere, and every club that closed with it."""
        self.seen.pop(user_id, None)
        self.ups.pop(user_id, None)
        for match in self.matches.values():
            if user_id in match.members:
                match.members.remove(user_id)
        for club_id in closed_clubs:
            self.forget_club(club_id)

    def sweep(self) -> None:
        for uid in list(self.ups):
            self.up_of(uid)
        for cid in list(self.matches):
            self.match_for(cid)
