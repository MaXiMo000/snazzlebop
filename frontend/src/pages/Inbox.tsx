import { useEffect, useId, useState } from "react";
import { Alert, errText } from "../components/auth";
import { Btn, Card } from "../components/ui";
import { useAccount } from "../lib/account";
import {
  disablePush,
  enablePush,
  markRead,
  notifyPrefs,
  pushState,
  refreshInbox,
  saveNotifyPrefs,
  useInbox,
  type InboxItem,
  type NotifyPrefs,
  type PushState,
} from "../lib/notify";

type Go = (path: string) => void;

/** "5 min ago", "3 h ago", "Mon 12 Oct". */
export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

const ICONS: Record<string, string> = { club_up: "🎲", invite: "💌" };

export function InboxPage({ go }: { go: Go }) {
  const { user, loaded } = useAccount();
  const inbox = useInbox(!!user);

  useEffect(() => {
    document.title = inbox?.unread ? `(${inbox.unread}) Inbox · Snazzlebop` : "Inbox · Snazzlebop";
  }, [inbox?.unread]);

  if (!loaded) return <p className="muted center">Loading…</p>;
  if (!user)
    return (
      <Card tone="stage" className="center">
        <p className="sign">Inbox</p>
        <p className="space-top">Sign in to hear when your club gets a game going or a friend invites you.</p>
        <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
          Sign in
        </Btn>
      </Card>
    );

  const open = async (item: InboxItem) => {
    if (!item.read) await markRead([item.id]).catch(() => undefined);
    go(item.link);
  };

  return (
    <div className="stack enter inbox">
      <Card aria-labelledby="inbox-h">
        <div className="inbox-head">
          <h2 id="inbox-h">Inbox</h2>
          {!!inbox?.unread && (
            <Btn size="small" variant="ghost" onClick={() => void markRead()}>
              Mark all read
            </Btn>
          )}
        </div>
        {inbox === null ? (
          <p className="muted">Loading…</p>
        ) : inbox.items.length ? (
          <ul className="inbox-list">
            {inbox.items.map((item) => (
              <li key={item.id}>
                <a
                  className={`inbox-item ${item.read ? "" : "unread"}`}
                  href={item.link}
                  onClick={(e) => {
                    e.preventDefault();
                    void open(item);
                  }}
                >
                  <span className="inbox-icon" aria-hidden="true">
                    {ICONS[item.kind] ?? "🔔"}
                  </span>
                  <span className="inbox-text">
                    <b>{item.title}</b>
                    <span>{item.body}</span>
                    <span className="muted inbox-when">
                      {!item.read && <span className="sr-only">Unread. </span>}
                      {ago(item.at)}
                    </span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <div className="empty-state">
            <span aria-hidden="true">📭</span>
            <p>
              <b>All quiet.</b> When your club gets a game going, or a friend invites you to a room, it lands here.
            </p>
          </div>
        )}
      </Card>
      <NotifySettings serverKey={inbox?.push_key ?? ""} />
    </div>
  );
}

function NotifySettings({ serverKey }: { serverKey: string }) {
  const [prefs, setPrefs] = useState<NotifyPrefs | null>(null);
  const [push, setPush] = useState<PushState | null>(null);
  const [from, setFrom] = useState("23:00");
  const [to, setTo] = useState("08:00");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const id = useId();

  useEffect(() => {
    notifyPrefs().then((p) => {
      setPrefs(p);
      if (p.quiet) {
        setFrom(p.quiet.from);
        setTo(p.quiet.to);
      }
    }, () => undefined);
    pushState().then(setPush, () => setPush("unsupported"));
  }, []);

  const run = async (fn: () => Promise<void>, ok?: string) => {
    setBusy(true);
    setNote(null);
    try {
      await fn();
      if (ok) setNote({ ok: true, text: ok });
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    } finally {
      setBusy(false);
    }
  };
  const save = (body: Parameters<typeof saveNotifyPrefs>[0], ok?: string) => run(async () => setPrefs(await saveNotifyPrefs(body)), ok);

  if (!prefs) return null;
  return (
    <Card aria-labelledby={`${id}-h`}>
      <h3 id={`${id}-h`}>Notifications</h3>

      <div className="notify-push space-top">
        <p className="notify-row-text">
          <b>On this device</b>
          <span className="muted">
            {push === "on"
              ? "Pushes are on here."
              : push === "blocked"
                ? "Notifications are blocked for this site in your browser settings."
                : push === "unsupported"
                  ? "This browser can't get pushes. On iPhone, add Snazzlebop to your home screen first."
                  : "Get a buzz when your club gets a game going, even with the app closed."}
          </span>
        </p>
        {push === "on" ? (
          <Btn size="small" variant="ghost" disabled={busy} onClick={() => void run(async () => setPush(await disablePush()), "Pushes are off on this device.")}>
            Turn off
          </Btn>
        ) : push === "off" ? (
          <Btn
            size="small"
            variant="go"
            disabled={busy || !serverKey}
            onClick={() =>
              void run(async () => {
                const next = await enablePush(serverKey);
                setPush(next);
                setNote(
                  next === "on"
                    ? { ok: true, text: "Pushes are on for this device." }
                    : { ok: false, text: next === "blocked" ? "Your browser blocked notifications for this site." : "Notifications weren't allowed, so pushes stay off." },
                );
                await refreshInbox();
              })
            }
          >
            Turn on
          </Btn>
        ) : null}
      </div>

      <fieldset className="notify-kinds space-top">
        <legend className="field">Tell me when</legend>
        {prefs.kinds.map((k) => (
          <label key={k.id} className="check">
            <input type="checkbox" checked={k.on} disabled={busy} onChange={(e) => void save({ types: { [k.id]: e.target.checked } })} />
            <span>{k.label}</span>
          </label>
        ))}
      </fieldset>

      <fieldset className="notify-quiet space-top">
        <legend className="field">Quiet hours</legend>
        <p className="muted">No pushes in these hours (your club's quiet hours count too). Everything still lands in your inbox.</p>
        <div className="notify-times">
          <div>
            <label className="field" htmlFor={`${id}-from`}>
              From
            </label>
            <input id={`${id}-from`} type="time" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div>
            <label className="field" htmlFor={`${id}-to`}>
              To
            </label>
            <input id={`${id}-to`} type="time" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </div>
        <div className="row space-top">
          <Btn size="small" variant="go" disabled={busy || !from || !to || from === to} onClick={() => void save({ quiet: { from, to } }, `Quiet from ${from} to ${to}.`)}>
            {prefs.quiet ? "Update quiet hours" : "Set quiet hours"}
          </Btn>
          {prefs.quiet && (
            <Btn size="small" variant="ghost" disabled={busy} onClick={() => void save({ clear_quiet: true }, "Quiet hours are off.")}>
              Turn off
            </Btn>
          )}
        </div>
      </fieldset>

      <label className="check space-top">
        <input type="checkbox" checked={prefs.hidden} disabled={busy} onChange={(e) => void save({ hidden: e.target.checked })} />
        <span>
          Appear offline
          <span className="muted acct-hint notify-hint">Friends and clubmates won't see when you're around. Saying you're up for a game still shows.</span>
        </span>
      </label>

      {note && (
        <div className="space-top">
          <Alert text={note.text} calm={note.ok} />
        </div>
      )}
    </Card>
  );
}
