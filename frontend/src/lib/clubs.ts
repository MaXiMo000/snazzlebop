import { request, saveSession } from "./api";
import type { ClubDetail, ClubList, ClubRules, NewInvite, Ok, RoomPass } from "./contract";

export type { ClubDetail, ClubRules, ClubSummary, NewInvite } from "./contract";

export const ROLE_NAMES: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  moderator: "Moderator",
  member: "Member",
};
const RANK: Record<string, number> = { owner: 4, admin: 3, moderator: 2, member: 1 };

/** The same checks the server makes (app/clubs/policy.py), so buttons only show when they'd work. */
export const mayEdit = (role: string) => (RANK[role] ?? 0) >= RANK.admin!;
export const mayInvite = (role: string) => (RANK[role] ?? 0) >= RANK.moderator!;
export const mayRemove = (actor: string, target: string) =>
  mayInvite(actor) && (RANK[actor] ?? 0) > (RANK[target] ?? 0);
/** Roles you can hand someone: below your own (and theirs must be below yours too). */
export const rolesYouCanGive = (actor: string, target: string): string[] =>
  mayEdit(actor) && (RANK[actor] ?? 0) > (RANK[target] ?? 0)
    ? ["admin", "moderator", "member"].filter((r) => RANK[r]! < RANK[actor]!)
    : [];

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
const at = (slug: string) => `/api/clubs/${encodeURIComponent(slug)}`;
const who = (name: string) => encodeURIComponent(name);

export const myClubs = () => request<ClubList>("/api/clubs");
export const club = (slug: string) => request<ClubDetail>(at(slug));
export const createClub = (name: string, about: string) => post<ClubDetail>("/api/clubs", { name, about });
export const saveClub = (slug: string, body: { name?: string; about?: string; rules?: Partial<ClubRules> }) =>
  post<ClubDetail>(`${at(slug)}/settings`, body);
export const newInvite = (slug: string, days: number, uses: number) =>
  post<NewInvite>(`${at(slug)}/invites`, { days, uses });
export const revokeInvite = (slug: string, id: number) => post<Ok>(`${at(slug)}/invites/${id}/revoke`);
export const joinClub = (code: string) => post<ClubDetail>("/api/clubs/join", { code });
export const setRole = (slug: string, username: string, role: string) =>
  post<Ok>(`${at(slug)}/members/${who(username)}`, { role });
export const removeMember = (slug: string, username: string, ban: boolean) =>
  post<Ok>(`${at(slug)}/members/${who(username)}/remove`, { ban });
export const handOver = (slug: string, username: string) => post<Ok>(`${at(slug)}/transfer`, { username });
export const leaveClub = (slug: string) => post<Ok>(`${at(slug)}/leave`);
export const closeClub = (slug: string) => post<Ok>(`${at(slug)}/delete`);

/** Open a room for the club and take the host's seat in this tab. Returns the room code. */
export async function clubRoom(slug: string, name: string): Promise<string> {
  const r = await post<RoomPass>(`${at(slug)}/rooms`, { name });
  saveSession(r.code, { token: r.token, playerId: r.player_id });
  return r.code;
}

// -- up for a game
export const upForGame = (slug: string, game: string | null, minutes: number) =>
  post<ClubDetail>(`${at(slug)}/up`, { game, minutes });
export const notUp = (slug: string) => post<ClubDetail>(`${at(slug)}/up/cancel`);
export const muteClub = (slug: string, muted: boolean) => post<Ok>(`${at(slug)}/mute`, { muted });

/** Tap through to the match: the first one in opens the room (and hosts it). Returns the room code. */
export async function goToMatch(slug: string, name: string): Promise<string> {
  const r = await post<RoomPass>(`${at(slug)}/up/go`, { name });
  saveSession(r.code, { token: r.token, playerId: r.player_id });
  return r.code;
}

export const STATUS_TEXT: Record<string, string> = {
  up: "Up for a game",
  online: "Online",
  in_game: "In a room",
  offline: "Offline",
};
