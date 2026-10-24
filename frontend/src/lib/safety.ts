import { request } from "./api";
import type { BlockList, ClubReports, Ok, SiteInfo, StaffQueue } from "./contract";

export type { BlockList, ClubReports, StaffQueue } from "./contract";

const post = <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
const club = (slug: string) => `/api/clubs/${encodeURIComponent(slug)}`;
const room = (code: string) => `/api/rooms/${encodeURIComponent(code)}`;

/** The reasons a report can give (the server checks the same list). */
export const REASONS: [string, string][] = [
  ["harassment", "Harassment or bullying"],
  ["hate", "Hate or slurs"],
  ["cheating", "Cheating or griefing"],
  ["spam", "Spam"],
  ["sexual", "Sexual content"],
  ["other", "Something else"],
];

export const blocked = () => request<BlockList>("/api/blocks");
export const block = (username: string) => post<Ok>("/api/blocks", { username });
export const unblock = (username: string) => post<Ok>("/api/blocks/remove", { username });
export const report = (username: string, reason: string, note: string, clubSlug?: string) =>
  post<Ok>("/api/reports", { username, reason, note, ...(clubSlug ? { club: clubSlug } : {}) });
export const reportSeat = (code: string, playerId: string, reason: string, note: string, alsoBlock: boolean) =>
  post<Ok>(`${room(code)}/report`, { player_id: playerId, reason, note, block: alsoBlock });
export const blockSeat = (code: string, playerId: string) => post<Ok>(`${room(code)}/block`, { player_id: playerId });

export const clubReports = (slug: string) => request<ClubReports>(`${club(slug)}/reports`);
export const actOnReport = (slug: string, id: number, action: string, hours?: number) =>
  post<Ok>(`${club(slug)}/reports/${id}`, { action, ...(hours ? { hours } : {}) });
export const unmute = (slug: string, username: string) => post<Ok>(`${club(slug)}/unmute`, { username });

export const siteInfo = () => request<SiteInfo>("/api/site");
export const EXPORT_URL = "/api/me/export";

// -- the platform staff console
export const staffQueue = () => request<StaffQueue>("/api/staff/reports");
export const staffAct = (id: number, action: string, days?: number, reason?: string) =>
  post<Ok>(`/api/staff/reports/${id}`, { action, ...(days !== undefined ? { days } : {}), ...(reason ? { reason } : {}) });
export const liftSuspension = (username: string) => post<Ok>("/api/staff/unsuspend", { username });
