"""Alibi: a murder-mystery deduction game.

Setup: the server generates a hidden truth (where every player really was in each
half-hour slot). One player is the killer. Innocents' cards are the truth. The
killer's card is a script with two fabricated slots (the murder slot and one
"witness" slot) where they claim to be somewhere that was actually empty.

Play: everyone's murder-slot alibi is published when interrogation starts. After
that, players reveal slots voluntarily or *ask* another player about a slot, which
forces that player's card entry onto the public board. The server flags
contradictions between published claims and the camera clues it drops. Finally the
room votes. The killer wins if they are not the single most-voted player.

There is deliberately no free text: every claim comes from a server-built card, so
there is nothing to inject, spam, or forge, and nobody can lie differently from
their script.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

SLOT_LABELS = ["7:00 PM", "7:30 PM", "8:00 PM", "8:30 PM", "9:00 PM", "9:30 PM"]
LOCATIONS = ["Kitchen", "Garden", "Library", "Cellar", "Balcony", "Garage"]
VICTIM = "Lord Ashby"
INTERROGATION_ROUNDS = 3
ASKS_PER_ROUND = 2


class Alibi(Game):
    game_id: ClassVar[str] = "alibi"
    title: ClassVar[str] = "Alibi"
    blurb: ClassVar[str] = (
        "Someone at this party is the killer. Everyone has an alibi card. "
        "One of them is a lie. Interrogate, spot the contradiction, vote."
    )
    min_players: ClassVar[int] = 4
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"briefing": 30.0, "round": 75.0, "vote": 45.0}

    # -- setup --------------------------------------------------------------
    def start(self) -> None:
        rng = self.rng
        ids = self.player_ids
        self.killer = rng.choice(ids)
        innocents = [i for i in ids if i != self.killer]
        n_slots = len(SLOT_LABELS)
        self.murder_slot = rng.randrange(1, n_slots - 1)
        self.witness_slot = rng.choice([s for s in range(n_slots) if s != self.murder_slot])

        truth: dict[str, list[str]] = {i: [""] * n_slots for i in ids}
        fake: dict[int, str] = {}
        self.scene = ""
        self.witness_true_location = ""
        for s in range(n_slots):
            if s == self.murder_slot:
                scene = rng.choice(LOCATIONS)
                empty = rng.choice([x for x in LOCATIONS if x != scene])
                self.scene = scene
                truth[self.killer][s] = scene
                pool = [x for x in LOCATIONS if x not in (scene, empty)]
                for i in innocents:
                    truth[i][s] = rng.choice(pool)
                fake[s] = empty
            elif s == self.witness_slot:
                true_loc = rng.choice(LOCATIONS)
                empty = rng.choice([x for x in LOCATIONS if x != true_loc])
                self.witness_true_location = true_loc
                truth[self.killer][s] = true_loc
                pool = [x for x in LOCATIONS if x != empty]
                witness = rng.choice(innocents)
                truth[witness][s] = true_loc
                for i in innocents:
                    if i != witness:
                        truth[i][s] = rng.choice(pool)
                fake[s] = empty
            else:
                for i in ids:
                    truth[i][s] = rng.choice(LOCATIONS)
        self.truth = truth
        self.fake = fake

        # Cards: what each player is supposed to say. Companions come from the truth.
        self.cards: dict[str, list[dict[str, Any]]] = {}
        for i in ids:
            card = []
            for s in range(n_slots):
                if i == self.killer and s in fake:
                    claimed, companions = fake[s], []
                else:
                    claimed = truth[i][s]
                    companions = [o for o in ids if o != i and truth[o][s] == claimed]
                card.append({"slot": s, "location": claimed, "with": companions})
            self.cards[i] = card

        self.claims: dict[tuple[str, int], dict[str, Any]] = {}
        self.log: list[dict[str, Any]] = []
        self.clues: list[dict[str, Any]] = []
        self.asked: set[tuple[str, str, int]] = set()
        self.asks_used: dict[str, int] = {i: 0 for i in ids}
        self.votes: dict[str, str] = {}
        self.round = 0
        self.result: dict[str, Any] | None = None
        self.phase = "briefing"
        self.set_deadline(self.timings["briefing"])
        self.bump()

    # -- helpers ------------------------------------------------------------
    def _publish(self, pid: str, slot: int) -> bool:
        key = (pid, slot)
        if key in self.claims:
            return False
        entry = self.cards[pid][slot]
        self.claims[key] = {
            "speaker": pid,
            "slot": slot,
            "label": SLOT_LABELS[slot],
            "location": entry["location"],
            "with": list(entry["with"]),
        }
        return True

    def _camera(self, location: str, slot: int) -> dict[str, Any]:
        occupants = sorted(i for i in self.player_ids if self.truth[i][slot] == location)
        return {
            "kind": "camera",
            "location": location,
            "slot": slot,
            "label": SLOT_LABELS[slot],
            "occupants": occupants,
        }

    def _enter_round(self) -> None:
        self.phase = "interrogate"
        self.set_deadline(self.timings["round"])
        for k in self.asks_used:
            self.asks_used[k] = 0
        if self.round == 0:
            for pid in self.player_ids:
                self._publish(pid, self.murder_slot)
            self.log.append({"kind": "alibis", "text": "Everyone's alibi for the murder is on the board."})
        elif self.round == 1:
            self.clues.append(self._camera(self.witness_true_location, self.witness_slot))
            self.log.append({"kind": "clue", "text": "New clue: a camera feed was recovered."})
        elif self.round == 2:
            non_scene = [x for x in LOCATIONS if x != self.scene]
            self.clues.append(self._camera(self.rng.choice(non_scene), self.murder_slot))
            self.log.append({"kind": "clue", "text": "New clue: another camera feed was recovered."})
        self.bump()

    def _enter_vote(self) -> None:
        self.phase = "vote"
        self.set_deadline(self.timings["vote"])
        self.bump()

    def _finish(self) -> None:
        tally: dict[str, int] = {}
        for target in self.votes.values():
            tally[target] = tally.get(target, 0) + 1
        top = max(tally.values(), default=0)
        leaders = [t for t, c in tally.items() if c == top and top > 0]
        caught = leaders == [self.killer]
        for pid, target in self.votes.items():
            if caught and pid != self.killer and target == self.killer:
                self.add_points(pid, 150)
        if caught:
            for pid in self.player_ids:
                if pid != self.killer:
                    self.add_points(pid, 50)
        else:
            self.add_points(self.killer, 300)
        self.result = {
            "killer": self.killer,
            "caught": caught,
            "tally": tally,
            "votes": dict(self.votes),
            "truth": {i: list(self.truth[i]) for i in self.player_ids},
            "fake_slots": sorted(self.fake),
        }
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.bump()

    # -- contradictions -----------------------------------------------------
    def flags(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[Any] = set()
        for (speaker, slot), a in self.claims.items():
            for other in a["with"]:
                b = self.claims.get((other, slot))
                if not b:
                    continue
                mismatch = b["location"] != a["location"] or speaker not in b["with"]
                key = (frozenset((speaker, other)), slot)
                if mismatch and key not in seen:
                    seen.add(key)
                    out.append(
                        {
                            "kind": "mismatch",
                            "slot": slot,
                            "label": SLOT_LABELS[slot],
                            "players": sorted((speaker, other)),
                            "text": (
                                f"{self.name_of(speaker)} says they were with {self.name_of(other)} "
                                f"at {SLOT_LABELS[slot]}, but {self.name_of(other)}'s story doesn't match."
                            ),
                        }
                    )
        for clue in self.clues:
            if clue["kind"] != "camera":
                continue
            occ = set(clue["occupants"])
            for (speaker, slot), claim in self.claims.items():
                if slot != clue["slot"]:
                    continue
                bad = (claim["location"] == clue["location"] and speaker not in occ) or (
                    speaker in occ and claim["location"] != clue["location"]
                )
                key = ("cam", speaker, slot, clue["location"])
                if bad and key not in seen:
                    seen.add(key)
                    out.append(
                        {
                            "kind": "camera",
                            "slot": slot,
                            "label": SLOT_LABELS[slot],
                            "players": [speaker],
                            "text": (
                                f"The {clue['location']} camera at {SLOT_LABELS[slot]} "
                                f"contradicts {self.name_of(speaker)}'s story."
                            ),
                        }
                    )
        return out

    # -- actions ------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        n_slots = len(SLOT_LABELS)
        if kind == "reveal":
            self._need("interrogate")
            slot = as_int(action.get("slot"), lo=0, hi=n_slots - 1, field="Slot")
            if self._publish(pid, slot):
                self.log.append(
                    {"kind": "reveal", "text": f"{self.name_of(pid)} shared their {SLOT_LABELS[slot]} alibi."}
                )
                self.bump()
        elif kind == "ask":
            self._need("interrogate")
            target = action.get("target")
            if not isinstance(target, str) or target not in self.round_scores or target == pid:
                raise GameError("bad_input", "Pick another player to question")
            slot = as_int(action.get("slot"), lo=0, hi=n_slots - 1, field="Slot")
            if self.asks_used[pid] >= ASKS_PER_ROUND:
                raise GameError("no_asks", "No questions left this round")
            if (pid, target, slot) in self.asked or (target, slot) in self.claims:
                raise GameError("already_known", "That alibi is already on the board")
            self.asked.add((pid, target, slot))
            self.asks_used[pid] += 1
            self._publish(target, slot)
            self.log.append(
                {
                    "kind": "ask",
                    "text": (
                        f"{self.name_of(pid)} grilled {self.name_of(target)} about {SLOT_LABELS[slot]}."
                    ),
                }
            )
            self.bump()
        elif kind == "vote":
            self._need("vote")
            target = action.get("target")
            if not isinstance(target, str) or target not in self.round_scores or target == pid:
                raise GameError("bad_input", "Vote for another player")
            self.votes[pid] = target
            self.bump()
            if len(self.votes) == len(self.players):
                self._finish()
        else:
            raise GameError("bad_action", "Unknown action")

    def _need(self, phase: str) -> None:
        if self.phase != phase:
            raise GameError("wrong_phase", "Not possible right now")

    def tick(self) -> None:
        if self.finished or not self.expired():
            return
        self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "briefing":
            self.round = 0
            self._enter_round()
        elif self.phase == "interrogate":
            if self.round + 1 < INTERROGATION_ROUNDS:
                self.round += 1
                self._enter_round()
            else:
                self._enter_vote()
        elif self.phase == "vote":
            self._finish()

    # -- views --------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        is_killer = pid == self.killer
        card = [
            {
                "slot": e["slot"],
                "label": SLOT_LABELS[e["slot"]],
                "location": e["location"],
                "with": e["with"],
                "shared": (pid, e["slot"]) in self.claims,
            }
            for e in self.cards.get(pid, [])
        ]
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": INTERROGATION_ROUNDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "victim": VICTIM,
            "scene": self.scene,
            "murder_slot": self.murder_slot,
            "murder_label": SLOT_LABELS[self.murder_slot],
            "slots": SLOT_LABELS,
            "locations": LOCATIONS,
            "you": {
                "card": card,
                "is_killer": is_killer,
                # Only the killer is told which parts of their card are lies.
                "fake_slots": sorted(self.fake) if is_killer else None,
                "asks_left": max(0, ASKS_PER_ROUND - self.asks_used.get(pid, 0)),
            },
            "claims": [{**c} for c in sorted(self.claims.values(), key=lambda c: (c["slot"], c["speaker"]))],
            "flags": self.flags(),
            "clues": self.clues,
            "log": self.log[-30:],
            "votes_in": len(self.votes),
            "you_voted": self.votes.get(pid),
        }
        if self.phase == "final" and self.result:
            view["result"] = self.result
        return view

    def summary(self) -> dict[str, Any]:
        return {
            "players": len(self.players),
            "caught": bool(self.result and self.result["caught"]),
        }
