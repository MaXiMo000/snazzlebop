import { useSyncExternalStore } from "react";
import { request } from "./api";

/** The signed-in account (the session itself is an HttpOnly cookie: this page never sees it). */
export interface Account {
  username: string;
  coins: number;
  powerups: Record<string, number>;
}

export interface ShopItem {
  id: string;
  name: string;
  icon: string;
  text: string;
  price: number;
}

export interface Stats {
  games: Record<string, { played: number; wins: number; best: number; coins: number }>;
  totals: { played: number; wins: number; coins: number };
  season: { id: string; played: number; wins: number; points: number; rank: number | null };
}

export interface Board {
  season: string;
  rows: { username: string; points: number; wins: number; played: number }[];
}

// -- a tiny shared store: the top bar, the account page and the in-game panel all see the same coins
interface AccountState {
  user: Account | null;
  loaded: boolean;
  /** accounts work (the database is up) */
  available: boolean;
}
let state: AccountState = { user: null, loaded: false, available: true };
let fetching = false;
const listeners = new Set<() => void>();

function set(next: Partial<AccountState>) {
  state = { ...state, loaded: true, ...next };
  listeners.forEach((fn) => fn());
}

export async function refreshAccount(): Promise<Account | null> {
  try {
    const r = await request<{ user: Account | null; accounts: boolean }>("/api/me");
    set({ user: r.user, available: r.accounts });
  } catch {
    set({});
  }
  return state.user;
}

export function useAccount(): AccountState {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      if (!state.loaded && !fetching) {
        fetching = true;
        void refreshAccount().finally(() => (fetching = false));
      }
      return () => listeners.delete(fn);
    },
    () => state,
  );
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export async function signUp(username: string, password: string): Promise<string> {
  const r = await post<{ user: Account; recovery_code: string }>("/api/auth/signup", { username, password });
  set({ user: r.user });
  return r.recovery_code;
}

export async function logIn(username: string, password: string): Promise<void> {
  const r = await post<{ user: Account }>("/api/auth/login", { username, password });
  set({ user: r.user });
}

export async function recover(username: string, recoveryCode: string, newPassword: string): Promise<string> {
  const r = await post<{ user: Account; recovery_code: string }>("/api/auth/recover", {
    username,
    recovery_code: recoveryCode,
    new_password: newPassword,
  });
  set({ user: r.user });
  return r.recovery_code;
}

export async function logOut(): Promise<void> {
  await post("/api/auth/logout");
  set({ user: null });
}

export async function changePassword(password: string, newPassword: string): Promise<void> {
  await post("/api/me/password", { password, new_password: newPassword });
}

export async function deleteAccount(password: string): Promise<void> {
  await post("/api/me/delete", { password });
  set({ user: null });
}

export const myStats = () => request<Stats>("/api/me/stats");
export const leaderboard = () => request<Board>("/api/leaderboard");
export const shopItems = () => request<{ items: ShopItem[] }>("/api/shop");

export async function buy(item: string): Promise<void> {
  const r = await post<{ user: Account }>("/api/shop/buy", { item });
  set({ user: r.user });
}
