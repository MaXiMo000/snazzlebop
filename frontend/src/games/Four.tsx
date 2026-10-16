import { Avatar } from "../components/avatar";
import { Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { FourView } from "../types";

interface Props {
  view: FourView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const SIDE = ["Red", "Yellow"] as const;
const COLS = 7;
const ROWS = 6;

export function Four({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const me = tv ? null : view.you;
  const name = (pid: string) => (pid === you && !tv ? "You" : nameOf(view.players, pid));
  const myTurn = !!me?.turn;

  useOnChange(view.last ? `${view.round}:${view.last.col}:${view.last.row}` : "", (_, now) => {
    if (now) sfx.pop();
  });
  useOnChange(myTurn, (was, now) => {
    if (now && !was) sfx.ding();
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "over") {
      if (view.winner === null) show.stinger("IT'S A DRAW!");
      else if (!tv && me?.side === view.winner) {
        sfx.fanfare();
        show.stinger("FOUR IN A ROW!");
        show.celebrate();
      } else {
        sfx.buzz();
        show.stinger(`${SIDE[view.winner]!.toUpperCase()} WINS!`, me && me.side !== view.winner ? "bad" : "good");
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.celebrate();
    }
  });

  const win = new Set(view.line.map(([c, r]) => `${c}:${r}`));
  const lastKey = view.last ? `${view.last.col}:${view.last.row}` : "";
  const status =
    view.phase === "final"
      ? "Final scores"
      : view.phase === "over"
        ? view.winner === null
          ? "Draw"
          : `${SIDE[view.winner]} wins the round`
        : `${SIDE[view.turn]} to play`;
  const sign = view.phase === "final" ? status : `Round ${view.round} of ${view.rounds} · ${status}`;

  return (
    <div className={`seg-four stack c4 ${tv ? "big" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Four in a Row" remaining={view.phase === "play" ? view.remaining : null} receivedAt={receivedAt}>
        <p className="c4-series" aria-label={`Rounds won: Red ${view.wins[0]}, Yellow ${view.wins[1]}`}>
          <span className="c4-pip s0" aria-hidden="true" />
          <b>{view.wins[0]}</b>
          <span aria-hidden="true">–</span>
          <b>{view.wins[1]}</b>
          <span className="c4-pip s1" aria-hidden="true" />
        </p>
      </ShowHead>

      <div className="c4-layout">
        <div className="c4-board-col">
          {view.phase === "play" && (
            <p className={`c4-turn s${view.turn} ${myTurn ? "mine" : ""}`} aria-live="polite">
              <span className={`c4-pip s${view.turn}`} aria-hidden="true" />
              {myTurn ? "Your turn: tap a column!" : view.mover ? `${name(view.mover)}’s turn (${SIDE[view.turn]})` : ""}
            </p>
          )}
          <div className={`c4-board ${myTurn ? `armed s${view.turn}` : ""}`} role="group" aria-label="Board: 7 columns">
            {Array.from({ length: COLS }, (_, c) => {
              const height = view.grid.filter((row) => row[c] !== null).length;
              const full = height >= ROWS;
              const cells = Array.from({ length: ROWS }, (_, i) => {
                const r = ROWS - 1 - i; // top row first
                const v = view.grid[r]![c];
                const key = `${c}:${r}`;
                return (
                  <span key={r} className={`c4-hole ${r === height && myTurn ? "next" : ""}`}>
                    {v !== null && v !== undefined && (
                      <span className={`c4-disc s${v} ${key === lastKey ? `drop r${r}` : ""} ${win.has(key) ? "win" : ""}`} />
                    )}
                  </span>
                );
              });
              const label = `Column ${c + 1}${full ? ", full" : `, ${ROWS - height} free`}`;
              return myTurn && !full ? (
                <button key={c} type="button" className="c4-col" aria-label={label} onClick={() => send({ t: "act", a: "drop", col: c })}>
                  {cells}
                </button>
              ) : (
                <div key={c} className="c4-col" role="img" aria-label={label}>
                  {cells}
                </div>
              );
            })}
          </div>
        </div>

        <div className="stack c4-side">
          <Sides view={view} you={you} tv={tv} />
          {view.phase !== "play" && (
            <Card tone="stage" className="center">
              <p className="sign">{view.phase === "final" ? "The match" : "The round"}</p>
              <h3 className="space-top">
                {view.phase === "final"
                  ? view.wins[0] === view.wins[1]
                    ? "All square!"
                    : `${SIDE[view.wins[0] > view.wins[1] ? 0 : 1]} wins the match ${Math.max(...view.wins)}–${Math.min(...view.wins)}!`
                  : view.winner === null
                    ? "The board is full: a draw."
                    : `${SIDE[view.winner]} lined up four!`}
              </h3>
            </Card>
          )}
          <Card>
            <h3>{view.phase === "final" ? "Final scores" : "Scores"}</h3>
            <ul className="score-rows">
              {[...view.players]
                .sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0))
                .map((p) => (
                  <li key={p.id}>
                    <b>
                      {p.name}
                      {p.id === you && !tv ? " (you)" : ""}
                    </b>
                    <span className="score-pts">{view.scores[p.id] ?? 0}</span>
                  </li>
                ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Sides({ view, you, tv }: { view: FourView; you: string; tv: boolean }) {
  return (
    <div className="c4-sides">
      {view.sides.map((members, s) => (
        <Card key={s} className={`c4-sidecard s${s} ${view.phase === "play" && view.turn === s ? "active" : ""}`}>
          <p className="c4-sidename">
            <span className={`c4-pip s${s}`} aria-hidden="true" /> {SIDE[s]}
          </p>
          <ul className="c4-members">
            {members.map((pid) => (
              <li key={pid} className={view.mover === pid ? "up" : ""}>
                <Avatar pid={pid} name={nameOf(view.players, pid)} />
                <span>
                  {nameOf(view.players, pid)}
                  {pid === you && !tv ? " (you)" : ""}
                </span>
                {view.mover === pid && <span className="sr-only">, to move</span>}
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}
