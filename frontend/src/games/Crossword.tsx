import { useMemo, useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { CrosswordClue, CrosswordView } from "../types";

interface Props {
  view: CrosswordView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

function cellsOf(c: CrosswordClue): string[] {
  return Array.from({ length: c.len }, (_, k) => (c.dir === "across" ? `${c.row},${c.col + k}` : `${c.row + k},${c.col}`));
}

export function Crossword({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const firstOpen = view.clues.find((c) => !c.solved_by)?.id ?? 0;
  const [selected, setSelected] = useState<number>(firstOpen);
  const [answer, setAnswer] = useState("");
  const clue = view.clues.find((c) => c.id === selected) ?? view.clues[0];
  const solvedCount = view.clues.filter((c) => c.solved_by).length;

  useOnChange(solvedCount, (prev, next) => {
    if (next <= prev) return;
    const newest = view.clues.filter((c) => c.solved_by).at(-1);
    if (newest?.solved_by === you && !tv) {
      sfx.ding();
      show.stinger("NAILED IT!");
    } else sfx.pop();
    // Your clue just got solved (by you or someone faster): hop to the next open one.
    if (clue?.solved_by) {
      const next = view.clues.find((c) => !c.solved_by);
      if (next) setSelected(next.id);
    }
  });
  useOnChange(view.hint_level, (_, lvl) => {
    if (lvl > 0) show.stinger(lvl === 1 ? "HINT: FIRST LETTERS" : "HINT: MIDDLE LETTERS");
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "final") {
      sfx.fanfare();
      show.stinger(solvedCount === view.clues.length ? "GRID COMPLETE!" : "TIME'S UP!");
      show.celebrate();
    }
  });

  const byCell = useMemo(() => new Map(view.cells.map((c) => [`${c.row},${c.col}`, c])), [view.cells]);
  const highlight = new Set(clue ? cellsOf(clue) : []);
  const solvedCells = new Set(view.clues.filter((c) => c.solved_by).flatMap(cellsOf));

  const pickCell = (key: string) => {
    const hits = view.clues.filter((c) => cellsOf(c).includes(key));
    if (!hits.length) return;
    // Tapping the same cell again flips between its across and down clue.
    const next = hits.find((c) => c.id !== selected && !c.solved_by) ?? hits.find((c) => !c.solved_by) ?? hits[0]!;
    setSelected(next.id);
  };

  const sign = view.phase === "final" ? "Pencils down" : `${solvedCount} of ${view.clues.length} solved`;
  return (
    <div className="seg-crossword stack">
      {show.node}
      <ShowHead sign={sign} title="Crossword Race" remaining={view.remaining} receivedAt={receivedAt}>
        <div className="row">
          {view.hint_level > 0 && view.phase !== "final" && <span className="chip plum">Hint {view.hint_level} revealed</span>}
          {view.mode === "teams" &&
            Object.entries(view.team_totals).map(([team, pts]) => (
              <span key={team} className={`chip ${view.teams[you] === team ? "teal" : "paper"}`}>
                {team}
                {view.teams[you] === team ? " (yours)" : ""}: {pts}
              </span>
            ))}
        </div>
      </ShowHead>
      {view.mode === "teams" && view.phase === "solve" && view.teams[you] && (
        <p className="muted">
          Your team: {Object.entries(view.teams).filter(([, t]) => t === view.teams[you]).map(([id]) => nameOf(view.players, id)).join(", ")}.
          Every solve scores for all of you; bought letters are shared.
        </p>
      )}

      <Card className="xw-card">
        <div className={`xw-grid cols-${view.width}`} aria-hidden="true">
          {Array.from({ length: view.height * view.width }, (_, i) => {
            const key = `${Math.floor(i / view.width)},${i % view.width}`;
            const cell = byCell.get(key);
            if (!cell) return <div key={key} className="xw-cell void" />;
            return (
              <div
                key={key}
                className={`xw-cell ${highlight.has(key) ? "hl" : ""} ${solvedCells.has(key) ? "solved" : ""} ${cell.bought ? "bought" : ""}`}
                onClick={() => pickCell(key)}
              >
                {cell.num && <span className="xw-num">{cell.num}</span>}
                <span className="xw-letter">{cell.letter ?? ""}</span>
              </div>
            );
          })}
        </div>
        <p className="sr-only" aria-live="polite">
          {solvedCount} of {view.clues.length} clues solved.
        </p>
      </Card>

      {!tv && view.phase === "solve" && clue && !clue.solved_by && (
        <Card tone="soft">
          <form
            className="ask-form"
            onSubmit={(e) => {
              e.preventDefault();
              const a = answer.replace(/[^a-zA-Z]/g, "");
              if (!a) return;
              send({ t: "act", a: "guess", clue: clue.id, answer: a });
              setAnswer("");
            }}
          >
            <div>
              <label className="field" htmlFor="xw-answer">
                {clue.num} {clue.dir === "across" ? "Across" : "Down"} ({clue.len} letters): {clue.clue}
              </label>
              <input
                id="xw-answer"
                className="code-input"
                type="text"
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                maxLength={clue.len}
                value={answer}
                onChange={(e) => setAnswer(e.target.value.replace(/[^a-zA-Z]/g, ""))}
              />
            </div>
            <Btn type="submit" variant="accent" disabled={!answer}>
              Solve it
            </Btn>
            <Btn
              variant="ghost"
              disabled={view.letters_left <= 0}
              onClick={() => {
                sfx.pop();
                send({ t: "act", a: "buy", clue: clue.id });
              }}
            >
              Buy a letter (−{view.letter_cost}) · {view.letters_left} left
            </Btn>
          </form>
        </Card>
      )}

      <div className="grid">
        {(["across", "down"] as const).map((dir) => (
          <Card key={dir}>
            <h3>{dir === "across" ? "Across" : "Down"}</h3>
            <ul className="xw-clues">
              {view.clues
                .filter((c) => c.dir === dir)
                .map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className={`xw-clue ${c.solved_by ? "done" : ""}`}
                      aria-pressed={c.id === selected}
                      disabled={tv || view.phase !== "solve" || !!c.solved_by}
                      onClick={() => setSelected(c.id)}
                    >
                      <b>{c.num}.</b> {c.clue} <span className="muted">({c.len})</span>
                      {c.answer && (
                        <span className="xw-answer">
                          {" "}
                          {c.answer}
                          {c.solved_by ? ` · ${nameOf(view.players, c.solved_by)}${c.solved_by === you ? " (you)" : ""}` : ""}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
            </ul>
          </Card>
        ))}
      </div>
    </div>
  );
}
