import { request } from "./api";
import type { Progress } from "./contract";

export type { Progress } from "./contract";

export const myProgress = () => request<Progress>("/api/me/progress");
/** Claim a finished quest: XP and coins, once. Returns your progress after. */
export const claimQuest = (id: string) => request<Progress>(`/api/me/quests/${encodeURIComponent(id)}/claim`, { method: "POST" });
