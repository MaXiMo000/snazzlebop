import { useRef, useState } from "react";
import { Btn, Card, ShowHead, initials, nameOf } from "../components/ui";
import { useOnChange, useReducedMotion, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { LastCardView, LcCard, LcColor, LcLog } from "../types";

interface Props {
  view: LastCardView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const COLORS: LcColor[] = ["red", "yellow", "green", "blue"];
const COLOR_NAME: Record<string, string> = { red: "Red", yellow: "Yellow", green: "Green", blue: "Blue", wild: "Wild" };
const SYMBOL: Record<string, string> = { skip: "⊘", reverse: "⇄", draw2: "+2", wild: "★", wild4: "+4" };
const VALUE_NAME: Record<string, string> = {
  skip: "Skip",
  reverse: "Reverse",
  draw2: "Draw Two",
  wild: "Wild",
  wild4: "Wild Draw Four",
};
const ORDER: Record<string, number> = { red: 0, yellow: 1, green: 2, blue: 3, wild: 4 };

export function cardName(c: Pick<LcCard, "color" | "value">): string {
  if (c.color === "wild") return VALUE_NAME[c.value] ?? c.value;
  return `${COLOR_NAME[c.color]} ${VALUE_NAME[c.value] ?? c.value}`;
}

/** A card face: colour, a big symbol in the oval, small ones in the corners. Wilds show all four colours. */
function Face({ card, size = "" }: { card: Pick<LcCard, "color" | "value">; size?: "" | "big" | "mini" }) {
  const sym = SYMBOL[card.value] ?? card.value;
  return (
    <span className={`lc-card c-${card.color} v-${card.value} ${size}`} aria-hidden="true">
      <span className="lc-corner tl">{sym}</span>
      <span className="lc-oval">
        <span className="lc-sym">{sym}</span>
      </span>
      <span className="lc-corner br">{sym}</span>
    </span>
  );
}

export function LastCard({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const [wild, setWild] = useState<number | null>(null);
  const me = !tv ? view.you : null;
  const myTurn = !!me && view.turn === you && view.phase === "play";
  const name = (id: string) => (id === you && !tv ? "You" : nameOf(view.players, id));

  // Stingers from what just happened (the log is public, so every screen reacts the same way).
  useOnChange(view.log.length, (prev, next) => {
    const fresh = view.log.slice(Math.max(0, view.log.length - (next - prev)));
    for (const e of fresh) react(e);
  });
  function react(e: LcLog) {
    if (e.type === "play") {
      const card = { color: e.base, value: e.value };
      if (card.value === "wild4") {
        sfx.buzz();
        show.stinger("+4!", "bad");
      } else if (card.value === "draw2") {
        sfx.buzz();
        show.stinger("+2!", "bad");
      } else if (card.value === "skip") {
        sfx.pop();
        show.stinger("SKIP!");
      } else if (card.value === "reverse") {
        sfx.spin();
        show.stinger("REVERSE!");
      } else if (card.value === "wild") {
        sfx.ding();
        show.stinger(`${COLOR_NAME[e.color]?.toUpperCase()}!`);
      } else {
        sfx.pop();
      }
    } else if (e.type === "last") {
      sfx.ding();
      show.stinger(`${nameOf(view.players, e.player).toUpperCase()}: LAST CARD!`);
    } else if (e.type === "caught") {
      sfx.buzz();
      show.stinger(`CAUGHT ${nameOf(view.players, e.player).toUpperCase()}!`, "bad");
    } else if (e.type === "challenge") {
      sfx[e.won ? "fanfare" : "buzz"]();
      show.stinger(e.won ? "BUSTED! +4" : "CHALLENGE FAILED +6", e.won ? "good" : "bad");
    } else if (e.type === "win") {
      sfx.fanfare();
      show.stinger(`${nameOf(view.players, e.player).toUpperCase()} GOES OUT!`);
      show.celebrate();
    }
  }
  useOnChange(myTurn, (_, mine) => {
    if (mine) sfx.tick();
    setWild(null);
  });

  const play = (c: LcCard & { playable: boolean }) => {
    if (!c.playable) return;
    if (c.color === "wild") setWild(c.id);
    else send({ t: "act", a: "play", card: c.id });
  };

  const sign =
    view.phase === "final"
      ? "Final scores"
      : view.phase === "hand_over"
        ? `Hand ${view.round} of ${view.rounds} · ${name(view.winner ?? "")} went out`
        : `Hand ${view.round} of ${view.rounds} · ${myTurn ? "Your turn" : `${nameOf(view.players, view.turn ?? "")}’s turn`}`;

  const hand = [...(me?.hand ?? [])].sort(
    (a, b) => ORDER[a.color]! - ORDER[b.color]! || a.value.localeCompare(b.value, "en", { numeric: true }),
  );

  return (
    <div className={`seg-lastcard stack lc-now-${view.color} ${tv ? "tv-cols" : ""}`}>
      {show.node}
      <ShowHead
        sign={sign}
        title="Last Card"
        remaining={view.phase === "play" ? view.remaining : view.remaining}
        receivedAt={receivedAt}
      >
        <span className="chip plum">
          {view.stacking ? "Stacking on · +2 on +2, +4 on +4" : "Match colour, number or symbol"}
        </span>
      </ShowHead>

      {/* TV: once the hand is over, the revealed hands take the stage and the table steps aside */}
      {(view.phase === "play" || (!tv && view.phase === "hand_over")) && (
        <Table view={view} you={you} tv={tv} myTurn={myTurn} send={send} />
      )}

      {myTurn && view.pending && (
        <Card tone="soft" className="center">
          <h3>
            {view.pending.kind === "wild4" ? "A Wild Draw Four hits you!" : `+${view.pending.n} coming your way!`}
          </h3>
          <div className="row center space-top">
            <Btn variant="danger" size="big" onClick={() => send({ t: "act", a: "draw" })}>
              Take {view.pending.n}
            </Btn>
            {view.pending.kind === "wild4" && (
              <Btn variant="gold" size="big" onClick={() => send({ t: "act", a: "challenge" })}>
                Challenge!
              </Btn>
            )}
          </div>
          {view.pending.kind === "wild4" && (
            <p className="muted space-top">
              Challenge if you think {nameOf(view.players, view.pending.by)} still had a{" "}
              {COLOR_NAME[view.pending.was ?? ""] ?? "matching"} card. Right: they take 4. Wrong: you take{" "}
              {view.pending.n + 2}.
            </p>
          )}
          {view.stacking && <p className="muted">Or stack a matching draw card from your hand.</p>}
        </Card>
      )}

      {me && view.phase === "play" && (
        <Card className="lc-hand-card">
          <div className="row between">
            <h3>Your hand · {hand.length}</h3>
            {me.can_last && (
              <Btn
                variant="gold"
                size="big"
                className="lc-last"
                onClick={() => {
                  sfx.ding();
                  send({ t: "act", a: "last" });
                }}
              >
                LAST CARD!
              </Btn>
            )}
          </div>
          {me.drawn != null && myTurn && (
            <div className="row between lc-drawn">
              <p>You drew a card you can play. Play it, or keep it?</p>
              <Btn variant="ghost" onClick={() => send({ t: "act", a: "pass" })}>
                Keep it ▶
              </Btn>
            </div>
          )}
          <ul className="lc-hand">
            {hand.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={`lc-hand-btn ${c.playable ? "playable" : ""} ${c.id === me.drawn ? "drawn" : ""}`}
                  aria-label={`${cardName(c)}${c.playable ? "" : " (can't play now)"}`}
                  aria-disabled={!c.playable}
                  onClick={() => play(c)}
                >
                  <Face card={c} />
                </button>
              </li>
            ))}
          </ul>
          {!myTurn && (
            <p className="muted center space-top">Wait for your turn… Catch anyone who forgets to call LAST CARD!</p>
          )}
        </Card>
      )}

      {wild !== null && (
        <div className="lc-picker" role="dialog" aria-modal="true" aria-labelledby="lc-pick-h">
          <Card tone="stage" className="center">
            <h3 id="lc-pick-h">Pick the new colour</h3>
            <div className="lc-colors space-top">
              {COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`lc-color c-${c}`}
                  onClick={() => {
                    send({ t: "act", a: "play", card: wild, color: c });
                    setWild(null);
                  }}
                >
                  {COLOR_NAME[c]}
                </button>
              ))}
            </div>
            <Btn variant="ghost" className="space-top" onClick={() => setWild(null)}>
              Cancel
            </Btn>
          </Card>
        </div>
      )}

      {view.phase !== "play" && view.hands && <HandsShown view={view} you={you} main />}

      <Log view={view} you={you} tv={tv} />
    </div>
  );
}

/** Who's next after `pid` in play order (direction -1 goes the other way round). */
function nextOf(view: LastCardView, pid: string | null): string | null {
  if (!pid) return null;
  const n = view.order.length;
  const k = view.order.indexOf(pid);
  return k < 0 ? null : (view.order[(k + (view.direction < 0 ? -1 : 1) + n) % n] ?? null);
}

const AVATAR_TONES = 8;
type Fx = {
  id: number;
  kind: "play" | "draw" | "skip" | "burst";
  seat: number;
  card?: Pick<LcCard, "color" | "value">;
  n?: number;
};

/**
 * The table, like the real thing: everyone seated round an oval in play order (you at the bottom), the
 * draw pile and the discard pile (the last few cards scattered underneath) in the middle, a colour ring
 * and a direction ring that spins the way play goes. Cards fly from a seat to the pile and back, skips
 * stamp the skipped seat, +2/+4 burst on whoever takes them.
 */
function Table({
  view,
  you,
  tv,
  myTurn,
  send,
}: {
  view: LastCardView;
  you: string;
  tv: boolean;
  myTurn: boolean;
  send: Props["send"];
}) {
  const me = !tv ? view.you : null;
  const n = view.order.length;
  const start = !tv && view.order.includes(you) ? view.order.indexOf(you) : 0;
  const seats = view.order.map((_, k) => view.order[(start + k) % n]!);
  const seatOf = (pid: string) => seats.indexOf(pid);
  const next = nextOf(view, view.turn);
  const [fx, setFx] = useState<Fx[]>([]);
  const fxId = useRef(0);
  const reduced = useReducedMotion();

  useOnChange(view.log.length, (prev, cur) => {
    if (reduced || cur <= prev) return;
    const fresh = view.log.slice(Math.max(0, view.log.length - (cur - prev)));
    const add: Fx[] = [];
    for (const e of fresh) {
      const id = ++fxId.current;
      if (e.type === "play")
        add.push({ id, kind: "play", seat: seatOf(e.player), card: { color: e.base, value: e.value } });
      else if (e.type === "draw") add.push({ id, kind: "draw", seat: seatOf(e.player), n: e.n });
      else if (e.type === "skipped") add.push({ id, kind: "skip", seat: seatOf(e.player) });
    }
    if (view.pending && view.turn)
      add.push({ id: ++fxId.current, kind: "burst", seat: seatOf(view.turn), n: view.pending.n });
    if (!add.length) return;
    setFx((f) => [...f, ...add].slice(-8));
    const ids = new Set(add.map((a) => a.id));
    window.setTimeout(() => setFx((f) => f.filter((a) => !ids.has(a.id))), 1100);
  });

  // The cards under the top one: the last few plays, scattered.
  const under = view.log
    .filter((e): e is Extract<LcLog, { type: "play" }> => e.type === "play")
    .slice(-4, -1)
    .map((e) => ({ color: e.base, value: e.value }));
  const catchable = view.vulnerable.filter((pid) => pid !== you && !tv);

  return (
    <Card tone="stage" className={`lc-table ${view.phase === "play" ? "tv-main" : ""}`}>
      <div className={`lc-felt seats-${n}`}>
        <span className={`lc-dir-ring ${view.direction < 0 ? "ccw" : ""}`} aria-hidden="true" />
        <span className={`lc-color-ring c-${view.color}`} aria-hidden="true" />
        <ol className="lc-ring">
          {seats.map((pid, k) => {
            const count = view.counts[pid] ?? 0;
            const on = pid === view.turn && view.phase === "play";
            return (
              <li
                key={pid}
                className={`lc-seat2 lc-pos-${n}-${k} ${on ? "on" : ""} ${pid === you && !tv ? "you" : ""}`}
              >
                <span className={`lc-avatar tone-${view.order.indexOf(pid) % AVATAR_TONES}`} aria-hidden="true">
                  {initials(nameOf(view.players, pid))}
                </span>
                <span className="lc-seat-who">
                  {pid === you && !tv ? "You" : (nameOf(view.players, pid).split(/\s+/)[0] ?? "")}
                </span>
                <span className="sr-only">{nameOf(view.players, pid)}</span>
                <span className="lc-seat-cards" aria-hidden="true">
                  <span className="lc-fan">
                    {Array.from({ length: Math.min(count, 6) }, (_, i) => (
                      <i key={i} />
                    ))}
                  </span>
                  <b>{count}</b>
                </span>
                <span className="sr-only">
                  {`, ${count} ${count === 1 ? "card" : "cards"}`}
                  {on ? ", their turn" : ""}
                  {pid === next && view.phase === "play" ? ", next" : ""}
                </span>
                {pid === next && view.phase === "play" && !on && <span className="lc-next">next</span>}
                {view.protected.includes(pid) && count === 1 && <span className="lc-badge">LAST CARD!</span>}
                {view.vulnerable.includes(pid) && <span className="lc-badge warn">No call!</span>}
              </li>
            );
          })}
        </ol>
        <div className="lc-middle">
          <button
            type="button"
            className="lc-deck"
            disabled={!myTurn || me?.drawn != null}
            onClick={() => {
              sfx.pop();
              send({ t: "act", a: "draw" });
            }}
          >
            <span className="lc-card back" aria-hidden="true">
              <span className="lc-back-mark">LAST CARD</span>
            </span>
            <span className="lc-deck-label">
              {myTurn && view.pending
                ? `Take ${view.pending.n}`
                : myTurn && me?.drawn == null
                  ? "Draw"
                  : `${view.deck}`}
            </span>
          </button>
          <div className="lc-discard2" aria-live="polite">
            {under.map((c, i) => (
              <span key={i} className={`lc-under u${i}`} aria-hidden="true">
                <Face card={c} />
              </span>
            ))}
            <span key={view.top.id} className="lc-top">
              <Face card={view.top} />
            </span>
            <span className="sr-only">
              Top card: {cardName(view.top)}. Colour to match: {COLOR_NAME[view.color]}. Play goes{" "}
              {view.direction < 0 ? "anticlockwise" : "clockwise"}.
            </span>
          </div>
        </div>
        {fx.map((f) =>
          f.seat < 0 ? null : f.kind === "play" && f.card ? (
            <span key={f.id} className={`lc-fly to-pile lc-from-${n}-${f.seat}`} aria-hidden="true">
              <Face card={f.card} />
            </span>
          ) : f.kind === "draw" ? (
            <span key={f.id} className={`lc-fly to-seat lc-from-${n}-${f.seat}`} aria-hidden="true">
              <span className="lc-card back">
                <span className="lc-back-mark">LAST CARD</span>
              </span>
              {f.n && f.n > 1 ? <b className="lc-fly-n">+{f.n}</b> : null}
            </span>
          ) : f.kind === "skip" ? (
            <span key={f.id} className={`lc-stamp lc-pos-${n}-${f.seat}`} aria-hidden="true">
              ⊘
            </span>
          ) : (
            <span key={f.id} className={`lc-stamp burst lc-pos-${n}-${f.seat}`} aria-hidden="true">
              +{f.n}
            </span>
          ),
        )}
      </div>
      {view.pending && (
        <p className="lc-pending" role="status">
          {view.pending.kind === "wild4" ? "Wild Draw Four" : "Draw Two"}: {nameOf(view.players, view.turn ?? "")} takes{" "}
          {view.pending.n}
          {view.stacking ? " unless they stack" : ""}
        </p>
      )}
      {catchable.length > 0 && (
        <div className="lc-catches">
          {catchable.map((pid) => (
            <Btn
              key={pid}
              size="small"
              variant="danger"
              onClick={() => {
                sfx.buzz();
                send({ t: "act", a: "catch", target: pid });
              }}
            >
              Catch {nameOf(view.players, pid)}!
            </Btn>
          ))}
        </div>
      )}
    </Card>
  );
}

function logLine(e: LcLog, who: (id: string) => string): string | null {
  switch (e.type) {
    case "play": {
      const c = { color: e.base, value: e.value };
      return c.color === "wild"
        ? `${who(e.player)} played ${cardName(c)} → ${COLOR_NAME[e.color]}`
        : `${who(e.player)} played ${cardName(c)}`;
    }
    case "draw":
      return e.reason === "draw" ? `${who(e.player)} drew a card` : `${who(e.player)} picked up ${e.n}`;
    case "start":
      return `The first card: ${cardName({ color: e.base, value: e.value })}`;
    case "skipped":
      return `${who(e.player)} was skipped`;
    case "reverse":
      return "Play reversed";
    case "pass":
      return `${who(e.player)} kept the card`;
    case "challenge":
      return e.won ? `${who(e.player)} caught ${who(e.against)} bluffing!` : `${who(e.player)}’s challenge failed`;
    case "last":
      return `${who(e.player)} called LAST CARD!`;
    case "caught":
      return `${who(e.by)} caught ${who(e.player)}: +2`;
    case "timeout":
      return `${who(e.player)} ran out of time`;
    case "reshuffle":
      return "The pile was reshuffled";
    case "win":
      return `${who(e.player)} went out for ${e.points} points!`;
    default:
      return null;
  }
}

function Log({ view, you, tv }: { view: LastCardView; you: string; tv: boolean }) {
  const who = (id: string) => (id === you && !tv ? "You" : nameOf(view.players, id));
  const lines = view.log.map((e) => logLine(e, who)).filter((l): l is string => !!l);
  return (
    <Card>
      <h3>{view.phase === "final" ? "Scores" : "What just happened"}</h3>
      {view.phase === "final" ? (
        <ul className="score-rows">
          {[...view.players]
            .sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0))
            .map((p, i) => (
              <li key={p.id}>
                <b>
                  {i === 0 && (view.scores[p.id] ?? 0) > 0 ? "👑 " : ""}
                  {p.name}
                  {p.id === you && !tv ? " (you)" : ""}
                </b>
                <span className="score-tally">
                  <span className="score-pts">{view.scores[p.id] ?? 0}</span>
                </span>
              </li>
            ))}
        </ul>
      ) : (
        <ol className="lc-log">
          {lines
            .slice(-6)
            .reverse()
            .map((l, i) => (
              <li key={`${view.log.length}-${i}`}>{l}</li>
            ))}
        </ol>
      )}
    </Card>
  );
}

function HandsShown({ view, you, main }: { view: LastCardView; you: string; main: boolean }) {
  return (
    <Card className={main ? "tv-main" : ""}>
      <h3>{view.phase === "final" ? "The last hand" : "Left in everyone’s hands"}</h3>
      <ul className="lc-shown">
        {view.order.map((pid) => {
          const cards = view.hands?.[pid] ?? [];
          return (
            <li key={pid}>
              <p>
                <b>
                  {pid === view.winner ? "🏆 " : ""}
                  {nameOf(view.players, pid)}
                  {pid === you ? " (you)" : ""}
                </b>
                <span className="muted"> {pid === view.winner ? "went out" : `${cards.length} cards`}</span>
              </p>
              <div className="lc-shown-cards">
                {cards.map((c) => (
                  <Face key={c.id} card={c} size="mini" />
                ))}
              </div>
              <p className="sr-only">{cards.map(cardName).join(", ")}</p>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
