"""Authenticator-app sign-in (TOTP, RFC 6238) and backup codes. Pure: no I/O, the time is passed in.

- The parameters are the ones every authenticator app assumes (HMAC-SHA1, 30 s steps, 6 digits);
  anything else silently fails to enrol in Google Authenticator, Authy or 1Password.
- No TOTP secret is stored. Each account keeps a random salt; its secret is derived from that salt and
  the server's key (HMAC), so a copy of the database alone reveals no one's secret.
- A code is good once: the time step it matched is remembered and an older or equal step is refused,
  so a code read over someone's shoulder can't be replayed in the same 90-second window.
- Backup codes (10, single use) are stored only as keyed hashes and compared in constant time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from urllib.parse import quote

TOTP_STEP = 30
TOTP_DIGITS = 6
DRIFT_STEPS = 1  # accept one step either side: phone clocks drift
BACKUP_CODE_COUNT = 10
# No I, L, O, U: the characters people copy wrongly from a printout.
_BACKUP_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
ISSUER = "Snazzlebop"


def new_salt() -> str:
    return secrets.token_hex(16)


def totp_secret(server_key: str, salt: str) -> str:
    """The account's base32 secret (160 bits), derived from its salt: never stored."""
    key = hmac.new(server_key.encode(), b"snazzlebop totp v1", hashlib.sha256).digest()
    raw = hmac.new(key, salt.encode(), hashlib.sha256).digest()[:20]
    return base64.b32encode(raw).decode().rstrip("=")


def totp_at(secret: str, counter: int) -> str:
    """The code for one 30-second step (RFC 4226 HOTP over the step counter)."""
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(value % 10**TOTP_DIGITS).zfill(TOTP_DIGITS)


def check_totp(secret: str, code: str, now: float, last_step: int = 0) -> int | None:
    """The time step a code matches (to remember as `last_step`), or None if it's wrong or reused."""
    code = "".join((code or "").split())
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return None
    step = int(now) // TOTP_STEP
    match = None
    for s in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):  # every step checked: constant work
        if hmac.compare_digest(totp_at(secret, s), code) and s > last_step:
            match = s
    return match


def totp_uri(secret: str, account: str) -> str:
    """What the authenticator app scans."""
    label = quote(f"{ISSUER}:{account}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits={TOTP_DIGITS}&period={TOTP_STEP}"


def qr_matrix(text: str) -> list[str]:
    """The QR code as rows of "1" (dark) and "0" (light), quiet zone included: the page draws it with its
    own elements (no injected SVG or HTML)."""
    import segno  # imported here: only enrolment needs it

    qr = segno.make(text, error="m")
    return ["".join("1" if dark else "0" for dark in row) for row in qr.matrix_iter(border=2)]


def new_backup_codes(server_key: str) -> tuple[list[str], list[str]]:
    """(codes to show once, keyed hashes to store)."""
    codes = [
        "-".join("".join(secrets.choice(_BACKUP_ALPHABET) for _ in range(4)) for _ in range(2))
        for _ in range(BACKUP_CODE_COUNT)
    ]
    return codes, [hash_backup_code(server_key, c) for c in codes]


def hash_backup_code(server_key: str, code: str) -> str:
    """Keyed, so the 40-bit codes can't be brute-forced from a copy of the database alone."""
    norm = "".join(code.split()).upper().replace("-", "")
    key = hmac.new(server_key.encode(), b"snazzlebop backup code v1", hashlib.sha256).digest()
    return hmac.new(key, norm.encode(), hashlib.sha256).hexdigest()


def take_backup_code(server_key: str, code: str, hashes: list[str]) -> list[str] | None:
    """Spend a backup code: the hashes left, or None if it isn't one. Every hash is compared."""
    wanted = hash_backup_code(server_key, code)
    found, kept = False, []
    for h in hashes:
        if hmac.compare_digest(h, wanted) and not found:
            found = True  # good exactly once
        else:
            kept.append(h)
    return kept if found else None
