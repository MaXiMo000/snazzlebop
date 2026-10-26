import { request, saveSession } from "./api";
import type { BattleRecord, RoomPass } from "./contract";

export type { BattleRecord } from "./contract";

// The same rules the server applies (backend app/battles.py), for the forms and the copy.
export const DUEL_GAMES = ["four", "chess", "ships", "trivia"] as const;
export const DUEL_PRIZE = 40;
export const GROUP_PRIZE = 60;
export const FINISH_PRIZE = 10;

type Format = BattleRecord["format"];
/** Is a battle of this kind and game in the week's featured format? */
export const isFeatured = (f: Format | null, kind: string, game: string) =>
  !!f && f.kinds.includes(kind) && (!f.games.length || f.games.includes(game));
/** The winner's prize for a kind of battle, with the featured bonus when it applies. */
export const winPrize = (kind: string, featured: boolean, bonus = 1.5) =>
  Math.floor((kind === "duel" ? DUEL_PRIZE : GROUP_PRIZE) * (featured ? bonus : 1));

/** Challenge a member to a duel, or open a group battle; takes the host's seat. Returns the room code. */
export async function startBattle(
  slug: string,
  body: { name: string; kind: "duel" | "group"; game: string; opponent?: string },
): Promise<string> {
  const r = await request<RoomPass>(`/api/clubs/${encodeURIComponent(slug)}/battles`, { method: "POST", body: JSON.stringify(body) });
  saveSession(r.code, { token: r.token, playerId: r.player_id });
  return r.code;
}

export const myBattles = () => request<BattleRecord>("/api/me/battles");
