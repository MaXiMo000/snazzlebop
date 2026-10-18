import { useState } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { HangmanView } from "../types";

interface Props {
  view: HangmanView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const ALPHABET = "abcdefghijklmnopqrstuvwxyz".split("");

export function Hangman({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const name = (pid: string) => (pid === you && !tv ? "You" : nameOf(view.players, pid));
  const setting = view.phase === "set";
  const mySet = !tv && setting && view.setter === you;
  const myTurn = !tv && view.phase === "guess" && view.guesser === you;

  useOnChange(view.misses.length, (was, now) => {
    if (now > was) sfx.buzz();
  });
  useOnChange(view.guessed.length, (was, now) => {
    if (now > was) sfx.ding();
  });
  useOnChange(myTurn, (was, now) => {
    if (now && !was) sfx.pop();
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "reveal" && view.result) {
      if (view.result.solver) {
        sfx.fanfare();
        show.stinger(view.result.solver === you && !tv ? "SOLVED IT!" : "SOLVED!");
      } else show.stinger("THE WORD WINS!", "bad");
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });

  const status =
    view.phase === "final"
      ? "Final scores"
      : setting
        ? `${name(view.setter)} ${view.setter === you && !tv ? "pick" : "picks"} the word`
        : view.phase === "guess"
          ? `${view.guesser ? name(view.guesser) : ""}${view.guesser === you && !tv ? "r turn" : "’s turn"}`
          : "The answer";
  const sign = view.phase === "final" ? status : `Round ${view.round} of ${view.rounds} · ${status}`;

  return (
    <div className={`seg-hangman stack hm ${tv ? "big" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Hangman" remaining={view.phase === "final" ? null : view.remaining} receivedAt={receivedAt}>
        {view.phase !== "final" && (
          <p className="hm-tags">
            <span className="chip plum">
              <span aria-hidden="true">✏️</span> Word by {view.setter === you && !tv ? "you" : nameOf(view.players, view.setter)}
            </span>
            {view.hint && <span className="chip paper">Hint: {view.hint}</span>}
          </p>
        )}
      </ShowHead>

      {setting && (mySet ? <SetWord key={view.round} view={view} send={send} /> : <Waiting view={view} />)}

      {(view.phase === "guess" || view.phase === "reveal") && (
        <div className="hm-stage">
          <Card tone="stage" className="hm-board">
            <Gallows misses={view.misses.length} max={view.max_misses} />
            <Word view={view} />
            {view.word && view.phase === "guess" && <p className="hm-yours">Your word: {view.word}</p>}
            {view.phase === "reveal" && view.result && (
              <p className="sign space-top">
                {view.result.solver ? `${name(view.result.solver)} solved it!` : `Nobody got it: ${name(view.result.setter)} scores!`}
              </p>
            )}
          </Card>
          <div className="stack">
            {view.phase === "guess" && <Turns view={view} you={you} tv={tv} />}
            <Keyboard view={view} send={send} active={myTurn} />
            {myTurn && <Solve send={send} />}
            {view.misses.length > 0 && (
              <p className="hm-misses">
                <b>
                  Misses ({view.misses.length} of {view.max_misses}):
                </b>{" "}
                {view.misses.map((m, i) => (
                  <span key={i} className="hm-miss">
                    {m === "⏱" ? "⏱ out of time" : m.toUpperCase()}
                  </span>
                ))}
              </p>
            )}
          </div>
        </div>
      )}

      <Scores view={view} you={you} tv={tv} />
    </div>
  );
}

/** The drawing: gallows first, then a piece per miss (head, body, arms, legs). */
function Gallows({ misses, max }: { misses: number; max: number }) {
  const parts = [
    <circle key="head" cx="140" cy="62" r="16" />,
    <line key="body" x1="140" y1="78" x2="140" y2="130" />,
    <line key="arm1" x1="140" y1="92" x2="118" y2="112" />,
    <line key="arm2" x1="140" y1="92" x2="162" y2="112" />,
    <line key="leg1" x1="140" y1="130" x2="122" y2="160" />,
    <line key="leg2" x1="140" y1="130" x2="158" y2="160" />,
  ];
  return (
    <svg className="hm-gallows" viewBox="0 0 200 190" role="img" aria-label={`${misses} of ${max} misses`}>
      <g className="hm-frame">
        <line x1="20" y1="180" x2="120" y2="180" />
        <line x1="50" y1="180" x2="50" y2="20" />
        <line x1="50" y1="20" x2="140" y2="20" />
        <line x1="140" y1="20" x2="140" y2="46" />
      </g>
      <g className="hm-figure">{parts.slice(0, misses)}</g>
    </svg>
  );
}

/** The blanks: each word stays on one line; letters fill in as they're found. */
function Word({ view }: { view: HangmanView }) {
  const words: (string | null)[][] = [[]];
  for (const c of view.pattern) {
    if (c === " ") words.push([]);
    else words[words.length - 1]!.push(c);
  }
  const shown = view.pattern.map((c) => c ?? "_").join("").replace(/_/g, " blank ");
  return (
    <p className={`hm-word ${sizeClass(Math.max(...words.map((w) => w.length)))}`}>
      <span className="sr-only">The word: {shown}</span>
      {words.map((w, i) => (
        <span key={i} className="hm-chunk" aria-hidden="true">
          {w.map((c, j) => (
            <span key={j} className={`hm-tile ${c ? "shown" : ""}`}>
              {c ? c.toUpperCase() : ""}
            </span>
          ))}
        </span>
      ))}
    </p>
  );
}

/** Tiles shrink so the longest word fits on one line where it can (it wraps as a last resort). */
function sizeClass(longest: number): string {
  if (longest > 16) return "len-24";
  if (longest > 11) return "len-16";
  if (longest > 7) return "len-11";
  return "";
}

function Keyboard({ view, send, active }: { view: HangmanView; send: Props["send"]; active: boolean }) {
  return (
    <div className="hm-keys" role="group" aria-label="Letters">
      {ALPHABET.map((l) => {
        const hit = view.guessed.includes(l);
        const miss = view.misses.includes(l);
        return (
          <button
            key={l}
            type="button"
            className={`hm-key ${hit ? "hit" : miss ? "miss" : ""}`}
            disabled={!active || hit || miss}
            aria-label={`${l.toUpperCase()}${hit ? ", in the word" : miss ? ", not in it" : ""}`}
            onClick={() => send({ t: "act", a: "letter", letter: l })}
          >
            {l.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}

function Solve({ send }: { send: Props["send"] }) {
  const [text, setText] = useState("");
  return (
    <form
      className="ask-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim()) return;
        send({ t: "act", a: "solve", word: text });
        setText("");
      }}
    >
      <div>
        <label className="field" htmlFor="hm-solve">
          Know it? Solve it (a wrong guess is a miss)
        </label>
        <input id="hm-solve" type="text" autoComplete="off" maxLength={24} value={text} onChange={(e) => setText(e.target.value)} placeholder="The whole thing" />
      </div>
      <Btn type="submit" variant="accent" disabled={!text.trim()}>
        Solve!
      </Btn>
    </form>
  );
}

function Turns({ view, you, tv }: { view: HangmanView; you: string; tv: boolean }) {
  return (
    <ul className="hm-turns" aria-label="Turn order">
      {view.order.map((pid) => (
        <li key={pid} className={pid === view.guesser ? "now" : ""}>
          <Avatar pid={pid} name={nameOf(view.players, pid)} />
          <span>{pid === you && !tv ? "You" : nameOf(view.players, pid).split(/\s+/)[0]}</span>
          {pid === view.guesser && <span className="sr-only">, guessing now</span>}
        </li>
      ))}
    </ul>
  );
}

function SetWord({ view, send }: { view: HangmanView; send: Props["send"] }) {
  const [own, setOwn] = useState("");
  const [hint, setHint] = useState("");
  const ok = /^[a-zA-Z]+( [a-zA-Z]+){0,3}$/.test(own.trim()) && own.replace(/ /g, "").length >= 3 && own.trim().length <= 24;
  const go = (word: string) => {
    sfx.pop();
    send({ t: "act", a: "set", word, hint });
  };
  return (
    <Card tone="stage">
      <p className="sign center">Your turn to set the word</p>
      <h3 className="space-top center">Pick one…</h3>
      <div className="hm-picks space-top" role="group" aria-label="Suggested words">
        {view.suggestions.map((w) => (
          <Btn key={w} variant="gold" onClick={() => go(w)}>
            {w}
          </Btn>
        ))}
      </div>
      <form
        className="stack-sm space-top"
        onSubmit={(e) => {
          e.preventDefault();
          if (ok) go(own.trim());
        }}
      >
        <label className="field" htmlFor="hm-own">
          …or type your own (letters and spaces)
        </label>
        <input id="hm-own" type="text" autoComplete="off" maxLength={24} value={own} onChange={(e) => setOwn(e.target.value)} placeholder="Secret word" />
        <label className="field" htmlFor="hm-hint">
          A hint (optional)
        </label>
        <input id="hm-hint" type="text" autoComplete="off" maxLength={40} value={hint} onChange={(e) => setHint(e.target.value)} placeholder="Food, a film, an animal…" />
        <Btn type="submit" variant="accent" block disabled={!ok}>
          Set my word
        </Btn>
      </form>
    </Card>
  );
}

function Waiting({ view }: { view: HangmanView }) {
  return (
    <Card tone="stage" className="center">
      <Avatar pid={view.setter} name={nameOf(view.players, view.setter)} className="xl" />
      <p className="sign space-top">{nameOf(view.players, view.setter)} is choosing a word…</p>
    </Card>
  );
}

function Scores({ view, you, tv }: { view: HangmanView; you: string; tv: boolean }) {
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
            </b>
            <span className="score-pts">{view.scores[p.id] ?? 0}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
