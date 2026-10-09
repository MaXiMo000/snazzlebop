"""Chess: the full rules, our own move generator (no third-party engine).

Rules: every piece moves as in FIDE chess, including castling (not out of, through or into check),
en passant, and promotion (to a queen, rook, bishop or knight). The game ends on checkmate (win),
stalemate, the fifty-move rule (fifty moves each without a capture or a pawn move), threefold repetition
(same position, same side to move, same castling and en-passant rights), insufficient material (no
side can ever mate: K v K, K+B v K, K+N v K, bishops all on one colour), resignation, an accepted draw
offer, or a flag fall (out of time; a draw if the side still on the clock can't possibly mate).
Party-friendly: repetition and the fifty-move rule end the game by themselves (no claim needed).

Clocks: each side has its own clock (option: 10 min, 5 min, 3 min + 2 s, 15 min + 10 s a move).

Players: 2 is one against one. With 3-8 (or the Teams switch), two teams play consultation chess:
the side's players take turns making the side's move, and teammates may suggest a move (an arrow on the
board that only their own side sees) before the mover decides.

Scoring: everyone on the winning side gets 300, a draw is 100 each.

Secrecy: the position is public; a side's suggestions are seen only by that side.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .base import Game, GameError

FILES = "abcdefgh"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
UCI = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$")
WIN_POINTS, DRAW_POINTS = 300, 100
CLOCKS = {"10": (600.0, 0.0), "5": (300.0, 0.0), "3+2": (180.0, 2.0), "15+10": (900.0, 10.0)}
VALUE = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0}

Board = list[str]  # 64 squares, a1 = 0 ... h8 = 63; "" or colour + piece: "wK", "bP"
Move = tuple[int, int, str]  # from, to, promotion piece ("" or "Q", "R", "B", "N")


def sq(name: str) -> int:
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])


def sq_name(s: int) -> str:
    return FILES[s % 8] + str(s // 8 + 1)


def _step(s: int, df: int, dr: int) -> int | None:
    f, r = s % 8 + df, s // 8 + dr
    return r * 8 + f if 0 <= f < 8 and 0 <= r < 8 else None


def _table(deltas: list[tuple[int, int]]) -> list[list[int]]:
    return [[t for d in deltas if (t := _step(s, *d)) is not None] for s in range(64)]


def _rays(dirs: list[tuple[int, int]]) -> list[list[list[int]]]:
    out = []
    for s in range(64):
        per = []
        for df, dr in dirs:
            ray, t = [], _step(s, df, dr)
            while t is not None:
                ray.append(t)
                t = _step(t, df, dr)
            per.append(ray)
        out.append(per)
    return out


KNIGHT = _table([(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)])
KING = _table([(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)])
DIAG = _rays([(1, 1), (1, -1), (-1, 1), (-1, -1)])
LINE = _rays([(1, 0), (-1, 0), (0, 1), (0, -1)])


def other(color: str) -> str:
    return "b" if color == "w" else "w"


class Position:
    """A position: board, side to move, castling rights, en-passant square, move counters."""

    __slots__ = ("board", "turn", "castling", "ep", "halfmove", "fullmove")

    def __init__(self, board: Board, turn: str, castling: str, ep: int | None, halfmove: int, fullmove: int):
        self.board, self.turn, self.castling, self.ep = board, turn, castling, ep
        self.halfmove, self.fullmove = halfmove, fullmove

    # -- FEN -------------------------------------------------------------------------------------------
    @classmethod
    def from_fen(cls, fen: str) -> Position:
        rows, turn, castling, ep, half, full = fen.split()
        board = [""] * 64
        for i, row in enumerate(rows.split("/")):
            r, f = 7 - i, 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                else:
                    board[r * 8 + f] = ("w" if ch.isupper() else "b") + ch.upper()
                    f += 1
        return cls(
            board,
            turn,
            "" if castling == "-" else castling,
            None if ep == "-" else sq(ep),
            int(half),
            int(full),
        )

    def fen(self) -> str:
        rows = []
        for r in range(7, -1, -1):
            row, gap = "", 0
            for f in range(8):
                p = self.board[r * 8 + f]
                if not p:
                    gap += 1
                    continue
                row += (str(gap) if gap else "") + (p[1] if p[0] == "w" else p[1].lower())
                gap = 0
            rows.append(row + (str(gap) if gap else ""))
        ep = sq_name(self.ep) if self.ep is not None else "-"
        return f"{'/'.join(rows)} {self.turn} {self.castling or '-'} {ep} {self.halfmove} {self.fullmove}"

    # -- attacks ---------------------------------------------------------------------------------------
    def attacked(self, s: int, by: str) -> bool:
        b = self.board
        back = -1 if by == "w" else 1  # a white pawn attacks upwards, so look one rank down
        for df in (-1, 1):
            t = _step(s, df, back)
            if t is not None and b[t] == by + "P":
                return True
        if any(b[t] == by + "N" for t in KNIGHT[s]) or any(b[t] == by + "K" for t in KING[s]):
            return True
        for rays, kinds in ((DIAG[s], "BQ"), (LINE[s], "RQ")):
            for ray in rays:
                for t in ray:
                    p = b[t]
                    if p:
                        if p[0] == by and p[1] in kinds:
                            return True
                        break
        return False

    def king(self, color: str) -> int:
        return self.board.index(color + "K")

    def in_check(self, color: str | None = None) -> bool:
        color = color or self.turn
        return self.attacked(self.king(color), other(color))

    # -- moves -----------------------------------------------------------------------------------------
    def pseudo(self) -> list[Move]:
        b, me, them = self.board, self.turn, other(self.turn)
        out: list[Move] = []
        for s, p in enumerate(b):
            if not p or p[0] != me:
                continue
            kind = p[1]
            if kind == "P":
                fwd = 1 if me == "w" else -1
                start, last = (1, 7) if me == "w" else (6, 0)
                promos = ("Q", "R", "B", "N")
                one = _step(s, 0, fwd)
                if one is not None and not b[one]:
                    out += [(s, one, q) for q in promos] if one // 8 == last else [(s, one, "")]
                    two = _step(s, 0, 2 * fwd)
                    if s // 8 == start and two is not None and not b[two]:
                        out.append((s, two, ""))
                for df in (-1, 1):
                    t = _step(s, df, fwd)
                    if t is None:
                        continue
                    if (b[t] and b[t][0] == them) or t == self.ep:
                        out += [(s, t, q) for q in promos] if t // 8 == last else [(s, t, "")]
            elif kind in "NK":
                for t in (KNIGHT if kind == "N" else KING)[s]:
                    if not b[t] or b[t][0] == them:
                        out.append((s, t, ""))
            else:
                rays = DIAG[s] if kind == "B" else LINE[s] if kind == "R" else DIAG[s] + LINE[s]
                for ray in rays:
                    for t in ray:
                        if not b[t]:
                            out.append((s, t, ""))
                            continue
                        if b[t][0] == them:
                            out.append((s, t, ""))
                        break
        out += self._castles()
        return out

    def _castles(self) -> list[Move]:
        me, b = self.turn, self.board
        home = 0 if me == "w" else 56
        if b[home + 4] != me + "K" or not self.castling:
            return []
        out: list[Move] = []
        them = other(me)
        k, q = ("K", "Q") if me == "w" else ("k", "q")
        if (
            k in self.castling
            and b[home + 7] == me + "R"
            and not b[home + 5]
            and not b[home + 6]
            and not any(self.attacked(home + i, them) for i in (4, 5, 6))
        ):
            out.append((home + 4, home + 6, ""))
        if (
            q in self.castling
            and b[home] == me + "R"
            and not b[home + 1]
            and not b[home + 2]
            and not b[home + 3]
            and not any(self.attacked(home + i, them) for i in (4, 3, 2))
        ):
            out.append((home + 4, home + 2, ""))
        return out

    def make(self, move: Move) -> Position:
        frm, to, promo = move
        b = list(self.board)
        piece, target = b[frm], b[to]
        me = self.turn
        b[frm], b[to] = "", me + promo if promo else piece
        if piece[1] == "P" and to == self.ep and not target:  # en passant: the pawn behind goes
            b[to - 8 if me == "w" else to + 8] = ""
        if piece[1] == "K" and abs(to - frm) == 2:  # castling: the rook jumps over
            rook_from, rook_to = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
            b[rook_to], b[rook_from] = b[rook_from], ""
        rights = self.castling
        for corner, right in ((0, "Q"), (7, "K"), (56, "q"), (63, "k")):
            if frm == corner or to == corner:
                rights = rights.replace(right, "")
        if piece[1] == "K":
            rights = rights.replace("K" if me == "w" else "k", "").replace("Q" if me == "w" else "q", "")
        ep = (frm + to) // 2 if piece[1] == "P" and abs(to - frm) == 16 else None
        half = 0 if piece[1] == "P" or target else self.halfmove + 1
        full = self.fullmove + (1 if me == "b" else 0)
        return Position(b, other(me), rights, ep, half, full)

    def legal(self) -> list[Move]:
        me = self.turn
        return [m for m in self.pseudo() if not self.make(m).in_check(me)]

    # -- draws -----------------------------------------------------------------------------------------
    def insufficient(self) -> bool:
        """No sequence of legal moves can mate: K v K, K + one minor v K, or only same-colour bishops."""
        rest = [(s, p) for s, p in enumerate(self.board) if p and p[1] != "K"]
        if not rest:
            return True
        if len(rest) == 1 and rest[0][1][1] in "BN":
            return True
        if all(p[1] == "B" for _, p in rest):
            return len({(s % 8 + s // 8) % 2 for s, _ in rest}) == 1
        return False

    def can_mate(self, color: str) -> bool:
        """Could this side ever mate (for a flag fall)? Not with a bare king or a lone minor piece."""
        mine = [p[1] for p in self.board if p and p[0] == color and p[1] != "K"]
        return not (not mine or (len(mine) == 1 and mine[0] in "BN"))

    def key(self) -> str:
        """For repetition: placement, side to move, castling, and en passant only if it can be taken."""
        ep = ""
        if self.ep is not None and any(m[1] == self.ep and self.board[m[0]][1] == "P" for m in self.legal()):
            ep = sq_name(self.ep)
        return f"{self.fen().split()[0]} {self.turn} {self.castling} {ep}"

    # -- notation --------------------------------------------------------------------------------------
    def san(self, move: Move) -> str:
        frm, to, promo = move
        piece = self.board[frm][1]
        capture = bool(self.board[to]) or (piece == "P" and to == self.ep)
        if piece == "K" and abs(to - frm) == 2:
            text = "O-O" if to > frm else "O-O-O"
        elif piece == "P":
            text = (FILES[frm % 8] + "x" if capture else "") + sq_name(to) + (f"={promo}" if promo else "")
        else:
            rivals = [
                m[0] for m in self.legal() if m[1] == to and m[0] != frm and self.board[m[0]][1] == piece
            ]
            hint = ""
            if rivals:
                if all(r % 8 != frm % 8 for r in rivals):
                    hint = FILES[frm % 8]
                elif all(r // 8 != frm // 8 for r in rivals):
                    hint = str(frm // 8 + 1)
                else:
                    hint = sq_name(frm)
            text = piece + hint + ("x" if capture else "") + sq_name(to)
        after = self.make(move)
        if after.in_check():
            text += "#" if not after.legal() else "+"
        return text


def to_uci(move: Move) -> str:
    return sq_name(move[0]) + sq_name(move[1]) + move[2].lower()


def perft(pos: Position, depth: int) -> int:
    """Leaf positions after `depth` plies: the standard way to check a move generator."""
    if depth == 0:
        return 1
    moves = pos.legal()
    if depth == 1:
        return len(moves)
    return sum(perft(pos.make(m), depth - 1) for m in moves)


class Chess(Game):
    game_id: ClassVar[str] = "chess"
    title: ClassVar[str] = "Chess"
    blurb: ClassVar[str] = (
        "The real thing: castling, en passant, promotion, chess clocks. One on one, or the whole room "
        "in two teams taking turns at the board."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    TEAMS: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"clock": ["10", "5", "3+2", "15+10"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Standard chess rules: castling, en passant and promotion included. White moves first.",
        "Checkmate wins. Stalemate, threefold repetition, fifty moves without a capture or pawn move, "
        "or too little material to mate is a draw.",
        "Each side has a chess clock. Run out of time and you lose (unless the other side can't mate).",
        "With more than two players, two teams take turns making their side's move. Teammates can "
        "suggest a move first: only your own side sees the arrow.",
        "You can offer a draw or resign at any time.",
    )

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {}

    # -- setup -----------------------------------------------------------------------------------------
    def start(self) -> None:
        ids = list(self.player_ids)
        self.rng.shuffle(ids)
        if self.teams:
            sides = [[p for p in ids if self.teams.get(p) == t] for t in (0, 1)]
            self.rng.shuffle(sides)  # which team gets white: a coin toss
        else:
            sides = [ids[0::2], ids[1::2]]
        self.sides: dict[str, list[str]] = {"w": sides[0], "b": sides[1]}
        self.side_of = {p: c for c, ps in self.sides.items() for p in ps}
        self.rota = {"w": 0, "b": 0}  # whose turn to move within the side
        base, self.increment = CLOCKS.get(self.options.get("clock", "10"), CLOCKS["10"])
        self.clocks = {"w": base, "b": base}
        self.pos = Position.from_fen(self.options.get("fen", START_FEN))
        self.seen: dict[str, int] = {self.pos.key(): 1}
        self.history: list[dict[str, Any]] = []  # {"uci", "san", "side", "by"}
        self.captured: dict[str, list[str]] = {"w": [], "b": []}  # pieces each side has taken
        self.suggestions: dict[str, dict[str, str]] = {"w": {}, "b": {}}  # side -> player -> uci
        self.draw_offer: str | None = None  # the side that offered
        self.result: dict[str, Any] | None = None
        self.stats = {"promotions": 0, "en_passant": 0, "castles": 0}
        self.phase = "play"
        self.turn_started = self.clock()
        self._arm_clock()
        self.bump()

    # -- helpers ---------------------------------------------------------------------------------------
    @property
    def mover(self) -> str:
        side = self.sides[self.pos.turn]
        return side[self.rota[self.pos.turn] % len(side)]

    def _arm_clock(self) -> None:
        self.deadline = self.turn_started + self.clocks[self.pos.turn]

    def _left(self, color: str) -> float:
        if self.phase == "play" and color == self.pos.turn:
            return max(0.0, self.clocks[color] - (self.clock() - self.turn_started))
        return self.clocks[color]

    def _parse(self, raw: Any) -> Move:
        if not isinstance(raw, str) or not UCI.match(raw):
            raise GameError("bad_move", "That's not a move")
        move = (sq(raw[:2]), sq(raw[2:4]), raw[4:].upper())
        if move not in self.pos.legal():
            raise GameError("illegal", "That move isn't allowed")
        return move

    def _side(self, pid: str) -> str:
        side = self.side_of.get(pid)
        if side is None:
            raise GameError("not_in_game", "You're not playing")
        return side

    # -- actions ---------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if self.phase != "play":
            raise GameError("wrong_phase", "The game is over")
        kind = action.get("a")
        side = self._side(pid)
        if kind == "move":
            if side != self.pos.turn:
                raise GameError("not_your_turn", "It's not your side's turn")
            if pid != self.mover:
                raise GameError("not_your_turn", f"It's {self.name_of(self.mover)}'s turn to move")
            if not self._flagged():  # a move after the flag fell doesn't count
                self._play(pid, self._parse(action.get("move")))
        elif kind == "suggest":
            if side != self.pos.turn:
                raise GameError("not_your_turn", "Suggest a move on your side's turn")
            move = self._parse(action.get("move"))
            self.suggestions[side][pid] = to_uci(move)
        elif kind == "offer":
            if self.draw_offer == other(side):
                self._end(None, "agreement")
            else:
                self.draw_offer = side
        elif kind == "decline":
            if self.draw_offer != other(side):
                raise GameError("no_offer", "There's no draw offer")
            self.draw_offer = None
        elif kind == "accept":
            if self.draw_offer != other(side):
                raise GameError("no_offer", "There's no draw offer")
            self._end(None, "agreement")
        elif kind == "resign":
            self._end(other(side), "resignation")
        else:
            raise GameError("bad_action", "Unknown action")
        self.bump()

    def _play(self, pid: str, move: Move) -> None:
        pos, color = self.pos, self.pos.turn
        spent = self.clock() - self.turn_started
        self.clocks[color] = max(0.0, self.clocks[color] - spent) + self.increment
        piece, target = pos.board[move[0]][1], pos.board[move[1]]
        san = pos.san(move)
        if target:
            self.captured[color].append(target[1])
        elif piece == "P" and move[1] == pos.ep:
            self.captured[color].append("P")
            self.stats["en_passant"] += 1
        if move[2]:
            self.stats["promotions"] += 1
        if piece == "K" and abs(move[1] - move[0]) == 2:
            self.stats["castles"] += 1
        self.pos = pos.make(move)
        self.history.append({"uci": to_uci(move), "san": san, "side": color, "by": pid})
        self.rota[color] += 1
        self.suggestions[color] = {}
        if self.draw_offer == other(color):
            self.draw_offer = None  # moving instead of answering declines the offer
        self.turn_started = self.clock()
        key = self.pos.key()
        self.seen[key] = self.seen.get(key, 0) + 1
        legal = self.pos.legal()
        if not legal:
            self._end(
                color if self.pos.in_check() else None, "checkmate" if self.pos.in_check() else "stalemate"
            )
        elif self.pos.insufficient():
            self._end(None, "insufficient material")
        elif self.seen[key] >= 3:
            self._end(None, "threefold repetition")
        elif self.pos.halfmove >= 100:
            self._end(None, "fifty-move rule")
        else:
            self._arm_clock()

    def _end(self, winner: str | None, reason: str) -> None:
        self.result = {"winner": winner, "reason": reason}
        for c, members in self.sides.items():
            pts = DRAW_POINTS if winner is None else WIN_POINTS if c == winner else 0
            for p in members:
                self.add_points(p, pts)
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.draw_offer = None
        self.suggestions = {"w": {}, "b": {}}

    def _flagged(self) -> bool:
        """The side to move ran out of time: it loses, unless the other side couldn't mate anyway."""
        color = self.pos.turn
        if self._left(color) > 0:
            return False
        self.clocks[color] = 0.0
        winner = other(color)
        self._end(winner if self.pos.can_mate(winner) else None, "time")
        return True

    # -- clocks ----------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self._flagged():
            self.bump()

    def advance(self) -> None:
        """The host can't skip a chess move: the clocks decide."""

    # -- views -----------------------------------------------------------------------------------------
    def chat_team(self, pid: str) -> tuple[str, str] | None:
        """Consultation chess: each side talks moves over privately (a side of one has no team chat)."""
        side = self.side_of.get(pid)
        if side is None or len(self.sides[side]) < 2:
            return None
        return f"side:{side}", "White" if side == "w" else "Black"

    def view_for(self, pid: str) -> dict[str, Any]:
        playing = self.phase == "play"
        mine = self.side_of.get(pid)
        pos = self.pos
        check = sq_name(pos.king(pos.turn)) if playing and pos.in_check() else None
        last = self.history[-1]["uci"] if self.history else None
        you: dict[str, Any] | None = None
        if mine is not None:
            my_turn = playing and mine == pos.turn
            you = {
                "side": mine,
                "mover": my_turn and pid == self.mover,
                "legal": [to_uci(m) for m in pos.legal()] if my_turn else [],
                "suggestions": [
                    {"by": p, "move": m, "san": pos.san((sq(m[:2]), sq(m[2:4]), m[4:].upper()))}
                    for p, m in self.suggestions[mine].items()
                ],
            }
        return {
            "game": self.game_id,
            "phase": self.phase,
            "round": 1,
            "rounds": 1,
            "remaining": self._left(pos.turn) if playing else None,
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "board": list(pos.board),
            "fen": pos.fen(),
            "turn": pos.turn,
            "sides": {c: list(ps) for c, ps in self.sides.items()},
            "mover": self.mover if playing else None,
            "check": check,
            "last": last,
            "history": [
                {"san": h["san"], "side": h["side"], "by": h["by"], "uci": h["uci"]} for h in self.history
            ],
            "captured": {c: list(v) for c, v in self.captured.items()},
            "clocks": {"w": self._left("w"), "b": self._left("b")},
            "increment": self.increment,
            "draw_offer": self.draw_offer,
            "result": self.result,
            "you": you,
            "scores": self.scores(),
        }

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished or not self.result:
            return []
        out: list[dict[str, str]] = []
        r, moves = self.result, (len(self.history) + 1) // 2
        side_name = {"w": "White", "b": "Black"}
        if r["winner"]:
            names = " & ".join(self.name_of(p) for p in self.sides[r["winner"]])
            how = {"checkmate": "checkmated", "resignation": "won on resignation", "time": "won on time"}
            out.append(
                {
                    "icon": "♚" if r["reason"] == "checkmate" else "⏱️" if r["reason"] == "time" else "🏳️",
                    "title": f"{side_name[r['winner']]} wins",
                    "text": f"{names} {how.get(r['reason'], 'won')} in {moves} moves",
                }
            )
        else:
            out.append({"icon": "🤝", "title": "A draw", "text": f"By {r['reason']} after {moves} moves"})
        if self.stats["en_passant"]:
            out.append({"icon": "🥐", "title": "En passant!", "text": "Somebody knew the secret rule"})
        if self.stats["promotions"]:
            n = self.stats["promotions"]
            out.append(
                {
                    "icon": "👑",
                    "title": "Promotion",
                    "text": f"{n} pawn{'s' if n > 1 else ''} made it all the way",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "players": len(self.players),
            "moves": len(self.history),
            "result": (self.result or {}).get("reason"),
            "teams": bool(self.teams),
        }
