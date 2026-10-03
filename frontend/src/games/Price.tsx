import { useEffect, useState } from "react";
import { Btn, Card, ShowHead, money, nameOf } from "../components/ui";
import { useCountUp, useOnChange, useReducedMotion, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { PriceDuelResult, PriceResult, PriceView } from "../types";

interface Props {
  view: PriceView;
  you: string;
  players: { id: string; name: string }[];
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

type Show = ReturnType<typeof useShow>;

export function Price({ view, you, players, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  useOnChange(`${view.phase}:${view.round}`, () => {
    if (view.phase !== "guess") return;
    if (view.rigged) {
      sfx.buzz();
      show.stinger("RIGGED ROUND!", "bad");
    } else if (view.final_round) {
      sfx.fanfare();
      show.stinger("DOUBLE OR NOTHING!");
    }
  });
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
      : `Item ${Math.min(view.round, view.rounds)} of ${view.rounds} · ${
          view.phase === "duel"
            ? "Price duel"
            : view.rigged
              ? "Rigged round"
              : view.final_round
                ? "The Showcase · Double or Nothing"
                : view.phase === "guess"
                  ? "Guess"
                  : "Chaos spin"
        }`;
  return (
    <div className="seg-price stack">
      {show.node}
      <ShowHead sign={sign} title="Price Is Weird" remaining={view.remaining} receivedAt={receivedAt}>
        <div className="row">
          {view.rigged && view.phase !== "final" && <span className="chip cherry">Wild spin · double pot</span>}
          {view.final_round && view.phase === "guess" && <span className="chip plum">Win it: score x2 · miss it: wiped</span>}
          {view.rollover > 0 && view.phase !== "final" && <span className="chip plum">Jackpot rollover +{view.rollover}</span>}
        </div>
      </ShowHead>

      <div key={`${view.phase}-${view.round}`} className="stack enter">
        {view.phase === "final" ? (
          <FinalBoard view={view} players={players} you={you} />
        ) : view.phase === "duel" && view.duel ? (
          <Duel view={view} players={players} send={send} tv={tv} />
        ) : (
          <>
            {view.phase === "guess" && view.last_duel && <LastDuel duel={view.last_duel} players={players} you={you} />}
            <Card tone="stage" className="prize">
              <span className="emoji" aria-hidden="true">
                {view.item.emoji}
              </span>
              <h3>{view.item.name}</h3>
              <p>{view.item.blurb}</p>
            </Card>
            {view.showcase && (
              <ul className="showcase" aria-label="The three Showcase prizes">
                {view.showcase.map((x, i) => (
                  <li key={x.name} className="card">
                    <span className="emoji" aria-hidden="true">
                      {x.emoji}
                    </span>
                    <b>{x.name}</b>
                    <span className="muted">{x.blurb}</span>
                    {view.showcase_prices && <span className="chip">{money(view.showcase_prices[i]!)}</span>}
                  </li>
                ))}
              </ul>
            )}
            {view.phase === "guess" &&
              (tv ? (
                <Card tone="soft" className="center">
                  <p className="lead" aria-live="polite">
                    {view.locked.length} of {players.length} guesses locked in
                  </p>
                  <p className="muted">Closest without going over wins. Then the chaos spin…</p>
                </Card>
              ) : (
                <>
                  <Tricks view={view} players={players} you={you} send={send} />
                  <GuessForm view={view} send={send} />
                </>
              ))}
            {view.phase === "reveal" && view.result && <Reveal result={view.result} players={players} you={you} show={show} />}
          </>
        )}
      </div>
    </div>
  );
}

function Duel({ view, players, send, tv }: { view: PriceView; players: Props["players"]; send: Props["send"]; tv: boolean }) {
  const duel = view.duel!;
  return (
    <>
      <Card tone="soft" className="center">
        <h3>Which costs more?</h3>
        <p className="muted">Quick! +25 if you pick the pricier one.</p>
      </Card>
      <div className="duel" role="group" aria-label="Pick the pricier item">
        {duel.items.map((x, i) => (
          <button
            key={x.name}
            type="button"
            className="duel-pick"
            aria-pressed={duel.your_pick === i}
            disabled={tv}
            onClick={() => {
              sfx.pop();
              send({ t: "act", a: "duel", pick: i });
            }}
          >
            <span className="emoji" aria-hidden="true">
              {x.emoji}
            </span>
            <b>{x.name}</b>
            <span>{x.blurb}</span>
            {duel.your_pick === i && <span className="chip plum">Your pick</span>}
          </button>
        ))}
      </div>
      <p className="center muted" aria-live="polite">
        {duel.locked.length} of {players.length} picked
      </p>
    </>
  );
}

function LastDuel({ duel, players, you }: { duel: PriceDuelResult; players: Props["players"]; you: string }) {
  const [a, b] = duel.items;
  const mine = duel.picks[you];
  return (
    <Card tone="soft">
      <p>
        <b>Price duel:</b> {a!.emoji} {a!.name} {money(a!.price)} vs {b!.emoji} {b!.name} {money(b!.price)}.{" "}
        {mine === undefined ? "" : duel.right.includes(you) ? "You got it: +25!" : "Not this time."}{" "}
        <span className="muted">
          {duel.right.length ? `Right: ${duel.right.map((id) => nameOf(players, id)).join(", ")}` : "Nobody got it."}
        </span>
      </p>
    </Card>
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

/** Secret moves for this item: the sabotage token and (final item only) Double or Nothing. */
function Tricks({ view, players, you, send }: Pick<Props, "view" | "players" | "you" | "send">) {
  const [target, setTarget] = useState("");
  const others = players.filter((p) => p.id !== you);
  const canSabotage = view.sabotage_left > 0 && !view.your_sabotage;
  if (!canSabotage && !view.your_sabotage && !view.final_round) return null;
  return (
    <Card tone="soft">
      <h3>Dirty tricks</h3>
      {view.final_round && (
        <label className="check space-top">
          <input
            type="checkbox"
            checked={view.your_double}
            disabled={view.you_locked}
            onChange={(e) => {
              sfx.pop();
              send({ t: "act", a: "double", on: e.target.checked });
            }}
          />
          <span>
            <b>Double or Nothing.</b> Win this item and your score for this game doubles. Miss it and it’s wiped. Nobody
            else knows until the reveal.
          </span>
        </label>
      )}
      {view.your_sabotage ? (
        <p className="space-top">
          💣 Sabotage set on <b>{nameOf(players, view.your_sabotage)}</b>. If they win this item, you steal half their pot.
        </p>
      ) : (
        canSabotage && (
          <div className="ask-form space-top">
            <div>
              <label className="field" htmlFor="sabotage-target">
                Sabotage (1 per game)
              </label>
              <select id="sabotage-target" value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">Pick a rival…</option>
                {others.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <Btn
              variant="danger"
              disabled={!target}
              onClick={() => {
                sfx.pop();
                send({ t: "act", a: "sabotage", target });
              }}
            >
              Plant it
            </Btn>
            <p className="muted">If they win this item, you steal half their pot. Secret until the reveal.</p>
          </div>
        )
      )}
    </Card>
  );
}

const MULT: Record<string, { label: string; cls: string; say: string }> = {
  "0.1": { label: "×0.1", cls: "half", say: "times one tenth" },
  "0.5": { label: "×½", cls: "half", say: "times one half" },
  "1": { label: "×1", cls: "one", say: "times one" },
  "2": { label: "×2", cls: "two", say: "times two" },
  "3": { label: "×3", cls: "two", say: "times three" },
  "5": { label: "×5", cls: "two", say: "times five" },
};
const mult = (m: number) => MULT[String(m)] ?? { label: `×${m}`, cls: "one", say: `times ${m}` };
const CYCLE = [0.5, 1, 2];
const WILD = [0.1, 3, 5];

function Reel({ modifier, rigged }: { modifier: number; rigged: boolean }) {
  // 17 decoy cells, then the sealed result: the strip always lands on its last cell.
  const decoys = rigged ? WILD : CYCLE;
  const cells = [...Array.from({ length: 17 }, (_, i) => decoys[i % 3]!), modifier];
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
      <Reel modifier={result.modifier} rigged={result.rigged} />
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
          {(Object.keys(result.sabotage).length > 0 || Object.keys(result.double).length > 0) && (
            <ul className="evidence">
              {Object.entries(result.sabotage).map(([who, target]) => (
                <li key={`s-${who}`} className={target === result.winner ? "flag" : ""}>
                  💣 {nameOf(players, who)} sabotaged {nameOf(players, target)}
                  {target === result.winner ? " and stole half the pot!" : ". It fizzled."}
                </li>
              ))}
              {Object.entries(result.double).map(([who, outcome]) => (
                <li key={`d-${who}`} className={outcome === "doubled" ? "clue" : "flag"}>
                  🎲 {nameOf(players, who)} went Double or Nothing: {outcome === "doubled" ? "DOUBLED!" : "wiped out."}
                </li>
              ))}
            </ul>
          )}
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
      {(view.duels ?? []).length > 0 && (
        <Card>
          <h3>Price duels</h3>
          <ol className="evidence">
            {view.duels!.map((d, i) => (
              <li key={i}>
                {d.items[0]!.name} {money(d.items[0]!.price)} vs {d.items[1]!.name} {money(d.items[1]!.price)}:{" "}
                {d.right.length ? d.right.map((id) => nameOf(players, id)).join(", ") : "nobody"}
              </li>
            ))}
          </ol>
        </Card>
      )}
    </>
  );
}

/** The seal is sha256 of Python's float text ("1.0", not JS's "1"), so show exactly what was hashed. */
function pyFloat(n: number): string {
  return Number.isInteger(n) ? n.toFixed(1) : String(n);
}
