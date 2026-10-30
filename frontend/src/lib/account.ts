import { useSyncExternalStore } from "react";
import { request } from "./api";
import type { Account, BackupCodes, Board, CoinHistory, Identities, Me, MfaSetup, MfaStatus, NewAccount, Ok, SessionList, Shop, Stats, UserBody } from "./contract";

// The signed-in account (the session itself is an HttpOnly cookie: this page never sees it).
export type { Account, Board, MfaSetup, MfaStatus, ShopItem, Stats } from "./contract";

// -- a tiny shared store: the top bar, the account page and the in-game panel all see the same coins
interface AccountState {
  user: Account | null;
  loaded: boolean;
  /** accounts work (the database is up) */
  available: boolean;
  /** the server can send email: sign-in by email, reset links, notices */
  mail: boolean;
  /** sign in with Google is set up on this site */
  google: boolean;
  /** platform staff (the console also needs the authenticator app) */
  staff: boolean;
  /** the last check couldn't reach the server */
  offline: boolean;
}
let state: AccountState = { user: null, loaded: false, available: true, mail: false, google: false, staff: false, offline: false };
let fetching = false;
const listeners = new Set<() => void>();

function set(next: Partial<AccountState>) {
  state = { ...state, loaded: true, ...next };
  listeners.forEach((fn) => fn());
}

export async function refreshAccount(): Promise<Account | null> {
  try {
    const r = await request<Me>("/api/me");
    set({ user: r.user, available: r.accounts, mail: r.mail, google: r.google, staff: r.staff, offline: false });
  } catch {
    // keep whoever was signed in; with no answer yet, pages keep loading instead of showing "signed out"
    set({ offline: true, loaded: state.loaded && !state.offline });
  }
  return state.user;
}

if (typeof window !== "undefined") window.addEventListener("online", () => void refreshAccount());

// Stable, so React subscribes once per component. The first screen fetches the account; after a failed
// check nothing retries on its own (that would loop): "Try again" or the device coming back online does.
function subscribe(fn: () => void) {
  listeners.add(fn);
  if (!state.loaded && !state.offline && !fetching) {
    fetching = true;
    void refreshAccount().finally(() => (fetching = false));
  }
  return () => void listeners.delete(fn);
}

export function useAccount(): AccountState {
  return useSyncExternalStore(subscribe, () => state);
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export async function signUp(username: string, password: string, email?: string): Promise<string> {
  const r = await post<NewAccount>("/api/auth/signup", { username, password, ...(email ? { email } : {}) });
  set({ user: r.user });
  return r.recovery_code;
}

/** `code`: from the authenticator app (or a backup code), once the server has asked for it. */
export async function logIn(username: string, password: string, code?: string): Promise<void> {
  const r = await post<UserBody>("/api/auth/login", { username, password, ...(code ? { code } : {}) });
  set({ user: r.user });
}

export async function recover(username: string, recoveryCode: string, newPassword: string, code?: string): Promise<string> {
  const r = await post<NewAccount>("/api/auth/recover", {
    username,
    recovery_code: recoveryCode,
    new_password: newPassword,
    ...(code ? { code } : {}),
  });
  set({ user: r.user });
  return r.recovery_code;
}

/** Email a reset link to the account's confirmed address (the same answer whether or not it exists). */
export const forgotPassword = (login: string) => post<Ok>("/api/auth/forgot", { login });

/** Email a one-time sign-in link to a confirmed address (the same answer whether or not it exists). */
export const emailSignInLink = (email: string) => post<Ok>("/api/auth/email-link", { email });

export async function signInWithLink(token: string, code?: string): Promise<void> {
  const r = await post<UserBody>("/api/auth/email-link/use", { token, ...(code ? { code } : {}) });
  set({ user: r.user });
}

export async function resetPassword(token: string, newPassword: string, code?: string): Promise<void> {
  const r = await post<UserBody>("/api/auth/reset", { token, new_password: newPassword, ...(code ? { code } : {}) });
  set({ user: r.user });
}

export async function verifyEmail(token: string): Promise<void> {
  await post<Ok>("/api/auth/verify", { token });
  if (state.user) await refreshAccount();
}

export async function setEmail(email: string, password: string): Promise<void> {
  const r = await post<UserBody>("/api/me/email", { email, password });
  set({ user: r.user });
}

export const resendEmail = () => post<Ok>("/api/me/email/resend");

export async function removeEmail(password: string): Promise<void> {
  const r = await post<UserBody>("/api/me/email/remove", { password });
  set({ user: r.user });
}

/** Google sign-in is a full-page trip (the browser goes to Google and back), so these are links. */
export const GOOGLE_SIGN_IN = "/api/auth/google/start";
export const GOOGLE_LINK = "/api/auth/google/start?mode=link";
export const myIdentities = () => request<Identities>("/api/me/identities");
export const unlinkGoogle = (password: string) => post<Ok>("/api/me/google/remove", { password });

export const signOutOthers = () => post<Ok>("/api/me/sessions/revoke");
export const mySessions = () => request<SessionList>("/api/me/sessions");
export const signOutSession = (id: string) => post<Ok>(`/api/me/sessions/${encodeURIComponent(id)}/revoke`);

export async function logOut(): Promise<void> {
  await post<Ok>("/api/auth/logout");
  set({ user: null });
}

export async function changePassword(password: string, newPassword: string): Promise<void> {
  await post<Ok>("/api/me/password", { password, new_password: newPassword });
  await refreshAccount(); // an account that had no password now has one
}

export async function deleteAccount(password: string, code?: string): Promise<void> {
  await post<Ok>("/api/me/delete", { password, ...(code ? { code } : {}) });
  set({ user: null });
}

export const myStats = () => request<Stats>("/api/me/stats");
/** Your balance, today's earnings toward the daily limit, and the ledger (newest first). */
export const myCoins = () => request<CoinHistory>("/api/me/coins");
export const leaderboard = () => request<Board>("/api/leaderboard");
export const shopItems = () => request<Shop>("/api/shop");

export async function buy(item: string): Promise<void> {
  const r = await post<UserBody>("/api/shop/buy", { item });
  set({ user: r.user });
}

// -- authenticator-app sign-in
export const mfaStatus = () => request<MfaStatus>("/api/me/mfa");
export const mfaSetup = (password: string) => post<MfaSetup>("/api/me/mfa/setup", { password });
export const mfaEnable = (code: string) => post<BackupCodes>("/api/me/mfa/enable", { code }).then((r) => r.codes);
export const mfaDisable = (password: string, code: string) => post<Ok>("/api/me/mfa/disable", { password, code });
export const mfaNewCodes = (code: string) => post<BackupCodes>("/api/me/mfa/backup-codes", { code }).then((r) => r.codes);
