import { request, saveSession } from "./api";
import type { BattleRecord, RoomPass } from "./contract";

export type { BattleRecord } from "./contract";

// The same rules the server applies (backend app/battles.py), for the forms and the copy.
export const DUEL_GAMES = ["four", "chess", "ships", "trivia"] as const;
export const DUEL_PRIZE = 40;
export const GROUP_PRIZE = 60;
export const FINISH_PRIZE = 10;

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
