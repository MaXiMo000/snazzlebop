import { useEffect, useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { ChickenView } from "../types";

interface Props {
  view: ChickenView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

/** The pot right now, computed on this device from the server's start offset (no countdown is sent). */
function useLiveValue(view: ChickenView, receivedAt: number): number {
  const [now, setNow] = useState(performance.now());
  const running = view.phase === "run" && view.started_ago !== null;
  useEffect(() => {
    if (!running) return;
    let raf = 0;
    const step = () => {
      setNow(performance.now());
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [running]);
  if (!running) return 0;
  const t = view.started_ago! + Math.max(0, now - receivedAt) / 1000;
  return Math.floor(view.base * view.growth ** t);
}

export function Chicken({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const value = useLiveValue(view, receivedAt);
  const mine = view.cashed[you];
  useOnChange(view.phase, (_, phase) => {
    if (phase === "run") sfx.ding();
    if (phase === "boom" && view.result) {
      sfx.buzz();
      show.stinger("KABOOM!", tv || view.result.boomed.includes(you) ? "bad" : "good");
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("WHAT A RIDE!");
      show.celebrate();
    }
  });
  const sign =
    view.phase === "final"
      ? "Final scores"
      : `Round ${view.round} of ${view.rounds} · ${{ ready: "Get ready", run: "RUN!", boom: "Boom" }[view.phase as "ready" | "run" | "boom"] ?? ""}`;
  return (
    <div className="seg-chicken stack">
      {show.node}
      <ShowHead sign={sign} title="Chicken Run" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">Cash out before the hidden bomb · biggest cash-out +50</span>
      </ShowHead>

      {view.phase === "ready" && (
        <Card tone="stage" className="center">
          <p className="sign">Get ready</p>
          <p className="lead space-top">The pot starts climbing in a moment. The bomb could go off any time after 4 seconds.</p>
        </Card>
      )}
      {view.phase === "ready" && !tv && <Tricks view={view} you={you} send={send} />}

      {view.phase === "run" && !tv && view.you.fused && !mine && (
        <p className="chip cherry wrap">⚠️ Someone shortened your fuse! Your bomb goes off early.</p>
      )}
      {view.phase === "run" && (
        <Card tone="stage" className="center chicken-run">
          <p className="sign">The pot</p>
          <p className="chicken-value" aria-hidden="true">
            {value}
          </p>
          <p className="sr-only">The pot is climbing. Cash out before the bomb.</p>
          {!tv &&
            (mine ? (
              <p className="lead">
                You banked <b>{mine.value}</b> at {mine.t.toFixed(1)}s. Now watch the others sweat.
              </p>
            ) : (
              <Btn
                variant="gold"
                size="big"
                className="cash-out"
                onClick={() => {
                  sfx.pop();
                  send({ t: "act", a: "cash" });
                }}
              >
                Cash out!
              </Btn>
            ))}
        </Card>
      )}

      {view.phase === "boom" && view.result && (
        <Card tone="stage" className="center">
          <p className="sign">Kaboom</p>
          <p className="lead space-top">
            The bomb went off at <b>{view.result.bomb.toFixed(1)}s</b> (the pot was {view.result.bomb_value}).
          </p>
          <p>
            {view.result.boomed.length
              ? `Blown up: ${view.result.boomed.map((p) => nameOf(view.players, p)).join(", ")}.`
              : "Everybody got out in time!"}
            {view.result.nerve ? ` Nerves of steel: ${nameOf(view.players, view.result.nerve)} (+50).` : ""}
          </p>
          {Object.entries(view.result.payouts).map(([p, pts]) => (
            <p key={p}>
              🛟 {nameOf(view.players, p)}’s insurance paid {pts}.
            </p>
          ))}
          {Object.entries(view.result.saboteurs).map(([target, by]) => (
            <p key={target}>
              🧨 {by.map((p) => nameOf(view.players, p)).join(" & ")} shortened {nameOf(view.players, target)}’s fuse (it blew at{" "}
              {view.result!.fuses[target]?.toFixed(1)}s).
            </p>
          ))}
        </Card>
      )}

      {view.phase !== "final" && (
        <Card>
          <h3>Who’s out</h3>
          <ul className="evidence" aria-live="polite">
            {view.players.map((p) => {
              const c = view.cashed[p.id];
              const boomed = view.result?.boomed.includes(p.id);
              return (
                <li key={p.id}>
                  <b>{p.name}</b>
                  {p.id === you ? " (you)" : ""}:{" "}
                  {c ? `banked ${c.value} at ${c.t.toFixed(1)}s` : boomed ? "💥 blown up" : view.phase === "run" ? "still in…" : "waiting"}
                  {view.insured.includes(p.id) ? " · 🛟 insured" : ""}
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {view.phase === "final" && (
        <Card>
          <h3>Every round</h3>
          <ol className="evidence">
            {(view.history ?? []).map((h, i) => (
              <li key={i}>
                Bomb at {h.bomb.toFixed(1)}s ·{" "}
                {Object.entries(h.cashed)
                  .sort((a, b) => b[1].value - a[1].value)
                  .map(([p, c]) => `${nameOf(view.players, p)} ${c.value}`)
                  .join(", ") || "nobody got out"}
                {h.boomed.length ? ` · boom: ${h.boomed.map((p) => nameOf(view.players, p)).join(", ")}` : ""}
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}

/** Before the run: buy insurance, or shorten a rival's fuse (once a game). */
function Tricks({ view, you, send }: { view: ChickenView; you: string; send: Props["send"] }) {
  const insured = view.insured.includes(you);
  return (
    <Card tone="soft">
      <h3>Dirty tricks</h3>
      <div className="row">
        <Btn variant="ghost" disabled={insured} onClick={() => send({ t: "act", a: "insure" })}>
          {insured ? "🛟 Insured" : `🛟 Insure (−${view.costs.insure})`}
        </Btn>
      </div>
      <p className="muted">Blow up this round and still keep 25% of the pot.</p>
      {view.you.fuse_used ? (
        <p className="muted space-top">You’ve used your short fuse this game.</p>
      ) : (
        <>
          <p className="space-top">
            🧨 Shorten a rival’s fuse (−{view.costs.fuse}, once a game). Their bomb goes off early:
          </p>
          <div className="row" role="group" aria-label="Shorten whose fuse">
            {view.players
              .filter((p) => p.id !== you)
              .map((p) => (
                <Btn key={p.id} size="small" variant="ghost" onClick={() => send({ t: "act", a: "fuse", target: p.id })}>
                  {p.name}
                </Btn>
              ))}
          </div>
        </>
      )}
    </Card>
  );
}
