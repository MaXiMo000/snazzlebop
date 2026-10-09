import { useEffect, useState } from "react";
import { Btn, Card, ShowHead, nameList, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { ERASER, Sketch } from "../components/sketch";
import { sfx } from "../lib/sfx";
import type { DrawGuessView } from "../types";

interface Props {
  view: DrawGuessView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen (TV and audience) */
  tv?: boolean;
}

type Send = Props["send"];

export function DrawGuess({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const drawing = !tv && view.you.drawer && view.phase === "draw";
  const [colour, setColour] = useState(0);
  const [size, setSize] = useState(1);
  const name = (id: string) => nameOf(view.players, id);
  const drawer = view.drawer ? name(view.drawer) : "";

  useOnChange(view.guessed.length, (prev, next) => {
    const who = view.guessed[next - 1];
    if (next <= prev || !who) return;
    if (who === you) {
      sfx.fanfare();
      show.stinger(`YOU GOT IT! +${view.gained[you] ?? 0}`);
      show.celebrate();
    } else {
      sfx.ding();
      show.stinger(`${name(who).toUpperCase()} GOT IT!`);
    }
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "draw" && view.you.drawer && !tv) {
      sfx.pop();
      show.stinger("DRAW!");
    } else if (phase === "reveal" && view.word) {
      sfx.ding();
      show.stinger(view.word.toUpperCase(), view.guessed.length ? "good" : "bad");
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });
  useEffect(() => {
    if (view.phase === "draw" && view.you.drawer) setColour((c) => (c === ERASER ? 0 : c));
  }, [view.phase, view.you.drawer]);

  const turn = `Round ${view.round} of ${view.rounds}`;
  const sign =
    view.phase === "final"
      ? "Final scores"
      : view.phase === "choose"
        ? `${turn} · ${view.you.drawer && !tv ? "Your turn to draw" : `${drawer} is picking`}`
        : view.phase === "reveal"
          ? `${turn} · The word was…`
          : `${turn} · ${
              view.you.drawer && !tv ? "Draw it!" : view.you.guessed ? "You got it!" : `Guess ${drawer}’s drawing`
            }`;

  return (
    <div className="seg-drawguess stack">
      {show.node}
      <ShowHead sign={sign} title="Draw & Guess" remaining={view.remaining} receivedAt={receivedAt} />
      {(view.phase === "draw" || view.phase === "reveal") && <Word view={view} />}

      {view.phase === "final" ? (
        <Final view={view} you={you} tv={tv} />
      ) : (
        <div className={`dg-layout ${tv ? "big" : ""}`}>
          <div className="dg-stage">
            {view.phase === "choose" ? (
              <Choose view={view} drawer={drawer} send={send} tv={tv} />
            ) : (
              <Sketch
                ink={view.ink}
                drawing={drawing}
                send={send}
                label={`${drawer}’s drawing`}
                pen={{ colour, size, setColour, setSize }}
              />
            )}
          </div>
          <div className="dg-side">
            {view.phase === "reveal" && <TurnScores view={view} you={you} />}
            {view.phase === "draw" && !tv && view.you.playing && !view.you.drawer && (
              <GuessBox done={view.you.guessed} word={view.word} gained={view.gained[you] ?? 0} send={send} />
            )}
            {view.phase === "draw" && <Feed view={view} you={you} />}
            <Players view={view} you={you} />
          </div>
        </div>
      )}
    </div>
  );
}

/** The blanks (letters appear as hints), whole words kept together on narrow screens. */
function Word({ view }: { view: DrawGuessView }) {
  const shown = view.word ?? null;
  const chars = shown ? [...shown] : view.pattern;
  const words: string[][] = [[]];
  for (const ch of chars) {
    if (ch === " ") words.push([]);
    else words[words.length - 1]!.push(ch);
  }
  const lengths = words.map((w) => w.length).join(", ");
  return (
    <Card className="dg-word">
      <p className="sr-only">
        {shown
          ? `The word: ${shown}`
          : `${chars.filter((c) => c !== " ").length} letters (${lengths}). Shown so far: ${chars.map((c) => c || "blank").join(" ")}`}
      </p>
      <div className="dg-blanks" aria-hidden="true">
        {words.map((w, i) => (
          <span key={i} className="dg-blank-word">
            {w.map((ch, j) => (
              <span key={j} className={`dg-slot ${ch ? "on" : ""}`}>
                {ch.toUpperCase()}
              </span>
            ))}
          </span>
        ))}
        <span className="dg-count">{lengths}</span>
      </div>
    </Card>
  );
}

function Choose({ view, drawer, send, tv }: { view: DrawGuessView; drawer: string; send: Send; tv: boolean }) {
  if (view.choices && !tv) {
    return (
      <Card tone="stage" className="center">
        <p className="sign">Pick a word to draw</p>
        <div className="dg-choices space-top">
          {view.choices.map((w, i) => (
            <Btn key={w} variant="gold" size="big" onClick={() => send({ t: "act", a: "pick", i })}>
              {w}
            </Btn>
          ))}
        </div>
        <p className="muted space-top">No letters or numbers in your drawing!</p>
      </Card>
    );
  }
  return (
    <Card tone="stage" className="center dg-waiting">
      <p className="dg-pencil" aria-hidden="true">
        ✏️
      </p>
      <p className="lead">
        <b>{drawer}</b> is picking a word…
      </p>
    </Card>
  );
}

/**
 * The shared canvas. Everyone replays the same operations: the artist's own as they draw, the rest from
 * the server's "ink" frames. A gap (missed frames, a reconnect, arriving late) asks for the whole drawing.
 */
function GuessBox({ done, word, gained, send }: { done: boolean; word: string | null; gained: number; send: Send }) {
  const [text, setText] = useState("");
  if (done) {
    return (
      <Card tone="soft" className="center">
        <p className="lead" aria-live="polite">
          ✅ You got it: <b>{word}</b> (+{gained})
        </p>
      </Card>
    );
  }
  return (
    <Card>
      <form
        className="dg-guess"
        onSubmit={(e) => {
          e.preventDefault();
          const t = text.trim();
          if (!t) return;
          send({ t: "act", a: "guess", text: t });
          setText("");
        }}
      >
        <label className="sr-only" htmlFor="dg-guess">
          Your guess
        </label>
        <input
          id="dg-guess"
          className="dg-input"
          type="text"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          enterKeyHint="send"
          maxLength={32}
          placeholder="Your guess"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Btn type="submit" variant="go" disabled={!text.trim()}>
          Guess
        </Btn>
      </form>
    </Card>
  );
}

/** Wrong guesses for everyone (like a chat), right ones as a tick: the newest at the top. */
function Feed({ view, you }: { view: DrawGuessView; you: string }) {
  const items = [...view.feed].reverse().slice(0, 12);
  return (
    <Card className="dg-feed-card">
      <h3>Guesses</h3>
      {items.length === 0 ? (
        <p className="muted">Nobody has guessed yet.</p>
      ) : (
        <ul className="dg-feed" aria-live="polite">
          {items.map((f, i) => (
            <li key={view.feed.length - i} className={f.ok ? "ok" : f.close ? "close" : ""}>
              <b>{nameOf(view.players, f.by)}</b>{" "}
              {f.ok ? (
                <span>got it! ✅</span>
              ) : (
                <>
                  <span className="dg-said">{f.text}</span>
                  {f.close && f.by === you && <span className="chip dg-close">So close!</span>}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Players({ view, you }: { view: DrawGuessView; you: string }) {
  const ranked = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  return (
    <Card className="dg-players-card">
      <h3>Scores</h3>
      <ul className="score-rows dg-scores">
        {ranked.map((p) => {
          const got = view.guessed.includes(p.id);
          const artist = p.id === view.drawer;
          return (
            <li key={p.id} className={got ? "dg-got" : ""}>
              <b>
                {artist ? "✏️ " : got ? "✅ " : ""}
                {p.name}
                {p.id === you ? "\u00a0(you)" : ""}
              </b>
              <span className="score-tally">
                {view.gained[p.id] ? <span className="dg-gain">+{view.gained[p.id]}</span> : null}
                <span className="score-pts">{view.scores[p.id] ?? 0}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function TurnScores({ view, you }: { view: DrawGuessView; you: string }) {
  const got = view.guessed.map((p) => nameOf(view.players, p) + (p === you ? " (you)" : ""));
  return (
    <Card tone="soft" className="center">
      <p className="lead">{got.length ? `${nameList(got)} got it.` : "Nobody got it this time!"}</p>
      {view.drawer && (view.gained[view.drawer] ?? 0) > 0 && (
        <p className="muted space-top">
          {nameOf(view.players, view.drawer)} +{view.gained[view.drawer]} for the drawing
        </p>
      )}
    </Card>
  );
}

function Final({ view, you, tv }: { view: DrawGuessView; you: string; tv: boolean }) {
  const ranked = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  const top = ranked[0] ? (view.scores[ranked[0].id] ?? 0) : 0;
  return (
    <div className={tv ? "dg-final big" : "dg-final"}>
      <Card>
        <h3>Standings</h3>
        <ul className="score-rows">
          {ranked.map((p) => (
            <li key={p.id}>
              <b>
                {top > 0 && (view.scores[p.id] ?? 0) === top ? "👑 " : ""}
                {p.name}
                {p.id === you ? " (you)" : ""}
              </b>
              <span className="score-pts">{view.scores[p.id] ?? 0}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <h3>The drawings</h3>
        <ul className="dg-history">
          {(view.history ?? []).map((h, i) => (
            <li key={i}>
              <span>
                <b>{nameOf(view.players, h.drawer)}</b> drew <b className="dg-history-word">{h.word}</b>
              </span>
              <span className="muted">{h.guessed.length ? `${h.guessed.length} got it` : "nobody got it"}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
