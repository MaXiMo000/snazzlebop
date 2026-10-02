"""Fresh game content from Claude: validated, de-duplicated, persisted, and fed into the live pools.

The games never wait on this. When a game starts, the hub asks for more of that game's content;
if the generator is enabled (an API key is configured), not cooling down, within its hourly budget
and not already busy with that kind, it asks Claude for a small batch in the background. Every item
is validated and de-duplicated against everything already in the pool before it's appended, saved to
the database, and dealt to rooms (new items come out of the decks first). Any failure (no key, rate
limit, refusal, timeout, bad output) just means the built-in pools carry on.

Security: the key lives in the server's environment only; generated text is treated as untrusted
data (strict validation, no markup or URLs, rendered as plain text by React); nothing about players
or rooms is ever sent to the API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .games import content as C

log = logging.getLogger("snazzlebop.contentgen")

MODEL = "claude-opus-5-5"
BATCH = 15  # items asked for per call
POOL_CAP = 20_000  # per kind, so a runaway can't eat memory

# Words that have no place in a friendly party game. Generation is told to stay kind; this is the
# belt to those braces.
_DENY = re.compile(
    r"\b(kill|murderer|die|dies|dead|death|suicide|drunk|drugs?|sex|sexy|naked|nude|fat|ugly|stupid|dumb|"
    r"idiot|hate|racist|gun|guns|bomb|blood|weed|cocaine|vodka|beer|wine|nazi|slave|religion|politic\w*)\b",
    re.I,
)
_URLISH = re.compile(r"(https?:|www\.|\.com\b|\.net\b|\.org\b|[<>{}\[\]\\`|@#$^*=~])", re.I)

ShowColor = {"red", "orange", "yellow", "green", "blue", "purple", "pink", "brown", "white", "black"}
ShowKind = {"food", "animal", "nature", "transport", "sport", "object"}


def _text(value: Any, lo: int, hi: int, *, allow_digits: bool = True) -> str | None:
    """NFKC-normalised single-line text with sane characters, or None."""
    if not isinstance(value, str):
        return None
    s = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()
    if not lo <= len(s) <= hi or _URLISH.search(s) or _DENY.search(s):
        return None
    if any(unicodedata.category(ch)[0] == "C" for ch in s):  # control / format / private-use
        return None
    if not allow_digits and any(ch.isdigit() for ch in s):
        return None
    return s


def _emoji(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not 1 <= len(s) <= 8 or any(ch.isalnum() and ord(ch) < 0x2000 for ch in s):
        return None
    # At least one real pictograph (So = "Symbol, other": where emoji live).
    return s if any(unicodedata.category(ch) == "So" for ch in s) else None


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.casefold())


# -- per-kind rules ------------------------------------------------------------------------------------
def v_frenemy(raw: Any) -> str | None:
    s = _text(raw, 15, 90)
    return s if s and not s.endswith("?") else None


def v_price(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name, blurb, emoji = (
        _text(raw.get("name"), 3, 40),
        _text(raw.get("blurb"), 8, 90),
        _emoji(raw.get("emoji")),
    )
    price = raw.get("price")
    if not (name and blurb and emoji) or isinstance(price, bool) or not isinstance(price, int):
        return None
    if not 2 <= price <= 9_500_000:
        return None
    return {
        "name": name,
        "blurb": blurb,
        "emoji": emoji,
        "price": price + (price % 2),
    }  # even: x1/2 stays whole


def v_alibi(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title, victim = _text(raw.get("title"), 6, 40), _text(raw.get("victim"), 3, 30)
    locs = raw.get("locations")
    slots = raw.get("slots")
    if not (title and victim and isinstance(locs, list) and isinstance(slots, list)):
        return None
    locs = [_text(x, 2, 18) for x in locs]
    slots = [_text(x, 2, 10) for x in slots]
    if len(locs) != 6 or len(slots) != 6 or None in locs or None in slots:
        return None
    if len({_key(x) for x in locs}) != 6 or len({_key(x) for x in slots}) != 6:  # type: ignore[arg-type]
        return None
    return {"title": title, "victim": victim, "locations": locs, "slots": slots}


def v_telepathy(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title, opts = _text(raw.get("title"), 4, 40), raw.get("options")
    if not title or not isinstance(opts, list):
        return None
    opts = [_text(x, 1, 22) for x in opts]
    if len(opts) != 6 or None in opts or len({_key(x) for x in opts}) != 6:  # type: ignore[arg-type]
        return None
    return {"title": title, "options": opts}


def v_mural(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    emoji, name = _emoji(raw.get("emoji")), _text(raw.get("name"), 2, 18, allow_digits=False)
    color, kind = raw.get("color"), raw.get("kind")
    if not (emoji and name) or color not in ShowColor or kind not in ShowKind:
        return None
    return {"emoji": emoji, "name": name, "color": color, "kind": kind}


def v_crossword(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("word"), str):
        return None
    word = raw["word"].strip().upper()
    clue = _text(raw.get("clue"), 6, 80)
    if not re.fullmatch(r"[A-Z]{3,10}", word) or not clue or _DENY.search(word):
        return None
    if word.casefold() in clue.casefold():  # never give the answer away
        return None
    return {"word": word, "clue": clue}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_S = {"type": "string"}
_I = {"type": "integer"}
_SL = {"type": "array", "items": _S}


@dataclass(frozen=True)
class Kind:
    pool: list[Any]
    key: Callable[[Any], str]
    validate: Callable[[Any], Any]
    item_schema: dict[str, Any]
    brief: str
    sample: Callable[[Any], str]


KINDS: dict[str, Kind] = {
    "frenemy": Kind(
        C.FRENEMY_PROMPTS,
        _key,
        v_frenemy,
        _S,
        "Frenemy Radar prompts. Friends rank each other on them, so every prompt must be fun and flattering "
        "to 'win': playful, kind, never about bodies, money, intelligence, relationships, age or anything "
        "anyone could feel singled out by. Phrase like 'Most likely to ...' or 'Would ...'. "
        "15-90 characters.",
        lambda x: x,
    ),
    "price": Kind(
        C.PRICE_ITEMS,
        lambda x: _key(x["name"]),
        v_price,
        _obj({"name": _S, "blurb": _S, "emoji": _S, "price": _I}),
        "Price Is Weird items: absurd but imaginable things to buy, with a funny one-line blurb, one fitting "
        "emoji and a plausible price in whole US dollars (between 2 and 9,500,000). Names 3-40 characters, "
        "blurbs under 90. Mix cheap and wildly expensive.",
        lambda x: f"{x['emoji']} {x['name']} (${x['price']:,}): {x['blurb']}",
    ),
    "alibi": Kind(
        C.ALIBI_SETTINGS,
        lambda x: _key(x["title"]),
        v_alibi,
        _obj({"title": _S, "victim": _S, "locations": _SL, "slots": _SL}),
        "Cosy, cartoonish murder-mystery settings for a party game (think board-game whodunnit, no gore): "
        "a title, a fictional victim's name with a playful title, exactly 6 distinct short location names "
        "(2-18 characters) and exactly 6 consecutive half-hour time labels (e.g. '7:00 PM').",
        lambda x: f"{x['title']} / {x['victim']} / {', '.join(x['locations'])}",
    ),
    "telepathy": Kind(
        C.TELEPATHY_CATEGORIES,
        lambda x: _key(x["title"]),
        v_telepathy,
        _obj({"title": _S, "options": _SL}),
        "Telepathy Tax categories: a short category ('A breakfast food') and exactly 6 distinct, common, "
        "family-friendly answers (1-22 characters) that real people would plausibly pick. "
        "Some answers should be obvious and some sneaky, so groups split.",
        lambda x: f"{x['title']}: {', '.join(x['options'])}",
    ),
    "mural": Kind(
        C.MURAL_TILES,
        lambda x: _key(x["name"]),
        v_mural,
        _obj(
            {
                "emoji": _S,
                "name": _S,
                "color": {"type": "string", "enum": sorted(ShowColor)},
                "kind": {"type": "string", "enum": sorted(ShowKind)},
            }
        ),
        "Mole in the Mural tiles: one standard emoji each, a 2-18 letter name for it, its main colour and "
        "its kind. Use widely supported emoji only.",
        lambda x: f"{x['emoji']} {x['name']} ({x['color']}, {x['kind']})",
    ),
    "crossword": Kind(
        C.CROSSWORD_ENTRIES,
        lambda x: x["word"],
        v_crossword,
        _obj({"word": _S, "clue": _S}),
        "Crossword answers and clues for a fast, friendly party crossword: common English words of 3-10 "
        "letters (A-Z only, no proper nouns or abbreviations) with a short, fair, fun clue (6-80 characters) "
        "that never contains the answer.",
        lambda x: f"{x['word']}: {x['clue']}",
    ),
}

GAME_KINDS = {
    "frenemy": "frenemy",
    "price": "price",
    "alibi": "alibi",
    "telepathy": "telepathy",
    "mural": "mural",
    "crossword": "crossword",
}

SYSTEM = (
    "You write content for Snazzlebop, a family-friendly party game show played by groups of friends. "
    "Everything must be kind, inclusive, fun to read aloud and safe for a mixed audience: no real people, "
    "brands, politics, religion, alcohol, drugs, violence, gore or innuendo. Be original and varied; never "
    "repeat anything from the 'already used' list."
)

Caller = Callable[[str, dict[str, Any], str], Awaitable[Any]]


def add_items(kind: str, items: list[Any]) -> list[Any]:
    """Validate and de-duplicate items into the live pool. Returns the ones actually added."""
    spec = KINDS[kind]
    seen = {spec.key(x) for x in spec.pool}
    added: list[Any] = []
    for raw in items:
        item = spec.validate(raw)
        if item is None or len(spec.pool) >= POOL_CAP:
            continue
        k = spec.key(item)
        if not k or k in seen:
            continue
        seen.add(k)
        spec.pool.append(item)
        added.append(item)
    return added


# Reviewed, committed output of scripts/grow_pools.py: loaded through the same validator at import.
EXTRA_FILE = Path(__file__).parent / "games" / "content_extra.json"


def load_extra(path: Path = EXTRA_FILE) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("content_extra.json unreadable; using the built-in pools")
        return 0
    return sum(
        len(add_items(kind, items))
        for kind, items in data.items()
        if kind in KINDS and isinstance(items, list)
    )


class ContentGenerator:
    def __init__(
        self,
        call: Caller | None,
        *,
        save: Callable[[str, list[tuple[str, Any]]], Awaitable[None]] | None = None,
        calls_per_hour: int = 20,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ) -> None:
        self.call = call  # None = no API key: generation off, pools only
        self.save = save
        self.calls_per_hour = calls_per_hour
        self.clock = clock
        self.rng = rng or random.Random()
        self.recent_calls: list[float] = []
        self.cooldown_until = 0.0
        self.failures = 0
        self.busy: set[str] = set()
        self.tasks: set[asyncio.Task[None]] = set()
        self.stats = {"calls": 0, "added": 0, "failed": 0, "rejected": 0}

    @property
    def enabled(self) -> bool:
        return self.call is not None

    def allowed(self, kind: str) -> bool:
        now = self.clock()
        self.recent_calls = [t for t in self.recent_calls if now - t < 3600]
        return (
            self.enabled
            and kind in KINDS
            and kind not in self.busy
            and now >= self.cooldown_until
            and len(self.recent_calls) < self.calls_per_hour
            and len(KINDS[kind].pool) < POOL_CAP
        )

    def request(self, game_id: str) -> None:
        """Called when a game starts. Never blocks; quietly does nothing when not allowed."""
        kind = GAME_KINDS.get(game_id)
        if kind is None or not self.allowed(kind):
            return
        self.busy.add(kind)
        self.recent_calls.append(self.clock())
        task = asyncio.get_running_loop().create_task(self._run(kind))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def prompt(self, kind: str) -> str:
        spec = KINDS[kind]
        examples = self.rng.sample(spec.pool, min(6, len(spec.pool)))
        used = self.rng.sample(spec.pool, min(60, len(spec.pool)))
        return (
            f"Write {BATCH} new {spec.brief}\n\nGood examples of the style:\n"
            + "\n".join(f"- {spec.sample(x)}" for x in examples)
            + "\n\nAlready used (do not repeat these or near-duplicates):\n"
            + "\n".join(f"- {spec.sample(x)}" for x in used)
        )

    async def generate(self, kind: str) -> list[Any]:
        """One batch: ask, validate, de-duplicate, add, persist. Raises on API/format trouble."""
        if self.call is None:
            raise RuntimeError("content generation is off (no API key)")
        spec = KINDS[kind]
        schema = _obj({"items": {"type": "array", "items": spec.item_schema}})
        data = await self.call(SYSTEM, schema, self.prompt(kind))
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("unexpected output shape")
        raw = data["items"][: BATCH * 2]
        added = add_items(kind, raw)
        self.stats["rejected"] += len(raw) - len(added)
        if added and self.save is not None:
            await self.save(kind, [(spec.key(x), x) for x in added])
        return added

    async def _run(self, kind: str) -> None:
        self.stats["calls"] += 1
        try:
            added = await self.generate(kind)
            self.stats["added"] += len(added)
            self.failures = 0
            log.info("content: +%d %s items (pool %d)", len(added), kind, len(KINDS[kind].pool))
        except Exception as exc:  # any failure: back off and let the built-in pools carry on
            self.failures += 1
            self.stats["failed"] += 1
            backoff = min(3600.0, 300.0 * 2 ** (self.failures - 1))
            self.cooldown_until = self.clock() + backoff
            log.warning("content generation failed (%s); pools only for %.0fs", type(exc).__name__, backoff)
        finally:
            self.busy.discard(kind)


def claude_caller(api_key: str, model: str = MODEL, client: Any = None) -> Caller:
    """The real call: Claude with structured output, low effort, server-side refusal fallback."""
    if client is None:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=90.0, max_retries=1)

    async def call(system: str, schema: dict[str, Any], prompt: str) -> Any:
        response = await client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            # If a request is declined, Anthropic re-runs it on its recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason != "end_turn":  # refusal (whole chain declined) or truncated output
            raise ValueError(f"stop_reason={response.stop_reason}")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ValueError("no text block")
        return json.loads(text)

    return call


load_extra()
