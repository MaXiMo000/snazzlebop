from __future__ import annotations

from .alibi import Alibi
from .base import Game, GameError, Player
from .blackjack import BlackjackShowdown
from .boxes import MysteryBoxes
from .chicken import ChickenRun
from .codes import CodeCrackers
from .codewords import Codewords
from .crossword import CrosswordRace
from .dice import LiarsDice
from .frenemy import FrenemyRadar
from .lonely import LowestLonely
from .mural import MoleInTheMural
from .price import PriceIsWeird
from .roulette import RouletteRoyale
from .split import SplitOrSteal
from .telepathy import TelepathyTax
from .truthdare import TruthOrDare
from .wits import WagerWits

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
        LiarsDice,
        SplitOrSteal,
        ChickenRun,
        WagerWits,
        CodeCrackers,
        RouletteRoyale,
        LowestLonely,
        MysteryBoxes,
        Codewords,
        TruthOrDare,
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
            "options": cls.OPTIONS,
            "how_to": list(cls.HOW_TO),
            "show": cls.SHOW,
            "classic": cls.CLASSIC,
        }
        for cls in REGISTRY.values()
    ]


__all__ = ["REGISTRY", "Game", "GameError", "Player", "catalog"]
