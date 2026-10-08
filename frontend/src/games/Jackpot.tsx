import { useState } from "react";
import { Btn, Card, ShowHead, money, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { JackpotView } from "../types";

interface Props {
  view: JackpotView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen (TV or audience) */
  tv?: boolean;
}

export function Jackpot({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  useOnChange(view.phase, (_, phase) => {
    if (phase !== "final" || !view.result) return;
    const mine = view.result.deltas[you];
    if (!tv && mine !== undefined && mine > 0) {
      sfx.fanfare();
      show.stinger("JACKPOT!");
      show.celebrate();
    } else if (!tv && mine !== undefined && mine < 0) {
      sfx.buzz();
      show.stinger("OUCH!", "bad");
    } else {
      sfx.fanfare();
      show.stinger(view.result.answer === "higher" ? "HIGHER!" : "LOWER!");
    }
  });
  return (
    <div className="seg-jackpot stack">
      {show.node}
      <ShowHead
        sign={view.phase === "wager" ? "Final wager · bets are secret" : "The jackpot is settled"}
        title="Jackpot Round"
        remaining={view.remaining}
        receivedAt={receivedAt}
      />
      <Card tone="stage" className="prize">
        <span className="emoji" aria-hidden="true">
          {view.item.emoji}
        </span>
        <h3>{view.item.name}</h3>
        <p>{view.item.blurb}</p>
        <p className="space-top">
          The tag says <span className="price-tag">{money(view.tag)}</span>
        </p>
        <p className="muted">It’s wrong on purpose. Is the real price higher or lower?</p>
      </Card>
      {view.phase === "wager" ? (
        tv || !(you in view.stakes) ? (
          <Card tone="soft" className="center">
            <p className="lead" aria-live="polite">
              {view.locked.length} of {view.players.length} wagers locked in
            </p>
            <p className="muted">Right doubles the stake back. Wrong loses it.</p>
          </Card>
        ) : (
          <WagerForm view={view} send={send} />
        )
      ) : (
        view.result && <Reveal view={view} you={you} />
      )}
    </div>
  );
}

function WagerForm({ view, send }: { view: JackpotView; send: Props["send"] }) {
  const [amount, setAmount] = useState(() => view.you?.amount ?? Math.round(view.cap / 2));
  const mine = view.you;
  const quick: [string, number][] = [
    ["Nothing", 0],
    ["A quarter", Math.floor(view.cap / 4)],
    ["Half", Math.floor(view.cap / 2)],
    ["All in", view.cap],
  ];
  return (
    <Card tone="soft" aria-labelledby="wager-h">
      <h3 id="wager-h">Your secret wager</h3>
      <p className="muted">
        Bet up to <b>{view.cap}</b> points (your show score, or 200 if that’s less). Nobody sees it until the
        reveal.
      </p>
      <label className="field space-top" htmlFor="wager-range">
        Stake: <b>{amount}</b> points
      </label>
      <input
        id="wager-range"
        type="range"
        min={0}
        max={view.cap}
        step={Math.max(1, Math.round(view.cap / 100))}
        value={amount}
        onChange={(e) => setAmount(Number(e.target.value))}
      />
      <div className="row space-top" role="group" aria-label="Quick stakes">
        {quick.map(([label, n]) => (
          <Btn key={label} size="small" variant="ghost" aria-pressed={amount === n} onClick={() => setAmount(n)}>
            {label}
          </Btn>
        ))}
      </div>
      <div className="call-row space-top" role="group" aria-label="Make your call">
        {(["higher", "lower"] as const).map((call) => (
          <Btn
            key={call}
            variant={call === "higher" ? "go" : "danger"}
            size="big"
            aria-pressed={mine?.call === call && mine.amount === amount}
            onClick={() => {
              sfx.pop();
              send({ t: "act", a: "wager", amount, call });
            }}
          >
            {/* gap from .btn, not a space: the arrow never wraps onto its own line */}
            <span aria-hidden="true">{call === "higher" ? "⬆" : "⬇"}</span>
            <span>{call === "higher" ? "Higher" : "Lower"}</span>
          </Btn>
        ))}
      </div>
      <p className="center muted space-top" aria-live="polite">
        {mine
          ? `Locked: ${mine.amount} on ${mine.call}. You can change it until time runs out.`
          : `${view.locked.length} of ${view.players.length} wagers in`}
      </p>
    </Card>
  );
}

function Reveal({ view, you }: { view: JackpotView; you: string }) {
  const r = view.result!;
  const order = [...view.players].sort((a, b) => (r.deltas[b.id] ?? 0) - (r.deltas[a.id] ?? 0));
  return (
    <>
      <Card tone="stage" className="center">
        <p className="sign">The real price</p>
        <p className="space-top">
          <span className="price-tag big">{money(r.price)}</span>
        </p>
        <p className="lead space-top">
          It was <b>{r.answer.toUpperCase()}</b> than {money(view.tag)}.
        </p>
      </Card>
      <Card aria-labelledby="wagers-h">
        <h3 id="wagers-h">The wagers</h3>
        <ul className="evidence">
          {order.map((p) => {
            const w = r.wagers[p.id];
            const d = r.deltas[p.id] ?? 0;
            return (
              <li key={p.id}>
                <b>{nameOf(view.players, p.id)}</b>
                {p.id === you ? " (you)" : ""}:{" "}
                {w && w.amount > 0 ? `${w.amount} on ${w.call}` : "sat it out"}{" "}
                <span className={`chip ${d > 0 ? "teal" : d < 0 ? "cherry" : ""}`}>
                  {d > 0 ? "+" : ""}
                  {d}
                </span>
              </li>
            );
          })}
        </ul>
      </Card>
    </>
  );
}
