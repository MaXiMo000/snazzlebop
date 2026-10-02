from __future__ import annotations

from .alibi import Alibi
from .base import Game, GameError, Player
from .blackjack import BlackjackShowdown
from .crossword import CrosswordRace
from .frenemy import FrenemyRadar
from .mural import MoleInTheMural
from .price import PriceIsWeird
from .telepathy import TelepathyTax

REGISTRY: dict[str, type[Game]] = {
    cls.game_id: cls
    for cls in (
        FrenemyRadar,
        Alibi,
        PriceIsWeird,
        TelepathyTax,
        MoleInTheMural,
        BlackjackShowdown,
        CrosswordRace,
    )
}


def catalog() -> list[dict[str, object]]:
    return [
        {
            "id": cls.game_id,
            "title": cls.title,
            "blurb": cls.blurb,
            "min_players": cls.min_players,
            "max_players": cls.max_players,
        }
        for cls in REGISTRY.values()
    ]


__all__ = ["REGISTRY", "Game", "GameError", "Player", "catalog"]
