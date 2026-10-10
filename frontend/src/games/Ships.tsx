import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { ShipsBoard, ShipsView } from "../types";

interface Props {
  view: ShipsView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const COLS = "ABCDEFGHIJ";
const cellName = (cell: number, size: number) => `${COLS[cell % size]}${Math.floor(cell / size) + 1}`;

/** One side's waters: shots taken there, sunk ships, and (for its own side) where the fleet sits. */
function Grid({
  board,
  size,
  label,
  last,
  onFire,
  small = false,
}: {
  board: ShipsBoard;
  size: number;
  label: string;
  last: number | null;
  onFire?: (cell: number) => void;
  small?: boolean;
}) {
  const ship = new Set((board.ships ?? []).flat());
  const sunk = new Set(board.sunk.flat());
  return (
    <div className={`sh-grid ${small ? "small" : ""} ${onFire ? "aim" : ""}`} role="group" aria-label={label}>
      {Array.from({ length: size * size }, (_, cell) => {
        const shot = board.shots[cell];
        const cls = [
          "sh-cell",
          ship.has(cell) ? "ship" : "",
          shot ?? "",
          sunk.has(cell) ? "sunk" : "",
          cell === last ? "last" : "",
        ].join(" ");
        const text = `${cellName(cell, size)}${sunk.has(cell) ? ", sunk" : shot ? `, ${shot}` : ship.has(cell) ? ", your ship" : ""}`;
        const mark = sunk.has(cell) ? "☠" : shot === "hit" ? "💥" : shot === "miss" ? "•" : "";
        return onFire && !shot ? (
          <button key={cell} type="button" className={cls} aria-label={`Fire at ${text}`} onClick={() => onFire(cell)} />
        ) : (
          <span key={cell} className={cls} role="img" aria-label={text}>
            <span key={shot ?? "none"} className="sh-mark" aria-hidden="true">
              {mark}
            </span>
          </span>
        );
      })}
    </div>
  );
}

export function Ships({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const name = (pid: string) => nameOf(view.players, pid);
  const mine = tv ? null : (view.you?.side ?? null);
  const foe = mine === null ? null : 1 - mine;
  const myShot = !tv && view.phase === "battle" && view.shooter === you;
  const last = view.last;

  useOnChange(last?.n ?? 0, () => {
    if (!last) return;
    if (last.result === "miss") sfx.pop();
    else if (last.result === "hit") sfx.buzz();
    else {
      sfx.fanfare();
      show.stinger("SUNK!", mine !== null && last.side === mine ? "bad" : "good");
    }
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "battle") {
      sfx.ding();
      show.stinger("BATTLE STATIONS!");
    } else if (phase === "final" && view.winner !== null) {
      const won = mine === view.winner;
      sfx.fanfare();
      show.stinger(mine === null ? `${view.side_names[view.winner]!.toUpperCase()} WINS!` : won ? "VICTORY!" : "FLEET LOST!", won || mine === null ? "good" : "bad");
      if (won) show.celebrate();
    }
  });

  const sideLabel = (s: number) => (view.sides[s]!.length === 1 ? name(view.sides[s]![0]!) : view.side_names[s]!);
  const sign =
    view.phase === "place"
      ? "Position your fleet"
      : view.phase === "final"
        ? "Battle over"
        : myShot
          ? "Your shot!"
          : `${name(view.shooter ?? "")} is aiming`;
  const story = last
    ? `${last.by === you && !tv ? "You" : name(last.by)} fired at ${cellName(last.cell, view.size)}: ${
        last.result === "miss" ? "splash, a miss" : last.result === "hit" ? "a hit!" : "hit and SUNK!"
      }`
    : view.phase === "battle"
      ? "First shot of the battle…"
      : "";
  const fire = (cell: number) => {
    sfx.tick();
    send({ t: "act", a: "fire", cell });
  };
  const lastOn = (s: number) => (last && last.side === s ? last.cell : null);
  const roster = (s: number) => (
    <span className="sh-roster">
      {view.sides[s]!.map((p) => (
        <span key={p} className={p === view.shooter ? "on" : ""}>
          {p === you && !tv ? "You" : name(p)}
        </span>
      ))}
    </span>
  );

  return (
    <div className={`seg-ships stack sh ${myShot ? "my-shot" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Battleships" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">Hit: fire again · sink all {view.fleet.length} to win</span>
      </ShowHead>

      {view.phase === "place" && mine !== null && (
        <Card tone="soft" className="sh-place">
          <h3>Your fleet</h3>
          <p className="muted">
            {view.boards[mine]!.ready ? "Locked in. Waiting for the other side…" : "Shuffle until you like it, then lock it in. The enemy can’t see this."}
          </p>
          <Grid board={view.boards[mine]!} size={view.size} label="Your fleet" last={null} />
          {!view.boards[mine]!.ready && (
            <div className="row center sh-buttons">
              <Btn
                variant="ghost"
                onClick={() => {
                  sfx.rattle();
                  send({ t: "act", a: "shuffle" });
                }}
              >
                🔀 Shuffle
              </Btn>
              <Btn variant="go" onClick={() => send({ t: "act", a: "ready" })}>
                ⚓ Lock it in
              </Btn>
            </div>
          )}
        </Card>
      )}
      {view.phase === "place" && (
        <Card tone="stage" className="center">
          {[0, 1].map((s) => (
            <p key={s} className="sh-ready">
              <b>{sideLabel(s)}</b>: {view.boards[s]!.ready ? "ready ✅" : "placing ships…"}
            </p>
          ))}
        </Card>
      )}

      {view.phase !== "place" && (
        <>
          {story && (
            <p key={last?.n ?? 0} className={`sh-story ${last?.result ?? ""}`} role="status">
              {story}
            </p>
          )}
          <div className="sh-boards">
            {(mine === null ? [0, 1] : [foe!, mine]).map((s) => {
              const enemy = mine !== null && s === foe;
              const target = view.phase === "battle" && view.turn !== null && s === 1 - view.turn;
              return (
                <Card key={s} className={`sh-board ${target ? "target" : ""} ${mine !== null && !enemy ? "own" : ""}`}>
                  <h3>
                    {mine === null ? sideLabel(s) : enemy ? "Enemy waters" : "Your fleet"}
                    <span className="sh-afloat">{view.boards[s]!.afloat} afloat</span>
                  </h3>
                  {(mine === null || view.sides[s]!.length > 1) && roster(s)}
                  <Grid
                    board={view.boards[s]!}
                    size={view.size}
                    label={enemy ? "Enemy waters" : `${sideLabel(s)}’s waters`}
                    last={lastOn(s)}
                    onFire={enemy && myShot ? fire : undefined}
                    small={mine !== null && !enemy}
                  />
                  {enemy && view.phase === "battle" && (
                    <p className="muted center sh-hint">{myShot ? "Tap a square to fire." : `${name(view.shooter ?? "")} has the guns.`}</p>
                  )}
                </Card>
              );
            })}
          </div>
        </>
      )}

      {view.phase === "final" && view.winner !== null && (
        <Card tone="stage" className="center">
          <h3 className="sh-winner">⚓ {sideLabel(view.winner)} rule{view.sides[view.winner]!.length === 1 ? "s" : ""} the waves!</h3>
          <ul className="score-rows space-top">
            {[...view.players]
              .sort((a, b) => (view.scores?.[b.id] ?? 0) - (view.scores?.[a.id] ?? 0))
              .map((p) => (
                <li key={p.id}>
                  <b>
                    {view.sides[view.winner!]!.includes(p.id) ? "👑 " : ""}
                    {p.name}
                    {p.id === you && !tv ? " (you)" : ""}
                    <span className="rx-best muted">
                      {view.tally?.[p.id]?.hits ?? 0} hits from {view.tally?.[p.id]?.shots ?? 0} shots
                    </span>
                  </b>
                  <span className="score-pts">{view.scores?.[p.id] ?? 0}</span>
                </li>
              ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
