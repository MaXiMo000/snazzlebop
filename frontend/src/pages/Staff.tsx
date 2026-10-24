import { useCallback, useEffect, useId, useState } from "react";
import { Alert, errText } from "../components/auth";
import { byPriority, CaseCard, when } from "../components/casecard";
import { Btn, Card } from "../components/ui";
import { ApiError } from "../lib/api";
import { liftSuspension, staffAct, staffQueue, type StaffQueue } from "../lib/safety";

type Go = (path: string) => void;
type Case = StaffQueue["reports"][number];

const DAYS: [number, string][] = [
  [1, "1 day"],
  [7, "7 days"],
  [30, "30 days"],
  [0, "For good"],
];
const STATUS: Record<Case["status"], string> = {
  open: "Open",
  triaged: "Triaged",
  escalated: "Escalated",
  dismissed: "Dismissed",
  actioned: "Dealt with",
};
const DID: Record<string, string> = {
  dismiss: "dismissed a case about",
  suspend: "suspended",
  unsuspend: "lifted the suspension of",
  return: "handed back to the club a case about",
};

/** /staff: the platform staff console. Escalated club cases, reports outside clubs, suspensions. */
export function Staff({ go }: { go: Go }) {
  const [queue, setQueue] = useState<StaffQueue | null>(null);
  const [gate, setGate] = useState<"loading" | "open" | "mfa" | "closed">("loading");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(
    () =>
      staffQueue().then(
        (q) => (setQueue(q), setGate("open")),
        (e) => setGate(e instanceof ApiError && e.code === "needs_mfa" ? "mfa" : "closed"),
      ),
    [],
  );
  useEffect(() => {
    document.title = "Staff · Snazzlebop";
    void load();
  }, [load]);

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

  if (gate === "loading") return <p className="muted center">Loading…</p>;
  if (gate === "closed")
    return (
      <Card className="center">
        <h2>Page not found</h2>
        <Btn className="space-top" onClick={() => go("/")}>
          Back to the show
        </Btn>
      </Card>
    );
  if (gate === "mfa")
    return (
      <Card className="center">
        <h2>One more step</h2>
        <p className="space-top">The staff console needs your authenticator app turned on.</p>
        <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
          Set it up on your account page
        </Btn>
      </Card>
    );
  if (!queue) return null;
  const waiting = byPriority(queue.reports.filter((r) => ["open", "triaged", "escalated"].includes(r.status)));
  const done = queue.reports.filter((r) => !["open", "triaged", "escalated"].includes(r.status));

  return (
    <div className="stack enter reports-page">
      <Card tone="stage" className="center">
        <p className="sign">Staff</p>
        <p className="space-top">{waiting.length ? `${waiting.length} ${waiting.length === 1 ? "case" : "cases"} waiting.` : "Nothing waiting."}</p>
      </Card>
      {note && <Alert text={note.text} calm={note.ok} />}

      {waiting.map((c) => (
        <StaffCase key={c.id} c={c} run={run} />
      ))}

      <Card aria-labelledby="sus-h">
        <h3 id="sus-h">Suspended accounts</h3>
        {queue.suspended.length ? (
          <ul className="club-rooms">
            {queue.suspended.map((s) => (
              <li key={s.username}>
                <span className="club-room-text">
                  <b>{s.username}</b>
                  <span className="muted">
                    {s.until ? `Until ${when(s.until)}` : "For good"}
                    {s.reason && ` · ${s.reason}`}
                  </span>
                </span>
                <Btn
                  size="small"
                  variant="ghost"
                  onClick={() => window.confirm(`Lift ${s.username}'s suspension?`) && void run(() => liftSuspension(s.username), `${s.username} can sign in again.`)}
                >
                  Lift<span className="sr-only"> {s.username}'s suspension</span>
                </Btn>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">Nobody is suspended.</p>
        )}
      </Card>

      <Card aria-labelledby="slog-h">
        <h3 id="slog-h">What staff did</h3>
        {queue.actions.length ? (
          <ul className="report-log">
            {queue.actions.map((a, i) => (
              <li key={i}>
                <b>{a.actor}</b> {DID[a.action] ?? a.action} <b>{a.target}</b>
                {a.note && <span className="no-break"> ({a.note})</span>}
                <span className="muted no-break"> · {when(a.at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">Nothing yet.</p>
        )}
      </Card>

      {done.length > 0 && (
        <Card aria-labelledby="sdone-h">
          <h3 id="sdone-h">Closed</h3>
          <ul className="report-log">
            {done.map((r) => (
              <li key={r.id}>
                <b>{r.target}</b>: {r.reason}{" "}
                <span className="no-break">
                  <span className="chip">{STATUS[r.status]}</span>
                  <span className="muted"> · {when(r.at)}</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function StaffCase({ c, run }: { c: Case; run: (fn: () => Promise<unknown>, ok: string) => Promise<void> }) {
  const [suspending, setSuspending] = useState(false);
  const [days, setDays] = useState(7);
  const [reason, setReason] = useState("");
  const id = useId();
  const actions = suspending ? (
    <div className="staff-suspend stack-sm space-top">
      <fieldset className="report-reasons">
        <legend className="field">Suspend {c.account} for</legend>
        <div className="auth-tabs staff-days">
          {DAYS.map(([d, label]) => (
            <button key={d} type="button" className={`auth-tab ${days === d ? "on" : ""}`} aria-pressed={days === d} onClick={() => setDays(d)}>
              {label}
            </button>
          ))}
        </div>
      </fieldset>
      <div>
        <label className="field" htmlFor={`${id}-why`}>
          Reason <span className="muted">(kept in the log)</span>
        </label>
        <input id={`${id}-why`} type="text" maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <div className="report-actions">
        <Btn
          size="small"
          variant="danger"
          onClick={() =>
            void run(() => staffAct(c.id, "suspend", days, reason.trim()), `${c.account} is suspended ${days === 0 ? "for good" : `for ${days} days`} and signed out everywhere.`)
          }
        >
          Suspend
        </Btn>
        <Btn size="small" variant="ghost" onClick={() => setSuspending(false)}>
          Cancel
        </Btn>
      </div>
    </div>
  ) : (
    <div className="report-actions">
      {c.can_suspend && (
        <Btn size="small" variant="danger" onClick={() => setSuspending(true)}>
          Suspend account
        </Btn>
      )}
      {c.can_return && (
        <Btn size="small" variant="gold" onClick={() => void run(() => staffAct(c.id, "return"), "Handed back to the club's moderators.")}>
          Hand back to the club
        </Btn>
      )}
      <Btn size="small" variant="ghost" onClick={() => void run(() => staffAct(c.id, "dismiss"), "Dismissed.")}>
        Dismiss
      </Btn>
    </div>
  );
  return (
    <CaseCard
      c={c}
      meta={[
        c.club ? `from ${c.club}` : "not in a club",
        ...(c.status === "escalated" ? ["escalated"] : []),
        ...(c.account ? [] : ["a guest (no account)"]),
      ]}
      actions={actions}
    />
  );
}
