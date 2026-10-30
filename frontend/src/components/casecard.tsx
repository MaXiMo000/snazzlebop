import type { ReactNode } from "react";
import { Card } from "./ui";

/** What both queues (a club's moderators, platform staff) show for one report case. */
export interface CaseLike {
  target: string;
  reason: string;
  note: string;
  context: { name: string; text: string }[];
  room: string | null;
  status: string;
  at: string;
  public_id: string;
  priority: "low" | "normal" | "high" | "urgent";
  triage: { label: string; score: number | null; summary: string; by: string } | null;
  tickets: { system: string; key: string; url: string | null }[];
  history: { at: string; actor: string; text: string }[];
}

export const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

const PRIORITY: Record<CaseLike["priority"], string> = {
  urgent: "Urgent",
  high: "High priority",
  normal: "",
  low: "Low priority",
};

/** Waiting cases first, most pressing on top. */
export function byPriority<T extends CaseLike>(cases: T[]): T[] {
  const order = { urgent: 0, high: 1, normal: 2, low: 3 };
  return cases.slice().sort((a, b) => order[a.priority] - order[b.priority]);
}

/**
 * One case: who, why, when and where; a triage suggestion (always marked as one); linked tickets;
 * the reporter's note; what the person said in the room; the history. `meta` adds facts to the
 * details row (each one wraps as a whole), `actions` are the queue's own buttons, `footer` sits under
 * the history.
 */
export function CaseCard({ c, meta, actions, footer }: { c: CaseLike; meta?: string[]; actions: ReactNode; footer?: ReactNode }) {
  return (
    <Card className="report-card" aria-label={`Report about ${c.target}`}>
      <div className="report-head">
        <h3>{c.target}</h3>
        <span className="report-chips">
          {PRIORITY[c.priority] && <span className={`chip priority-${c.priority}`}>{PRIORITY[c.priority]}</span>}
          <span className="chip cherry">{c.reason}</span>
        </span>
      </div>
      <ul className="case-meta muted">
        <li>{when(c.at)}</li>
        {c.room && <li>in room {c.room}</li>}
        {(meta ?? []).map((m) => (
          <li key={m} className={m.length > 24 ? "long" : ""}>
            {m}
          </li>
        ))}
        {c.status === "triaged" && <li>triaged</li>}
        <li className="report-id">{c.public_id}</li>
      </ul>
      {c.triage && (
        <div className="report-triage">
          <p>
            <b>Suggested: {c.triage.label}</b>
          </p>
          <p className="muted">
            {[typeof c.triage.score === "number" ? `${Math.round(c.triage.score * 100)}% sure` : "", c.triage.by ? `by ${c.triage.by}` : ""]
              .filter(Boolean)
              .join(" ·\u00a0")}
          </p>
          {c.triage.summary && <p className="muted">{c.triage.summary}</p>}
          <p className="muted acct-hint">A suggestion only: you decide.</p>
        </div>
      )}
      {c.tickets.length > 0 && (
        <p className="report-tickets">
          {c.tickets.map((t) =>
            t.url ? (
              <a key={t.system} className="chip" href={t.url} target="_blank" rel="noopener noreferrer">
                {t.system} {t.key}
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            ) : (
              <span key={t.system} className="chip">
                {t.system} {t.key}
              </span>
            ),
          )}
        </p>
      )}
      {c.note && <p className="report-quote">“{c.note}”</p>}
      {c.context.length > 0 && (
        <div className="report-context">
          <p className="field">What they said in the room</p>
          <ul>
            {c.context.map((line, i) => (
              <li key={i}>
                <b>{line.name}:</b> {line.text}
              </li>
            ))}
          </ul>
        </div>
      )}
      {actions}
      {c.history.length > 1 && (
        <details className="report-history">
          <summary>History ({c.history.length})</summary>
          <ol>
            {c.history.map((h, i) => (
              <li key={i}>
                <span className="muted no-break">{when(h.at)}</span> <b>{h.actor}</b>: {h.text}
              </li>
            ))}
          </ol>
        </details>
      )}
      {footer}
    </Card>
  );
}
