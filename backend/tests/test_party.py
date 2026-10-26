"""Party items: everyone in the room sees one when it's used (any phase), no score changes, spam held
back per player and per room (a refused one isn't spent), signed-in players only."""

from __future__ import annotations

import unittest

from app import party as P
from tests.test_accounts import Wallet
from tests.test_accounts import client as client  # noqa: F401 - the fixture, shared
from tests.test_ranked import room_of


class PartyTests(unittest.IsolatedAsyncioTestCase):
    async def room(self, wallet, guests=0):
        hub, room, pids, conns = await room_of(3, guests=guests)
        hub.spend_powerup, hub.refund_powerup = wallet.spend, wallet.refund
        hub.clock = lambda: self.t
        self.t = 1000.0
        return hub, room, pids, conns

    async def use(self, hub, room, conns, pid, item):
        await hub.handle_message(room, pid, conns[pid], {"t": "party", "item": item})
        return conns[pid].errors()

    async def test_everyone_sees_it_and_scores_dont_move(self):
        wallet = Wallet({(1, "party_confetti"): 1})
        hub, room, pids, conns = await self.room(wallet)
        before = dict(room.total_scores)
        self.assertEqual(await self.use(hub, room, conns, pids[0], "party_confetti"), [])
        for pid in pids:
            effects = hub.view_for(room, pid)["party"]["effects"]
            self.assertEqual([(e["item"], e["by"]) for e in effects], [("party_confetti", "Host")])
        self.assertEqual(room.total_scores, before)
        self.assertEqual(wallet.owned[(1, "party_confetti")], 0)

    async def test_spam_is_held_back_and_refused_ones_are_not_spent(self):
        wallet = Wallet({(1, "party_airhorn"): 3, (2, "party_airhorn"): 1})
        hub, room, pids, conns = await self.room(wallet)
        await self.use(hub, room, conns, pids[0], "party_airhorn")
        self.assertIn("slow_down", await self.use(hub, room, conns, pids[1], "party_airhorn"))  # room gap
        self.assertEqual(wallet.owned[(2, "party_airhorn")], 1)  # not spent
        self.t += P.ROOM_GAP
        self.assertIn("slow_down", await self.use(hub, room, conns, pids[0], "party_airhorn"))  # player gap
        self.t += P.PLAYER_GAP
        await self.use(hub, room, conns, pids[0], "party_airhorn")
        self.assertEqual(len(room.party_effects), 2)  # the wait is over: it plays
        self.assertEqual(wallet.owned[(1, "party_airhorn")], 1)

    async def test_guests_unknown_items_and_empty_pockets(self):
        hub, room, pids, conns = await self.room(Wallet({}), guests=1)
        self.assertIn("signed_out", await self.use(hub, room, conns, pids[-1], "party_ovation"))
        self.assertIn("bad_item", await self.use(hub, room, conns, pids[0], "party_fireworks"))
        self.assertIn("no_powerup", await self.use(hub, room, conns, pids[0], "party_ovation"))
        self.assertEqual(room.party_effects, [])

    async def test_the_replay_needs_a_moment_and_shows_it_to_everyone(self):
        wallet = Wallet({(1, "party_replay"): 1})
        hub, room, pids, conns = await self.room(wallet)
        self.assertIn("nothing_to_replay", await self.use(hub, room, conns, pids[0], "party_replay"))
        self.assertEqual(wallet.owned[(1, "party_replay")], 1)  # refused: not spent
        room.highlights = [{"icon": "🎯", "title": "Sharpshooter", "text": "Bo guessed within $3"}]
        self.assertEqual(
            await self.use(hub, room, conns, pids[0], "party_replay"), ["nothing_to_replay"]
        )  # no new error
        for pid in pids:
            [effect] = hub.view_for(room, pid)["party"]["effects"]
            self.assertEqual(effect["moment"]["title"], "Sharpshooter")


class EmoteTests(unittest.IsolatedAsyncioTestCase):
    async def test_pack_emoji_only_for_owners(self):
        hub, room, pids, conns = await room_of(2, guests=1)
        owned = {(1, "emote_spooky")}
        asked = []

        async def owns(uid, item):
            asked.append(uid)
            return (uid, item) in owned

        hub.owns_item = owns
        ghost = P.EMOTES["emote_spooky"]["emoji"][0]
        await hub.handle_message(room, pids[1], conns[pids[1]], {"t": "react", "e": ghost})
        self.assertIn("no_emotes", conns[pids[1]].errors())
        await hub.handle_message(room, pids[-1], conns[pids[-1]], {"t": "react", "e": ghost})  # a guest
        self.assertIn("no_emotes", conns[pids[-1]].errors())
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "react", "e": ghost})
        self.assertEqual(conns[pids[0]].errors(), [])
        self.assertEqual(room.reactions[-1]["e"], ghost)
        room.react_last.clear()
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "react", "e": ghost})
        self.assertEqual(asked.count(1), 1)  # remembered for the room after the first check


def test_an_emote_pack_is_bought_once_and_kept(client):  # noqa: F811 - the fixture
    from sqlalchemy import update

    from app.db import User
    from tests.test_accounts import signup

    signup(client)
    db = client.app.state.db

    async def rich():
        async with db.sessions() as s:
            await s.execute(update(User).values(coins=500))
            await s.commit()

    client.portal.call(rich)
    assert client.post("/api/shop/buy", json={"item": "emote_royal"}).status_code == 200
    again = client.post("/api/shop/buy", json={"item": "emote_royal"})
    assert again.status_code == 400 and again.json()["error"]["code"] == "owned"
    assert client.get("/api/me").json()["user"]["powerups"] == {"emote_royal": 1}
    uid = client.portal.call(db.user_by_name, "Ana_99").id
    assert client.portal.call(db.owns_item, uid, "emote_royal")
