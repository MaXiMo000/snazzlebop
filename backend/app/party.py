"""Party items: bought in the shop, used anywhere in a room (lobby, game or results), seen and heard by
everyone there, with no effect on any score. Pure.

Spam is held back twice over: each player waits PLAYER_GAP seconds between items, and a room plays at
most one every ROOM_GAP seconds (a refused one isn't spent).
"""

from __future__ import annotations

ITEMS: dict[str, dict[str, str]] = {
    "party_confetti": {
        "name": "Confetti cannon",
        "icon": "🎉",
        "text": "Confetti on every screen in the room",
    },
    "party_airhorn": {"name": "Air horn", "icon": "📯", "text": "One mighty HONK for the whole room"},
    "party_drumroll": {"name": "Drum roll", "icon": "🥁", "text": "Build the suspense before a reveal"},
    "party_ovation": {"name": "Standing ovation", "icon": "👏", "text": "The whole room applauds"},
    "party_spotlight": {"name": "Spotlight", "icon": "🔦", "text": "Your name in lights on every screen"},
}
PLAYER_GAP = 20.0
ROOM_GAP = 4.0
KEEP = 6  # recent effects sent with the room (each screen plays the ones it hasn't yet)
