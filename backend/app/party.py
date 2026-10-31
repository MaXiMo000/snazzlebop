"""Party items: bought in the shop, used anywhere in a room (lobby, game or results), seen and heard by
everyone there, with no effect on any score. Pure.

Spam is held back twice over: each player waits PLAYER_GAP seconds between items, and a room plays at
most one every ROOM_GAP seconds (a refused one isn't spent).

Emote packs are kept, not spent: buying one adds its emoji to your live reactions in every room, for
good. They go through the same reaction limits as the standard six.
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
    "party_replay": {
        "name": "Slow-mo replay",
        "icon": "🎬",
        "text": "The last game's big moment again, in slow motion",
    },
}
REPLAY = "party_replay"  # needs a moment to replay: a game's highlights, or the show's reel
EMOTES: dict[str, dict[str, object]] = {
    "emote_spooky": {"name": "Spooky emotes", "icon": "👻", "emoji": ("👻", "🎃", "🦇", "🕸️")},
    "emote_animals": {"name": "Animal emotes", "icon": "🦄", "emoji": ("🐸", "🦄", "🐙", "🦖")},
    "emote_snacks": {"name": "Snack emotes", "icon": "🍕", "emoji": ("🍕", "🌮", "🍩", "🍿")},
    "emote_royal": {"name": "Royal emotes", "icon": "👑", "emoji": ("👑", "💎", "🏆", "🥇")},
    "emote_weather": {"name": "Weather emotes", "icon": "🌈", "emoji": ("🌈", "⚡", "🌪️", "❄️")},
    "emote_party": {"name": "Party emotes", "icon": "🎉", "emoji": ("🎉", "🥳", "🎊", "🪅")},
    "emote_love": {"name": "Love emotes", "icon": "❤️", "emoji": ("❤️", "😍", "💘", "🥰")},
    "emote_gamer": {"name": "Gamer emotes", "icon": "🎮", "emoji": ("🎮", "🕹️", "👾", "🏅")},
    "emote_hype": {"name": "Hype emotes", "icon": "🚀", "emoji": ("🚀", "💯", "🙌", "🤩")},
    "emote_sports": {"name": "Sports emotes", "icon": "⚽", "emoji": ("⚽", "🏀", "🎯", "🏓")},
    "emote_music": {"name": "Music emotes", "icon": "🎸", "emoji": ("🎵", "🎸", "🥁", "🎤")},
    "emote_space": {"name": "Space emotes", "icon": "🪐", "emoji": ("🪐", "👽", "🌙", "☄️")},
    "emote_ocean": {"name": "Ocean emotes", "icon": "🐬", "emoji": ("🐬", "🦈", "🐳", "🌊")},
    "emote_faces": {"name": "Face emotes", "icon": "🤔", "emoji": ("🤔", "😏", "🙄", "😭")},
    "emote_salty": {"name": "Salty emotes", "icon": "🧂", "emoji": ("🧂", "🤡", "🫠", "😤")},
    "emote_magic": {"name": "Magic emotes", "icon": "🔮", "emoji": ("🔮", "✨", "🪄", "🧙")},
    "emote_sweets": {"name": "Sweet emotes", "icon": "🧁", "emoji": ("🍰", "🧁", "🍦", "🍪")},
    "emote_retro": {"name": "Retro emotes", "icon": "📺", "emoji": ("📺", "📼", "☎️", "💾")},
}
PACK_OF: dict[str, str] = {e: pack for pack, info in EMOTES.items() for e in info["emoji"]}  # type: ignore[attr-defined]
PLAYER_GAP = 20.0
ROOM_GAP = 4.0
KEEP = 6  # recent effects sent with the room (each screen plays the ones it hasn't yet)
