import type { GameCard, Session } from "../types";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError("network", "Can't reach the server. Check your connection.", 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string } }).error;
    throw new ApiError(err?.code ?? "error", err?.message ?? "Something went wrong", res.status);
  }
  return body as T;
}

interface JoinResponse {
  code: string;
  player_id: string;
  token: string;
}

const key = (code: string) => `snazzlebop:${code}`;

export function loadSession(code: string): Session | null {
  try {
    const raw = sessionStorage.getItem(key(code));
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function saveSession(code: string, session: Session): void {
  try {
    sessionStorage.setItem(key(code), JSON.stringify(session));
  } catch {
    /* storage unavailable (private mode): the session just won't survive a reload */
  }
}

export function clearSession(code: string): void {
  try {
    sessionStorage.removeItem(key(code));
  } catch {
    /* ignore */
  }
}

export async function createRoom(name: string): Promise<{ code: string; session: Session }> {
  const r = await request<JoinResponse>("/api/rooms", { method: "POST", body: JSON.stringify({ name }) });
  const session = { token: r.token, playerId: r.player_id };
  saveSession(r.code, session);
  return { code: r.code, session };
}

export async function joinRoom(code: string, name: string): Promise<Session> {
  const r = await request<JoinResponse>(`/api/rooms/${encodeURIComponent(code)}/join`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  const session = { token: r.token, playerId: r.player_id };
  saveSession(r.code, session);
  return session;
}

/** A read-only big-screen seat (TV mode). Stored per tab, like a player seat. */
export async function tvSeat(code: string): Promise<Session> {
  const saved = loadSession(`tv:${code}`);
  if (saved) return saved;
  const r = await request<{ code: string; token: string }>(`/api/rooms/${encodeURIComponent(code)}/tv`, { method: "POST" });
  const session = { token: r.token, playerId: "" };
  saveSession(`tv:${r.code}`, session);
  return session;
}

export const fetchGames = () => request<GameCard[]>("/api/games");
