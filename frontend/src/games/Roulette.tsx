import { useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { RouletteBet, RouletteView } from "../types";

interface Props {
  view: RouletteView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const color = (n: number) => (n === 0 ? "green" : RED.has(n) ? "red" : "black");
const OUTSIDE: [RouletteBet["kind"], string][] = [
  ["red", "Red"],
  ["black", "Black"],
  ["odd", "Odd"],
  ["even", "Even"],
  ["low", "1-18"],
  ["high", "19-36"],
];

function describe(b: RouletteBet): string {
  if (b.kind === "number") return `${b.amount} on ${b.value} (35:1)`;
  if (b.kind === "dozen") return `${b.amount} on dozen ${b.value} (2:1)`;
  return `${b.amount} on ${OUTSIDE.find(([k]) => k === b.kind)?.[1] ?? b.kind} (1:1)`;
}

function Pocket({ n, big = false }: { n: number; big?: boolean }) {
  return (
    <span className={`pocket ${color(n)} ${big ? "big" : ""}`} role="img" aria-label={`${n} ${color(n)}`}>
      <span aria-hidden="true">{n}</span>
    </span>
  );
}

export function Roulette({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  useOnChange(view.phase, (_, phase) => {
    if (phase === "spin" && view.result) {
      const mine = view.result.net[you] ?? 0;
      if (!tv && view.result.house === you) {
        sfx.fanfare();
        show.stinger(view.result.house_net >= 0 ? "THE HOUSE WINS" : "THE HOUSE PAYS", view.result.house_net >= 0 ? "good" : "bad");
      } else if (!tv && mine > 0) {
        sfx.fanfare();
        show.stinger(`+${mine}!`);
      } else {
        sfx.ding();
        show.stinger(`${view.result.number} ${view.result.color.toUpperCase()}`);
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("CASH OUT!");
      show.celebrate();
    }
  });
  const sign = view.phase === "final" ? "Final stacks" : `Spin ${view.round} of ${view.rounds} · ${view.phase === "bet" ? "Place your bets" : "No more bets"}`;
  return (
    <div className="seg-roulette stack">
      {show.node}
      <ShowHead sign={sign} title="Roulette Royale" remaining={view.remaining} receivedAt={receivedAt}>
        <div className="row">
          <span className="chip plum">One of you is secretly the House</span>
          {view.spins.length > 0 && (
            <span className="spins" aria-label={`Recent spins: ${view.spins.slice(-8).join(", ")}`}>
              {view.spins.slice(-8).map((n, i) => (
                <Pocket key={i} n={n} />
              ))}
            </span>
          )}
        </div>
      </ShowHead>

      {view.phase === "bet" && !tv && (view.you.is_house ? <HousePanel view={view} you={you} send={send} /> : <BetPanel view={view} you={you} send={send} />)}
      {view.phase === "bet" && (
        <p className="center muted" aria-live="polite">
          {view.locked_count} of {view.players.length} locked in
        </p>
      )}

      {view.phase === "spin" && view.result && (
        <>
          <Card tone="stage" className="center">
            <p className="sign">The wheel says</p>
            <p className="space-top">
              <Pocket n={view.result.number} big />
            </p>
            <p className="lead space-top">
              The House was <b>{nameOf(view.players, view.result.house)}</b>
              {view.result.house === you ? " (you!)" : ""}: {view.result.house_net >= 0 ? "+" : ""}
              {view.result.house_net}
            </p>
            {view.result.spotted.length > 0 && (
              <p>Spotted by {view.result.spotted.map((p) => nameOf(view.players, p)).join(", ")} (+100 each)</p>
            )}
          </Card>
          <Card>
            <h3>The table</h3>
            <ul className="evidence">
              {view.players
                .filter((p) => p.id !== view.result!.house)
                .map((p) => {
                  const bets = view.result!.bets[p.id] ?? [];
                  const net = view.result!.net[p.id] ?? 0;
                  return (
                    <li key={p.id}>
                      <b>{p.name}</b>
                      {p.id === you ? " (you)" : ""}: {bets.length ? bets.map(describe).join(" · ") : "no bets"}{" "}
                      <span className={`chip ${net > 0 ? "teal" : net < 0 ? "cherry" : ""}`}>
                        {net > 0 ? "+" : ""}
                        {net}
                      </span>
                    </li>
                  );
                })}
            </ul>
            <details className="muted">
              <summary>Check the spin wasn’t rigged</summary>
              <p className="mono">
                sha256("{view.result.number}:{view.result.nonce}") = {view.result.commit}
              </p>
            </details>
          </Card>
        </>
      )}

      <Card>
        <h3>{view.phase === "final" ? "Final stacks" : "Stacks"}</h3>
        <ul className="evidence">
          {[...view.players]
            .sort((a, b) => (view.chips[b.id] ?? 0) - (view.chips[a.id] ?? 0))
            .map((p) => (
              <li key={p.id}>
                <b>{p.name}</b>
                {p.id === you ? " (you)" : ""}: {view.chips[p.id]} chips
              </li>
            ))}
        </ul>
      </Card>
    </div>
  );
}

function Accuse({ view, you, value, onChange }: { view: RouletteView; you: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="field" htmlFor="accuse">
        Who’s the House? (+100 if you’re right)
      </label>
      <select id="accuse" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">No guess</option>
        {view.players
          .filter((p) => p.id !== you)
          .map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
      </select>
    </div>
  );
}

function HousePanel({ view, you, send }: { view: RouletteView; you: string; send: Props["send"] }) {
  const [accuse, setAccuse] = useState("");
  if (view.you.locked) {
    return (
      <Card tone="stage" className="center">
        <p className="lead">🏦 You’re the House. Locked in. Keep a straight face…</p>
      </Card>
    );
  }
  return (
    <Card tone="stage">
      <p className="sign">Top secret</p>
      <p className="lead space-top">
        🏦 You’re the <b>House</b> this spin. You win whatever they lose, and pay whatever they win.
      </p>
      <p>Lock in like everyone else (a decoy guess helps) so nobody can tell.</p>
      <div className="ask-form space-top">
        <Accuse view={view} you={you} value={accuse} onChange={setAccuse} />
        <Btn variant="gold" onClick={() => send({ t: "act", a: "lock", bets: [], ...(accuse ? { accuse } : {}) })}>
          Lock in
        </Btn>
      </div>
    </Card>
  );
}

function BetPanel({ view, you, send }: { view: RouletteView; you: string; send: Props["send"] }) {
  const [bets, setBets] = useState<RouletteBet[]>([]);
  const [stake, setStake] = useState(view.stakes[0] ?? 50);
  const [number, setNumber] = useState(17);
  const [accuse, setAccuse] = useState("");
  const chips = view.chips[you] ?? 0;
  const spent = bets.reduce((s, b) => s + b.amount, 0);
  const canAdd = bets.length < view.max_bets && spent + stake <= chips;
  const add = (b: Omit<RouletteBet, "amount">) => canAdd && setBets((x) => [...x, { ...b, amount: stake }]);
  if (view.you.locked) {
    return (
      <Card tone="soft" className="center">
        <h3>Locked in</h3>
        <p>{view.you.bets.length ? view.you.bets.map(describe).join(" · ") : "No bets this spin."}</p>
      </Card>
    );
  }
  return (
    <Card tone="soft">
      <h3>Your bets ({bets.length}/{view.max_bets})</h3>
      <div className="row" role="group" aria-label="Chip size">
        {view.stakes.map((s) => (
          <Btn key={s} size="small" variant="ghost" aria-pressed={stake === s} onClick={() => setStake(s)}>
            {s}
          </Btn>
        ))}
      </div>
      <div className="row space-top" role="group" aria-label="Outside bets">
        {OUTSIDE.map(([kind, label]) => (
          <Btn key={kind} size="small" variant={kind === "red" ? "danger" : "ghost"} disabled={!canAdd} onClick={() => add({ kind, value: null })}>
            {label}
          </Btn>
        ))}
        {[1, 2, 3].map((d) => (
          <Btn key={d} size="small" variant="ghost" disabled={!canAdd} onClick={() => add({ kind: "dozen", value: d })}>
            Dozen {d}
          </Btn>
        ))}
      </div>
      <div className="ask-form space-top">
        <div>
          <label className="field" htmlFor="roulette-number">
            Single number (35:1)
          </label>
          <select id="roulette-number" value={number} onChange={(e) => setNumber(Number(e.target.value))}>
            {Array.from({ length: 37 }, (_, n) => (
              <option key={n} value={n}>
                {n} ({color(n)})
              </option>
            ))}
          </select>
        </div>
        <Btn variant="ghost" disabled={!canAdd} onClick={() => add({ kind: "number", value: number })}>
          Bet on {number}
        </Btn>
      </div>
      {bets.length > 0 && (
        <ul className="evidence space-top">
          {bets.map((b, i) => (
            <li key={i}>
              {describe(b)}{" "}
              <Btn size="small" variant="ghost" aria-label={`Remove ${describe(b)}`} onClick={() => setBets((x) => x.filter((_, j) => j !== i))}>
                ✕
              </Btn>
            </li>
          ))}
        </ul>
      )}
      <div className="ask-form space-top">
        <Accuse view={view} you={you} value={accuse} onChange={setAccuse} />
        <Btn
          variant="accent"
          size="big"
          onClick={() => {
            sfx.pop();
            send({ t: "act", a: "lock", bets, ...(accuse ? { accuse } : {}) });
          }}
        >
          {bets.length ? `Lock in ${spent}` : "Lock in (no bets)"}
        </Btn>
      </div>
    </Card>
  );
}
