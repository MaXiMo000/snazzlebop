import { useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { DiceView } from "../types";

interface Props {
  view: DiceView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const PIPS = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];
const FACE_NAME = ["", "one", "two", "three", "four", "five", "six"];

function Die({ face, hot = false }: { face: number; hot?: boolean }) {
  return (
    <span className={`die ${face === 1 ? "wild" : ""} ${hot ? "hot" : ""}`} role="img" aria-label={face === 1 ? "one (wild)" : FACE_NAME[face]}>
      <span aria-hidden="true">{PIPS[face]}</span>
    </span>
  );
}

function bidText(qty: number, face: number): string {
  return `${qty} × ${FACE_NAME[face]}${qty === 1 ? "" : "s"}`;
}

/** Does this die count toward a bid on `face`? Ones are wild unless it's palifico (or the bid is on ones). */
const counts = (d: number, face: number, wild: boolean) => d === face || (wild && face !== 1 && d === 1);

/** What you know: how many of `face` you hold, and how many the rest of the table probably holds. */
function estimate(view: DiceView, face: number) {
  const wild = !view.palifico;
  const mine = view.you.dice.filter((d) => counts(d, face, wild)).length;
  const others = view.total - view.you.dice.length;
  const likely = Math.round(mine + others * (wild && face !== 1 ? 1 / 3 : 1 / 6));
  return { mine, others, likely };
}

/** A bid shown as dice: "at least 5 × ⚃". */
function BidDice({ qty, face, wild }: { qty: number; face: number; wild: boolean }) {
  return (
    <span className="bid-dice">
      <span className="bid-least">at least</span>
      <span className="bid-qty">{qty}</span>
      <span aria-hidden="true">×</span>
      <Die face={face} />
      {wild && face !== 1 && (
        <span className="bid-wild">
          (counting wild <Die face={1} />)
        </span>
      )}
    </span>
  );
}

export function Dice({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const myTurn = !tv && view.turn === you;
  useOnChange(myTurn, (_, now) => {
    if (now) sfx.ding();
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "reveal" && view.last) {
      const l = view.last;
      if (l.call === "spot" && l.loser === null) {
        sfx.fanfare();
        show.stinger("SPOT ON!");
      } else {
        sfx.buzz();
        show.stinger(l.loser === l.caller ? "IT WAS TRUE!" : "LIAR!", l.loser === you ? "bad" : "good");
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("LAST ONE ROLLING!");
      show.celebrate();
    }
  });
  const sign =
    view.phase === "final"
      ? "Game over"
      : view.phase === "reveal"
        ? "The cups come up"
        : `Round ${view.round} · ${view.turn === you && !tv ? "your turn" : `${nameOf(view.players, view.turn ?? "")}’s turn`}`;
  return (
    <div className="seg-dice stack">
      {show.node}
      <ShowHead sign={sign} title="Liar's Dice" remaining={view.remaining} receivedAt={receivedAt}>
        <span className={`chip ${view.palifico ? "cherry" : "plum"}`}>
          {view.total} dice on the table · {view.palifico ? "PALIFICO: ones are NOT wild, face is fixed" : "ones are wild"}
        </span>
      </ShowHead>

      {view.phase !== "final" && (
        <Card tone="stage" className="center">
          <p className="sign">Current bid</p>
          {view.bid ? (
            <>
              <p className="lead space-top">
                <b>{nameOf(view.players, view.bid.player)}</b> says that among <b>all {view.total} dice</b> on the table there are
              </p>
              <p className="lead">
                <BidDice qty={view.bid.qty} face={view.bid.face} wild={!view.palifico} />
              </p>
            </>
          ) : (
            <p className="lead space-top">No bid yet. {view.phase === "bid" ? "Opening bid coming up…" : ""}</p>
          )}
        </Card>
      )}

      {!tv && view.phase === "bid" && view.you.dice.length > 0 && (
        <Card tone="soft">
          <h3>Your secret dice</h3>
          <p className="dice-row" role="group" aria-label="Your dice">
            {view.you.dice.map((d, i) => (
              <Die key={i} face={d} hot={!!view.bid && counts(d, view.bid.face, !view.palifico)} />
            ))}
          </p>
          {view.bid && <Hint view={view} face={view.bid.face} />}
          {myTurn && <BidForm view={view} send={send} />}
        </Card>
      )}
      {!tv && view.phase === "bid" && view.you.dice.length === 0 && view.counts[you] === 0 && (
        <Card tone="soft" className="center">
          <p>You’re out of dice. Watch the bluffs fly!</p>
        </Card>
      )}

      {view.phase === "reveal" && view.last && <Reveal view={view} you={you} />}
      {view.phase === "final" && <Final view={view} you={you} />}

      <Card>
        <h3>The table</h3>
        <ul className="dice-table">
          {view.players.map((p) => (
            <li key={p.id} className={`${view.turn === p.id ? "turn" : ""} ${view.counts[p.id] === 0 ? "out" : ""}`}>
              <b>
                {p.name}
                {p.id === you ? " (you)" : ""}
              </b>
              {view.counts[p.id] === 0 ? (
                <span className="cups">out</span>
              ) : (
                <span className="cups" role="img" aria-label={`${view.counts[p.id]} dice`}>
                  <span aria-hidden="true">{"🎲".repeat(view.counts[p.id] ?? 0)}</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      </Card>

      {view.history.length > 0 && (
        <Card>
          <h3>Challenges</h3>
          <ol className="evidence">
            {[...view.history].reverse().map((h, i) => (
              <li key={i}>
                {nameOf(view.players, h.caller)} {h.call === "spot" ? "called spot on" : "called liar"} on{" "}
                {nameOf(view.players, h.bid.player)}’s {bidText(h.bid.qty, h.bid.face)}: there were {h.actual}.{" "}
                {h.loser ? `${nameOf(view.players, h.loser)} lost a die.` : h.gained ? `${nameOf(view.players, h.gained)} won a die back!` : "Nobody lost a die."}
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}

/** Plain odds: what you hold for this face and what the hidden dice probably add. */
function Hint({ view, face }: { view: DiceView; face: number }) {
  const { mine, others, likely } = estimate(view, face);
  return (
    <p className="muted dice-hint">
      You hold <b>{mine}</b> that count. The other {others} hidden {others === 1 ? "die" : "dice"} probably add about {likely - mine}, so about{" "}
      <b>{likely}</b> is likely in all.
    </p>
  );
}

function BidForm({ view, send }: { view: DiceView; send: Props["send"] }) {
  // Default to the smallest legal raise: same count with the next face, or one more die of twos.
  // Palifico: the opening bid fixes the face (ones allowed), and every raise adds dice.
  const bid = view.bid;
  const pal = view.palifico;
  const start = bid
    ? pal
      ? { qty: bid.qty + 1, face: bid.face }
      : bid.face < 6
        ? { qty: bid.qty, face: bid.face + 1 }
        : { qty: bid.qty + 1, face: 2 }
    : { qty: 1, face: 2 };
  const [qty, setQty] = useState(start.qty);
  const [face, setFace] = useState(start.face);
  const faces = pal ? (bid ? [bid.face] : [1, 2, 3, 4, 5, 6]) : [2, 3, 4, 5, 6];
  const legal = !bid || (pal ? qty > bid.qty && face === bid.face : qty > bid.qty || (qty === bid.qty && face > bid.face));
  const mineFor = estimate(view, face).likely;
  const risk = qty <= mineFor ? "looks safe" : qty === mineFor + 1 ? "is a bit of a stretch" : "is a big bluff";
  const theirs = bid ? estimate(view, bid.face).likely : 0;
  return (
    <div className="stack-sm space-top">
      <p>
        <b>Your move.</b> {bid ? "Raise the bid, or call it." : "Open the bidding: say how many of one face you think are on the whole table."}
      </p>
      {bid && (
        <p className="dice-advice">
          {bid.qty > theirs
            ? `${bidText(bid.qty, bid.face)} is more than the ${theirs} you’d expect: calling Liar! looks good.`
            : bid.qty === theirs
              ? `${bidText(bid.qty, bid.face)} is about what you’d expect: Spot on! could pay, or raise.`
              : `${bidText(bid.qty, bid.face)} is fewer than the ${theirs} you’d expect: probably true, so raise.`}
        </p>
      )}
      <div className="row" role="group" aria-label="How many dice">
        <Btn size="small" variant="ghost" aria-label="One fewer" disabled={qty <= 1} onClick={() => setQty((q) => q - 1)}>
          −
        </Btn>
        <span className="lead" aria-live="polite">
          {qty} ×
        </span>
        <Btn size="small" variant="ghost" aria-label="One more" disabled={qty >= view.total} onClick={() => setQty((q) => q + 1)}>
          +
        </Btn>
      </div>
      <div className="row" role="group" aria-label="Which face">
        {faces.map((f) => (
          <Btn key={f} size="small" variant="ghost" aria-pressed={face === f} aria-label={FACE_NAME[f]} onClick={() => setFace(f)}>
            <span aria-hidden="true" className="die-btn">
              {PIPS[f]}
            </span>
          </Btn>
        ))}
      </div>
      <div className="row">
        <Btn
          variant="accent"
          size="big"
          disabled={!legal}
          onClick={() => {
            sfx.pop();
            send({ t: "act", a: "bid", qty, face });
          }}
        >
          Bid {bidText(qty, face)}
        </Btn>
        {bid && (
          <>
            <Btn variant="danger" size="big" onClick={() => send({ t: "act", a: "liar" })}>
              Liar!
            </Btn>
            <Btn variant="gold" onClick={() => send({ t: "act", a: "spot" })}>
              Spot on!
            </Btn>
          </>
        )}
      </div>
      {legal ? (
        <p className="muted">
          Your bid {risk}: about {mineFor} {FACE_NAME[face]}
          {mineFor === 1 ? "" : "s"} are likely.
        </p>
      ) : (
        <p className="muted">{pal ? "Palifico: same face, more dice." : "Raise it: more dice, or the same number of a higher face."}</p>
      )}
    </div>
  );
}

function Reveal({ view, you }: { view: DiceView; you: string }) {
  const l = view.last!;
  return (
    <Card tone="soft">
      <h3>
        {nameOf(view.players, l.caller)} called {l.call === "spot" ? "spot on" : "liar"} on {bidText(l.bid.qty, l.bid.face)}
      </h3>
      <p className="lead">
        There were <b>{l.actual}</b>
        {l.wild > 0 ? (
          <>
            {" "}
            ({l.exact} {FACE_NAME[l.bid.face]}
            {l.exact === 1 ? "" : "s"} + {l.wild} wild {l.wild === 1 ? "one" : "ones"})
          </>
        ) : null}
        .{" "}
        {l.loser
          ? `${nameOf(view.players, l.loser)}${l.loser === you ? " (you)" : ""} loses a die.`
          : l.gained
            ? `${nameOf(view.players, l.gained)} wins a die back!`
            : "Exactly right!"}
      </p>
      <ul className="dice-reveal">
        {Object.entries(l.dice).map(([pid, ds]) => (
          <li key={pid}>
            <b>{nameOf(view.players, pid)}</b>
            <span className="dice-row">
              {ds.map((d, i) => (
                <Die key={i} face={d} hot={d === l.bid.face || (d === 1 && !l.palifico)} />
              ))}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Final({ view, you }: { view: DiceView; you: string }) {
  const order = view.standings ?? [];
  return (
    <>
      <Card tone="stage" className="center">
        <p className="sign">Last one rolling</p>
        {order[0] && (
          <p className="lead space-top">
            <span className="burst">
              <b>{nameOf(view.players, order[0])}</b>
            </span>
            {order[0] === you ? " (you!)" : ""} wins.
          </p>
        )}
      </Card>
      <Card>
        <h3>Standings</h3>
        <ol className="evidence">
          {order.map((pid) => (
            <li key={pid}>
              {nameOf(view.players, pid)}
              {pid === you ? " (you)" : ""}
            </li>
          ))}
        </ol>
      </Card>
    </>
  );
}
