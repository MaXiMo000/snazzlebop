"""The Hub: every live room, composed from one mixin per area (see the other modules here)."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .. import prank
from ..config import Settings
from .delivery import DeliveryMixin
from .flow import FlowMixin
from .lobby import LobbyMixin
from .models import (
    INTRO_SECONDS,
    Connection,
    Room,
    SnapshotStore,
)
from .routing import RoutingMixin
from .shows import ShowMixin
from .social import SocialMixin
from .store import PersistMixin
from .views import ViewsMixin


class Hub(
    PersistMixin, LobbyMixin, ViewsMixin, DeliveryMixin, RoutingMixin, FlowMixin, ShowMixin, SocialMixin
):
    def __init__(
        self,
        settings: Settings,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        on_game_finished: Callable[[str, dict[str, Any]], None] | None = None,
        on_game_started: Callable[[str, str], None] | None = None,  # (game id, show pack)
        timings: dict[str, dict[str, float]] | None = None,
        intro_seconds: float = INTRO_SECONDS,  # 0 = games start straight away (used by unit tests)
        store: SnapshotStore | None = None,  # saves rooms so they survive a restart (None: memory only)
        # Accounts: pay coins for a finished game ({account: coins} paid), spend / refund a power-up.
        on_results: Callable[[list[dict[str, Any]]], Awaitable[dict[int, int]]] | None = None,
        spend_powerup: Callable[[int, str], Awaitable[bool]] | None = None,
        refund_powerup: Callable[[int, str], Awaitable[None]] | None = None,
        # (host's account, belt holder's name, forfeits): remembered for that host's next rooms
        save_circle: Callable[[int, str, list[str]], Awaitable[None]] | None = None,
        wall: Callable[[], float] = time.time,  # real time, for things that end at a set hour (mutes)
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.wall = wall
        self.rng = rng or random.SystemRandom()
        self.rooms: dict[str, Room] = {}
        self.on_game_finished = on_game_finished
        self.on_game_started = on_game_started
        self.timings = timings or {}
        self.intro_seconds = intro_seconds
        self.prank_targets = prank.targets(settings.jumpscare_names) if settings.jumpscare else ()
        self.send_timeout = 5.0  # a socket that can't take a frame this long is dropped
        self._mail: dict[Connection, dict[str, Any]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self.store = store
        self.on_results = on_results
        self.spend_powerup = spend_powerup
        self.refund_powerup = refund_powerup
        self.save_circle = save_circle
        self._saving: dict[str, bool] = {}  # room code -> another save is due once this one lands
