"""Levels, daily quests, streaks and weekly challenges. Pure.

XP comes only from fair games (fairplay.py: two or more signed-in players, not too quick, no shared
device, not the same group over and over), up to a daily cap, plus finished quests and challenges.
Each level pays coins and a random power-up, once.

Daily quests come from a large pool in five kinds (social, games, skill, club, fun). Every day has one
social quest (the product's goal is people meeting through games) and two of two other kinds. Within a
kind, each account walks its own shuffled order of that kind's quests, one step a day, and every kind
holds at least a week of them: a quest can't come back within seven days. One reroll a day swaps a
quest for another of its kind. Finishing all three on consecutive days builds a streak, with a bonus
every seventh day. Weekly challenges are three bigger goals, Monday to Sunday.

Club challenges are one shared goal a week for a whole club, sized to its members. Everyone who played
a club game that week can claim the reward once the club reaches it. Each member counts for at most
CLUB_DAY_GAMES games a day, so two people can't play the goal in on their own.

Season challenges are five long goals for each 8-week ratings season, tied to ranked play and
battles. Finishing all five earns that season's badge.

Each quest names a measure (how its progress is counted, from what really happened, in db.py) and a
target; some carry an argument (a game category, a player count, an activity kind).
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date, timedelta

XP_FINISH = 10  # finishing a fair game
XP_WIN = 5  # on top, for first place
XP_FIRST_WIN = 25  # the day's first win
XP_QUEST = 50
XP_DAILY_CAP = 400  # from games; quests come on top
QUEST_COINS = 25
LEVEL_COINS = 30
STREAK_DAYS = 7  # a bonus every this many days of all three quests in a row
STREAK_COINS = 100
STREAK_GIFT = "party_confetti"
WEEKLY_XP = 150
CLUB_XP = 100
CLUB_COINS = 60
CLUB_DAY_GAMES = 5  # the most club games one member adds to a club's goal in a day
SEASON_XP = 200
# The Club score: activity in a club this ratings season, not skill, so casual players climb too. Club
# games and hosting count up to CLUB_DAY_GAMES a day each; battles only when fair play passed them.
CLUB_SCORE = {"club_game": 10, "club_host": 5, "battle": 15}
SEASON_COINS = 150
WEEKLY_COINS = 100
EPOCH = date(2026, 1, 5)  # a Monday: day and week numbers count from here

KINDS = ("social", "games", "skill", "club", "fun")


def q(title: str, kind: str, measure: str, target: int, arg: object = None) -> dict[str, object]:
    return {"title": title, "kind": kind, "measure": measure, "target": target, "arg": arg}


QUESTS: dict[str, dict[str, object]] = {
    # social: playing with people, especially new ones
    "new_person": q("Play with someone you've never played with", "social", "new_people", 1),
    "new_two": q("Play with 2 people you've never played with", "social", "new_people", 2),
    "three_people": q("Play with 3 different people today", "social", "people", 3),
    "five_people": q("Play with 5 different people today", "social", "people", 5),
    "old_friend": q("Play again with someone you've played with before", "social", "old_friends", 1),
    "group4": q("Finish a game with 4 or more players", "social", "big_games", 1, 4),
    "group6": q("Finish a game with 6 or more players", "social", "big_games", 1, 6),
    "new_clubmate": q("Play with a clubmate you haven't played with yet", "social", "new_clubmates", 1),
    # games: variety
    "finish3": q("Finish 3 games with other players", "games", "fair_games", 3),
    "finish5": q("Finish 5 games with other players", "games", "fair_games", 5),
    "try_game": q("Play a game you've never played before", "games", "new_games", 1),
    "two_games": q("Play 2 different games", "games", "distinct_games", 2),
    "three_games": q("Play 3 different games", "games", "distinct_games", 3),
    "cat_party": q("Play a party game", "games", "category", 1, "party"),
    "cat_quiz": q("Play a quiz or word game", "games", "category", 1, "quiz"),
    "cat_bluff": q("Play a bluffing game", "games", "category", 1, "bluff"),
    "cat_nerve": q("Play a game of nerve", "games", "category", 1, "nerve"),
    "cat_classics": q("Play a classic", "games", "category", 1, "classics"),
    # skill
    "win1": q("Win a game", "skill", "wins", 1),
    "win2": q("Win 2 games", "skill", "wins", 2),
    "top2_three": q("Finish in the top 2 three times", "skill", "top2", 3),
    "win_big": q("Win a game with 4 or more players", "skill", "big_wins", 1, 4),
    "ranked1": q("Play a ranked game", "skill", "ranked", 1),
    "ranked3": q("Play 3 ranked games", "skill", "ranked", 3),
    "ranked_win": q("Win a ranked game", "skill", "ranked_wins", 1),
    "battle_win": q("Win a battle", "skill", "battle_wins", 1),
    # club
    "clubmate1": q("Play with a clubmate", "club", "clubmates", 1),
    "clubmates2": q("Play with 2 different clubmates", "club", "clubmates", 2),
    "clubmates3": q("Play with 3 different clubmates", "club", "clubmates", 3),
    "club_game1": q("Finish a game in a club room", "club", "activity", 1, "club_game"),
    "club_games3": q("Finish 3 games in club rooms", "club", "activity", 3, "club_game"),
    "club_host": q("Host a club room game that finishes", "club", "activity", 1, "club_host"),
    "battle1": q("Finish a battle", "club", "battles", 1),
    "battle_host": q("Challenge a clubmate to a battle", "club", "activity", 1, "battle_sent"),
    # fun
    "use_power": q("Use a power-up in a game", "fun", "activity", 1, "power"),
    "use_party": q("Use a party item", "fun", "activity", 1, "party"),
    "react": q("Send reactions in 2 different games", "fun", "activity", 2, "react"),
    "mvp": q("Win the audience's MVP vote", "fun", "activity", 1, "mvp"),
    "show_night": q("Play a whole show night", "fun", "activity", 1, "show"),
    "host_game": q("Host a game that finishes", "fun", "activity", 1, "host"),
    "earn100": q("Earn 100 coins from games today", "fun", "coins_earned", 100),
    "xp150": q("Earn 150 XP from games today", "fun", "xp_earned", 150),
    "shop": q("Buy something in the shop", "fun", "shop", 1),
}

WEEKLY: dict[str, dict[str, object]] = {
    "w_win10": q("Win 10 games", "skill", "wins", 10),
    "w_games20": q("Finish 20 games with other players", "games", "fair_games", 20),
    "w_diff6": q("Play 6 different games", "games", "distinct_games", 6),
    "w_people8": q("Play with 8 different people", "social", "people", 8),
    "w_new4": q("Play with 4 people you've never played with", "social", "new_people", 4),
    "w_battles3": q("Win 3 battles", "skill", "battle_wins", 3),
    "w_ranked5": q("Play 5 ranked games", "skill", "ranked", 5),
    "w_club10": q("Finish 10 games in club rooms", "club", "activity", 10, "club_game"),
    "w_cats4": q("Play a game from 4 different categories", "games", "categories", 4),
}

SEASON: dict[str, dict[str, object]] = {
    "s_ranked20": q("Play 20 ranked games", "skill", "ranked", 20),
    "s_ranked_wins8": q("Win 8 ranked games", "skill", "ranked_wins", 8),
    "s_battles10": q("Play 10 battles", "skill", "battles", 10),
    "s_battle_wins5": q("Win 5 battles", "skill", "battle_wins", 5),
    "s_people20": q("Play with 20 different people", "social", "people", 20),
}


def xp_for(level: int) -> int:
    """Total XP needed to reach a level (level 1 at 0, then 100, 300, 600...)."""
    return 50 * (level - 1) * level


def level_of(xp: int) -> int:
    level = max(1, int((1 + math.sqrt(1 + 8 * max(xp, 0) / 50)) / 2))
    while xp_for(level + 1) <= xp:  # guard the float maths at the edges
        level += 1
    while level > 1 and xp_for(level) > xp:
        level -= 1
    return level


# What a level-up gives besides coins: one of each game's power-ups (coins.GAME_POWER_PRICES).
LEVEL_GIFTS = (
    "trivia_fifty",
    "trivia_time",
    "drawguess_letter",
    "dice_peek",
    "chicken_shield",
    "imposter_revote",
    "four_undo",
    "rather_room",
    "ships_sonar",
    "hangman_vowel",
    "tod_fresh",
    "wordrace_letter",
    "codes_peek",
    "lastcard_peek",
    "snakes_repel",
    "fivedice_roll",
)


def _seed(*parts: object) -> int:
    return int(hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest(), 16)


def level_gift(user_id: int, level: int) -> str:
    """The power-up a level-up gives this account (the same if it's ever worked out twice)."""
    return LEVEL_GIFTS[_seed("gift", user_id, level) % len(LEVEL_GIFTS)]


# -- unlocks: what levels (and Plus) open up. Cosmetic only, never an advantage in ranked or battles. --
# id -> (name, level needed); level 0 = Plus members only.
FRAMES: dict[str, tuple[str, int]] = {
    "none": ("No frame", 1),
    "bronze": ("Bronze", 3),
    "silver": ("Silver", 6),
    "gold": ("Gold", 10),
    "neon": ("Neon", 15),
    "rainbow": ("Rainbow", 20),
    "starlight": ("Starlight", 30),
    "plus": ("Plus spotlight", 0),
}
WINS: dict[str, tuple[str, int]] = {  # the victory animation the room sees when you win
    "confetti": ("Confetti", 1),
    "fireworks": ("Fireworks", 5),
    "spotlight": ("Spotlight", 8),
    "disco": ("Disco ball", 12),
    "rocket": ("Rocket", 18),
    "crown": ("Crown rain", 25),
}
DEFAULT_LOOK = {"frame": "none", "win": "confetti"}
SLOT_LEVEL = 10  # a second power-up slot from this level
MAX_SLOTS = 2


def power_slots(level: int, plus: bool) -> int:
    """How many power-ups an account can use in one casual game."""
    return MAX_SLOTS if plus or level >= SLOT_LEVEL else 1


def unlocked(need: int, level: int, plus: bool) -> bool:
    return plus if need == 0 else level >= need


def clean_look(raw: object, level: int, plus: bool) -> dict[str, str]:
    """The look an account shows: its saved pick where still unlocked (Plus can lapse), else the default."""
    saved = raw if isinstance(raw, dict) else {}
    look = dict(DEFAULT_LOOK)
    for key, table in (("frame", FRAMES), ("win", WINS)):
        pick = saved.get(key)
        if isinstance(pick, str) and pick in table and unlocked(table[pick][1], level, plus):
            look[key] = pick
    return look


def look_options(level: int, plus: bool) -> dict[str, list[dict[str, object]]]:
    def rows(table: dict[str, tuple[str, int]]) -> list[dict[str, object]]:
        return [
            {"id": k, "name": name, "level": need, "plus": need == 0, "unlocked": unlocked(need, level, plus)}
            for k, (name, need) in table.items()
        ]

    return {"frames": rows(FRAMES), "wins": rows(WINS)}


def day_number(day: date) -> int:
    return (day - EPOCH).days


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _order(user_id: int, kind: str) -> list[str]:
    """This account's own shuffled walk through one kind's quests."""
    ids = sorted(k for k, v in QUESTS.items() if v["kind"] == kind)
    random.Random(_seed("order", user_id, kind)).shuffle(ids)  # noqa: S311 - a shuffle, not a secret
    return ids


def daily_quests(user_id: int, day: date) -> list[str]:
    """Today's three quests: one social, then two of two other kinds, each the next step of its kind's
    walk (so nothing repeats within a week)."""
    n = day_number(day)
    others = [k for k in KINDS if k != "social"]
    pairs = [(a, b) for i, a in enumerate(others) for b in others[i + 1 :]]
    random.Random(_seed("pairs", user_id)).shuffle(pairs)  # noqa: S311 - a shuffle, not a secret
    kinds = ("social", *pairs[n % len(pairs)])
    out = []
    for kind in kinds:
        walk = _order(user_id, kind)
        out.append(walk[n % len(walk)])
    return out


def reroll_for(user_id: int, day: date, quest: str) -> str:
    """The quest a reroll swaps in: another of the same kind, never one of today's."""
    kind = str(QUESTS[quest]["kind"])
    walk = _order(user_id, kind)
    today = set(daily_quests(user_id, day))
    start = walk.index(quest) + len(walk) // 2
    for i in range(len(walk)):
        pick = walk[(start + i) % len(walk)]
        if pick not in today:
            return pick
    return quest


def weekly_challenges(user_id: int, day: date) -> list[str]:
    """This week's three challenges (the same all week)."""
    week = day_number(week_start(day)) // 7
    ids = sorted(WEEKLY)
    random.Random(_seed("weekly", user_id)).shuffle(ids)  # noqa: S311 - a shuffle, not a secret
    return [ids[(week * 3 + i) % len(ids)] for i in range(3)]


# Club challenges: (title with {n} for the target, measure, target per member, smallest, largest).
CLUB: dict[str, tuple[str, str, float, int, int]] = {
    "c_games": ("Members play {n} games in club rooms", "club_games", 4, 15, 60),
    "c_members": ("{n} different members play a club game", "club_members", 0.6, 2, 12),
    "c_hosts": ("{n} different members host a club game", "club_hosts", 0.3, 2, 5),
    "c_battles": ("Play {n} battles in the club", "club_battles", 0.5, 2, 10),
}


def club_challenge(club_id: int, day: date) -> str:
    """This week's challenge for a club: each club walks its own order, one a week."""
    week = day_number(week_start(day)) // 7
    ids = sorted(CLUB)
    random.Random(_seed("club", club_id)).shuffle(ids)  # noqa: S311 - a shuffle, not a secret
    return ids[week % len(ids)]


def club_target(challenge: str, members: int) -> int:
    _, measure, per, low, high = CLUB[challenge]
    target = max(low, min(high, round(per * members)))
    # counting people: never more than the club has
    return min(target, max(members, 1)) if measure in ("club_members", "club_hosts") else target
