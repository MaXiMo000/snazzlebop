import { useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { useCountdown } from "../lib/useRoom";
import { sfx } from "../lib/sfx";
import type { ChessSide, ChessView } from "../types";

interface Props {
  view: ChessView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const FILES = "abcdefgh";
const SIDE: Record<ChessSide, string> = { w: "White", b: "Black" };
const PIECE: Record<string, string> = { K: "king", Q: "queen", R: "rook", B: "bishop", N: "knight", P: "pawn" };
const VALUE: Record<string, number> = { P: 1, N: 3, B: 3, R: 5, Q: 9, K: 0 };
const REASON: Record<string, string> = {
  checkmate: "Checkmate",
  stalemate: "Stalemate",
  resignation: "Resignation",
  time: "Out of time",
  agreement: "Draw agreed",
  "threefold repetition": "Threefold repetition",
  "fifty-move rule": "Fifty-move rule",
  "insufficient material": "Not enough to mate",
};

const name = (i: number) => FILES[i % 8]! + String(Math.floor(i / 8) + 1);
const index = (sq: string) => (Number(sq[1]) - 1) * 8 + FILES.indexOf(sq[0]!);

/** Our own pieces (one shape each, drawn once and reused): the same on every phone, no emoji fonts. */
function PieceSprites() {
  return (
    <svg className="cs-sprites" aria-hidden="true" focusable="false">
      <defs>
        <g id="cp-P">
          <rect x="12" y="33" width="21" height="4.5" rx="2" />
          <path d="M17 34C17 27 20 24 20.5 20.5H24.5C25 24 28 27 28 34Z" />
          <rect x="16.5" y="18.5" width="12" height="3" rx="1.5" />
          <circle cx="22.5" cy="13.5" r="5.5" />
        </g>
        <g id="cp-R">
          <rect x="10" y="33" width="25" height="4.5" rx="1.5" />
          <path d="M14 33L15.5 18H29.5L31 33Z" />
          <path d="M12.5 18V10H16.5V13H20V10H25V13H28.5V10H32.5V18Z" />
        </g>
        <g id="cp-B">
          <rect x="11" y="33" width="23" height="4.5" rx="2" />
          <path d="M15 33C15 28 17 26 18.5 25C15.5 22 15.5 15 22.5 9.5C29.5 15 29.5 22 26.5 25C28 26 30 28 30 33Z" />
          <circle cx="22.5" cy="7" r="2.6" />
          <path className="cs-mark" d="M25 13.5L20.5 19.5M18.5 25H26.5" />
        </g>
        <g id="cp-N">
          <rect x="11" y="33" width="23" height="4.5" rx="2" />
          <path d="M14 33C14 27 18 24 21 21C19 21 16 23 13.5 24C11 22.5 11.5 19 14 17C16 12 20 9 24 8.5L26 6L27.5 9C32 11 33.5 18 32.5 25C32 28 31 31 31 33Z" />
          <circle className="cs-eye" cx="21.5" cy="14" r="1.4" />
        </g>
        <g id="cp-Q">
          <rect x="10" y="33" width="25" height="4.5" rx="2" />
          <path d="M13 33L10.5 15L16 25L16.8 12L21 24L22.5 10L24 24L28.2 12L29 25L34.5 15L32 33Z" />
          <circle cx="10.5" cy="14" r="2.2" />
          <circle cx="16.8" cy="11" r="2.2" />
          <circle cx="22.5" cy="9" r="2.2" />
          <circle cx="28.2" cy="11" r="2.2" />
          <circle cx="34.5" cy="14" r="2.2" />
        </g>
        <g id="cp-K">
          <rect x="10" y="33" width="25" height="4.5" rx="2" />
          <path d="M13 33C11 27 9 22 12 19C15 16 19 18 22.5 22C26 18 30 16 33 19C36 22 34 27 32 33Z" />
          <rect x="21" y="5" width="3" height="12" rx="1" />
          <rect x="17.5" y="8.5" width="10" height="3" rx="1" />
          <path className="cs-mark" d="M13.5 28H31.5" />
        </g>
      </defs>
    </svg>
  );
}

function Piece({ code, className = "" }: { code: string; className?: string }) {
  return (
    <svg className={`cs-piece ${code[0] === "w" ? "white" : "black"} ${className}`} viewBox="0 0 45 45" aria-hidden="true" focusable="false">
      <use href={`#cp-${code[1]}`} />
    </svg>
  );
}

/** A side's clock, counting down live while it's running. */
function ClockFace({ seconds, running, receivedAt }: { seconds: number; running: boolean; receivedAt: number }) {
  const live = useCountdown(running ? seconds : null, receivedAt);
  const left = running ? (live ?? seconds) : seconds;
  const m = Math.floor(left / 60);
  const s = Math.floor(left % 60);
  return (
    <span className={`cs-clock ${running ? "running" : ""} ${running && left <= 20 ? "low" : ""}`} role="timer" aria-label={`${m} minutes ${s} seconds`}>
      {m}:{String(s).padStart(2, "0")}
    </span>
  );
}

export function Chess({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const me = tv ? null : view.you;
  const flip = me?.side === "b"; // your side at the bottom
  const [picked, setPicked] = useState<number | null>(null);
  const [promo, setPromo] = useState<string[] | null>(null); // the four promotion moves waiting for a choice
  const [confirmResign, setConfirmResign] = useState(false);
  const playing = view.phase === "play";
  const myTurn = !!me && playing && me.side === view.turn;
  const canAct = myTurn && me!.legal.length > 0;
  const who = (id: string) => (id === you && !tv ? "You" : nameOf(view.players, id));
  const sideNames = (c: ChessSide) => view.sides[c].map((p) => nameOf(view.players, p));
  const last = view.history.at(-1);

  useOnChange(view.history.length, (prev, next) => {
    if (next <= prev || !last) return;
    if (last.san.includes("#")) return;
    if (last.san.includes("+")) {
      sfx.ding();
      show.stinger("CHECK!");
    } else if (last.san.includes("x")) sfx.buzz();
    else sfx.pop();
    if (last.san.includes("=")) show.stinger("PROMOTION!");
    setPicked(null);
    setPromo(null);
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase !== "final" || !view.result) return;
    sfx.fanfare();
    const r = view.result;
    show.stinger(r.winner ? (r.reason === "checkmate" ? "CHECKMATE!" : `${SIDE[r.winner].toUpperCase()} WINS!`) : "A DRAW!", r.winner && me && r.winner !== me.side ? "bad" : "good");
    if (r.winner && (!me || r.winner === me.side)) show.celebrate();
  });
  useOnChange(myTurn, (_, now) => {
    if (now) sfx.tick();
  });

  const targets = picked === null || !me ? [] : me.legal.filter((m) => m.startsWith(name(picked)));
  const tap = (i: number) => {
    if (!canAct) return;
    const code = view.board[i];
    if (picked !== null) {
      const moves = targets.filter((m) => m.slice(2, 4) === name(i));
      if (moves.length > 1) return setPromo(moves); // a promotion: pick the piece
      if (moves.length === 1) return submit(moves[0]!);
    }
    if (code && code[0] === me!.side && me!.legal.some((m) => m.startsWith(name(i)))) setPicked(picked === i ? null : i);
    else setPicked(null);
  };
  const submit = (move: string) => {
    send({ t: "act", a: me!.mover ? "move" : "suggest", move });
    if (!me!.mover) sfx.pop();
    setPicked(null);
    setPromo(null);
  };

  const sign = !playing
    ? view.result?.winner
      ? `${REASON[view.result.reason] ?? view.result.reason} · ${SIDE[view.result.winner]} wins`
      : `${REASON[view.result?.reason ?? ""] ?? "Draw"} · a draw`
    : myTurn
      ? me!.mover
        ? "Your move"
        : `${SIDE[view.turn]} to move · suggest one to ${nameOf(view.players, view.mover ?? "")}`
      : `${SIDE[view.turn]} to move · ${nameOf(view.players, view.mover ?? "")}`;

  // Display order: rank 8 at the top for White, rank 1 at the top for Black.
  const order = Array.from({ length: 64 }, (_, k) => {
    const row = Math.floor(k / 8);
    const col = k % 8;
    return flip ? row * 8 + (7 - col) : (7 - row) * 8 + col;
  });
  const pos = (i: number) => {
    const k = order.indexOf(i);
    return { row: Math.floor(k / 8), col: k % 8 };
  };
  const lastFrom = view.last ? index(view.last.slice(0, 2)) : -1;
  const lastTo = view.last ? index(view.last.slice(2, 4)) : -1;
  const slide = lastTo >= 0 ? { dx: pos(lastFrom).col - pos(lastTo).col, dy: pos(lastFrom).row - pos(lastTo).row } : null;
  const top: ChessSide = flip ? "w" : "b";
  const bottom: ChessSide = flip ? "b" : "w";

  return (
    <div className={`seg-chess stack ${tv ? "tv-chess" : ""}`}>
      {show.node}
      <PieceSprites />
      <ShowHead sign={sign} title="Chess" remaining={null} receivedAt={receivedAt}>
        <span className="chip plum">{view.increment ? `Chess clocks · +${view.increment} s a move` : "Chess clocks · no increment"}</span>
      </ShowHead>

      <div className="cs-layout">
        <div className="cs-board-col">
          <SideBar view={view} side={top} you={you} tv={tv} receivedAt={receivedAt} />
          <div className="cs-frame">
            <div className="cs-board" role="group" aria-label={`Chess board, ${SIDE[view.turn]} to move`}>
              {order.map((i) => {
                const code = view.board[i] ?? "";
                const light = (Math.floor(i / 8) + (i % 8)) % 2 === 1;
                const target = targets.some((m) => m.slice(2, 4) === name(i));
                const { row, col } = pos(i);
                const moving = i === lastTo && slide;
                return (
                  <button
                    key={i}
                    type="button"
                    className={[
                      "cs-sq",
                      light ? "light" : "dark",
                      i === lastFrom || i === lastTo ? "last" : "",
                      view.check === name(i) ? "check" : "",
                      picked === i ? "picked" : "",
                      target ? (code ? "target capture" : "target") : "",
                    ].join(" ")}
                    aria-label={`${name(i)}${code ? `, ${SIDE[code[0] as ChessSide].toLowerCase()} ${PIECE[code[1]!]}` : ""}${target ? ", move here" : ""}`}
                    aria-pressed={picked === i ? true : undefined}
                    disabled={!canAct}
                    onClick={() => tap(i)}
                  >
                    {col === 0 && <span className="cs-rank" aria-hidden="true">{Math.floor(i / 8) + 1}</span>}
                    {row === 7 && <span className="cs-file" aria-hidden="true">{FILES[i % 8]}</span>}
                    {i === lastTo && last?.san.includes("x") && <span key={view.last} className="cs-hit" aria-hidden="true" />}
                    {code && <Piece key={moving ? view.last : i} code={code} className={moving ? `slide dx${slide.dx} dy${slide.dy}` : ""} />}
                  </button>
                );
              })}
            </div>
            {me && me.suggestions.length > 0 && <Arrows view={view} order={order} />}
          </div>
          <SideBar view={view} side={bottom} you={you} tv={tv} receivedAt={receivedAt} />
        </div>

        <div className="cs-side">
          {playing && me && (
            <Card tone={myTurn ? "soft" : "plain"} className="cs-turn">
              <p className="lead">
                {myTurn
                  ? me.mover
                    ? "Your move: tap a piece, then where it goes."
                    : `Tap a move to suggest it to ${nameOf(view.players, view.mover ?? "")}.`
                  : `${SIDE[view.turn]} to move: ${who(view.mover ?? "")} ${view.sides[view.turn].length > 1 ? "for their team" : ""}`}
              </p>
              {me.suggestions.length > 0 && (
                <ul className="cs-suggest">
                  {me.suggestions.map((s) => (
                    <li key={s.by}>
                      <span>
                        <b>{who(s.by)}</b> {s.by === you ? "suggest" : "suggests"} <b className="cs-san">{s.san}</b>
                      </span>
                      {me.mover && s.by !== you && (
                        <Btn size="small" variant="gold" onClick={() => send({ t: "act", a: "move", move: s.move })}>
                          Play it
                        </Btn>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {view.draw_offer && view.draw_offer !== me.side ? (
                <div className="cs-offer space-top" role="alert">
                  <p>
                    <b>{SIDE[view.draw_offer]}</b> offers a draw.
                  </p>
                  <div className="row">
                    <Btn variant="go" onClick={() => send({ t: "act", a: "accept" })}>
                      Accept draw
                    </Btn>
                    <Btn variant="ghost" onClick={() => send({ t: "act", a: "decline" })}>
                      Play on
                    </Btn>
                  </div>
                </div>
              ) : (
                <div className="row space-top cs-actions">
                  <Btn variant="ghost" disabled={view.draw_offer === me.side} onClick={() => send({ t: "act", a: "offer" })}>
                    {view.draw_offer === me.side ? "Draw offered" : "Offer a draw"}
                  </Btn>
                  {confirmResign ? (
                    <>
                      <Btn variant="danger" onClick={() => send({ t: "act", a: "resign" })}>
                        Yes, resign
                      </Btn>
                      <Btn variant="ghost" onClick={() => setConfirmResign(false)}>
                        Keep playing
                      </Btn>
                    </>
                  ) : (
                    <Btn variant="danger" onClick={() => setConfirmResign(true)}>
                      Resign
                    </Btn>
                  )}
                </div>
              )}
            </Card>
          )}

          {!playing && view.result && (
            <Card tone="stage" className="center cs-result" role="status">
              <p className="sign">{REASON[view.result.reason] ?? view.result.reason}</p>
              <h3 className="cs-result-head">{view.result.winner ? `${SIDE[view.result.winner]} wins!` : "A draw!"}</h3>
              {view.result.winner && <p className="cs-names">{sideNames(view.result.winner).join(" & ")}</p>}
              <p className="muted space-top">{(view.history.length + 1) >> 1} moves</p>
            </Card>
          )}

          <Moves view={view} />
        </div>
      </div>

      {promo && (
        <div className="lc-picker" role="dialog" aria-modal="true" aria-labelledby="cs-promo-h">
          <Card tone="stage" className="center">
            <h3 id="cs-promo-h">Promote to</h3>
            <div className="cs-promo space-top">
              {["q", "r", "b", "n"].map((p) => {
                const move = promo.find((m) => m.endsWith(p));
                return (
                  <button key={p} type="button" className="cs-promo-btn" aria-label={PIECE[p.toUpperCase()]} onClick={() => move && submit(move)}>
                    <Piece code={`${me?.side ?? "w"}${p.toUpperCase()}`} />
                  </button>
                );
              })}
            </div>
            <Btn variant="ghost" className="space-top" onClick={() => setPromo(null)}>
              Cancel
            </Btn>
          </Card>
        </div>
      )}
    </div>
  );
}

/** A player bar above / below the board: who, their clock, what they've taken. */
function SideBar({ view, side, you, tv, receivedAt }: { view: ChessView; side: ChessSide; you: string; tv: boolean; receivedAt: number }) {
  const taken = [...view.captured[side]].sort((a, b) => VALUE[b]! - VALUE[a]!);
  const lead = view.captured[side].reduce((n, p) => n + VALUE[p]!, 0) - view.captured[side === "w" ? "b" : "w"].reduce((n, p) => n + VALUE[p]!, 0);
  const running = view.phase === "play" && view.turn === side;
  return (
    <div className={`cs-bar ${running ? "on" : ""}`}>
      <span className={`cs-dot ${side}`} aria-hidden="true" />
      <div className="grow">
        <p className="cs-who">
          {view.sides[side].map((p) => (
            <span key={p} className={`nm ${p === view.mover ? "moving" : ""}`}>
              {nameOf(view.players, p).replace(/ (\S{1,2})$/, "\u00a0$1")}
              {p === you && !tv && <span className="cs-you"> (you)</span>}
            </span>
          ))}
        </p>
        <p className="cs-taken">
          <span className="sr-only">
            {SIDE[side]} has taken {taken.length ? taken.map((p) => PIECE[p]).join(", ") : "nothing yet"}
          </span>
          {taken.map((p, i) => (
            <Piece key={i} code={`${side === "w" ? "b" : "w"}${p}`} className="mini" />
          ))}
          {lead > 0 && <span className="cs-lead">+{lead}</span>}
        </p>
      </div>
      <ClockFace seconds={view.clocks[side]} running={running} receivedAt={receivedAt} />
    </div>
  );
}

/** Teammates' suggestions as arrows on the board (only your side gets these). */
function Arrows({ view, order }: { view: ChessView; order: number[] }) {
  const at = (sqName: string) => {
    const k = order.indexOf(index(sqName));
    return { x: (k % 8) + 0.5, y: Math.floor(k / 8) + 0.5 };
  };
  return (
    <svg className="cs-arrows" viewBox="0 0 8 8" aria-hidden="true">
      <defs>
        <marker id="cs-head" viewBox="0 0 4 4" refX="2.2" refY="2" markerWidth="3" markerHeight="3" orient="auto">
          <path d="M0 0L4 2L0 4Z" />
        </marker>
      </defs>
      {view.you!.suggestions.map((s) => {
        const a = at(s.move.slice(0, 2));
        const b = at(s.move.slice(2, 4));
        return <line key={s.by} x1={a.x} y1={a.y} x2={b.x} y2={b.y} markerEnd="url(#cs-head)" />;
      })}
    </svg>
  );
}

function Moves({ view }: { view: ChessView }) {
  const pairs: { n: number; w?: string; b?: string }[] = [];
  view.history.forEach((h, i) => {
    if (h.side === "w" || i === 0) pairs.push({ n: pairs.length + 1, [h.side]: h.san });
    else pairs[pairs.length - 1]!.b = h.san;
  });
  return (
    <Card aria-labelledby="cs-moves-h">
      <h3 id="cs-moves-h">Moves</h3>
      {pairs.length ? (
        <ol className="cs-moves">
          {pairs.slice(-12).map((p) => (
            <li key={p.n}>
              <span className="cs-no">{p.n}.</span>
              <span className="cs-san">{p.w ?? "…"}</span>
              <span className="cs-san">{p.b ?? ""}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">White moves first.</p>
      )}
    </Card>
  );
}
