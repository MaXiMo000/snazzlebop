import { useSyncExternalStore } from "react";
import { request } from "./api";
import type { Inbox, NotifyPrefs, Ok } from "./contract";

export type { Inbox, InboxItem, NotifyPrefs } from "./contract";

// -- the inbox: polled while the app is open (which is also what makes you "online" to friends) -------
interface InboxState {
  inbox: Inbox | null;
}
let state: InboxState = { inbox: null };
const listeners = new Set<() => void>();
let timer: number | undefined;
let running = 0;

const tz = () => -new Date().getTimezoneOffset(); // minutes east of UTC

export async function refreshInbox(): Promise<void> {
  try {
    const inbox = await request<Inbox>(`/api/notifications?tz=${tz()}`);
    state = { inbox };
  } catch {
    state = { inbox: null }; // signed out, or offline: no bell
  }
  listeners.forEach((fn) => fn());
}

/** Poll every minute while the page is visible, and at once when it comes back into view. */
function start() {
  running += 1;
  if (running > 1) return;
  void refreshInbox();
  timer = window.setInterval(() => document.visibilityState === "visible" && void refreshInbox(), 60000);
  document.addEventListener("visibilitychange", onVisible);
}
function stop() {
  running -= 1;
  if (running > 0) return;
  window.clearInterval(timer);
  document.removeEventListener("visibilitychange", onVisible);
}
function onVisible() {
  if (document.visibilityState === "visible") void refreshInbox();
}

// Stable functions: React subscribes again whenever `subscribe` changes, and every new subscription
// polls at once, so an inline function here would fetch on every render.
function watchAndPoll(fn: () => void) {
  listeners.add(fn);
  start();
  return () => {
    listeners.delete(fn);
    stop();
  };
}
function watchOnly(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
const snapshot = () => state.inbox;
const nothing = () => null;

/** The inbox for a signed-in person (null when signed out). Mounting it starts the poll. */
export function useInbox(enabled: boolean): Inbox | null {
  return useSyncExternalStore(enabled ? watchAndPoll : watchOnly, enabled ? snapshot : nothing);
}

export async function markRead(ids?: number[]): Promise<void> {
  await request<Ok>("/api/notifications/read", { method: "POST", body: JSON.stringify(ids ? { ids } : {}) });
  await refreshInbox();
}

// -- settings ---------------------------------------------------------------------------------------
export const notifyPrefs = () => request<NotifyPrefs>("/api/me/notify");
export const saveNotifyPrefs = (body: {
  hidden?: boolean;
  types?: Record<string, boolean>;
  quiet?: { from: string; to: string };
  clear_quiet?: boolean;
}) => request<NotifyPrefs>("/api/me/notify", { method: "POST", body: JSON.stringify({ ...body, tz: tz() }) });

// -- push on this device ----------------------------------------------------------------------------
export type PushState = "unsupported" | "blocked" | "off" | "on";

export function pushSupported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function registration(): Promise<ServiceWorkerRegistration> {
  return (await navigator.serviceWorker.getRegistration("/")) ?? navigator.serviceWorker.register("/sw.js", { scope: "/" });
}

export async function pushState(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "blocked";
  const reg = await navigator.serviceWorker.getRegistration("/");
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  return sub && Notification.permission === "granted" ? "on" : "off";
}

function keyBytes(b64url: string): Uint8Array<ArrayBuffer> {
  const raw = atob(b64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (b64url.length % 4)) % 4));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

const b64url = (buf: ArrayBuffer | null) =>
  buf ? btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "") : "";

/** Ask the browser for permission and subscribe this device. Returns the new state. */
export async function enablePush(serverKey: string): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "blocked" : "off";
  const reg = await registration();
  await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(serverKey) }));
  await request<Ok>("/api/push/subscribe", {
    method: "POST",
    body: JSON.stringify({ endpoint: sub.endpoint, p256dh: b64url(sub.getKey("p256dh")), auth: b64url(sub.getKey("auth")) }),
  });
  return "on";
}

export async function disablePush(): Promise<PushState> {
  const reg = await navigator.serviceWorker.getRegistration("/");
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  if (sub) {
    await request<Ok>("/api/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) }).catch(() => undefined);
    await sub.unsubscribe();
  }
  return "off";
}
