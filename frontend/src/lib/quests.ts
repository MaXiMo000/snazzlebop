import { request } from "./api";
import type { Progress } from "./contract";

export type { Progress } from "./contract";

export const myProgress = () => request<Progress>("/api/me/progress");
/** Claim a finished quest: XP and coins, once. Returns your progress after. */
export const claimQuest = (id: string) => request<Progress>(`/api/me/quests/${encodeURIComponent(id)}/claim`, { method: "POST" });
/** Swap one of today's quests for another of its kind (once a day). */
export const rerollQuest = (id: string) => request<Progress>(`/api/me/quests/${encodeURIComponent(id)}/reroll`, { method: "POST" });
/** Claim a finished challenge of this ratings season. */
export const claimSeason = (id: string) => request<Progress>(`/api/me/season/${encodeURIComponent(id)}/claim`, { method: "POST" });
/** Claim a finished weekly challenge. */
export const claimWeekly = (id: string) => request<Progress>(`/api/me/weekly/${encodeURIComponent(id)}/claim`, { method: "POST" });
