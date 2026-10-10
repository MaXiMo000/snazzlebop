import { useEffect, useRef, useState } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useReducedMotion, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { SnakesView } from "../types";

interface Props {
  view: SnakesView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

/** The middle of a square on a 100 x 100 drawing (rows snake left-right, then right-left). */
function centre(n: number): [number, number] {
  const row = Math.floor((n - 1) / 10);
  const col = (n - 1) % 10;
  return [(row % 2 ? 9 - col : col) * 10 + 5, (9 - row) * 10 + 5];
}

function Ladder({ a, b }: { a: number; b: number }) {
  const [x1, y1] = centre(a);
  const [x2, y2] = centre(b);
  const len = Math.hypot(x2 - x1, y2 - y1);
  const px = (-(y2 - y1) / len) * 1.7; // across the ladder
  const py = ((x2 - x1) / len) * 1.7;
  const rungs = Math.max(2, Math.round(len / 5));
  return (
    <g className="sn-ladder">
      <line x1={x1 - px} y1={y1 - py} x2={x2 - px} y2={y2 - py} />
      <line x1={x1 + px} y1={y1 + py} x2={x2 + px} y2={y2 + py} />
      {Array.from({ length: rungs }, (_, i) => {
        const t = (i + 0.5) / rungs;
        const cx = x1 + (x2 - x1) * t;
        const cy = y1 + (y2 - y1) * t;
        return <line key={i} className="rung" x1={cx - px} y1={cy - py} x2={cx + px} y2={cy + py} />;
      })}
    </g>
  );
}

function Snake({ head, tail, tone }: { head: number; tail: number; tone: number }) {
  const [x1, y1] = centre(head);
  const [x2, y2] = centre(tail);
  const len = Math.hypot(x2 - x1, y2 - y1);
  const px = -(y2 - y1) / len;
  const py = (x2 - x1) / len;
  const waves = Math.max(1, Math.round(len / 14));
  const points = Array.from({ length: 41 }, (_, i) => {
    const t = i / 40;
    const sway = Math.sin(t * Math.PI * 2 * waves) * 2.6 * Math.sin(t * Math.PI); // still at both ends
    return `${(x1 + (x2 - x1) * t + px * sway).toFixed(2)},${(y1 + (y2 - y1) * t + py * sway).toFixed(2)}`;
  });
  return (
    <g className={`sn-snake c${tone % 4}`}>
      <polyline className="body" points={points.join(" ")} />
      <polyline className="belly" points={points.join(" ")} />
      <circle className="head" cx={x1} cy={y1} r={2.6} />
      <circle className="eye" cx={x1 - 0.9} cy={y1 - 0.7} r={0.55} />
      <circle className="eye" cx={x1 + 0.9} cy={y1 - 0.7} r={0.55} />
    </g>
  );
}

/** Tokens walk square by square, then ride the ladder or the snake in one long slide. */
function useWalk(view: SnakesView) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState<Record<string, number>>(view.pos);
  const [sliding, setSliding] = useState<string | null>(null);
  const seen = useRef(view.last?.n ?? 0);
  const last = view.last;
  useEffect(() => {
    if (!last || last.n === seen.current || reduced) {
      seen.current = last?.n ?? 0;
      setShown(view.pos);
      setSliding(null);
      return;
    }
    seen.current = last.n;
    const { player, mid, to, via } = last;
    let at = last.from;
    setSliding(null);
    setShown({ ...view.pos, [player]: at });
    const timers: number[] = [];
    const finish = () => {
      if (via) {
        setSliding(player);
        if (via === "ladder") sfx.fanfare();
        else sfx.buzz();
      }
      setShown((s) => ({ ...s, [player]: to }));
    };
    const step = () => {
      if (at >= mid) return finish();
      at += 1;
      sfx.hop();
      setShown((s) => ({ ...s, [player]: at }));
      timers.push(window.setTimeout(step, 130));
    };
    timers.push(window.setTimeout(step, 350)); // after the die has landed
    return () => timers.forEach((t) => window.clearTimeout(t));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [last?.n, reduced]);
  const moving = !!last && shown[last.player] !== view.pos[last.player];
  return { shown, sliding, moving };
}

export function Snakes({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const name = (pid: string) => nameOf(view.players, pid);
  const { shown, sliding, moving } = useWalk(view);
  const myTurn = !tv && view.phase === "play" && view.turn === you;
  const last = view.last;

  useOnChange(view.last?.n ?? 0, () => sfx.rattle());
  useOnChange(view.phase, (_, phase) => {
    if (phase !== "final") return;
    sfx.fanfare();
    show.stinger(view.winner === you && !tv ? "YOU'RE HOME!" : `${name(view.winner ?? "").toUpperCase()} WINS!`);
    if (view.winner === you && !tv) show.celebrate();
  });

  const sign =
    view.phase === "final"
      ? "Home!"
      : myTurn
        ? "Your turn · roll!"
        : `${name(view.turn ?? "")}’s turn`;
  const who = (pid: string) => (pid === you && !tv ? "You" : name(pid));
  const story = last
    ? `${who(last.player)} rolled ${last.die}${
        last.mid === last.from
          ? ": too many, staying put"
          : last.via === "ladder"
            ? ` · up the ladder to ${last.to}!`
            : last.via === "snake"
              ? ` · down the snake to ${last.to}!`
              : ` · now on ${last.to}`
      }`
    : "Roll to get going. First to 100 wins.";
  const waiting = view.order.filter((p) => (shown[p] ?? 0) === 0);

  return (
    <div className="seg-snakes stack sn">
      {show.node}
      <ShowHead sign={sign} title="Snakes and Ladders" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">First to 100 · a 6 rolls again</span>
      </ShowHead>

      <div className="sn-layout">
        <div className="sn-board-col">
          <div className="sn-frame">
            <div className="sn-board" aria-hidden="true">
              {Array.from({ length: 100 }, (_, i) => {
                const row = 9 - Math.floor(i / 10);
                const col = i % 10;
                const n = row * 10 + (row % 2 ? 9 - col : col) + 1;
                return (
                  <span key={n} className={`sn-sq ${(row + col) % 2 ? "alt" : ""} ${n === 100 ? "home" : ""}`}>
                    {n === 100 ? "🏁" : n}
                  </span>
                );
              })}
              <svg className="sn-art" viewBox="0 0 100 100" focusable="false">
                {view.ladders.map(([a, b]) => (
                  <Ladder key={a} a={a!} b={b!} />
                ))}
                {view.snakes.map(([head, tail], i) => (
                  <Snake key={head} head={head!} tail={tail!} tone={i} />
                ))}
              </svg>
              {view.order.map((pid, seat) => {
                const at = shown[pid] ?? 0;
                if (at === 0) return null;
                return (
                  <span
                    key={pid}
                    className={`sn-token sn-at-${at} sn-s${seat} ${sliding === pid ? "slide" : ""} ${pid === view.turn ? "now" : ""}`}
                  >
                    <Avatar pid={pid} name={name(pid)} tone={seat} className="sn-avatar" />
                  </span>
                );
              })}
            </div>
          </div>
          {waiting.length > 0 && (
            <p className="sn-start">
              <span className="muted">At the start:</span>{" "}
              {waiting.map((p) => (
                <span key={p} className="sn-start-chip">
                  <Avatar pid={p} name={name(p)} tone={view.order.indexOf(p)} /> {who(p).split(/\s+/)[0]}
                </span>
              ))}
            </p>
          )}
        </div>

        <div className="sn-side stack">
          <Card tone={myTurn ? "soft" : "plain"} className="sn-action center">
            <div className="sn-dice">
              {last && (
                <span key={last.n} className={`ludo-die f-${last.die} rolled`} aria-hidden="true">
                  {Array.from({ length: 9 }, (_, j) => (
                    <i key={j} className={`p${j}`} />
                  ))}
                </span>
              )}
              <p className="sn-story" role="status">
                {story}
              </p>
            </div>
            {view.phase === "play" &&
              (myTurn ? (
                <Btn
                  variant="go"
                  size="big"
                  block
                  disabled={moving}
                  onClick={() => {
                    sfx.pop();
                    send({ t: "act", a: "roll" });
                  }}
                >
                  🎲 Roll{view.sixes > 0 ? " again" : ""}
                </Btn>
              ) : (
                <p className="lead">
                  {tv ? "" : "Waiting for "}
                  <b>{name(view.turn ?? "")}</b>
                  {tv ? " to roll" : ""}
                </p>
              ))}
            {view.phase === "final" && (
              <h3 className="sn-winner">🏁 {view.winner === you && !tv ? "You made it home!" : `${name(view.winner ?? "")} made it home!`}</h3>
            )}
          </Card>

          <Card>
            <h3>{view.phase === "final" ? "Final scores" : "The race"}</h3>
            <ul className="score-rows">
              {[...view.order]
                .sort((a, b) => (view.scores ? (view.scores[b] ?? 0) - (view.scores[a] ?? 0) : (view.pos[b] ?? 0) - (view.pos[a] ?? 0)))
                .map((pid) => (
                  <li key={pid} className={pid === view.turn ? "on" : ""}>
                    <Avatar pid={pid} name={name(pid)} tone={view.order.indexOf(pid)} />
                    <b>
                      {pid === view.winner ? "👑 " : ""}
                      {name(pid)}
                      {pid === you && !tv ? " (you)" : ""}
                    </b>
                    <span className="score-pts">{view.scores ? (view.scores[pid] ?? 0) : view.pos[pid] ? `square ${view.pos[pid]}` : "start"}</span>
                  </li>
                ))}
            </ul>
          </Card>
        </div>
      </div>
      <p className="sr-only">
        {view.order.map((p) => `${name(p)} is on ${view.pos[p] ? `square ${view.pos[p]}` : "the start"}`).join(". ")}
      </p>
    </div>
  );
}
