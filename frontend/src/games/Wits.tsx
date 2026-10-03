import { useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { WitsView } from "../types";

interface Props {
  view: WitsView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const fmt = (n: number) => n.toLocaleString("en-US");

export function Wits({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  useOnChange(view.phase, (_, phase) => {
    if (phase === "reveal" && view.result) {
      const mine = view.result.gains[you] ?? 0;
      if (!tv && mine > 0) {
        sfx.fanfare();
        show.stinger(`+${mine}!`);
      } else {
        sfx.ding();
        show.stinger("THE ANSWER IS…");
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });
  const sign =
    view.phase === "final"
      ? "Final scores"
      : `Question ${view.round} of ${view.rounds} · ${{ answer: "Answer", bet: "Place your bets", reveal: "Reveal" }[view.phase as "answer" | "bet" | "reveal"] ?? ""}`;
  return (
    <div className="seg-wits stack">
      {show.node}
      <ShowHead sign={sign} title="Wager Wits" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">Closest without going over wins · bet on anyone’s answer</span>
      </ShowHead>

      {view.phase !== "final" && (
        <Card tone="stage" className="center">
          <p className="sign">The question</p>
          <h3 className="prompt space-top">{view.question.q}</h3>
        </Card>
      )}

      {view.phase === "answer" &&
        (tv ? (
          <Card tone="soft" className="center">
            <p className="lead" aria-live="polite">
              {view.answered.length} of {view.players.length} answers in
            </p>
          </Card>
        ) : (
          <AnswerForm view={view} send={send} />
        ))}

      {(view.phase === "bet" || view.phase === "reveal") && (
        <Board view={view} you={you} send={send} tv={tv} />
      )}

      {view.phase === "reveal" && view.result && (
        <Card tone="soft">
          <h3>
            The answer: {fmt(view.result.answer)} {view.question.unit}
          </h3>
          <ul className="evidence">
            {view.players.map((p) => (
              <li key={p.id}>
                <b>{p.name}</b>
                {p.id === you ? " (you)" : ""}: guessed{" "}
                {view.result!.answers[p.id] !== undefined ? fmt(view.result!.answers[p.id]!) : "nothing"} ·{" "}
                <span className={`chip ${(view.result!.gains[p.id] ?? 0) > 0 ? "teal" : ""}`}>+{view.result!.gains[p.id] ?? 0}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {view.phase === "final" && (
        <Card>
          <h3>Every question</h3>
          <ol className="evidence">
            {(view.history ?? []).map((h, i) => (
              <li key={i}>
                {h.q} <b>{fmt(h.answer)}</b>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}

function AnswerForm({ view, send }: { view: WitsView; send: Props["send"] }) {
  const [text, setText] = useState("");
  if (view.you.answer !== null && view.you.answer !== undefined) {
    return (
      <Card tone="soft" className="center">
        <h3>Locked in: {fmt(view.you.answer)}</h3>
        <p className="muted" aria-live="polite">
          {view.answered.length} of {view.players.length} answers in
        </p>
      </Card>
    );
  }
  const n = Number(text.replace(/[^0-9]/g, ""));
  const ok = text.replace(/[^0-9]/g, "") !== "" && Number.isSafeInteger(n) && n <= 1_000_000_000;
  return (
    <Card>
      <form
        className="ask-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ok) return;
          sfx.pop();
          send({ t: "act", a: "answer", value: n });
        }}
      >
        <div>
          <label className="field" htmlFor="wits-answer">
            Your answer{view.question.unit ? ` (${view.question.unit})` : ""}
          </label>
          <input
            id="wits-answer"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="A whole number"
          />
        </div>
        <Btn type="submit" variant="accent" disabled={!ok}>
          Lock it in!
        </Btn>
      </form>
    </Card>
  );
}

function Board({ view, you, send, tv }: { view: WitsView; you: string; send: Props["send"]; tv: boolean }) {
  const [chips, setChips] = useState<number[]>([]);
  const placed = view.you.bets && view.you.bets.length > 0;
  const betting = !tv && view.phase === "bet" && !placed;
  const winner = view.result?.slot;
  return (
    <Card>
      <h3>{view.phase === "bet" ? "The board: who’s closest without going over?" : "The board"}</h3>
      {betting && (
        <p className="muted">
          Tap a slot for each of your {view.chips} chips (you can double up). Each winning chip pays {view.chip_value} × its odds.
        </p>
      )}
      <div className="wits-board" role="group" aria-label="Answer slots">
        {view.board.map((s) => {
          const mine = (placed ? view.you.bets! : chips).filter((c) => c === s.slot).length;
          return (
            <button
              key={s.slot}
              type="button"
              className={`wits-slot ${winner === s.slot ? "win" : ""}`}
              aria-pressed={mine > 0}
              disabled={!betting || chips.length >= view.chips}
              onClick={() => {
                sfx.pop();
                setChips((c) => [...c, s.slot]);
              }}
            >
              <span className="wits-value">{s.value === null ? "Lower than all" : fmt(s.value)}</span>
              <span className="chip plum">×{s.odds}</span>
              {s.by.length > 0 && <span className="muted">{s.by.map((p) => nameOf(view.players, p)).join(", ")}</span>}
              {mine > 0 && <span className="chip teal">{"🪙".repeat(mine)}</span>}
              {s.by.includes(you) && <span className="sr-only">(your answer)</span>}
            </button>
          );
        })}
      </div>
      {betting && (
        <div className="row space-top">
          <Btn
            variant="accent"
            size="big"
            disabled={chips.length !== view.chips}
            onClick={() => {
              sfx.pop();
              send({ t: "act", a: "bet", slots: chips });
            }}
          >
            {chips.length === view.chips ? "Place my bets" : `Pick ${view.chips - chips.length} more`}
          </Btn>
          <Btn variant="ghost" disabled={!chips.length} onClick={() => setChips([])}>
            Clear
          </Btn>
        </div>
      )}
      {view.phase === "bet" && (
        <p className="muted space-top" aria-live="polite">
          {placed ? "Your chips are down. " : ""}
          {view.bet_in.length} of {view.players.length} have bet
        </p>
      )}
    </Card>
  );
}
