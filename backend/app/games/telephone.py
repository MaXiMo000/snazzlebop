"""Draw Telephone: the drawing game of Chinese whispers (Gartic Phone rules).

Everyone writes a silly sentence. The books then pass round the circle: the next player draws the
sentence, the next describes that drawing in words, the next draws the description, and so on until every
book has been through every player. Then the album: each book is revealed one page at a time, from the
first sentence to wherever it ended up.

Steps run at the same time for everyone; a step ends when everybody is done or the clock runs out. Out of
time: a missing first sentence becomes the suggested idea, a missing description "???", and a drawing is
whatever was drawn.

Scoring (Gartic Phone has none; the room needs some): during the album and on the final screen, everyone
can like any page but their own; each like is worth 100 points to the page's author.

Secrecy: during the steps you see only your own task (the sentence to draw, or the drawing to describe),
never another book. The TV and audience see who is done. Drawings are relayed to nobody while they're
drawn; the album shows pages only as they are revealed.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError
from .content import TELEPHONE_IDEAS
from .ink import InkLog

MAX_TEXT = 80
LIKE_POINTS = 100
DRAWING_POINTS = 20000  # per drawing: a room holds up to 32 of them, and every change is snapshotted
TIMEOUT_TEXT = "???"


class DrawTelephone(Game):
    game_id: ClassVar[str] = "telephone"
    title: ClassVar[str] = "Draw Telephone"
    blurb: ClassVar[str] = (
        "Write something silly, draw what the last player wrote, describe what they drew... then watch "
        "every story fall apart in the album."
    )
    min_players: ClassVar[int] = 3
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    TEAMS: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"time": ["90", "60", "120"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Everyone writes a silly sentence to start their own book.",
        "Books pass round: draw the sentence you get, then describe the drawing you get, and so on.",
        "You only ever see the page just before yours.",
        "Then the album shows how each story changed, page by page.",
        "Like the best pages: every like is 100 points to whoever made it.",
    )
    READING: ClassVar[frozenset[str]] = frozenset({"album"})

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"write": 45.0, "describe": 40.0, "page_text": 5.0, "page_drawing": 9.0}

    def start(self) -> None:
        self.draw_seconds = float(self.options.get("time", "90"))
        self.order = list(self.player_ids)
        self.rng.shuffle(self.order)
        n = len(self.order)
        picks = self.deal("ideas", len(TELEPHONE_IDEAS), n)
        self.ideas = {p: TELEPHONE_IDEAS[i] for p, i in zip(self.order, picks, strict=True)}
        self.books: list[list[dict[str, Any]]] = [[] for _ in range(n)]  # book i starts with order[i]
        self.step = 0
        self.book = 0  # the album page being shown: book, entry
        self.entry = 0
        self._begin_step()

    @property
    def stage(self) -> str:
        return f"{self.phase}:{self.step}:{self.book}:{self.entry}"

    # -- steps ----------------------------------------------------------------------------------------
    def _book_of(self, pid: str) -> int:
        """The book this player holds at the current step (book i travels i, i+1, i+2, ...)."""
        return (self.order.index(pid) - self.step) % len(self.order)

    def _begin_step(self) -> None:
        self.done: set[str] = set()
        self.pending: dict[str, str] = {}
        if self.step == 0:
            self.phase = "write"
            self.set_deadline(self.timings["write"])
        elif self.step % 2:
            self.phase = "draw"
            for pid in self.order:
                self.books[self._book_of(pid)].append(
                    {"by": pid, "kind": "drawing", "canvas": InkLog(DRAWING_POINTS), "likes": set()}
                )
            self.set_deadline(self.draw_seconds)
        else:
            self.phase = "describe"
            self.set_deadline(self.timings["describe"])
        self.round = self.step
        self.bump()

    def _end_step(self) -> None:
        if self.phase in ("write", "describe"):
            for pid in self.order:
                fallback = self.ideas[pid] if self.phase == "write" else TIMEOUT_TEXT
                text = self.pending.get(pid, fallback)
                self.books[self._book_of(pid)].append(
                    {"by": pid, "kind": "text", "text": text, "likes": set()}
                )
        self.step += 1
        if self.step >= len(self.order):
            self.phase, self.book, self.entry = "album", 0, 0
            self._page_clock()
            self.bump()
        else:
            self._begin_step()

    def _page_clock(self) -> None:
        page = self.books[self.book][self.entry]
        self.set_deadline(self.timings["page_drawing" if page["kind"] == "drawing" else "page_text"])

    def _previous(self, pid: str) -> dict[str, Any]:
        """The page this player works from: the one just before theirs in the book they hold."""
        return self.books[self._book_of(pid)][self.step - 1]

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "text":
            self._text(pid, action.get("text"))
        elif kind == "done":
            if self.phase != "draw":
                raise GameError("wrong_phase", "Nothing to finish right now")
            flag = action.get("done", True)
            if not isinstance(flag, bool):
                raise GameError("bad_input", "Done or not?")
            if flag:
                self.done.add(pid)
            else:
                self.done.discard(pid)
            self.bump()
            self._maybe_next()
        elif kind == "like":
            self._like(pid, action.get("book"), action.get("entry"))
        else:
            raise GameError("bad_action", "Unknown action")

    def _text(self, pid: str, raw: Any) -> None:
        if self.phase not in ("write", "describe"):
            raise GameError("wrong_phase", "Not a writing step")
        if not isinstance(raw, str) or not raw.isprintable():
            raise GameError("bad_input", "Type something")
        text = " ".join(raw.split())
        if not text or len(text) > MAX_TEXT:
            raise GameError("bad_input", f"1-{MAX_TEXT} characters, please")
        self.pending[pid] = text  # sending again replaces it, until the step ends
        self.done.add(pid)
        self.bump()
        self._maybe_next()

    def _maybe_next(self) -> None:
        if all(p in self.done for p in self.order):
            self._end_step()

    def _revealed(self, b: int, e: int) -> bool:
        if self.phase == "final":
            return True
        if self.phase != "album":
            return False
        return b < self.book or (b == self.book and e <= self.entry)

    def _like(self, pid: str, b: Any, e: Any) -> None:
        n = len(self.order)
        if isinstance(b, bool) or isinstance(e, bool) or not isinstance(b, int) or not isinstance(e, int):
            raise GameError("bad_input", "Which page?")
        if not (0 <= b < n and 0 <= e < n) or not self._revealed(b, e):
            raise GameError("bad_input", "That page isn't out yet")
        page = self.books[b][e]
        if page["by"] == pid:
            raise GameError("own_page", "You can't like your own page")
        likes: set[str] = page["likes"]
        if pid in likes:
            likes.discard(pid)
            self.add_points(page["by"], -LIKE_POINTS)
        else:
            likes.add(pid)
            self.add_points(page["by"], LIKE_POINTS)
        self.bump()

    # -- drawing --------------------------------------------------------------------------------------
    def ink(self, pid: str, msg: dict[str, Any]) -> InkLog:
        canvas = self.canvas_for(pid)
        if canvas is None:
            raise GameError("wrong_phase", "Not drawing right now")
        canvas.add(msg)
        return canvas

    def canvas_for(self, pid: str) -> InkLog | None:
        """Only the artist sees a drawing while it's being drawn."""
        if self.phase != "draw" or pid not in self.round_scores:
            return None
        canvas: InkLog = self.books[self._book_of(pid)][self.step]["canvas"]
        return canvas

    def drawing(self, pid: str, drawing_id: str) -> InkLog | None:
        """A finished drawing this screen may look at: the one you're describing, or an album page."""
        if self.phase == "describe" and pid in self.round_scores:
            page = self._previous(pid)
            return page["canvas"] if page["canvas"].id == drawing_id else None
        for b, book in enumerate(self.books):
            for e, page in enumerate(book):
                if page["kind"] == "drawing" and page["canvas"].id == drawing_id and self._revealed(b, e):
                    canvas: InkLog = page["canvas"]
                    return canvas
        return None

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase in ("write", "draw", "describe"):
            self._end_step()
        elif self.phase == "album":
            if self.entry + 1 < len(self.order):
                self.entry += 1
            elif self.book + 1 < len(self.order):
                self.book, self.entry = self.book + 1, 0
            else:
                self.phase = "final"
                self.deadline = None
                self.finished = True
                self.bump()
                return
            self._page_clock()
            self.bump()

    # -- views ----------------------------------------------------------------------------------------
    def _page(self, page: dict[str, Any], pid: str, named: bool = True) -> dict[str, Any]:
        """A page of a book. Nobody is named until the whole book has been shown (you know your own)."""
        return {
            "by": page["by"] if named else None,
            "mine": page["by"] == pid,
            "kind": page["kind"],
            "text": page.get("text"),
            "drawing": page["canvas"].id if page["kind"] == "drawing" else None,
            "likes": len(page["likes"]),
            "liked": pid in page["likes"],
        }

    def _task(self, pid: str) -> dict[str, Any] | None:
        if pid not in self.round_scores or self.phase not in ("write", "draw", "describe"):
            return None
        task: dict[str, Any] = {"kind": self.phase, "done": pid in self.done, "text": self.pending.get(pid)}
        if self.phase == "write":
            task["idea"] = self.ideas[pid]
        else:
            prev = self._previous(pid)  # whose page it is stays secret until the album names them
            if self.phase == "draw":
                task["prompt"] = prev["text"]
            else:
                task["drawing"] = prev["canvas"].id
        return task

    def view_for(self, pid: str) -> dict[str, Any]:
        canvas = self.canvas_for(pid)
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": min(self.step, len(self.order) - 1) + 1,
            "rounds": len(self.order),
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "order": list(self.order),
            "seconds": self.draw_seconds,
            "done": sorted(self.done) if self.phase in ("write", "draw", "describe") else [],
            "task": self._task(pid),
            "ink": canvas.view() if canvas is not None else None,
            "you": {"playing": pid in self.round_scores},
            "scores": self.scores(),
        }
        if self.phase == "album":
            named = self.entry == len(self.order) - 1  # the last page is out: now say who did what
            view["album"] = {
                "book": self.book,
                "books": len(self.books),
                "owner": self.order[self.book] if named else None,
                "named": named,
                "entry": self.entry,
                "pages": [self._page(pg, pid, named) for pg in self.books[self.book][: self.entry + 1]],
            }
        if self.phase == "final":
            view["books"] = [
                {"owner": self.order[b], "pages": [self._page(pg, pid) for pg in book]}
                for b, book in enumerate(self.books)
            ]
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        pages = [pg for book in self.books for pg in book]
        best = max(pages, key=lambda pg: len(pg["likes"]))
        if best["likes"]:
            what = "drawing" if best["kind"] == "drawing" else f"“{best['text']}”"
            n = len(best["likes"])
            out.append(
                {
                    "icon": "❤️",
                    "title": "Crowd favourite",
                    "text": f"{self.name_of(best['by'])}'s {what} ({n} {'like' if n == 1 else 'likes'})",
                }
            )
        for book in self.books:
            texts = [pg["text"] for pg in book if pg["kind"] == "text"]
            if len(texts) >= 2 and not _words(texts[0]) & _words(texts[-1]):
                out.append(
                    {
                        "icon": "📞",
                        "title": "Lost in translation",
                        "text": f"“{texts[0]}” became “{texts[-1]}”",
                    }
                )
                break
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "players": len(self.players),
            "likes": sum(len(pg["likes"]) for book in self.books for pg in book),
        }


def _words(text: str) -> set[str]:
    small = {"a", "an", "the", "of", "in", "on", "at", "to", "with", "and", "is", "for"}
    return {w for w in "".join(c if c.isalpha() else " " for c in text.lower()).split() if w not in small}
