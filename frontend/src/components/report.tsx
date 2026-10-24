import { useId, useState, type FormEvent } from "react";
import { useAccount } from "../lib/account";
import { REASONS, reportSeat } from "../lib/safety";
import { sfx } from "../lib/sfx";
import { Alert, errText } from "./auth";
import { Btn } from "./ui";

/**
 * Report someone: a reason, an optional note, and (when it applies) block them too. Shared by the club
 * member list and the room lobby; `send` does the right call for each.
 */
export function ReportForm({
  who,
  canBlock,
  fromRoom = false,
  send,
  done,
}: {
  who: string;
  canBlock: boolean;
  fromRoom?: boolean;
  send: (reason: string, note: string, alsoBlock: boolean) => Promise<unknown>;
  done: (text: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [alsoBlock, setAlsoBlock] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await send(reason, note.trim(), alsoBlock);
      sfx.pop();
      done(alsoBlock ? `Reported and blocked ${who}. Thanks for telling us.` : `Reported ${who}. Thanks for telling us.`);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="report-form stack-sm" onSubmit={(e) => void submit(e)}>
      <fieldset className="report-reasons">
        <legend className="field">What happened with {who}?</legend>
        {REASONS.map(([value, label]) => (
          <label key={value} className="check report-reason">
            <input type="radio" name={`${id}-reason`} value={value} checked={reason === value} onChange={() => setReason(value)} />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
      <div>
        <label className="field" htmlFor={`${id}-note`}>
          Anything else? <span className="muted">(optional)</span>
        </label>
        <textarea id={`${id}-note`} className="report-note" maxLength={500} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        <p className="muted acct-hint">
          {fromRoom ? "Moderators also see what they said in this room recently. " : ""}They won't be told who reported them.
        </p>
      </div>
      {canBlock && (
        <label className="check">
          <input type="checkbox" checked={alsoBlock} onChange={(e) => setAlsoBlock(e.target.checked)} />
          <span>Block {who} too</span>
        </label>
      )}
      <Alert text={error} />
      <Btn type="submit" variant="danger" disabled={busy || !reason}>
        Send report
      </Btn>
    </form>
  );
}

/**
 * In the lobby, for a signed-in player: report (and optionally block) someone in the room. Their recent
 * chat lines go along, taken by the server. Guests can't be blocked; the host can remove anyone.
 */
export function ReportInRoom({ code, players, you }: { code: string; players: { id: string; name: string }[]; you: string }) {
  const { user } = useAccount();
  const [open, setOpen] = useState(false);
  const [who, setWho] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const others = players.filter((p) => p.id !== you);
  const id = useId();
  if (!user || others.length === 0) return null;
  const target = others.find((p) => p.id === who);
  return (
    <div className="room-report space-top">
      <Btn size="small" variant="ghost" aria-expanded={open} onClick={() => (setOpen(!open), setNotice(null))}>
        {open ? "Close" : "Report a problem"}
      </Btn>
      {open && (
        <div className="invite-panel stack-sm">
          <div>
            <label className="field" htmlFor={`${id}-who`}>
              Who?
            </label>
            <select id={`${id}-who`} className="select-button" value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">Pick someone</option>
              {others.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          {target && (
            <ReportForm
              key={target.id}
              who={target.name}
              canBlock
              fromRoom
              send={(reason, note, alsoBlock) => reportSeat(code, target.id, reason, note, alsoBlock)}
              done={(text) => {
                setNotice(text);
                setOpen(false);
                setWho("");
              }}
            />
          )}
        </div>
      )}
      {notice && (
        <p className="alert calm space-top" role="status">
          {notice}
        </p>
      )}
    </div>
  );
}
