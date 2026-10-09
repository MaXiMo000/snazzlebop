import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { sfx } from "../lib/sfx";
import type { ChatMessage, ChatState } from "../types";

type Send = (msg: Record<string, unknown>) => void;
const MAX = 200;

// The room publishes its chat here; the top bar's button and the panel read it.
let snap = { available: false, unread: 0, open: false, teamUnread: false };
const subs = new Set<() => void>();
const set = (next: Partial<typeof snap>) => {
  const merged = { ...snap, ...next };
  if ((Object.keys(merged) as (keyof typeof snap)[]).every((k) => merged[k] === snap[k])) return; // no change, no re-render
  snap = merged;
  for (const fn of subs) fn();
};
const useChatStore = () =>
  useSyncExternalStore(
    (fn) => {
      subs.add(fn);
      return () => void subs.delete(fn);
    },
    () => snap,
  );

/** Top-bar button (only inside a room): opens the chat, with a count of unread messages. */
export function ChatButton() {
  const s = useChatStore();
  if (!s.available) return null;
  const label = s.unread ? `Chat, ${s.unread} unread` : "Chat";
  return (
    <button
      type="button"
      className={`btn ghost chat-button ${s.unread ? "has-unread" : ""}`}
      aria-label={label}
      aria-expanded={s.open}
      onClick={() => set({ open: !s.open })}
    >
      <span aria-hidden="true">💬</span>
      <span className="btn-label">Chat</span>
      {s.unread > 0 && (
        <span className="chat-badge" aria-hidden="true">
          {s.unread > 9 ? "9+" : s.unread}
        </span>
      )}
    </button>
  );
}

/**
 * The room's chat: "Everyone" (players, audience; the TV shows it too) and, when there are teams, a
 * private team channel. Lives in a panel opened from the top bar; new messages pop up briefly at the top
 * of the screen while it's closed.
 */
export function ChatDock({ chat, you, send }: { chat: ChatState; you: string; send: Send }) {
  const s = useChatStore();
  const [tab, setTab] = useState<"all" | "team">("all");
  const [text, setText] = useState("");
  const [seen, setSeen] = useState<{ all: number; team: number }>(() => ({
    all: Math.max(0, ...chat.messages.filter((m) => !m.team).map((m) => m.id)),
    team: Math.max(0, ...chat.messages.filter((m) => m.team).map((m) => m.id)),
  }));
  const [popup, setPopup] = useState<ChatMessage | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const channel = tab === "team" && chat.team ? "team" : "all";
  const shown = useMemo(() => chat.messages.filter((m) => m.team === (channel === "team")), [chat.messages, channel]);
  const newest = (team: boolean) => Math.max(0, ...chat.messages.filter((m) => m.team === team).map((m) => m.id));
  const unread = (team: boolean) =>
    chat.messages.filter((m) => m.team === team && m.by !== you && m.id > (team ? seen.team : seen.all)).length;

  // Publish the button's state; leaving the room hides it.
  useEffect(() => {
    set({ available: true, unread: unread(false) + unread(true), teamUnread: unread(true) > 0 });
  });
  useEffect(() => () => set({ available: false, unread: 0, open: false }), []);
  useEffect(() => {
    if (!chat.team && tab === "team") setTab("all");
  }, [chat.team, tab]);

  // While open, what's on screen counts as read; keep the list scrolled to the newest message.
  useEffect(() => {
    if (!s.open) return;
    setSeen((old) => ({ ...old, [channel]: newest(channel === "team") }));
    const el = list.current;
    if (el) el.scrollTop = el.scrollHeight;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.open, channel, chat.messages.length]);

  // A new message from someone else while the panel is closed: a short pop-up at the top.
  const last = chat.messages[chat.messages.length - 1];
  const lastId = useRef(last?.id ?? 0);
  useEffect(() => {
    if (!last || last.id <= lastId.current) return;
    lastId.current = last.id;
    if (last.by === you || s.open) return;
    setPopup(last);
    sfx.pop();
    const t = window.setTimeout(() => setPopup(null), 4000);
    return () => window.clearTimeout(t);
  }, [last, you, s.open]);

  useEffect(() => {
    if (!s.open) return;
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && set({ open: false });
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [s.open]);

  const submit = () => {
    const t = text.trim();
    if (!t) return;
    send({ t: "chat", text: t, to: channel });
    setText("");
  };

  return (
    <>
      {popup && !s.open && (
        <button type="button" className="chat-popup" onClick={() => set({ open: true })}>
          <b>{popup.team ? `${popup.name} (team)` : popup.name}:</b> {popup.text}
        </button>
      )}
      {s.open && (
        <section className="chat-panel" aria-label="Chat">
          <header className="chat-head">
            <div className="chat-tabs" role="group" aria-label="Chat channel">
              <button type="button" className="chat-tab" aria-pressed={channel === "all"} onClick={() => setTab("all")}>
                Everyone
                {unread(false) > 0 && channel !== "all" && <span className="chat-dot" aria-label="unread" />}
              </button>
              {chat.team && (
                <button
                  type="button"
                  className="chat-tab"
                  aria-pressed={channel === "team"}
                  onClick={() => setTab("team")}
                >
                  <span aria-hidden="true">{chat.team.replace(/^Team /, "")}</span>
                  <span className="sr-only">{chat.team}</span>
                  {unread(true) > 0 && channel !== "team" && <span className="chat-dot" aria-label="unread" />}
                </button>
              )}
            </div>
            <button type="button" className="chat-close" aria-label="Close chat" onClick={() => set({ open: false })}>
              ✕
            </button>
          </header>
          <div className="chat-log" ref={list} role="log" aria-live="polite">
            <ol className="chat-list">
              {shown.length === 0 ? (
                <li className="chat-empty muted">
                  {channel === "team" ? "Only your team sees this channel." : "Say hi! Everyone in the room sees this."}
                </li>
              ) : (
                shown.map((m) => (
                  <li key={m.id} className={m.by === you ? "mine" : ""}>
                    {m.by !== you && <b className="chat-name">{m.name}</b>}
                    <span className="chat-text">{m.text}</span>
                  </li>
                ))
              )}
            </ol>
          </div>
          {!chat.can_send ? (
            <p className="chat-note muted">The TV only watches.</p>
          ) : chat.muted ? (
            <p className="chat-note muted">Spymasters stay silent until the game is over.</p>
          ) : (
            <form
              className="chat-form"
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
            >
              <label className="sr-only" htmlFor="chat-input">
                {channel === "team" ? `Message ${chat.team}` : "Message everyone"}
              </label>
              <input
                id="chat-input"
                ref={input}
                type="text"
                autoComplete="off"
                enterKeyHint="send"
                maxLength={MAX}
                placeholder={channel === "team" ? "To your team…" : "To everyone…"}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <button type="submit" className="btn go" disabled={!text.trim()}>
                Send
              </button>
            </form>
          )}
        </section>
      )}
    </>
  );
}

/** TV: the latest messages from everyone, like live comments, fading after a few seconds. */
export function ChatTicker({ chat }: { chat: ChatState }) {
  const recent = chat.messages.filter((m) => !m.team).slice(-3);
  if (!recent.length) return null;
  return (
    <ol className="chat-ticker" aria-label="Latest chat">
      {recent.map((m) => (
        <li key={m.id}>
          <b>{m.name}:</b> {m.text}
        </li>
      ))}
    </ol>
  );
}
