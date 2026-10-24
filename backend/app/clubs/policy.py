"""Club rules that need no I/O: roles and who may do what, names, club settings, invite codes, limits.

Roles, highest first: owner (one per club), admin, moderator, member. A role can act only on roles
below its own, and can never hand out a role as high as its own (only the owner makes admins, and the
owner role moves only by transfer).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from typing import Any

from ..games import REGISTRY

ROLES = ("owner", "admin", "moderator", "member")
RANK = {role: len(ROLES) - i for i, role in enumerate(ROLES)}  # owner 4 ... member 1

MAX_OWNED = 5  # clubs one account can own
MAX_JOINED = 30  # clubs one account can be in
MAX_MEMBERS = 500
INVITE_DAYS = (1, 30)  # how long an invite link can last
INVITE_USES = (1, 100)
NAME_LEN = (3, 40)
ABOUT_MAX = 200
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no 0/O, 1/I/L, U: read aloud and typed by hand


class PolicyError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# -- who may do what -------------------------------------------------------------------------------------
def at_least(role: str, needed: str) -> bool:
    return RANK.get(role, 0) >= RANK[needed]


def may_edit(role: str) -> bool:
    """Name, description and club rules."""
    return at_least(role, "admin")


def may_invite(role: str) -> bool:
    return at_least(role, "moderator")


def may_remove(actor: str, target: str) -> bool:
    """Moderators remove members; admins remove moderators and members; the owner removes anyone else."""
    return at_least(actor, "moderator") and RANK.get(actor, 0) > RANK.get(target, 0)


def may_set_role(actor: str, target: str, new: str) -> bool:
    """Change someone's role: they must be below you now, and the new role must be below yours too."""
    if new not in ROLES or new == "owner":
        return False
    return at_least(actor, "admin") and RANK[actor] > RANK.get(target, 0) and RANK[actor] > RANK[new]


# -- names and settings ----------------------------------------------------------------------------------
def clean_text(raw: Any, lo: int, hi: int, what: str) -> str:
    if not isinstance(raw, str):
        raise PolicyError("bad_input", f"{what} must be text")
    text = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not all(ch.isprintable() for ch in text):
        raise PolicyError("bad_input", f"{what} has characters that can't be shown")
    if not lo <= len(text) <= hi:
        raise PolicyError("bad_input", f"{what} must be {lo}-{hi} characters")
    return text


def clean_name(raw: Any) -> str:
    return clean_text(raw, *NAME_LEN, "A club name")


def clean_about(raw: Any) -> str:
    return clean_text(raw or "", 0, ABOUT_MAX, "The description")


def slug_for(name: str) -> str:
    """A readable, unique-ish address: "hostel-4-quiz-crew-7k3m". The random tail keeps names unguessable
    and lets two clubs share a name."""
    base = re.sub(
        r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    )
    base = base.strip("-")[:36].strip("-") or "club"
    tail = "".join(secrets.choice("abcdefghjkmnpqrstvwxyz23456789") for _ in range(4))
    return f"{base}-{tail}"


_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DEFAULT_RULES: dict[str, Any] = {"games": [], "chat": True, "battles": True, "quiet": None, "place": None}
_PLACE = re.compile(r"^[a-z0-9-]{1,48}$")


def clean_rules(raw: Any) -> dict[str, Any]:
    """Club settings: which games the club plays (none listed = all), chat and battles on or off, and
    quiet hours when nothing notifies members ({"from": "23:00", "to": "08:00"}, or None)."""
    if raw is None:
        return dict(DEFAULT_RULES)
    if not isinstance(raw, dict) or set(raw) - set(DEFAULT_RULES):
        raise PolicyError("bad_input", "Unknown club setting")
    rules = {**DEFAULT_RULES, **raw}
    games = rules["games"]
    if not isinstance(games, list) or len(games) > len(REGISTRY) or not all(g in REGISTRY for g in games):
        raise PolicyError("bad_input", "Pick games from the list")
    for key in ("chat", "battles"):
        if not isinstance(rules[key], bool):
            raise PolicyError("bad_input", f"{key} must be on or off")
    quiet = rules["quiet"]
    if quiet is not None:
        ok = isinstance(quiet, dict) and set(quiet) == {"from", "to"}
        if not ok or not all(isinstance(quiet[k], str) and _TIME.match(quiet[k]) for k in ("from", "to")):
            raise PolicyError("bad_input", "Quiet hours are two times like 23:00 and 08:00")
        if quiet["from"] == quiet["to"]:
            raise PolicyError("bad_input", "Quiet hours must start and end at different times")
    place = rules["place"]
    if place is not None and (not isinstance(place, str) or not _PLACE.fullmatch(place)):
        raise PolicyError("bad_input", "Pick a place from the list")
    return {
        "games": sorted(set(games)),
        "chat": rules["chat"],
        "battles": rules["battles"],
        "quiet": quiet,
        "place": place,  # only people verified at this place can join (a place slug), or None
    }


# -- invite codes ----------------------------------------------------------------------------------------
def new_invite_code() -> str:
    """10 characters, ~49 bits: shared in a group chat, typed by hand, never guessable."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(10))


def hash_invite(server_key: str, code: str) -> str:
    norm = "".join(code.split()).upper().replace("-", "")
    key = hmac.new(server_key.encode(), b"snazzlebop club invite v1", hashlib.sha256).digest()
    return hmac.new(key, norm.encode(), hashlib.sha256).hexdigest()


def clamp(value: Any, bounds: tuple[int, int], default: int, what: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not bounds[0] <= value <= bounds[1]:
        raise PolicyError("bad_input", f"{what} must be {bounds[0]}-{bounds[1]}")
    return value
