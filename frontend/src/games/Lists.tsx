import { useEffect, useRef, useState } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { ListsView } from "../types";

interface Props {
  view: ListsView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const MAX = 30;
const SAVE_MS = 700;

/** The same check the server makes: the first letter, not counting a leading "the", "a" or "an". */
function fits(text: string, letter: string): boolean {
  const s = text.trim().toLowerCase().replace(/^(the|a|an) /, "");
  const first = [...s].find((c) => /[\p{L}\p{N}]/u.test(c)) ?? "";
  return first === letter.toLowerCase();
}

const MARK: Record<string, { icon: string; label: string; cls: string }> = {
  ok: { icon: "✓", label: "100", cls: "ok" },
  same: { icon: "=", label: "Same", cls: "same" },
  nope: { icon: "👎", label: "Out", cls: "nope" },
  bad: { icon: "✗", label: "No", cls: "bad" },
};

export function Lists({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const me = tv ? null : view.you;
  useOnChange(view.phase, (_, phase) => {
    if (phase === "write") {
      sfx.ding();
      show.stinger(`THE LETTER IS ${view.letter}!`);
    } else if (phase === "review") sfx.pop();
    else if (phase === "scores" && view.result) {
      const mine = view.result.gains[you] ?? 0;
      if (!tv && mine > 0) {
        sfx.fanfare();
        show.stinger(`+${mine}`);
      } else sfx.ding();
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });
  const label = { write: "Write", review: "Check the answers", scores: "Scores", final: "" }[view.phase];
  const sign = view.phase === "final" ? "Final scores" : `List ${view.round} of ${view.rounds} · ${label}`;
  return (
    <div className={`seg-lists stack ll ${tv ? "big" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Letter Lists" remaining={view.phase === "final" ? null : view.remaining} receivedAt={receivedAt}>
        {view.phase !== "final" && (
          <p className="ll-letter-line">
            <span className="ll-tile" aria-label={`The letter is ${view.letter}`}>
              {view.letter}
            </span>
            <span className="ll-rule">Every answer starts with {view.letter}</span>
          </p>
        )}
      </ShowHead>
      {view.phase === "write" && me && <Sheet key={`${view.round}`} view={view} send={send} />}
      {view.phase === "write" && !me && <Categories view={view} />}
      {view.phase === "write" && <Done view={view} you={you} tv={tv} />}
      {(view.phase === "review" || view.phase === "scores") && <Review view={view} you={you} tv={tv} send={send} />}
      <Scores view={view} you={you} tv={tv} />
    </div>
  );
}

/** Your answer sheet: saves as you type, Done locks it in (and can be undone until the clock ends). */
function Sheet({ view, send }: { view: ListsView; send: Props["send"] }) {
  const me = view.you!;
  const [answers, setAnswers] = useState<string[]>(() => [...me.answers]);
  const [done, setDone] = useState(me.done);
  const timer = useRef<number | undefined>(undefined);
  const latest = useRef(answers);
  latest.current = answers;
  const save = (list: string[], finished: boolean) => send({ t: "act", a: "answers", answers: list, done: finished });
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const change = (i: number, text: string) => {
    const next = answers.map((a, j) => (j === i ? text.slice(0, MAX) : a));
    setAnswers(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => save(latest.current, false), SAVE_MS);
  };
  const filled = answers.filter((a) => a.trim()).length;
  return (
    <Card>
      <form
        className="ll-sheet"
        onSubmit={(e) => {
          e.preventDefault();
          window.clearTimeout(timer.current);
          sfx.pop();
          setDone(true);
          save(answers, true);
        }}
      >
        <ol className="ll-fields">
          {view.categories.map((cat, i) => {
            const text = answers[i] ?? "";
            const ok = text.trim() !== "" && fits(text, view.letter);
            const wrong = text.trim() !== "" && !ok;
            return (
              <li key={i} className={ok ? "ok" : wrong ? "wrong" : ""}>
                <label className="field" htmlFor={`ll-${i}`}>
                  {cat}
                </label>
                <div className="ll-input">
                  <input
                    id={`ll-${i}`}
                    type="text"
                    value={text}
                    maxLength={MAX}
                    autoComplete="off"
                    autoCapitalize="words"
                    enterKeyHint={i < view.categories.length - 1 ? "next" : "done"}
                    disabled={done}
                    placeholder={`${view.letter}…`}
                    aria-describedby={wrong ? `ll-${i}-hint` : undefined}
                    onChange={(e) => change(i, e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && i < view.categories.length - 1) {
                        e.preventDefault();
                        document.getElementById(`ll-${i + 1}`)?.focus();
                      }
                    }}
                  />
                  <span className="ll-check" aria-hidden="true">
                    {ok ? "✓" : wrong ? "!" : ""}
                  </span>
                </div>
                {wrong && (
                  <p id={`ll-${i}-hint`} className="ll-hint">
                    Must start with {view.letter}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
        {done ? (
          <Btn
            variant="ghost"
            block
            onClick={() => {
              setDone(false);
              save(answers, false);
            }}
          >
            Locked in ({filled} of {view.categories.length}): change answers
          </Btn>
        ) : (
          <Btn type="submit" variant="accent" size="big" block>
            Done! ({filled} of {view.categories.length})
          </Btn>
        )}
      </form>
    </Card>
  );
}

function Categories({ view }: { view: ListsView }) {
  return (
    <Card tone="stage">
      <ol className="ll-cats">
        {view.categories.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ol>
    </Card>
  );
}

function Done({ view, you, tv }: { view: ListsView; you: string; tv: boolean }) {
  return (
    <Card tone="soft">
      <p className="center" aria-live="polite">
        <b>{view.done.length}</b> of {view.players.length} done
      </p>
      <ul className="ll-done space-top" aria-label="Players">
        {view.players.map((p) => {
          const done = view.done.includes(p.id);
          return (
            <li key={p.id} className={done ? "done" : ""}>
              <Avatar pid={p.id} name={p.name} />
              <span className="ll-done-name">{p.id === you && !tv ? "You" : p.name.split(/\s+/)[0]}</span>
              <span aria-hidden="true">{done ? "✅" : "✍️"}</span>
              <span className="sr-only">{done ? ", done" : ", still writing"}</span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Review({ view, you, tv, send }: { view: ListsView; you: string; tv: boolean; send: Props["send"] }) {
  const answers = view.answers ?? {};
  const scoring = view.phase === "scores" && view.result;
  return (
    <>
      {view.phase === "review" && (
        <p className="ll-howto center">
          {tv ? "Checking the answers. Anything you won’t accept? Vote no on your phone." : "Tap No on any answer you won’t accept. More than half of the others saying no knocks it out."}
        </p>
      )}
      <div className="ll-review">
        {view.categories.map((cat, i) => (
          <Card key={cat} className="ll-cat">
            <h3>
              <span className="ll-num">{i + 1}</span> {cat}
            </h3>
            <ul className="ll-answers">
              {view.players.map((p) => {
                const text = answers[p.id]?.[i] ?? "";
                const k = `${p.id}:${i}`;
                const nos = view.nopes[k] ?? 0;
                const mine = p.id === you && !tv;
                const voted = view.you?.noped.includes(k) ?? false;
                const mark = scoring ? MARK[view.result!.status[p.id]?.[i] ?? "bad"] : null;
                const autoBad = !text.trim() || !fits(text, view.letter);
                return (
                  <li key={p.id} className={`${mark ? mark.cls : autoBad ? "bad" : ""}`}>
                    <Avatar pid={p.id} name={p.name} className="tiny" />
                    <span className="ll-answer">
                      <b>{text.trim() ? text : "—"}</b>
                      <span className="muted">
                        {mine ? "you" : p.name}
                        {!scoring && nos > 0 && <span className="ll-votes"> · {nos} no</span>}
                      </span>
                    </span>
                    {mark ? (
                      <span className={`ll-mark ${mark.cls}`}>
                        <span aria-hidden="true">{mark.icon}</span> {mark.label}
                      </span>
                    ) : !mine && !tv && view.you && text.trim() && !autoBad ? (
                      <button type="button" className="ll-no" aria-pressed={voted} onClick={() => send({ t: "act", a: "nope", who: p.id, i })}>
                        <span aria-hidden="true">👎</span> No
                        <span className="sr-only"> to {text} by {p.name}</span>
                      </button>
                    ) : autoBad ? (
                      <span className="ll-mark bad">
                        <span aria-hidden="true">✗</span> No
                      </span>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </Card>
        ))}
      </div>
    </>
  );
}

function Scores({ view, you, tv }: { view: ListsView; you: string; tv: boolean }) {
  const rows = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  const top = view.scores[rows[0]?.id ?? ""] ?? 0;
  const tied = rows.filter((p) => (view.scores[p.id] ?? 0) === top).length > 1;
  return (
    <Card>
      <h3>{view.phase === "final" ? (tied || top === 0 ? "Final scores: a tie at the top!" : `${nameOf(view.players, rows[0]!.id)} wins!`) : "Scores"}</h3>
      <ol className="score-rows">
        {rows.map((p, i) => (
          <li key={p.id}>
            <b>
              {view.phase === "final" && i === 0 && !tied && top > 0 ? "👑 " : ""}
              {p.name}
              {p.id === you && !tv ? " (you)" : ""}
              {view.result && view.phase === "scores" && (view.result.gains[p.id] ?? 0) > 0 && <span className="chip teal">+{view.result.gains[p.id]}</span>}
            </b>
            <span className="score-pts">{view.scores[p.id] ?? 0}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
