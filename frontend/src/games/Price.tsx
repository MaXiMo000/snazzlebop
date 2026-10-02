import { useEffect, useState } from "react";
import { Btn, Card, ShowHead, money, nameOf } from "../components/ui";
import { useCountUp, useOnChange, useReducedMotion, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { PriceResult, PriceView } from "../types";

interface Props {
  view: PriceView;
  you: string;
  players: { id: string; name: string }[];
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
}

type Show = ReturnType<typeof useShow>;

export function Price({ view, you, players, receivedAt, send }: Props) {
  const show = useShow();
  useOnChange(view.phase, (_, phase) => {
    if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT’S A WRAP!");
      show.celebrate();
    }
  });
  const sign =
    view.phase === "final"
      ? "Final scores"
      : `Item ${Math.min(view.round, view.rounds)} of ${view.rounds} · ${view.phase === "guess" ? "Guess" : "Chaos spin"}`;
  return (
    <div className="seg-price stack">
      {show.node}
      <ShowHead sign={sign} title="Price Is Weird" remaining={view.remaining} receivedAt={receivedAt}>
        {view.rollover > 0 && view.phase !== "final" && <span className="chip plum">Jackpot rollover +{view.rollover}</span>}
      </ShowHead>

      <div key={`${view.phase}-${view.round}`} className="stack enter">
        {view.phase === "final" ? (
          <FinalBoard view={view} players={players} you={you} />
        ) : (
          <>
            <Card tone="stage" className="prize">
              <span className="emoji" aria-hidden="true">
                {view.item.emoji}
              </span>
              <h3>{view.item.name}</h3>
              <p>{view.item.blurb}</p>
            </Card>
            {view.phase === "guess" && <GuessForm view={view} send={send} />}
            {view.phase === "reveal" && view.result && <Reveal result={view.result} players={players} you={you} show={show} />}
          </>
        )}
      </div>
    </div>
  );
}

function toInt(text: string): number | null {
  const digits = text.replace(/[^0-9]/g, "");
  if (!digits) return null;
  const n = Number(digits);
  return Number.isSafeInteger(n) && n > 0 && n <= 10_000_000 ? n : null;
}

function GuessForm({ view, send }: Pick<Props, "view" | "send">) {
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [hedge, setHedge] = useState(false);
  if (view.you_locked) {
    return (
      <Card tone="soft" className="center">
        <h3>Locked in 🔒</h3>
        <p className="lead">{view.your_guesses?.map(money).join(" / ")}</p>
        <p className="muted" aria-live="polite">
          {view.locked.length} guess{view.locked.length === 1 ? "" : "es"} in. The chaos spin is sealed.
        </p>
      </Card>
    );
  }
  const first = toInt(a);
  const second = hedge ? toInt(b) : null;
  const valid = first !== null && (!hedge || second !== null);
  return (
    <Card>
      <form
        className="stack-sm"
        onSubmit={(e) => {
          e.preventDefault();
          if (!valid || first === null) return;
          sfx.pop();
          send({ t: "act", a: "guess", amount: first, ...(hedge && second !== null ? { amount2: second } : {}) });
        }}
      >
        <p className="muted">
          Closest <b>without going over</b> wins. Then the sealed chaos spin may halve or double the real price.
        </p>
        <div>
          <label className="field" htmlFor="g1">
            Your price ($)
          </label>
          <input
            id="g1"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={a}
            onChange={(e) => setA(e.target.value)}
            placeholder="e.g. 25,000"
          />
        </div>
        {view.chips > 0 && (
          <label className="check">
            <input type="checkbox" checked={hedge} onChange={(e) => setHedge(e.target.checked)} />
            <span>
              Spend a hedge chip on a second guess ({view.chips} left). The best valid one counts.
            </span>
          </label>
        )}
        {hedge && (
          <div>
            <label className="field" htmlFor="g2">
              Second price ($)
            </label>
            <input id="g2" type="text" inputMode="numeric" autoComplete="off" value={b} onChange={(e) => setB(e.target.value)} />
          </div>
        )}
        <Btn variant="accent" size="big" block type="submit" disabled={!valid}>
          Lock it in!
        </Btn>
        <p className="muted">
          Sealed spin: <span className="seal mono">{view.commit.slice(0, 16)}…</span>
        </p>
      </form>
    </Card>
  );
}

const MULT: Record<string, { label: string; cls: string; say: string }> = {
  "0.5": { label: "×½", cls: "half", say: "times one half" },
  "1": { label: "×1", cls: "one", say: "times one" },
  "2": { label: "×2", cls: "two", say: "times two" },
};
const mult = (m: number) => MULT[String(m)] ?? { label: `×${m}`, cls: "one", say: `times ${m}` };
const CYCLE = [0.5, 1, 2];

function Reel({ modifier }: { modifier: number }) {
  // 17 decoy cells, then the sealed result: the strip always lands on its last cell.
  const cells = [...Array.from({ length: 17 }, (_, i) => CYCLE[i % 3]!), modifier];
  return (
    <div className="reel-window" aria-hidden="true">
      <ul className="reel">
        {cells.map((m, i) => (
          <li key={i} className={mult(m).cls}>
            {mult(m).label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Reveal({ result, players, you, show }: { result: PriceResult; players: Props["players"]; you: string; show: Show }) {
  const reduced = useReducedMotion();
  const [landed, setLanded] = useState(reduced);
  useEffect(() => {
    if (reduced) return;
    sfx.spin();
    const id = window.setTimeout(() => setLanded(true), 2300);
    return () => window.clearTimeout(id);
  }, [reduced]);
  const { stinger, celebrate } = show;
  useEffect(() => {
    if (!landed) return;
    if (result.winner === you) {
      sfx.fanfare();
      stinger("DING DING!");
      celebrate();
    } else if (result.winner) {
      sfx.ding();
      stinger("SOLD!");
    } else {
      sfx.buzz();
      stinger("BZZZT!", "bad");
    }
  }, [landed, result.winner, you, stinger, celebrate]);
  const price = useCountUp(landed ? result.true_price : result.base_price, 1100);
  const m = mult(result.modifier);

  return (
    <Card className="center">
      <h3>The chaos spin</h3>
      <Reel modifier={result.modifier} />
      <p className="space-top" role="status">
        {landed ? (
          <>
            <span className="sr-only">
              The spin landed on {m.say}.{" "}
            </span>
            Listed at <b>{money(result.base_price)}</b>, so the real price is…
          </>
        ) : (
          "Spinning…"
        )}
      </p>
      <p className="burst">
        <span className="price-tag">{money(price)}</span>
      </p>

      {landed && (
        <div className="stack enter">
          <div className="table-scroll" role="region" aria-label="Guesses" tabIndex={0}>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Player</th>
                  <th scope="col">Guess</th>
                  <th scope="col">Won</th>
                </tr>
              </thead>
              <tbody>
                {players.map((p) => {
                  const gs = result.guesses[p.id];
                  return (
                    <tr key={p.id} className={result.winner === p.id ? "winner-row" : ""}>
                      <th scope="row">
                        {p.name}
                        {p.id === you ? " (you)" : ""}
                      </th>
                      <td>
                        {gs
                          ? gs.map((g, i) => (
                              <span key={g} className={g > result.true_price ? "over" : ""}>
                                {i > 0 ? " / " : ""}
                                {money(g)}
                                {g > result.true_price ? <span className="sr-only"> (over)</span> : null}
                              </span>
                            ))
                          : "—"}
                      </td>
                      <td>{result.winner === p.id ? `🏆 +${result.pot}` : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!result.winner && (
            <p>
              {Object.keys(result.guesses).length ? "💥 Everyone went over!" : "🦗 Nobody guessed."} The pot rolls into the next item.
            </p>
          )}
          <details className="muted">
            <summary>Check the spin wasn’t rigged</summary>
            <p className="mono">
              sha256("{pyFloat(result.modifier)}:{result.nonce}") = {result.commit}
            </p>
          </details>
        </div>
      )}
    </Card>
  );
}

function FinalBoard({ view, players, you }: { view: PriceView; players: Props["players"]; you: string }) {
  const wins: Record<string, number> = {};
  for (const r of view.history ?? []) if (r.winner) wins[r.winner] = (wins[r.winner] ?? 0) + 1;
  const best = Object.entries(wins).sort((a, b) => b[1] - a[1])[0];
  return (
    <>
      <Card tone="stage" className="center">
        <p className="sign">That’s a wrap!</p>
        {best ? (
          <p className="lead space-top">
            <span className="burst">
              <b>{nameOf(players, best[0])}</b>
            </span>
            {best[0] === you ? " (you!)" : ""} won {best[1]} item{best[1] === 1 ? "" : "s"}.
          </p>
        ) : (
          <p className="lead space-top">Nobody won an item. Impressive chaos.</p>
        )}
      </Card>
      <Card>
        <h3>The price list</h3>
        <ol className="evidence">
          {(view.history ?? []).map((r) => (
            <li key={r.item}>
              <b>{r.item}</b>: {money(r.true_price)} ({mult(r.modifier).label}) → {r.winner ? nameOf(players, r.winner) : "nobody"}
            </li>
          ))}
        </ol>
      </Card>
    </>
  );
}

/** The seal is sha256 of Python's float text ("1.0", not JS's "1"), so show exactly what was hashed. */
function pyFloat(n: number): string {
  return Number.isInteger(n) ? n.toFixed(1) : String(n);
}
