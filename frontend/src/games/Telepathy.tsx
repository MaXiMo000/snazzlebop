import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { TelepathyResult, TelepathyView } from "../types";

interface Props {
  view: TelepathyView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

export function Telepathy({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  useOnChange(view.phase, (_, phase) => {
    if (phase === "reveal" && view.result) {
      const mine = view.result.picks[you];
      if (tv || mine === undefined) {
        sfx.ding();
        show.stinger("MINDS REVEALED!");
      } else if (view.result.taxed.includes(mine)) {
        sfx.buzz();
        show.stinger("TAXED!", "bad");
      } else if ((view.result.points[you] ?? 0) > 0) {
        sfx.fanfare();
        show.stinger("MIND MELD!");
      } else {
        sfx.buzz();
        show.stinger("LONELY MIND", "bad");
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT’S A WRAP!");
      show.celebrate();
    }
  });
  const sign =
    view.phase === "final" ? "Final reveal" : `Round ${view.round} of ${view.rounds} · ${view.phase === "pick" ? "Read the room" : "Reveal"}`;
  return (
    <div className="seg-telepathy stack">
      {show.node}
      <ShowHead sign={sign} title="Telepathy Tax" remaining={view.remaining} receivedAt={receivedAt}>
        {view.phase !== "final" && <span className="chip plum">+100 per matching mind · majority = taxed</span>}
      </ShowHead>
      <div key={`${view.phase}-${view.round}`} className="stack enter">
        {view.phase === "pick" && <Pick view={view} send={send} tv={tv} />}
        {view.phase === "reveal" && view.result && <Reveal result={view.result} view={view} you={you} />}
        {view.phase === "final" && view.final && <Final view={view} you={you} />}
      </div>
    </div>
  );
}

function Pick({ view, send, tv }: { view: TelepathyView; send: Props["send"]; tv: boolean }) {
  const waiting = view.players.filter((p) => !view.locked.includes(p.id));
  return (
    <>
      <Card tone="stage" className="center">
        <p className="sign">Name…</p>
        <h3 className="prompt space-top">{view.category.title}</h3>
      </Card>
      <Card>
        {!tv && !view.you_locked && (
          <p>Pick the answer you think <b>some</b> of the room will pick. Not too many!</p>
        )}
        <div className="option-grid" role="group" aria-label={`Answers for ${view.category.title}`}>
          {view.category.options.map((opt, i) => (
            <Btn
              key={opt}
              variant={view.your_pick === i ? "accent" : "ghost"}
              size="big"
              aria-pressed={view.your_pick === i}
              disabled={tv || view.you_locked}
              onClick={() => {
                sfx.pop();
                send({ t: "act", a: "pick", option: i });
              }}
            >
              {opt}
            </Btn>
          ))}
        </div>
        <p className="muted space-top" aria-live="polite">
          {view.locked.length} of {view.players.length} locked in
          {waiting.length > 0 && waiting.length <= 3 ? ` · waiting for ${waiting.map((p) => p.name).join(", ")}` : ""}
        </p>
      </Card>
    </>
  );
}

function Reveal({ result, view, you }: { result: TelepathyResult; view: TelepathyView; you: string }) {
  return (
    <>
      <Card tone="stage" className="center">
        <p className="sign">The minds were…</p>
        <h3 className="prompt space-top">{result.category.title}</h3>
      </Card>
      <div className="grid">
        {result.category.options.map((opt, i) => {
          const pickers = view.players.filter((p) => result.picks[p.id] === i);
          if (!pickers.length) return null;
          const taxed = result.taxed.includes(i);
          return (
            <Card key={opt} className={`answer ${taxed ? "taxed" : ""}`}>
              <div className="row between">
                <h3>{opt}</h3>
                {taxed ? <span className="chip cherry">TAXED!</span> : <span className="chip">+{(pickers.length - 1) * 100} each</span>}
              </div>
              <ul className="contestants">
                {pickers.map((p) => (
                  <li key={p.id} className={`contestant ${p.id === you ? "you" : ""}`}>
                    {p.name}
                    {p.id === you ? " (you)" : ""}
                  </li>
                ))}
              </ul>
            </Card>
          );
        })}
      </div>
      {Object.keys(result.picks).length < view.players.length && (
        <p className="muted center">
          No pick from:{" "}
          {view.players
            .filter((p) => result.picks[p.id] === undefined)
            .map((p) => p.name)
            .join(", ")}
        </p>
      )}
    </>
  );
}

function Final({ view, you }: { view: TelepathyView; you: string }) {
  const fin = view.final!;
  const meld = fin.mind_meld;
  return (
    <>
      <Card tone="stage" className="center">
        <p className="sign">Mind Meld award</p>
        {meld ? (
          <p className="lead space-top">
            <span className="burst">
              <b>
                {nameOf(view.players, meld.players[0])} &amp; {nameOf(view.players, meld.players[1])}
              </b>
            </span>
            {meld.players.includes(you) ? " (that’s you!)" : ""} matched {meld.matches} times.
          </p>
        ) : (
          <p className="lead space-top">No two minds matched twice. A room of free thinkers.</p>
        )}
      </Card>
      <Card>
        <h3>Round by round</h3>
        <ol className="evidence">
          {fin.history.map((h) => {
            const best = Object.entries(h.points).sort((a, b) => b[1] - a[1])[0];
            return (
              <li key={h.category.title}>
                <b>{h.category.title}</b>
                {h.taxed.length ? ` · taxed: ${h.taxed.map((i) => h.category.options[i]).join(", ")}` : ""}
                {best && best[1] > 0 ? ` · top: ${nameOf(view.players, best[0])} +${best[1]}` : " · nobody matched"}
              </li>
            );
          })}
        </ol>
      </Card>
    </>
  );
}
