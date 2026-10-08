import { useEffect, useMemo, useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useReducedMotion, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { LudoColor, LudoLog, LudoView } from "../types";

interface Props {
  view: LudoView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const NAME: Record<LudoColor, string> = { red: "Red", green: "Green", yellow: "Yellow", blue: "Blue" };
const HOME = 56;
const YARD = -1;

// ---- board geometry (15 x 15 cells; [row, col]) ---------------------------------------------------
// The 52-square loop, clockwise from red's start square.
const TRACK: [number, number][] = [
  ...[1, 2, 3, 4, 5].map((c) => [6, c] as [number, number]),
  ...[5, 4, 3, 2, 1, 0].map((r) => [r, 6] as [number, number]),
  [0, 7],
  ...[0, 1, 2, 3, 4, 5].map((r) => [r, 8] as [number, number]),
  ...[9, 10, 11, 12, 13, 14].map((c) => [6, c] as [number, number]),
  [7, 14],
  ...[14, 13, 12, 11, 10, 9].map((c) => [8, c] as [number, number]),
  ...[9, 10, 11, 12, 13, 14].map((r) => [r, 8] as [number, number]),
  [14, 7],
  ...[14, 13, 12, 11, 10, 9].map((r) => [r, 6] as [number, number]),
  ...[5, 4, 3, 2, 1, 0].map((c) => [8, c] as [number, number]),
  [7, 0],
  [6, 0],
];
const START: Record<LudoColor, number> = { red: 0, green: 13, yellow: 26, blue: 39 };
const STARS = [8, 21, 34, 47];
const SAFE = new Set([...Object.values(START), ...STARS]);
const LANE: Record<LudoColor, [number, number][]> = {
  red: [1, 2, 3, 4, 5].map((c) => [7, c]),
  green: [1, 2, 3, 4, 5].map((r) => [r, 7]),
  yellow: [13, 12, 11, 10, 9].map((c) => [7, c]),
  blue: [13, 12, 11, 10, 9].map((r) => [r, 7]),
};
const CORNER: Record<LudoColor, [number, number]> = { red: [0, 0], green: [0, 9], yellow: [9, 9], blue: [9, 0] };
// Centre of each colour's home triangle, in board units (x, y).
const FINISH: Record<LudoColor, [number, number]> = { red: [6.55, 7.5], green: [7.5, 6.55], yellow: [8.45, 7.5], blue: [7.5, 8.45] };
const ALL: LudoColor[] = ["red", "green", "yellow", "blue"];

function trackSquare(color: LudoColor, pos: number): number | null {
  return pos >= 0 && pos <= 50 ? (START[color] + pos) % 52 : null;
}

/** Where a token sits, as the centre point (x, y) in board units. */
function spot(color: LudoColor, pos: number, token: number): [number, number] {
  if (pos === YARD) {
    const [r, c] = CORNER[color];
    return [c + 2 + (token % 2) * 2, r + 2 + Math.floor(token / 2) * 2];
  }
  if (pos === HOME) return FINISH[color];
  const [r, c] = pos <= 50 ? TRACK[trackSquare(color, pos)!]! : LANE[color][pos - 51]!;
  return [c + 0.5, r + 0.5];
}

// ---- the hop animation: tokens step one square at a time towards where the server says they are ----
type Spots = Record<string, number[]>;

function useHops(teams: LudoView["teams"]): Spots {
  const reduced = useReducedMotion();
  const target = useMemo(() => Object.fromEntries(teams.map((t) => [t.color, t.tokens])) as Spots, [teams]);
  const key = JSON.stringify(target);
  const [shown, setShown] = useState<Spots>(target);
  useEffect(() => {
    if (reduced) {
      setShown(target);
      return;
    }
    const id = window.setInterval(() => {
      setShown((prev) => {
        const next: Spots = {};
        let hopping = false;
        let changed = false;
        for (const [c, want] of Object.entries(target)) {
          next[c] = want.map((t, i) => {
            const s = prev[c]?.[i] ?? t;
            if (s >= 0 && t > s) {
              hopping = changed = true;
              return s + 1;
            }
            return s;
          });
        }
        // Tokens leaving the yard or sent back to it jump once the movers have landed.
        if (!hopping) {
          for (const [c, want] of Object.entries(target)) {
            next[c] = want.map((t, i) => {
              if (next[c]![i] !== t) changed = true;
              return t;
            });
          }
        }
        if (!changed) window.clearInterval(id);
        return changed ? next : prev;
      });
    }, 170);
    return () => window.clearInterval(id);
  }, [key, reduced]);
  return shown;
}

export function Ludo({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const shown = useHops(view.teams);
  const mine = !tv ? view.you : null;
  const myTurn = !!mine && view.turn === you && view.phase === "play";
  const name = (id: string) => (id === you && !tv ? "You" : nameOf(view.players, id));
  const last = view.log.at(-1);
  const lastRoll = [...view.log].reverse().find((e) => e.type === "roll");

  // Hop sounds follow the animation; stingers follow the public log, so every screen reacts alike.
  useOnChange(JSON.stringify(shown), () => sfx.hop());
  useOnChange(last?.n ?? 0, (prev) => {
    for (const e of view.log.filter((l) => l.n > prev)) react(e);
  });
  function react(e: LudoLog) {
    if (e.type === "roll") sfx.rattle();
    else if (e.type === "capture") {
      sfx.buzz();
      show.stinger(e.victims.length > 1 ? "DOUBLE KNOCKOUT!" : "KNOCKED OUT!", "bad");
    } else if (e.type === "home") {
      sfx.ding();
      show.stinger("HOME!");
    } else if (e.type === "bust") {
      sfx.buzz();
      show.stinger("THREE SIXES! TURN LOST", "bad");
    } else if (e.type === "again" && rollBefore(view.log, e.n) === 6) {
      show.stinger("SIX!");
    } else if (e.type === "win") {
      sfx.fanfare();
      show.stinger(`${NAME[e.color].toUpperCase()} WINS!`);
      show.celebrate();
    }
  }
  useOnChange(myTurn, (_, now) => {
    if (now) sfx.ding();
  });

  const team = (c: LudoColor | null) => view.teams.find((t) => t.color === c);
  const who = (c: LudoColor) => team(c)?.members.map((p) => nameOf(view.players, p)) ?? [];
  const turnTeam = team(view.turn_color);
  const sign =
    view.phase === "final"
      ? `${NAME[view.winner ?? "red"]} wins!`
      : myTurn
        ? view.rolled === null
          ? "Your turn: roll!"
          : "Your turn: pick a token"
        : `${NAME[view.turn_color ?? "red"]}’s turn · ${nameOf(view.players, view.turn ?? "")}`;

  return (
    <div className={`seg-ludo stack ludo-now-${view.turn_color ?? view.winner ?? "red"}`}>
      {show.node}
      <ShowHead sign={sign} title="Ludo" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">Six to get out · stars are safe</span>
      </ShowHead>

      <div className="ludo-layout">
        <div className="ludo-frame">
          <Board view={view} shown={shown} pick={myTurn ? (t) => send({ t: "act", a: "move", token: t }) : null} />
        </div>

        <div className="ludo-side">
          {view.phase === "play" && turnTeam && (
            <Card tone={myTurn ? "soft" : "plain"} className={`ludo-turn ${myTurn ? "mine" : ""}`}>
              <div className="ludo-turn-row">
                <Die value={lastRoll?.type === "roll" ? lastRoll.value : null} roll={lastRoll?.n ?? 0} color={lastRoll?.color ?? view.turn_color!} />
                {myTurn && view.rolled === null ? (
                  <Btn
                    variant="gold"
                    size="big"
                    className="grow ludo-roll"
                    onClick={() => send({ t: "act", a: "roll" })}
                  >
                    🎲 Roll!
                  </Btn>
                ) : (
                  <div className="grow">
                    <p className="ludo-turn-who">
                      <span className={`ludo-dot c-${view.turn_color}`} aria-hidden="true" />
                      <b>{myTurn ? "Your turn" : name(view.turn ?? "")}</b>
                    </p>
                    <p className="muted">{turnLine(view, myTurn, lastRoll)}</p>
                    {lastRoll?.type === "roll" && lastRoll.color !== view.turn_color && (
                      <p className="muted ludo-prev">
                        {name(lastRoll.player)} rolled {lastRoll.value}
                        {view.log.some((l) => l.n > lastRoll.n && l.type === "stuck") ? ": no move" : ""}
                      </p>
                    )}
                  </div>
                )}
              </div>
              {myTurn && view.rolled !== null && (
                <ul className="ludo-moves space-top" aria-label="Pick a token to move">
                  {choices(view, mine!).map((i) => (
                    <li key={i}>
                      <Btn variant="accent" block onClick={() => send({ t: "act", a: "move", token: i })}>
                        Token {i + 1}
                        <small>{moveHint(view, mine!, i, view.rolled!)}</small>
                      </Btn>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}

          {view.phase === "final" && view.winner && (
            <Card tone="soft" className="center ludo-winner">
              <p className="sign">🏁 Every token home</p>
              <h3>
                <span className={`ludo-dot c-${view.winner}`} aria-hidden="true" /> {NAME[view.winner]} wins!
              </h3>
              <p className="ludo-names">
                {who(view.winner).map((n, i) => (
                  <span key={i} className="nm">
                    {n}
                  </span>
                ))}
              </p>
            </Card>
          )}

          <Teams view={view} you={you} tv={tv} />
        </div>
        <Log view={view} name={name} lines={tv ? 5 : 6} />
      </div>
    </div>
  );
}

/** Movable tokens, one per square: tokens in the yard (or sharing a square) are the same move. */
function choices(view: LudoView, color: LudoColor): number[] {
  const tokens = view.teams.find((t) => t.color === color)?.tokens ?? [];
  return view.movable.filter((i) => view.movable.findIndex((j) => tokens[j] === tokens[i]) === view.movable.indexOf(i));
}

function rollBefore(log: LudoLog[], n: number): number | null {
  const r = [...log].reverse().find((l) => l.type === "roll" && l.n < n);
  return r?.type === "roll" ? r.value : null;
}

function turnLine(view: LudoView, myTurn: boolean, lastRoll: LudoLog | undefined): string {
  const rolled = lastRoll?.type === "roll" && lastRoll.player === view.turn ? lastRoll.value : null;
  if (view.rolled !== null) return myTurn ? `You rolled ${view.rolled}.` : `Rolled ${view.rolled}: choosing…`;
  if (view.sixes > 0) return myTurn ? `${sixes(view.sixes)}: roll again!` : `${sixes(view.sixes)}: rolling again…`;
  if (rolled !== null && myTurn) return "Roll again!";
  return myTurn ? "Roll the die." : "Rolling…";
}

function sixes(n: number): string {
  return n === 1 ? "A six" : "Two sixes";
}

/** What moving this token would do, for the move buttons. */
function moveHint(view: LudoView, color: LudoColor, i: number, roll: number): string {
  const from = view.teams.find((t) => t.color === color)!.tokens[i]!;
  const to = from === YARD ? 0 : from + roll;
  if (to === HOME) return "Home!";
  if (from === YARD) return "Out of the yard";
  const sq = trackSquare(color, to);
  if (sq !== null && !SAFE.has(sq)) {
    const hit = view.teams.find((t) => t.color !== color && t.tokens.some((p) => trackSquare(t.color, p) === sq));
    if (hit) return `Knock out ${NAME[hit.color]}`;
  }
  if (sq !== null && SAFE.has(sq)) return "To a safe square";
  return to > 50 ? "Up the home column" : `${HOME - to} to go`;
}

/** A die face: pips on a 3 x 3 grid. It tumbles each time a new roll lands. */
function Die({ value, roll, color }: { value: number | null; roll: number; color: LudoColor }) {
  return (
    <span key={roll} className={`ludo-die c-${color} f-${value ?? 0} ${value ? "rolled" : ""}`} role="img" aria-label={value ? `Die shows ${value}` : "Die"}>
      {Array.from({ length: 9 }, (_, i) => (
        <i key={i} className={`p${i}`} />
      ))}
    </span>
  );
}

function Board({ view, shown, pick }: { view: LudoView; shown: Spots; pick: ((token: number) => void) | null }) {
  const lit = new Set(view.movable);
  // Tokens sharing a square shrink and fan out so each stays visible.
  const tokens = view.teams.flatMap((t) => (shown[t.color] ?? t.tokens).map((pos, i) => ({ color: t.color, pos, i, at: spot(t.color, pos, i) })));
  const groups = new Map<string, number>();
  const placed = tokens.map((tk) => {
    const k = tk.at.join(",");
    const idx = groups.get(k) ?? 0;
    groups.set(k, idx + 1);
    return { ...tk, k, idx };
  });
  const summary = view.teams
    .map((t) => {
      const home = t.tokens.filter((p) => p === HOME).length;
      const yard = t.tokens.filter((p) => p === YARD).length;
      return `${NAME[t.color]}: ${home} home, ${t.tokens.length - home - yard} on the board, ${yard} in the yard`;
    })
    .join(". ");

  return (
    <svg className="ludo-board" viewBox="-0.15 -0.15 15.3 15.3" role="img" aria-label={`Ludo board. ${summary}.`}>
      <rect className="lb-paper" x={-0.15} y={-0.15} width={15.3} height={15.3} rx={0.5} />
      {ALL.map((c) => {
        const [r, col] = CORNER[c];
        return (
          <g key={c} className={`c-${c}`}>
            <rect className="lb-yard" x={col} y={r} width={6} height={6} rx={0.35} />
            <rect className="lb-yard-in" x={col + 0.9} y={r + 0.9} width={4.2} height={4.2} rx={0.5} />
            {[0, 1, 2, 3].map((i) => {
              const [x, y] = spot(c, YARD, i);
              return <circle key={i} className="lb-nest" cx={x} cy={y} r={0.62} />;
            })}
          </g>
        );
      })}
      {TRACK.map(([r, c], sq) => {
        const owner = ALL.find((col) => START[col] === sq);
        return (
          <g key={sq}>
            <rect className={`lb-sq ${owner ? `lb-start c-${owner}` : ""}`} x={c} y={r} width={1} height={1} />
            {STARS.includes(sq) && <path className="lb-star" d={star(c + 0.5, r + 0.5)} />}
            {owner && <path className="lb-star on-start" d={star(c + 0.5, r + 0.5)} />}
          </g>
        );
      })}
      {ALL.map((c) =>
        LANE[c].map(([r, col], i) => <rect key={`${c}${i}`} className={`lb-sq lb-lane c-${c}`} x={col} y={r} width={1} height={1} />),
      )}
      <polygon className="lb-tri c-red" points="6,6 6,9 7.5,7.5" />
      <polygon className="lb-tri c-green" points="6,6 9,6 7.5,7.5" />
      <polygon className="lb-tri c-yellow" points="9,6 9,9 7.5,7.5" />
      <polygon className="lb-tri c-blue" points="6,9 9,9 7.5,7.5" />
      {placed.map(({ color, pos, i, at, k, idx }) => {
        const n = groups.get(k) ?? 1;
        const scale = n > 1 ? 0.62 : 1;
        const dx = n > 1 ? (idx % 2 ? 0.2 : -0.2) : 0;
        const dy = n > 1 ? (idx > 1 ? 0.2 : n > 2 ? -0.2 : 0) : 0;
        const can = pick && color === view.turn_color && lit.has(i);
        return (
          <g
            key={`${color}${i}`}
            className={`lb-token c-${color} ${can ? "lit" : ""}`}
            transform={`translate(${at[0] + dx} ${at[1] + dy}) scale(${scale})`}
            onClick={can ? () => pick(i) : undefined}
          >
            <g key={pos} className="lb-hop">
              <ellipse className="lb-shadow" cx={0} cy={0.3} rx={0.36} ry={0.12} />
              <circle className="lb-ring" r={0.52} />
              <circle className="lb-body" r={0.38} />
              <circle className="lb-cap" r={0.2} cy={-0.06} />
              <text className="lb-num" y={0.13}>
                {i + 1}
              </text>
            </g>
          </g>
        );
      })}
    </svg>
  );
}

/** A five-point star (or the start squares' badge), centred on (x, y), in board units. */
function star(x: number, y: number): string {
  const pts: string[] = [];
  for (let k = 0; k < 10; k++) {
    const r = k % 2 ? 0.16 : 0.38;
    const a = (Math.PI / 5) * k - Math.PI / 2;
    pts.push(`${(x + r * Math.cos(a)).toFixed(3)},${(y + r * Math.sin(a)).toFixed(3)}`);
  }
  return `M${pts.join("L")}Z`;
}

function Teams({ view, you, tv }: { view: LudoView; you: string; tv: boolean }) {
  return (
    <Card className="ludo-teams-card">
      <h3>{view.teams.some((t) => t.members.length > 1) ? "Teams" : "Players"}</h3>
      <ul className="ludo-teams">
        {view.teams.map((t) => {
          const home = t.tokens.filter((p) => p === HOME).length;
          const yard = t.tokens.filter((p) => p === YARD).length;
          return (
            <li key={t.color} className={`${t.color === view.turn_color ? "on" : ""} ${t.color === view.winner ? "won" : ""}`}>
              <span className={`ludo-dot c-${t.color}`} aria-hidden="true" />
              <div className="grow">
                <p className="ludo-names">
                  {t.members.map((p) => (
                    <span key={p} className={`nm ${p === view.turn ? "rolling" : ""}`}>
                      {nameOf(view.players, p)}
                    </span>
                  ))}
                </p>
                <p className="muted ludo-count">
                  <span>
                    {NAME[t.color]}
                    {t.members.includes(you) && !tv ? " (you)" : ""}
                  </span>
                  <span>{home} home</span>
                  <span>{t.tokens.length - home - yard} out</span>
                  <span>{yard} in yard</span>
                </p>
              </div>
              <b className="ludo-pts">{t.points}</b>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function logLine(e: LudoLog, who: (id: string) => string): string | null {
  switch (e.type) {
    case "roll":
      return `${who(e.player)} rolled ${e.value}`;
    case "move":
      if (e.from === YARD) return `${NAME[e.color]} ${e.token + 1} came out`;
      return e.to === HOME ? null : `${NAME[e.color]} ${e.token + 1} moved ${e.to - e.from}`;
    case "capture":
      return `${who(e.player)} knocked out ${e.victims.map((v) => `${NAME[v.color]} ${v.token + 1}`).join(" and ")}!`;
    case "home":
      return `${NAME[e.color]} ${e.token + 1} reached home!`;
    case "stuck":
      return `${who(e.player)} couldn’t move`;
    case "bust":
      return `${who(e.player)} rolled three 6s: turn lost`;
    case "timeout":
      return `${who(e.player)} ran out of time`;
    case "win":
      return `${NAME[e.color]} wins!`;
    default:
      return null;
  }
}

function Log({ view, name, lines: shown }: { view: LudoView; name: (id: string) => string; lines: number }) {
  const lines = view.log.map((e) => [e.n, logLine(e, name)] as const).filter((l): l is readonly [number, string] => !!l[1]);
  return (
    <Card>
      <h3>What just happened</h3>
      {!lines.length && <p className="muted">Nothing yet. First roll coming up!</p>}
      <ol className="lc-log">
        {lines
          .slice(-shown)
          .reverse()
          .map(([n, l]) => (
            <li key={n}>{l}</li>
          ))}
      </ol>
    </Card>
  );
}
