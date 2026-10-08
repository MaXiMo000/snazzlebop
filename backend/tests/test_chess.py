"""Chess: the move generator against published perft counts, every special move, every way a game ends,
the clocks, consultation teams (taking turns, suggestions only your side sees), and the views in every
phase."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.chess import START_FEN, Chess, Position, perft, sq

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=2, fen=START_FEN, clock="10", teams=None, seed=1):
    c = Clock()
    g = Chess(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=c,
        options={"clock": clock, "fen": fen},
        teams=teams,
    )
    g.start()
    return g, c


def play(g, *moves):
    for m in moves:
        g.handle(g.mover, {"a": "move", "move": m})


class PerftTests(unittest.TestCase):
    """Published node counts (chessprogramming.org "Perft Results")."""

    def test_start_position(self):
        pos = Position.from_fen(START_FEN)
        self.assertEqual([perft(pos, d) for d in (1, 2, 3)], [20, 400, 8902])

    def test_kiwipete_castles_pins_and_en_passant(self):
        pos = Position.from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
        self.assertEqual([perft(pos, d) for d in (1, 2, 3)], [48, 2039, 97862])

    def test_position_3_discovered_checks_and_en_passant_pins(self):
        pos = Position.from_fen("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1")
        self.assertEqual([perft(pos, d) for d in (1, 2, 3, 4)], [14, 191, 2812, 43238])

    def test_position_4_promotions_and_checks(self):
        pos = Position.from_fen("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1")
        self.assertEqual([perft(pos, d) for d in (1, 2, 3)], [6, 264, 9467])

    def test_position_5(self):
        pos = Position.from_fen("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8")
        self.assertEqual([perft(pos, d) for d in (1, 2, 3)], [44, 1486, 62379])

    def test_fen_round_trips(self):
        for fen in (START_FEN, "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"):
            self.assertEqual(Position.from_fen(fen).fen(), fen)


class RuleTests(unittest.TestCase):
    def test_fools_mate_and_notation(self):
        g, _ = make()
        play(g, "f2f3", "e7e5", "g2g4", "d8h4")
        self.assertEqual(g.result, {"winner": "b", "reason": "checkmate"})
        self.assertEqual([h["san"] for h in g.history], ["f3", "e5", "g4", "Qh4#"])
        black = g.sides["b"][0]
        self.assertEqual(g.scores()[black], 300)

    def test_castling_both_ways_and_not_through_check(self):
        g, _ = make(fen="r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        play(g, "e1g1")
        self.assertEqual(g.pos.board[sq("f1")], "wR")
        play(g, "e8c8")
        self.assertEqual(g.pos.board[sq("d8")], "bR")
        self.assertEqual([h["san"] for h in g.history], ["O-O", "O-O-O"])
        g, _ = make(fen="r3k2r/8/8/8/8/8/5r2/R3K2R w KQkq - 0 1")  # f-file attacked: no short castle
        self.assertNotIn("e1g1", g.view_for(g.mover)["you"]["legal"])
        with self.assertRaises(GameError):
            play(g, "e1g1")

    def test_en_passant_and_promotion(self):
        g, _ = make(fen="4k3/8/8/8/1p6/8/P7/4K3 w - - 0 1")
        play(g, "a2a4", "b4a3")
        self.assertEqual(g.pos.board[sq("a4")], "")
        self.assertEqual(g.history[-1]["san"], "bxa3")
        self.assertEqual(g.captured["b"], ["P"])
        g, _ = make(fen="4k3/1P6/8/8/8/8/8/4K3 w - - 0 1")
        play(g, "b7b8n")
        self.assertEqual(g.pos.board[sq("b8")], "wN")
        self.assertEqual(g.history[-1]["san"], "b8=N")

    def test_draws(self):
        g, _ = make(fen="7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        self.assertEqual(g.pos.legal(), [])  # black to move: stalemate positions end on the move before
        g, _ = make(fen="7k/8/5QK1/8/8/8/8/8 w - - 0 1")
        play(g, "f6f7")
        self.assertEqual(g.result, {"winner": None, "reason": "stalemate"})
        g, _ = make(fen="4k3/8/8/8/8/8/3r4/4K3 w - - 0 1")
        play(g, "e1d2")
        self.assertEqual(g.result["reason"], "insufficient material")
        g, _ = make()
        play(g, "g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1", "f6g8")
        self.assertEqual(g.result["reason"], "threefold repetition")
        g, _ = make(fen="4k3/8/8/8/8/8/8/R3K3 w - - 99 80")
        play(g, "a1a2")
        self.assertEqual(g.result["reason"], "fifty-move rule")
        for fen in ("4k3/8/8/8/8/8/8/4KB2 w - - 0 1", "2b1k3/8/8/8/8/8/8/4KB2 w - - 0 1"):
            self.assertTrue(Position.from_fen(fen).insufficient(), fen)
        self.assertFalse(Position.from_fen("1b2k3/8/8/8/8/8/8/4KB2 w - - 0 1").insufficient())

    def test_bad_moves_are_refused(self):
        g, _ = make()
        black = g.sides["b"][0]
        for bad in ("e2e5", "e7e5", "zz", "e2e4q", 42, None, "e2e4 ", "E2E4"):
            with self.assertRaises(GameError):
                g.handle(g.mover, {"a": "move", "move": bad})
        with self.assertRaises(GameError):
            g.handle(black, {"a": "move", "move": "e7e5"})  # not your turn
        self.assertEqual(g.history, [])

    def test_resign_and_draw_offers(self):
        g, _ = make()
        white, black = g.sides["w"][0], g.sides["b"][0]
        g.handle(white, {"a": "offer"})
        self.assertEqual(g.view_for(black)["draw_offer"], "w")
        g.handle(black, {"a": "decline"})
        self.assertIsNone(g.draw_offer)
        g.handle(white, {"a": "offer"})
        play(g, "e2e4")  # white moves on; the offer still stands for black...
        play(g, "e7e5")  # ...until black moves instead of answering
        self.assertIsNone(g.draw_offer)
        g.handle(black, {"a": "offer"})
        g.handle(white, {"a": "accept"})
        self.assertEqual(g.result, {"winner": None, "reason": "agreement"})
        self.assertEqual(g.scores(), {white: 100, black: 100})
        g, _ = make()
        g.handle(g.sides["w"][0], {"a": "resign"})
        self.assertEqual(g.result, {"winner": "b", "reason": "resignation"})


class ClockTests(unittest.TestCase):
    def test_increments_and_the_flag(self):
        g, clock = make(clock="3+2")
        clock.t = 10
        play(g, "e2e4")
        self.assertEqual(g.clocks["w"], 180 - 10 + 2)
        clock.t = 10 + 180
        g.tick()
        self.assertEqual(g.result, {"winner": "w", "reason": "time"})

    def test_a_flag_against_a_bare_king_is_a_draw(self):
        g, clock = make(fen="4k3/8/8/8/8/8/8/4K2R b - - 0 1")
        clock.t = 601
        g.tick()
        self.assertEqual(g.result, {"winner": "w", "reason": "time"})
        g, clock = make(fen="4k2r/8/8/8/8/8/8/4K3 w - - 0 1")
        clock.t = 601
        g.handle(g.mover, {"a": "move", "move": "e1d1"})  # too late: the flag falls first
        self.assertEqual(g.result, {"winner": "b", "reason": "time"})
        g, clock = make(fen="4k3/8/8/8/8/8/8/4KN2 b - - 0 1")
        clock.t = 601
        g.tick()
        self.assertEqual(g.result, {"winner": None, "reason": "time"})  # a lone knight can't mate

    def test_the_host_cannot_skip_a_move(self):
        g, _ = make()
        g.advance()
        self.assertEqual(g.phase, "play")
        self.assertEqual(g.history, [])


class TeamTests(unittest.TestCase):
    def test_teammates_take_turns_and_suggestions_stay_on_their_side(self):
        teams = {"p0": 0, "p1": 0, "p2": 1, "p3": 1}
        g, _ = make(4, teams=teams)
        white = g.sides["w"]
        self.assertEqual(len(white), 2)
        self.assertEqual({teams[p] for p in white}, {teams[white[0]]})
        mover, mate = g.mover, next(p for p in white if p != g.mover)
        g.handle(mate, {"a": "suggest", "move": "d2d4"})
        self.assertEqual(g.view_for(mover)["you"]["suggestions"], [{"by": mate, "move": "d2d4", "san": "d4"}])
        for other in [*g.sides["b"], *SPECTATORS]:
            view = json.dumps(g.view_for(other))
            self.assertNotIn("d2d4", view)
        with self.assertRaises(GameError):
            g.handle(mate, {"a": "move", "move": "d2d4"})  # it's the mover's go
        play(g, "e2e4")
        self.assertEqual(g.view_for(mover)["you"]["suggestions"], [])
        play(g, "e7e5")
        self.assertEqual(g.mover, mate)  # the side's next move is the teammate's

    def test_three_players_split_into_two_sides(self):
        g, _ = make(3)
        self.assertEqual(sorted(map(len, g.sides.values())), [1, 2])


class ViewTests(unittest.TestCase):
    def test_views_in_every_phase(self):
        g, _ = make(4, teams={"p0": 0, "p1": 1, "p2": 0, "p3": 1})
        ids = [*g.player_ids, *SPECTATORS]
        for p in ids:
            v = g.view_for(p)
            self.assertEqual(len(v["board"]), 64)
        self.assertEqual(len(g.view_for(g.mover)["you"]["legal"]), 20)
        self.assertIsNone(g.view_for("tv:screen")["you"])
        play(g, "f2f3", "e7e5", "g2g4", "d8h4")
        for p in ids:
            v = g.view_for(p)
            self.assertEqual(v["phase"], "final")
            self.assertEqual(v["result"]["reason"], "checkmate")
            if v["you"]:
                self.assertEqual(v["you"]["legal"], [])
        self.assertTrue(g.highlights())
        with self.assertRaises(GameError):
            g.handle(g.player_ids[0], {"a": "resign"})


if __name__ == "__main__":
    unittest.main()
