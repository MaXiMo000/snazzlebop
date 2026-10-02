import { useState } from "react";
import { Btn, Panel, Timer, money, nameOf } from "../components/ui";
import type { PriceResult, PriceView } from "../types";

interface Props {
  view: PriceView;
  you: string;
  players: { id: string; name: string }[];
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
}

export function Price({ view, you, players, receivedAt, send }: Props) {
  return (
    <div className="theme-price">
      <Panel themed className="halftone">
        <div className="row between">
          <div>
            <span className="tag pink">
              Item {Math.min(view.round, view.rounds)}/{view.rounds}
            </span>
            <h2>Price Is Weird</h2>
          </div>
          <div className="row">
            {view.rollover > 0 && <span className="tag lime">Pot rolls over +{view.rollover}</span>}
            <Timer remaining={view.remaining} receivedAt={receivedAt} />
          </div>
        </div>
      </Panel>

      {view.phase === "final" ? (
        <FinalBoard view={view} players={players} />
      ) : (
        <Panel className="item-card halftone">
          <div className="emoji" aria-hidden="true">
            {view.item.emoji}
          </div>
          <h2>{view.item.name}</h2>
          <p>{view.item.blurb}</p>
          {view.phase === "guess" && <GuessForm key={view.round} view={view} send={send} />}
          {view.phase === "reveal" && view.result && <Reveal result={view.result} players={players} you={you} />}
        </Panel>
      )}
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
      <div className="stack">
        <h3>Locked in 🔒 {view.your_guesses?.map(money).join(" / ")}</h3>
        <p className="muted">
          {view.locked.length} guess{view.locked.length === 1 ? "" : "es"} in. The chaos spin is sealed.
        </p>
        <p className="mono muted">
          Seal (sha256 of modifier:nonce): {view.commit.slice(0, 16)}…
        </p>
      </div>
    );
  }
  const first = toInt(a);
  const second = hedge ? toInt(b) : null;
  const valid = first !== null && (!hedge || second !== null);
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        if (!valid || first === null) return;
        send({ t: "act", a: "guess", amount: first, ...(hedge && second !== null ? { amount2: second } : {}) });
      }}
    >
      <p className="mono muted">Sealed chaos spin: {view.commit.slice(0, 16)}… (revealed after guessing)</p>
      <div>
        <label className="field" htmlFor="g1">
          Your price ($)
        </label>
        <input id="g1" type="text" inputMode="numeric" autoComplete="off" value={a} onChange={(e) => setA(e.target.value)} placeholder="e.g. 25000" />
      </div>
      {view.chips > 0 && (
        <label className="row">
          <input type="checkbox" checked={hedge} onChange={(e) => setHedge(e.target.checked)} style={{ width: 28, height: 28 }} />
          <span>
            Spend a hedge chip for a second guess ({view.chips} left). The best valid one counts.
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
      <Btn color="lime" size="big" type="submit" disabled={!valid}>
        Lock it in!
      </Btn>
    </form>
  );
}

function Reveal({ result, players, you }: { result: PriceResult; players: { id: string; name: string }[]; you: string }) {
  const label = result.modifier === 2 ? "×2 !!" : result.modifier === 0.5 ? "×½ !!" : "×1 (phew)";
  const cls = result.modifier === 2 ? "x2" : result.modifier === 0.5 ? "half" : "";
  return (
    <div className="stack">
      <div className={`spin ${cls}`} role="status">
        {label}
      </div>
      <p>
        Listed at <b>{money(result.base_price)}</b>, so the real price is <b>{money(result.true_price)}</b>.
      </p>
      <table className="table">
        <thead>
          <tr>
            <th>Player</th>
            <th>Guess</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {players.map((p) => {
            const gs = result.guesses[p.id];
            return (
              <tr key={p.id} className={result.winner === p.id ? "winner" : ""}>
                <td>
                  {p.name}
                  {p.id === you ? " (you)" : ""}
                </td>
                <td>
                  {gs
                    ? gs.map((g) => (
                        <span key={g} style={{ marginRight: 8, textDecoration: g > result.true_price ? "line-through" : "none" }}>
                          {money(g)}
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
      {!result.winner && (
        <p>
          {Object.keys(result.guesses).length ? "💥 Everyone went over!" : "🦗 Nobody guessed."} The pot rolls into the next
          round.
        </p>
      )}
      <p className="mono muted">
        Proof: sha256("{pyFloat(result.modifier)}:{result.nonce.slice(0, 12)}…") = {result.commit.slice(0, 16)}…
      </p>
    </div>
  );
}

function FinalBoard({ view, players }: { view: PriceView; players: { id: string; name: string }[] }) {
  const wins: Record<string, number> = {};
  for (const r of view.history ?? []) if (r.winner) wins[r.winner] = (wins[r.winner] ?? 0) + 1;
  const best = Object.entries(wins).sort((a, b) => b[1] - a[1])[0];
  return (
    <Panel className="halftone">
      <h2>That's a wrap!</h2>
      {best ? (
        <p>
          <b>{nameOf(players, best[0])}</b> won {best[1]} round{best[1] === 1 ? "" : "s"}.
        </p>
      ) : (
        <p>Nobody won a round. Impressive chaos.</p>
      )}
      <ol>
        {(view.history ?? []).map((r) => (
          <li key={r.item}>
            {r.item}: {money(r.true_price)} (×{r.modifier}) {r.winner ? `→ ${nameOf(players, r.winner)}` : "→ nobody"}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

/** The seal is sha256 of Python's float text ("1.0", not JS's "1"), so show exactly what was hashed. */
function pyFloat(n: number): string {
  return Number.isInteger(n) ? n.toFixed(1) : String(n);
}
