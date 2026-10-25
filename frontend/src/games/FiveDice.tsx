import { useState } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { FiveDiceCard, FiveDiceView } from "../types";

interface Props {
  view: FiveDiceView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const UPPER: [string, string][] = [
  ["ones", "Ones"],
  ["twos", "Twos"],
  ["threes", "Threes"],
  ["fours", "Fours"],
  ["fives", "Fives"],
  ["sixes", "Sixes"],
];
const LOWER: [string, string][] = [
  ["three_kind", "Three of a kind"],
  ["four_kind", "Four of a kind"],
  ["full_house", "Full house"],
  ["small_straight", "Small straight"],
  ["large_straight", "Large straight"],
  ["five_dice", "Five dice!"],
  ["chance", "Chance"],
];
const NAMES = Object.fromEntries([...UPPER, ...LOWER]);
// Which of the nine pip spots are lit for each face (a 3 x 3 grid, read row by row).
const PIPS: Record<number, number[]> = {
  1: [4],
  2: [0, 8],
  3: [0, 4, 8],
  4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8],
  6: [0, 2, 3, 5, 6, 8],
};

function Die({ face, held, small = false }: { face: number; held?: boolean; small?: boolean }) {
  return (
    <span className={`fd-die ${held ? "held" : ""} ${small ? "small" : ""} ${face ? "" : "blank"}`} aria-hidden="true">
      {Array.from({ length: 9 }, (_, i) => (
        <span key={i} className={PIPS[face]?.includes(i) ? "pip on" : "pip"} />
      ))}
    </span>
  );
}

export function FiveDice({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const mine = tv ? undefined : view.cards[you];
  useOnChange(view.round, (was, now) => {
    if (now > was) sfx.ding();
  });
  useOnChange(view.last.length ? view.last[view.last.length - 1]! : null, (_, e) => {
    if (e && e.box === "five_dice" && e.points === 50) {
      sfx.fanfare();
      show.stinger(e.by === you && !tv ? "FIVE DICE!" : `${nameOf(view.players, e.by)}: FIVE DICE!`);
      show.celebrate();
    }
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });
  const waiting = view.players.filter((p) => !view.cards[p.id]?.done).length;
  const sign =
    view.phase === "final"
      ? "Final scores"
      : `Round ${view.round} of ${view.rounds} · ${mine?.done ? `Waiting for ${waiting}` : "Roll and score"}`;
  return (
    <div className={`seg-fivedice stack fd ${tv ? "big" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Five Dice" remaining={view.phase === "final" ? null : view.remaining} receivedAt={receivedAt}>
        {mine && view.phase === "play" && !mine.done && (
          <p className="fd-tags">
            <span className="chip plum">{mine.rolls === 0 ? "Roll to start your turn" : `Roll ${mine.rolls} of ${mine.max_rolls}`}</span>
          </p>
        )}
      </ShowHead>
      <div className="fd-layout">
        <div className="stack">
          {mine && view.phase === "play" && <Tray key={`${view.round}`} card={mine} send={send} />}
          {mine && <Scorecard view={view} card={mine} send={send} />}
          {!mine && <Table view={view} />}
        </div>
        <div className="stack">
          {mine && <Table view={view} you={you} />}
          <Standings view={view} you={you} tv={tv} />
        </div>
      </div>
    </div>
  );
}

function Tray({ card, send }: { card: FiveDiceCard; send: Props["send"] }) {
  const [held, setHeld] = useState<boolean[]>(card.held);
  const left = card.max_rolls - card.rolls;
  if (card.done) {
    return (
      <Card tone="soft" className="center">
        <p className="lead">Scored! Waiting for the others…</p>
      </Card>
    );
  }
  return (
    <Card tone="stage" className="fd-tray">
      <div className="fd-dice" role="group" aria-label={card.rolls ? "Your dice: tap to hold" : "Your dice"}>
        {card.dice.map((d, i) =>
          card.rolls > 0 && left > 0 ? (
            <button
              key={i}
              type="button"
              className="fd-hold"
              aria-pressed={held[i]}
              aria-label={`Die ${i + 1}: ${d}${held[i] ? ", held" : ""}`}
              onClick={() => {
                sfx.tick();
                setHeld(held.map((h, j) => (j === i ? !h : h)));
              }}
            >
              <Die face={d} held={held[i]} />
              <span className="fd-held-tag" aria-hidden="true">
                {held[i] ? "HELD" : ""}
              </span>
            </button>
          ) : (
            <span key={i} className="fd-hold static">
              <Die face={d} />
              <span className="sr-only">{d ? `Die ${i + 1}: ${d}` : ""}</span>
            </span>
          ),
        )}
      </div>
      {left > 0 ? (
        <Btn
          variant="accent"
          size="big"
          block
          className="space-top"
          onClick={() => {
            sfx.pop();
            send({ t: "act", a: "roll", ...(card.rolls ? { held } : {}) });
          }}
        >
          {card.rolls === 0 ? "Roll!" : `Roll again (${left} left)`}
        </Btn>
      ) : (
        <p className="center space-top lead">Last roll: pick a box below</p>
      )}
      {card.rolls > 0 && <p className="center muted space-top">Tap a box on your scorecard to score these dice.</p>}
      <p className="sr-only" aria-live="polite">
        {card.rolls ? `You rolled ${card.dice.join(", ")}` : ""}
      </p>
    </Card>
  );
}

function Scorecard({ view, card, send }: { view: FiveDiceView; card: FiveDiceCard; send: Props["send"] }) {
  const options = view.you?.options ?? {};
  const row = ([id, label]: [string, string]) => {
    const filled = card.boxes[id];
    const can = options[id];
    return (
      <li key={id} className={filled !== undefined ? "filled" : can !== undefined ? "open" : ""}>
        {filled === undefined && can !== undefined && view.phase === "play" ? (
          <button
            type="button"
            className="fd-box"
            onClick={() => {
              sfx.pop();
              send({ t: "act", a: "score", box: id });
            }}
          >
            <span>{label}</span>
            <b className={can > 0 ? "fd-can" : "fd-can zero"}>
              {can > 0 ? `+${can}` : "0"}
              <span className="sr-only"> points: score here</span>
            </b>
          </button>
        ) : (
          <span className="fd-box static">
            <span>{label}</span>
            <b>{filled === undefined ? "" : filled}</b>
          </span>
        )}
      </li>
    );
  };
  return (
    <Card>
      <h3>Your scorecard</h3>
      <ul className="fd-card space-top">{UPPER.map(row)}</ul>
      <p className="fd-bonus">
        Upper bonus: {card.upper >= 63 ? <b>+35 ✓</b> : <span>{card.upper} of 63</span>}
      </p>
      <meter className="fd-meter" min={0} max={63} value={Math.min(63, card.upper)} aria-hidden="true" />
      <ul className="fd-card space-top">{LOWER.map(row)}</ul>
      {card.bonus > 0 && <p className="fd-bonus">Five Dice bonus: <b>+{card.bonus}</b></p>}
      <p className="fd-total">
        Total <b>{card.total}</b>
      </p>
    </Card>
  );
}

/** Everyone's dice this round (and who has scored). */
function Table({ view, you }: { view: FiveDiceView; you?: string }) {
  return (
    <Card>
      <h3>The table</h3>
      <ul className="fd-table space-top">
        {view.players
          .filter((p) => p.id !== you)
          .map((p) => {
            const c = view.cards[p.id]!;
            const last = [...view.last].reverse().find((e) => e.by === p.id && e.round === view.round - 1);
            return (
              <li key={p.id} className={c.done ? "done" : ""}>
                <span className="fd-who">
                  <Avatar pid={p.id} name={p.name} className="tiny" />
                  <b>{p.name}</b>
                </span>
                <span className="fd-row-dice">
                  {c.dice.map((d, i) => (
                    <Die key={i} face={d} held={c.held[i] && !c.done} small />
                  ))}
                </span>
                <span className="fd-state muted">
                  {c.done && last ? `${NAMES[last.box]}: ${last.points}` : c.done ? "scored" : c.rolls ? `roll ${c.rolls} of ${c.max_rolls}` : "thinking…"}
                </span>
              </li>
            );
          })}
      </ul>
    </Card>
  );
}

function Standings({ view, you, tv }: { view: FiveDiceView; you: string; tv: boolean }) {
  const rows = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  const top = view.scores[rows[0]?.id ?? ""] ?? 0;
  const tied = rows.filter((p) => (view.scores[p.id] ?? 0) === top).length > 1;
  return (
    <Card>
      <h3>{view.phase === "final" ? (tied ? "A tie at the top!" : `${nameOf(view.players, rows[0]!.id)} wins!`) : "Scores"}</h3>
      <ol className="score-rows">
        {rows.map((p, i) => (
          <li key={p.id}>
            <b>
              {view.phase === "final" && i === 0 && !tied ? "👑 " : ""}
              {p.name}
              {p.id === you && !tv ? " (you)" : ""}
            </b>
            <span className="score-pts">{view.scores[p.id] ?? 0}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
