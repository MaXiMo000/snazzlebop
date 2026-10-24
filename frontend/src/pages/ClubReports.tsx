import { useCallback, useEffect, useState } from "react";
import { Alert, errText } from "../components/auth";
import { Btn, Card } from "../components/ui";
import { useAccount } from "../lib/account";
import { ApiError } from "../lib/api";
import { actOnReport, clubReports, unmute, type ClubReports as Queue } from "../lib/safety";

type Go = (path: string) => void;
type Report = Queue["reports"][number];

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const STATUS: Record<Report["status"], string> = {
  open: "Open",
  dismissed: "Dismissed",
  actioned: "Dealt with",
  escalated: "Sent to staff",
};
const ACTION_TEXT: Record<string, string> = {
  dismiss: "dismissed a report about",
  mute: "muted",
  unmute: "unmuted",
  remove: "removed",
  ban: "banned",
  escalate: "sent to staff a report about",
};

/** /clubs/<slug>/reports: the moderators' queue, who's muted, and the audit log. */
export function ClubReports({ slug, go }: { slug: string; go: Go }) {
  const { user, loaded } = useAccount();
  const [queue, setQueue] = useState<Queue | null>(null);
  const [denied, setDenied] = useState<string | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(
    () =>
      clubReports(slug).then(setQueue, (e) => {
        if (e instanceof ApiError && (e.status === 403 || e.status === 404)) setDenied(e.message);
      }),
    [slug],
  );
  useEffect(() => {
    document.title = "Reports · Snazzlebop";
    if (user) void load();
  }, [user, load]);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setNote(null);
    try {
      await fn();
      setNote({ ok: true, text: ok });
      await load();
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    }
  };

  if (!loaded) return <p className="muted center">Loading…</p>;
  const back = (
    <Btn variant="ghost" onClick={() => go(`/clubs/${slug}`)}>
      Back to the club
    </Btn>
  );
  if (!user || denied)
    return (
      <Card className="center">
        <h2>Moderators only</h2>
        <p className="space-top">{denied ?? "Sign in to see this club's reports."}</p>
        <div className="space-top">{back}</div>
      </Card>
    );
  if (!queue) return <p className="muted center">Loading…</p>;
  const open = queue.reports.filter((r) => r.status === "open");
  const done = queue.reports.filter((r) => r.status !== "open");

  return (
    <div className="stack enter reports-page">
      <Card tone="stage" className="center">
        <p className="sign">Reports</p>
        <p className="space-top">
          {open.length ? `${open.length} waiting for a moderator.` : "Nothing waiting. Nice and calm."}
        </p>
        <div className="space-top">{back}</div>
      </Card>
      {note && <Alert text={note.text} calm={note.ok} />}

      {open.map((r) => (
        <ReportCard key={r.id} r={r} act={(action, hours) => void run(() => actOnReport(slug, r.id, action, hours), "Done. It's in the log below.")} />
      ))}

      {queue.muted.length > 0 && (
        <Card aria-labelledby="muted-h">
          <h3 id="muted-h">Muted now</h3>
          <ul className="club-rooms">
            {queue.muted.map((m) => (
              <li key={m.username}>
                <span className="club-room-text">
                  <b>{m.username}</b>
                  <span className="muted">Until {when(m.until)}</span>
                </span>
                <Btn size="small" variant="ghost" onClick={() => void run(() => unmute(slug, m.username), `Unmuted ${m.username}.`)}>
                  Unmute<span className="sr-only"> {m.username}</span>
                </Btn>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card aria-labelledby="log-h">
        <h3 id="log-h">What moderators did</h3>
        {queue.actions.length ? (
          <ul className="report-log">
            {queue.actions.map((a, i) => (
              <li key={i}>
                <b>{a.actor}</b> {ACTION_TEXT[a.action] ?? a.action} <b>{a.target}</b>
                {a.note && <span className="no-break"> ({a.note})</span>}
                <span className="muted no-break"> · {when(a.at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">Nothing yet. Every action lands here, so the team can see who did what.</p>
        )}
      </Card>

      {done.length > 0 && (
        <Card aria-labelledby="done-h">
          <h3 id="done-h">Handled</h3>
          <ul className="report-log">
            {done.map((r) => (
              <li key={r.id}>
                <b>{r.target}</b>: {r.reason} <span className="chip">{STATUS[r.status]}</span>
                <span className="muted no-break"> · {when(r.at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function ReportCard({ r, act }: { r: Report; act: (action: string, hours?: number) => void }) {
  const [confirm, setConfirm] = useState<string | null>(null);
  return (
    <Card className="report-card" aria-label={`Report about ${r.target}`}>
      <div className="report-head">
        <h3>{r.target}</h3>
        <span className="chip cherry">{r.reason}</span>
      </div>
      <p className="muted">
        {when(r.at)}
        {r.room && ` · in room ${r.room}`}
        {!r.member && " · no longer in the club"}
      </p>
      {r.note && <p className="report-quote">“{r.note}”</p>}
      {r.context.length > 0 && (
        <div className="report-context">
          <p className="field">What they said in the room</p>
          <ul>
            {r.context.map((c, i) => (
              <li key={i}>
                <b>{c.name}:</b> {c.text}
              </li>
            ))}
          </ul>
        </div>
      )}
      {confirm ? (
        <div className="report-actions">
          <p>
            <b>{confirm === "ban" ? `Ban ${r.target}? They can't come back.` : `Remove ${r.target} from the club?`}</b>
          </p>
          <Btn size="small" variant="danger" onClick={() => act(confirm)}>
            {confirm === "ban" ? "Yes, ban" : "Yes, remove"}
          </Btn>
          <Btn size="small" variant="ghost" onClick={() => setConfirm(null)}>
            Cancel
          </Btn>
        </div>
      ) : (
        <div className="report-actions">
          {r.can_act && r.member && (
            <>
              <Btn size="small" variant="gold" onClick={() => act("mute", 1)}>
                Mute 1 hour
              </Btn>
              <Btn size="small" variant="gold" onClick={() => act("mute", 24)}>
                Mute 1 day
              </Btn>
              <Btn size="small" variant="danger" onClick={() => setConfirm("remove")}>
                Remove
              </Btn>
              <Btn size="small" variant="danger" onClick={() => setConfirm("ban")}>
                Ban
              </Btn>
            </>
          )}
          <Btn size="small" variant="ghost" onClick={() => act("escalate")}>
            Send to staff
          </Btn>
          <Btn size="small" variant="ghost" onClick={() => act("dismiss")}>
            Dismiss
          </Btn>
        </div>
      )}
      {!r.can_act && r.member && <p className="muted acct-hint">They're at your level or above, so this one goes to staff (or the owner).</p>}
    </Card>
  );
}
