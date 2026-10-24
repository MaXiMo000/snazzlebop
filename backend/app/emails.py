# ruff: noqa: E501  (email markup: one tag per line reads better than wrapped strings)
"""Every email Snazzlebop sends, as HTML (for mail apps) and plain text (the fallback part), built from
one description so the two never drift apart.

Email HTML is its own world: tables for layout, inline styles only, no web fonts, no remote images
(often blocked, and they would let a sender track opens). This keeps to what Gmail, Outlook and Apple
Mail all render the same way. Every value is escaped; links are only ever ones we build.

The look is the site's: a plum marquee header with bulbs, a cream card, a tangerine podium button.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape

PLUM = "#2b1b33"
PLUM_SOFT = "#6b4f73"
CREAM = "#fff1dc"
PAPER = "#fffaf1"
TANGERINE = "#ff6b2c"
MUSTARD = "#f2b705"
BULB = "#ffe7a1"
FONT = "font-family:'Trebuchet MS','Segoe UI',Roboto,Helvetica,Arial,sans-serif"
DISPLAY = "font-family:'Arial Black',Impact,'Segoe UI',Arial,sans-serif"


@dataclass(frozen=True)
class Email:
    subject: str
    html: str
    text: str


@dataclass(frozen=True)
class Message:
    """What one email says. Rendered by `render` into an Email."""

    subject: str
    preheader: str  # the grey preview line in the inbox
    heading: str
    paragraphs: list[str]
    greeting: str = ""
    button: tuple[str, str] | None = None  # (label, url)
    details: list[tuple[str, str]] = field(default_factory=list)  # a small facts table
    note: str = ""  # a quieter line under the main content
    code: str = ""  # a code to type, shown big
    why: str = ""  # first footer line: why this email arrived


def _p(text: str, size: int = 16, colour: str = PLUM, margin: str = "0 0 12px") -> str:
    return f'<p style="margin:{margin};{FONT};font-size:{size}px;line-height:1.55;color:{colour}">{escape(text)}</p>'


def _bulbs() -> str:
    dot = f'<span style="display:inline-block;width:8px;height:8px;margin:0 5px;border-radius:50%;background:{BULB}"></span>'
    return dot * 9


def _button(label: str, url: str) -> str:
    u, lab = escape(url, quote=True), escape(label)
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 10px">
  <tr><td style="background:{TANGERINE};border:3px solid {PLUM};border-radius:999px;box-shadow:0 4px 0 {PLUM}">
    <a href="{u}" style="display:inline-block;padding:14px 30px;{DISPLAY};font-size:15px;letter-spacing:1px;text-transform:uppercase;color:{PLUM};text-decoration:none">{lab}</a>
  </td></tr>
</table>
{_p("Button not working? Copy this link into your browser:", 12, PLUM_SOFT, "0 0 2px")}
<p style="margin:0 0 4px;{FONT};font-size:12px;line-height:1.5;word-break:break-all"><a href="{u}" style="color:{PLUM}">{escape(url)}</a></p>"""


def _details(rows: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<tr><td style="padding:9px 14px;{FONT};font-size:13px;font-weight:700;color:{PLUM_SOFT};width:100px;vertical-align:top">{escape(k)}</td>'
        f'<td style="padding:9px 14px 9px 0;{FONT};font-size:14px;color:{PLUM}">{escape(v)}</td></tr>'
        for k, v in rows
    )
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="margin:18px 0 4px;background:{CREAM};border:2px dashed {PLUM_SOFT};border-radius:12px">{cells}</table>'
    )


def _code(code: str) -> str:
    return (
        f'<p style="margin:18px 0 6px;padding:14px;background:{CREAM};border:3px solid {PLUM};border-radius:12px;'
        f'{DISPLAY};font-size:26px;letter-spacing:6px;text-align:center;color:{PLUM}">{escape(code)}</p>'
    )


def render(m: Message, site: str) -> Email:
    """The email for `m`. `site` is the public address, for the footer link."""
    home = escape(site, quote=True)
    body = "".join(
        [
            f'<h1 style="margin:0 0 14px;{DISPLAY};font-size:22px;line-height:1.25;color:{PLUM}">{escape(m.heading)}</h1>',
            _p(m.greeting) if m.greeting else "",
            "".join(_p(x) for x in m.paragraphs),
            _code(m.code) if m.code else "",
            _details(m.details) if m.details else "",
            _button(*m.button) if m.button else "",
            _p(m.note, 14, PLUM_SOFT, "20px 0 0") if m.note else "",
        ]
    )
    footer = "<br>".join(
        escape(x)
        for x in [m.why, "Snazzlebop: the party game show where your friends are the contestants."]
        if x
    )
    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">
<title>{escape(m.heading)}</title>
</head>
<body style="margin:0;padding:0;background:{CREAM}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{escape(m.preheader)}</div>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:{CREAM}">
<tr><td align="center" style="padding:26px 12px">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:560px">
  <tr><td align="center" style="background:{PLUM};border:3px solid {PLUM};border-radius:18px 18px 0 0;padding:14px 20px 16px">
    <div style="line-height:8px">{_bulbs()}</div>
    <div style="margin:10px 0 8px;{DISPLAY};font-size:26px;letter-spacing:1px;color:{MUSTARD}">&#9733; SNAZZLEBOP<span style="color:{TANGERINE}">!</span></div>
    <div style="line-height:8px">{_bulbs()}</div>
  </td></tr>
  <tr><td style="background:{PAPER};border:3px solid {PLUM};border-top:0;border-radius:0 0 18px 18px;padding:28px 26px 26px">{body}</td></tr>
  <tr><td style="padding:16px 10px 0;{FONT};font-size:12px;line-height:1.6;color:{PLUM_SOFT};text-align:center">
    {footer}<br><a href="{home}" style="color:{PLUM_SOFT};text-decoration:underline">Open Snazzlebop</a>
    &nbsp;&middot;&nbsp; <a href="{home}/account" style="color:{PLUM_SOFT};text-decoration:underline">Your account</a>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

    lines = [m.heading.upper(), ""]
    if m.greeting:
        lines += [m.greeting, ""]
    for x in m.paragraphs:
        lines += [x, ""]
    if m.code:
        lines += [f"    {m.code}", ""]
    if m.details:
        lines += [f"  {k}: {v}" for k, v in m.details] + [""]
    if m.button:
        lines += [f"{m.button[0]}: {m.button[1]}", ""]
    if m.note:
        lines += [m.note, ""]
    lines += ["--", *([m.why] if m.why else []), f"Snazzlebop: {site}", f"Your account: {site}/account"]
    return Email(subject=m.subject, html=html, text="\n".join(lines).strip())


# -- the emails ----------------------------------------------------------------------------------------
def now_text(at: datetime | None = None) -> str:
    return (at or datetime.now(UTC)).strftime("%d %b %Y, %H:%M UTC")


NOT_YOU = (
    "If that was you, there's nothing to do. If it wasn't, reset your password straight away, then use "
    '"Sign out other devices" on your account page.'
)


def verify_email(site: str, username: str, url: str, changed: bool = False) -> Email:
    return render(
        Message(
            subject="Confirm your email for Snazzlebop",
            preheader="One tap and you're all set.",
            heading="Confirm your email",
            greeting=f"Hi {username}," if changed else f"Welcome to the show, {username}!",
            paragraphs=[
                "Confirm this is your email address. Once it is, you can sign in with it, reset a forgotten "
                "password by email, and we'll warn you if anything changes on your account."
            ],
            button=("Confirm my email", url),
            note="The link works once, for 2 days. If you didn't ask for this, ignore this email: "
            "nothing happens until the link is used.",
            why="You got this because this address was added to a Snazzlebop account.",
        ),
        site,
    )


def sign_in_link(site: str, username: str, url: str) -> Email:
    return render(
        Message(
            subject="Your Snazzlebop sign-in link",
            preheader="Tap to sign in. The link works for 15 minutes.",
            heading="Sign in to Snazzlebop",
            greeting=f"Hi {username},",
            paragraphs=["Here's the sign-in link you asked for. Tap it on the device you want to play on."],
            button=("Sign me in", url),
            note="The link works once, for 15 minutes. If you didn't ask for it, ignore this email: "
            "nobody can sign in without it.",
            why="You got this because a sign-in link was asked for on your Snazzlebop account.",
        ),
        site,
    )


def reset_password(site: str, username: str, url: str) -> Email:
    return render(
        Message(
            subject="Reset your Snazzlebop password",
            preheader="Choose a new password. The link works for 30 minutes.",
            heading="Reset your password",
            greeting=f"Hi {username},",
            paragraphs=[
                "Someone (hopefully you) asked to reset the password for your Snazzlebop account. "
                "Choose a new one with the button below."
            ],
            button=("Choose a new password", url),
            note="The link works once, for 30 minutes. If you didn't ask for this, ignore this email: "
            "your password stays the same.",
            why="You got this because a password reset was asked for on your Snazzlebop account.",
        ),
        site,
    )


def notice(
    site: str, username: str, subject: str, what: str, details: list[tuple[str, str]] | None = None
) -> Email:
    """A short "this changed on your account" email, always ending with what to do if it wasn't you."""
    return render(
        Message(
            subject=subject,
            preheader=what,
            heading=subject.removeprefix("Snazzlebop: "),
            greeting=f"Hi {username},",
            paragraphs=[what],
            details=[*(details or []), ("When", now_text())],
            button=("This wasn't me: reset my password", f"{site}/account/forgot"),
            note=NOT_YOU,
            why="You got this because something changed on your Snazzlebop account.",
        ),
        site,
    )


def new_device(site: str, username: str, device: str) -> Email:
    return notice(
        site,
        username,
        "New sign-in to your Snazzlebop account",
        "Your account was just signed in from a device we haven't seen before.",
        [("Device", device)],
    )


def email_changed(site: str, username: str, new: str) -> Email:
    return notice(
        site,
        username,
        "Your Snazzlebop email was changed",
        "The email address on your account was changed. This address won't get account emails any more.",
        [("New email", mask(new))],
    )


def goodbye(site: str, username: str) -> Email:
    return render(
        Message(
            subject="Your Snazzlebop account was deleted",
            preheader="Your coins, stats and power-ups are gone for good.",
            heading="Account deleted",
            greeting=f"Hi {username},",
            paragraphs=[
                "Your Snazzlebop account and everything in it (coins, power-ups, stats, season points) has been "
                "deleted. Thanks for playing! Every game still works without an account, any time."
            ],
            details=[("When", now_text())],
            note="If you didn't do this, someone else had your password. Make a new account with a "
            "password you don't use anywhere else.",
            why="You got this because your Snazzlebop account was deleted.",
        ),
        site,
    )


def mask(email: str) -> str:
    """a***@example.com: enough to recognise, not enough to harvest."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def describe_device(ua: str) -> str:
    """ "Chrome on Windows" from a User-Agent, or a plain fallback. Only for email text."""
    browser = next(
        (
            name
            for key, name in (
                ("Edg/", "Edge"),
                ("OPR/", "Opera"),
                ("Firefox/", "Firefox"),
                ("Chrome/", "Chrome"),
                ("Safari/", "Safari"),
            )
            if key in ua
        ),
        "a browser",
    )
    system = next(
        (
            name
            for key, name in (
                ("Windows", "Windows"),
                ("Android", "Android"),
                ("iPhone", "iOS"),
                ("iPad", "iPadOS"),
                ("Mac OS X", "macOS"),
                ("CrOS", "ChromeOS"),
                ("Linux", "Linux"),
            )
            if key in ua
        ),
        "",
    )
    return f"{browser} on {system}" if system else browser
