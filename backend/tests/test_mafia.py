"""Mafia Night: the deal, night and day rules, who wins, and above all who may know what."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.mafia import DETECTIVE, DOCTOR, MAFIA, VILLAGER, MafiaNight, roles_for

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=6, seed=1, **opts):
    clock = Clock()
    g = MafiaNight(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def who(g, role):
    return [p for p in g.alive if g.roles[p] == role]


def night(g, kill=None, protect=None, check=None):
    """Everyone alive acts: the given choices for the roles, harmless picks for the rest."""
    for pid in list(g.alive):
        if g.phase != "night":
            break
        role = g.roles[pid]
        others = [p for p in g.alive if p != pid]
        if role == MAFIA:
            target = kill or next(p for p in others if g.roles[p] != MAFIA)
        elif role == DOCTOR:
            target = protect or next(p for p in g.alive if p != g.last_protected and p != kill)
        elif role == DETECTIVE:
            target = check or others[0]
        else:
            target = others[0]
        g.handle(pid, {"a": "night", "target": target})


def day(g, out=None):
    for pid in list(g.alive):
        if g.phase != "day":
            break
        g.handle(pid, {"a": "vote", "target": None if out is None or out == pid else out})


class DealTests(unittest.TestCase):
    def test_roles_by_player_count(self):
        self.assertEqual(roles_for(4), [MAFIA, DETECTIVE, VILLAGER, VILLAGER])
        self.assertEqual(roles_for(5).count(DOCTOR), 1)
        self.assertEqual(roles_for(6).count(MAFIA), 1)
        for n in (7, 8):
            self.assertEqual(roles_for(n).count(MAFIA), 2)
            self.assertEqual(len(roles_for(n)), n)
        with self.assertRaises(GameError):
            make(3)

    def test_different_seeds_deal_different_tables(self):
        self.assertGreater(len({json.dumps(make(6, s)[0].roles) for s in range(8)}), 1)


class RuleTests(unittest.TestCase):
    def test_night_kill_dawn_day_and_town_win(self):
        g, _ = make(6)
        g.advance()
        self.assertEqual(g.phase, "night")
        (mafia,) = who(g, MAFIA)
        victim = who(g, VILLAGER)[0]
        night(g, kill=victim, check=mafia)
        self.assertEqual(g.phase, "dawn")
        self.assertNotIn(victim, g.alive)
        self.assertEqual(g.news["killed"], victim)
        self.assertEqual(g.findings, {mafia: True})
        g.advance()
        self.assertEqual(g.phase, "day")
        day(g, out=mafia)
        self.assertEqual((g.phase, g.news["out"], g.news["role"]), ("verdict", mafia, MAFIA))
        g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(g.winner, "town")
        self.assertEqual(g.round_scores[mafia], 100)  # one kill, no win
        (detective,) = [p for p, r in g.roles.items() if r == DETECTIVE]
        self.assertEqual(g.round_scores[detective], 300 + 100 + 100 + 50)  # win, alive, found, good vote

    def test_doctor_saves_and_cannot_repeat(self):
        g, _ = make(6)
        g.advance()
        victim = who(g, VILLAGER)[0]
        (doctor,) = who(g, DOCTOR)
        night(g, kill=victim, protect=victim)
        self.assertEqual((g.news["killed"], g.news["saved"]), (None, True))
        self.assertIn(victim, g.alive)
        self.assertEqual(g.round_scores[doctor], 150)
        g.advance()
        day(g)
        g.advance()
        self.assertEqual(g.phase, "night")
        with self.assertRaises(GameError):
            g.handle(doctor, {"a": "night", "target": victim})
        g.handle(doctor, {"a": "night", "target": doctor})  # protecting yourself is allowed

    def test_mafia_win_when_they_are_half(self):
        g, _ = make(4)
        g.advance()
        night(g)
        g.advance()  # three left: one Mafia, two town
        self.assertEqual(g.phase, "day")
        (mafia,) = who(g, MAFIA)
        innocent = next(p for p in g.alive if p != mafia)
        day(g, out=innocent)
        g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(g.winner, "mafia")

    def test_ties_and_skips_remove_nobody(self):
        g, _ = make(6)
        g.advance()
        night(g)
        g.advance()
        a, b, *rest = g.alive
        g.handle(a, {"a": "vote", "target": b})
        g.handle(b, {"a": "vote", "target": a})
        for p in rest:
            g.handle(p, {"a": "vote", "target": None})
        self.assertEqual((g.phase, g.news["out"]), ("verdict", None))

    def test_two_mafia_agreeing_or_not(self):
        g, _ = make(8)
        g.advance()
        m1, m2 = who(g, MAFIA)
        v = who(g, VILLAGER)
        g.handle(m1, {"a": "night", "target": v[0]})
        self.assertEqual(g.view_for(m2)["you"]["mate_picks"], {m1: v[0]})
        with self.assertRaises(GameError):
            g.handle(m2, {"a": "night", "target": m1})  # not your own
        g.handle(m2, {"a": "night", "target": v[1]})
        g.advance()
        self.assertIn(g.news["killed"], (v[0], v[1], None))

    def test_bad_input_and_ghosts(self):
        g, _ = make(6)
        (mafia,) = who(g, MAFIA)
        with self.assertRaises(GameError):
            g.handle(mafia, {"a": "night", "target": who(g, VILLAGER)[0]})  # roles screen: not night yet
        g.advance()
        for bad in (None, 3, "nobody", mafia, ["p1"]):
            with self.assertRaises(GameError):
                g.handle(mafia, {"a": "night", "target": bad})
        with self.assertRaises(GameError):
            g.handle("stranger", {"a": "night", "target": "p0"})
        with self.assertRaises(GameError):
            g.handle(mafia, {"a": "vote", "target": None})
        victim = who(g, VILLAGER)[0]
        night(g, kill=victim, protect=mafia)
        g.advance()
        with self.assertRaises(GameError):
            g.handle(victim, {"a": "vote", "target": mafia})
        self.assertTrue(g.chat_muted(victim))
        self.assertFalse(g.chat_muted(mafia))

    def test_timers_move_every_phase_and_the_game_always_ends(self):
        for seed in range(6):
            g, clock = make(8, seed, day="60")
            for _ in range(200):
                if g.finished:
                    break
                clock.t += 200
                g.tick()
            self.assertTrue(g.finished)
            self.assertEqual(g.winner, "mafia")  # nobody acted: no kills, no votes, the round limit ends it

    def test_random_games_finish_with_a_winner(self):
        for seed in range(30):
            rng = random.Random(seed)
            g, _ = make(rng.choice([4, 5, 6, 7, 8]), seed)
            g.advance()
            for _ in range(60):
                if g.finished:
                    break
                if g.phase == "night":
                    for pid in list(g.alive):
                        options = [
                            p
                            for p in g.alive
                            if (p != pid or g.roles[pid] == DOCTOR)
                            and not (g.roles[pid] == MAFIA and g.roles[p] == MAFIA)
                            and not (g.roles[pid] == DOCTOR and p == g.last_protected)
                        ]
                        if g.phase == "night" and options:
                            g.handle(pid, {"a": "night", "target": rng.choice(options)})
                    if g.phase == "night":
                        g.advance()
                elif g.phase == "day":
                    for pid in list(g.alive):
                        if g.phase == "day":
                            pick = rng.choice([None, *[p for p in g.alive if p != pid]])
                            g.handle(pid, {"a": "vote", "target": pick})
                else:
                    g.advance()
            self.assertTrue(g.finished, seed)
            self.assertIn(g.winner, ("town", "mafia"))
            mafia_left = sum(g.roles[p] == MAFIA for p in g.alive)
            self.assertEqual(g.winner == "town", mafia_left == 0)


class SecrecyTests(unittest.TestCase):
    def test_roles_reach_only_their_owners(self):
        g, _ = make(8)
        mafia = [p for p, r in g.roles.items() if r == MAFIA]
        for _ in range(2):  # the roles screen, then the night
            for pid in g.player_ids:
                view = g.view_for(pid)
                self.assertIsNone(view["roles"])
                self.assertEqual(view["you"]["role"], g.roles[pid])
                self.assertEqual(
                    sorted(view["you"]["mates"]), sorted(m for m in mafia if m != pid) if pid in mafia else []
                )
                blob = json.dumps({k: v for k, v in view.items() if k not in ("you", "counts", "game")})
                for role in (MAFIA, DETECTIVE, DOCTOR):
                    self.assertNotIn(f'"{role}"', blob, (pid, role))
            for viewer in SPECTATORS:
                view = g.view_for(viewer)
                self.assertIsNone(view["you"])
                self.assertIsNone(view["roles"])
            g.advance()

    def test_night_picks_and_findings_stay_private(self):
        g, _ = make(6)
        g.advance()
        (mafia,) = who(g, MAFIA)
        (detective,) = who(g, DETECTIVE)
        victim = who(g, VILLAGER)[0]
        g.handle(mafia, {"a": "night", "target": victim})
        g.handle(detective, {"a": "night", "target": mafia})
        for viewer in [*g.player_ids, *SPECTATORS]:
            view = g.view_for(viewer)
            self.assertEqual(view["acted"], sorted([mafia, detective]))  # who has acted, never what
            if viewer not in (mafia, detective):
                self.assertNotIn(victim, json.dumps(view.get("you") or {}))
                self.assertNotIn("findings", view.get("you") or {})
        night(g, kill=victim, check=mafia)
        self.assertEqual(g.view_for(detective)["you"]["findings"], {mafia: True})
        for viewer in [p for p in g.alive if p != detective] + list(SPECTATORS):
            self.assertNotIn("findings", g.view_for(viewer).get("you") or {})

    def test_the_dead_are_named_and_ghosts_see_everything(self):
        g, _ = make(6)
        g.advance()
        victim = who(g, VILLAGER)[0]
        night(g, kill=victim, protect=who(g, MAFIA)[0])
        for viewer in [*g.alive, *SPECTATORS]:
            view = g.view_for(viewer)
            self.assertEqual(view["dead"], [{"id": victim, "role": VILLAGER, "how": "night", "round": 1}])
            self.assertIsNone(view["roles"])
        self.assertEqual(g.view_for(victim)["roles"], g.roles)

    def test_final_shows_all(self):
        g, clock = make(4)
        while not g.finished:
            clock.t += 500
            g.tick()
        for viewer in [*g.player_ids, *SPECTATORS]:
            view = g.view_for(viewer)
            self.assertEqual(view["roles"], g.roles)
            self.assertEqual(view["winner"], g.winner)

    def test_mafia_channel_only_for_two_living_mafia(self):
        g, _ = make(8)
        m1, m2 = who(g, MAFIA)
        self.assertEqual(g.chat_team(m1), ("mafia", "Mafia"))
        self.assertIsNone(g.chat_team(who(g, VILLAGER)[0]))
        solo, _ = make(6)
        self.assertIsNone(solo.chat_team(who(solo, MAFIA)[0]))


if __name__ == "__main__":
    unittest.main()
