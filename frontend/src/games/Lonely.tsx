import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { LonelyView } from "../types";

interface Props {
  view: LonelyView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

export function Lonely({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  useOnChange(view.phase, (_, phase) => {
    if (phase === "reveal" && view.result) {
      const w = view.result.winner;
      if (w === null) {
        sfx.buzz();
        show.stinger("NOBODY LONELY!", "bad");
      } else if (!tv && w === you) {
        sfx.fanfare();
        show.stinger(`+${view.result.pot}!`);
      } else {
        sfx.ding();
        show.stinger(`${view.result.picks[w]} WINS`);
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });
  const r = view.result;
  const sign = view.phase === "final" ? "Final scores" : `Round ${view.round} of ${view.rounds} · ${view.phase === "pick" ? "Pick a number" : "Reveal"}`;
  // Group the revealed picks by number: lonely numbers glow, crowded ones are crossed out.
  const byNumber = new Map<number, string[]>();
  if (r) for (const [pid, n] of Object.entries(r.picks)) byNumber.set(n, [...(byNumber.get(n) ?? []), pid]);
  return (
    <div className="seg-lonely stack">
      {show.node}
      <ShowHead sign={sign} title="Lowest Lonely Number" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">Lowest number nobody else picked wins</span>
      </ShowHead>

      {view.phase === "pick" && (
        <Card tone="stage" className="center">
          <p className="sign">{view.round === view.rounds ? "Final round · double pot" : "This pot"}</p>
          <p className="space-top">
            <span className="price-tag">{view.pot}</span>
          </p>
          {view.rollover > 0 && <p className="lead space-top">Includes {view.rollover} rolled over!</p>}
          <p className="space-top" aria-live="polite">
            {view.locked.length} of {view.players.length} locked in
          </p>
        </Card>
      )}

      {!tv && view.phase === "pick" && (
        <Card tone="soft">
          {view.you.pick !== null ? (
            <p className="lead center">
              You picked <b>{view.you.pick}</b>. Hope nobody else did…
            </p>
          ) : (
            <>
              <h3>Your number</h3>
              <div className="number-grid" role="group" aria-label="Pick a number">
                {Array.from({ length: view.top }, (_, i) => i + 1).map((n) => (
                  <Btn
                    key={n}
                    size="small"
                    variant="ghost"
                    onClick={() => {
                      sfx.pop();
                      send({ t: "act", a: "pick", n });
                    }}
                  >
                    {n}
                  </Btn>
                ))}
              </div>
            </>
          )}
        </Card>
      )}

      {view.phase === "reveal" && r && (
        <Card tone="stage" className="center">
          <p className="sign">{r.winner ? "Lonely and lowest" : "Nobody was lonely"}</p>
          <p className="lead space-top">
            {r.winner ? (
              <>
                <b>{nameOf(view.players, r.winner)}</b>
                {r.winner === you ? " (you!)" : ""} wins {r.pot} with <b>{r.picks[r.winner]}</b>
              </>
            ) : (
              `The ${r.pot} pot rolls over.`
            )}
          </p>
        </Card>
      )}

      {view.phase === "reveal" && r && (
        <Card>
          <h3>Who picked what</h3>
          <ul className="lonely-picks">
            {[...byNumber.entries()]
              .sort(([a], [b]) => a - b)
              .map(([n, who]) => (
                <li key={n} className={who.length === 1 ? (r.winner === who[0] ? "win" : "lonely") : "crowded"}>
                  <span className="lonely-n">{n}</span> {who.map((p) => nameOf(view.players, p)).join(", ")}
                  {who.length > 1 && <span className="muted"> · crowded</span>}
                </li>
              ))}
          </ul>
          {Object.keys(r.picks).length < view.players.length && <p className="muted">No pick, no chance.</p>}
        </Card>
      )}

      <Card>
        <h3>{view.phase === "final" ? "Rounds won" : "Wins so far"}</h3>
        <ul className="evidence">
          {[...view.players]
            .sort((a, b) => (view.wins[b.id] ?? 0) - (view.wins[a.id] ?? 0))
            .map((p) => (
              <li key={p.id}>
                <b>{p.name}</b>
                {p.id === you ? " (you)" : ""}: {view.wins[p.id] ?? 0}
              </li>
            ))}
        </ul>
        {view.history && (
          <p className="muted">
            Winning numbers: {view.history.map((h) => (h.winner ? h.picks[h.winner] : "–")).join(" · ")}
          </p>
        )}
      </Card>
    </div>
  );
}
