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
        <span className="chip plum">
          {view.total} dice on the table · ones are wild
        </span>
      </ShowHead>

      {view.phase !== "final" && (
        <Card tone="stage" className="center">
          <p className="sign">Current bid</p>
          {view.bid ? (
            <p className="lead space-top">
              <b>{nameOf(view.players, view.bid.player)}</b> says there are at least <b>{bidText(view.bid.qty, view.bid.face)}</b>
            </p>
          ) : (
            <p className="lead space-top">No bid yet. {view.phase === "bid" ? "Opening bid coming up…" : ""}</p>
          )}
        </Card>
      )}

      {!tv && view.phase === "bid" && view.you.dice.length > 0 && (
        <Card tone="soft">
          <h3>Your dice</h3>
          <p className="dice-row" role="group" aria-label="Your dice">
            {view.you.dice.map((d, i) => (
              <Die key={i} face={d} />
            ))}
          </p>
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

function BidForm({ view, send }: { view: DiceView; send: Props["send"] }) {
  // Default to the smallest legal raise: same count with the next face, or one more die of twos.
  const bid = view.bid;
  const start = bid ? (bid.face < 6 ? { qty: bid.qty, face: bid.face + 1 } : { qty: bid.qty + 1, face: 2 }) : { qty: 1, face: 2 };
  const [qty, setQty] = useState(start.qty);
  const [face, setFace] = useState(start.face);
  const legal = !bid || qty > bid.qty || (qty === bid.qty && face > bid.face);
  return (
    <div className="stack-sm space-top">
      <p>
        <b>Your move.</b> Raise the bid, or call it.
      </p>
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
        {[2, 3, 4, 5, 6].map((f) => (
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
      {!legal && <p className="muted">Raise it: more dice, or the same number of a higher face.</p>}
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
        There were <b>{l.actual}</b>.{" "}
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
                <Die key={i} face={d} hot={d === l.bid.face || d === 1} />
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
