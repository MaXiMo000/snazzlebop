import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { SplitView } from "../types";

interface Props {
  view: SplitView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

export function Split({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  useOnChange(view.phase, (_, phase) => {
    if (phase === "reveal" && view.result && !tv) {
      const mine = view.result.pairs.find((p) => p.players.includes(you));
      if (!mine) return;
      const other = mine.players.find((p) => p !== you)!;
      const me = mine.choices[you];
      const them = mine.choices[other];
      if (me === "split" && them === "split") {
        sfx.fanfare();
        show.stinger("SHARED!");
      } else if (them === "steal" && me === "split") {
        sfx.buzz();
        show.stinger("BETRAYED!", "bad");
      } else if (me === "steal" && them === "split") {
        sfx.fanfare();
        show.stinger("YOINK!");
      } else {
        sfx.buzz();
        show.stinger("NOBODY WINS", "bad");
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });
  const partner = view.you.partner;
  const myPair = view.pairs.find((p) => p.players.includes(you));
  const sign =
    view.phase === "final" ? "Final scores" : `Round ${view.round} of ${view.rounds} · ${view.phase === "choose" ? "Decide" : "Reveal"}`;
  return (
    <div className="seg-split stack">
      {show.node}
      <ShowHead sign={sign} title="Split or Steal" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">Both split: share · one steals: takes all · both steal: nothing</span>
      </ShowHead>

      {!tv && view.phase === "choose" && partner && myPair && (
        <Card tone="stage" className="center">
          <p className="sign">Your pot</p>
          <p className="space-top">
            <span className="price-tag">{myPair.pot}</span>
          </p>
          <p className="lead space-top">
            You’re paired with <b>{nameOf(view.players, partner)}</b>
          </p>
          <p>
            Their record: {view.record[partner]?.split ?? 0} splits, {view.record[partner]?.steal ?? 0} steals.
            {view.said[partner] ? (
              <>
                {" "}
                They say: <b>“{view.said[partner]}”</b>
              </>
            ) : null}
          </p>
        </Card>
      )}
      {!tv && view.phase === "choose" && !partner && view.bye === you && (
        <Card tone="soft" className="center">
          <p className="lead">You’re sitting this round out (+50 for the bye). Watch the drama!</p>
        </Card>
      )}

      {!tv && view.phase === "choose" && partner && (
        <Card tone="soft">
          {view.you.choice ? (
            <p className="lead center">
              Locked in: <b>{view.you.choice === "split" ? "SPLIT 🤝" : "STEAL 🦹"}</b>. No take-backs.
            </p>
          ) : (
            <>
              <h3>Your choice</h3>
              <div className="row center split-buttons">
                <Btn
                  variant="go"
                  size="big"
                  onClick={() => {
                    sfx.pop();
                    send({ t: "act", a: "choose", choice: "split" });
                  }}
                >
                  🤝 Split
                </Btn>
                <Btn
                  variant="danger"
                  size="big"
                  onClick={() => {
                    sfx.pop();
                    send({ t: "act", a: "choose", choice: "steal" });
                  }}
                >
                  🦹 Steal
                </Btn>
              </div>
            </>
          )}
          {!view.said[you] && (
            <div className="space-top">
              <p className="muted">Say one thing to your partner (everyone hears it):</p>
              <div className="row" role="group" aria-label="Say something">
                {view.lines.map((line, i) => (
                  <Btn key={line} size="small" variant="ghost" onClick={() => send({ t: "act", a: "say", line: i })}>
                    {line}
                  </Btn>
                ))}
              </div>
            </div>
          )}
          {view.said[you] && <p className="muted space-top">You said: “{view.said[you]}”</p>}
        </Card>
      )}

      {view.phase !== "final" && (
        <Card>
          <h3>{view.phase === "reveal" ? "The reveal" : "This round"}</h3>
          <ul className="split-pairs">
            {(view.phase === "reveal" && view.result
              ? view.result.pairs.map((r) => ({ players: r.players, pot: r.pot, r }))
              : view.pairs.map((p) => ({ ...p, r: null }))
            ).map(({ players, pot, r }) => (
              <li key={players.join("-")} className={players.includes(you) ? "mine" : ""}>
                <span className="chip">{pot}</span>
                {players.map((pid) => (
                  <span key={pid} className="split-player">
                    <b>{nameOf(view.players, pid)}</b>
                    {r ? (
                      <span className={`chip ${r.choices[pid] === "split" ? "teal" : "cherry"}`}>
                        {r.choices[pid] === "split" ? "🤝 split" : "🦹 steal"} · +{r.gain[pid]}
                      </span>
                    ) : (
                      <span className="muted">{view.locked.includes(pid) ? " locked in" : " deciding…"}</span>
                    )}
                    {!r && view.said[pid] && <span className="muted"> · “{view.said[pid]}”</span>}
                  </span>
                ))}
              </li>
            ))}
          </ul>
          {view.bye && <p className="muted">{nameOf(view.players, view.bye)} sits this one out.</p>}
        </Card>
      )}

      <Card>
        <h3>Trust record</h3>
        <ul className="evidence">
          {view.players.map((p) => (
            <li key={p.id}>
              <b>{p.name}</b>
              {p.id === you ? " (you)" : ""}: 🤝 {view.record[p.id]?.split ?? 0} · 🦹 {view.record[p.id]?.steal ?? 0}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
