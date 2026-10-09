import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Btn, Card, ShowHead, nameList, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { COLOURS, COLOUR_NAMES, H, Painter, SIZES, W, apply, onInk, type Stroke } from "../lib/ink";
import { sfx } from "../lib/sfx";
import type { DrawGuessView, InkOp } from "../types";

interface Props {
  view: DrawGuessView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen (TV and audience) */
  tv?: boolean;
}

type Send = Props["send"];
const SIZE_NAMES = ["Fine", "Medium", "Thick", "Huge"];
const ERASER = 1; // the paper colour
const FLUSH_MS = 200; // strokes go out in small batches (well under the socket's message rate)
const MAX_NUMS = 120; // numbers per message, as the server allows
const PLAYBACK_FRAMES = 10; // a received batch plays back over ~1/6 s (about one batch interval)
const MAX_PLAYBACK = 1200; // numbers; beyond this (catching up) the drawing appears at once

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
                label={drawer}
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
function Sketch({
  ink,
  drawing,
  send,
  label,
  pen: tools,
}: {
  ink: DrawGuessView["ink"];
  drawing: boolean;
  send: Send;
  label: string;
  pen: PenProps;
}) {
  const { colour, size } = tools;
  const canvas = useRef<HTMLCanvasElement>(null);
  const strokes = useRef<Stroke[]>([]);
  const painter = useRef<Painter | null>(null);
  const log = useRef({ id: "", n: 0 }); // the canvas we hold and how many operations of it
  const backlog = useRef<InkOp[]>([]); // received strokes still being played back
  const frame = useRef(0);
  const lastSync = useRef(-Infinity); // performance.now() starts near 0 on a fresh page
  const pen = useRef<{
    c: number;
    w: number;
    sent: boolean;
    queue: number[];
    last: [number, number];
  } | null>(null);

  const draw = useCallback((op: InkOp) => {
    apply(strokes.current, op);
    if (op.op === "undo" || op.op === "clear") painter.current?.invalidate();
  }, []);
  const settle = useCallback(() => {
    for (const op of backlog.current) draw(op);
    backlog.current = [];
  }, [draw]);
  // Strokes from the artist arrive in batches (every 200 ms): play each batch back over the next few
  // frames, so other screens see the line flow rather than jump.
  const step = useCallback(() => {
    const queue = backlog.current;
    let left = 0;
    for (const op of queue) left += "p" in op ? op.p.length : 2;
    let budget = Math.max(2, Math.ceil(left / PLAYBACK_FRAMES / 2) * 2);
    while (budget > 0 && queue.length) {
      const op = queue[0]!;
      if (!("p" in op) || op.p.length <= budget) {
        draw(op);
        queue.shift();
        budget -= "p" in op ? op.p.length : 2;
      } else {
        draw({ ...op, p: op.p.slice(0, budget) });
        queue[0] = { op: "more", p: op.p.slice(budget) };
        budget = 0;
      }
    }
  }, [draw]);
  const redraw = useCallback(() => {
    if (frame.current) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      if (backlog.current.length) step();
      const ctx = canvas.current?.getContext("2d");
      if (ctx) (painter.current ??= new Painter()).paint(ctx, strokes.current);
      if (backlog.current.length) redraw();
    });
  }, [step]);
  const reset = useCallback(
    (id: string) => {
      strokes.current = [];
      backlog.current = [];
      painter.current?.invalidate();
      log.current = { id, n: 0 };
      redraw();
    },
    [redraw],
  );
  const askSync = useCallback(() => {
    const now = performance.now();
    if (now - lastSync.current < 1500) return;
    lastSync.current = now;
    send({ t: "inksync" });
  }, [send]);

  useEffect(
    () => () => {
      cancelAnimationFrame(frame.current);
      frame.current = 0; // or no later redraw would ever be scheduled
    },
    [],
  );

  // Keep the bitmap as sharp as the screen.
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const fit = () => {
      const w = Math.round(c.clientWidth * Math.min(window.devicePixelRatio || 1, 2));
      if (w > 0 && w !== c.width) {
        c.width = w;
        c.height = Math.round((w * H) / W);
        redraw();
      }
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(c);
    return () => ro.disconnect();
  }, [redraw]);

  // Strokes from the server.
  useEffect(
    () =>
      onInk((f) => {
        if (f.resync) return askSync();
        if (!f.id || f.n == null || !f.ops) return;
        if (f.n === 0) reset(f.id);
        else if (f.id !== log.current.id) return askSync();
        const skip = log.current.n - f.n;
        if (skip < 0) return askSync();
        log.current.n = Math.max(log.current.n, f.n + f.ops.length);
        backlog.current.push(...f.ops.slice(skip));
        // A whole drawing (catching up) or a long backlog appears at once rather than replaying slowly.
        let queued = 0;
        for (const op of backlog.current) queued += "p" in op ? op.p.length : 2;
        if (queued > MAX_PLAYBACK) settle();
        redraw();
      }),
    [askSync, redraw, reset, settle],
  );

  // Snapshots carry the canvas's id and length: a new canvas starts blank, a longer one means a gap.
  const id = ink?.id ?? "";
  const count = ink?.count ?? 0;
  useEffect(() => {
    if (!id) return reset("");
    if (id !== log.current.id) {
      if (count === 0) reset(id);
      else askSync();
    } else if (count > log.current.n) askSync();
  }, [id, count, askSync, reset]);

  // -- the artist's pen ---------------------------------------------------------------------------------
  const flush = useCallback(() => {
    const p = pen.current;
    if (!p) return;
    while (p.queue.length) {
      const chunk = p.queue.splice(0, MAX_NUMS);
      send(p.sent ? { t: "ink", op: "more", p: chunk } : { t: "ink", op: "line", c: p.c, w: p.w, p: chunk });
      p.sent = true;
      log.current.n += 1;
    }
  }, [send]);
  useEffect(() => {
    if (!drawing) return;
    const timer = window.setInterval(flush, FLUSH_MS);
    return () => {
      window.clearInterval(timer);
      flush();
      pen.current = null;
    };
  }, [drawing, flush]);

  const at = (x: number, y: number, r: DOMRect): [number, number] => [
    Math.min(W, Math.max(0, Math.round(((x - r.left) / r.width) * W))),
    Math.min(H, Math.max(0, Math.round(((y - r.top) / r.height) * H))),
  ];
  const down = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!drawing || (e.pointerType === "mouse" && e.button !== 0)) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    flush();
    settle();
    const pt = at(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect());
    pen.current = { c: colour, w: size, sent: false, queue: [...pt], last: pt };
    strokes.current.push({ c: colour, w: size, p: [...pt] });
    redraw();
  };
  const move = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    const p = pen.current;
    if (!drawing || !p || !e.currentTarget.hasPointerCapture(e.pointerId)) return;
    const r = e.currentTarget.getBoundingClientRect();
    // Every position the device reported since the last event, not just the latest: fast strokes keep
    // their shape.
    const events = e.nativeEvent.getCoalescedEvents?.() ?? [];
    const stroke = strokes.current[strokes.current.length - 1];
    for (const ev of events.length ? events : [e.nativeEvent]) {
      const pt = at(ev.clientX, ev.clientY, r);
      if (Math.abs(pt[0] - p.last[0]) + Math.abs(pt[1] - p.last[1]) < 3) continue;
      p.last = pt;
      p.queue.push(...pt);
      stroke?.p.push(...pt);
    }
    redraw();
  };
  const up = () => {
    flush();
    pen.current = null;
  };

  const tool = (op: "undo" | "clear") => {
    flush();
    pen.current = null;
    send({ t: "ink", op });
    log.current.n += 1;
    settle();
    draw({ op });
    redraw();
  };

  return (
    <>
      <div className="dg-paper">
        <canvas
          ref={canvas}
          className={`dg-canvas ${drawing ? "drawing" : ""}`}
          width={W}
          height={H}
          role="img"
          aria-label={drawing ? "Your canvas: draw with your finger or mouse" : `${label}’s drawing`}
          onPointerDown={down}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={up}
        />
      </div>
      {drawing && <Tools {...tools} tool={tool} />}
    </>
  );
}

interface PenProps {
  colour: number;
  size: number;
  setColour: (c: number) => void;
  setSize: (s: number) => void;
}

function Tools({ colour, size, setColour, setSize, tool }: PenProps & { tool: (op: "undo" | "clear") => void }) {
  return (
    <Card className="dg-tools">
      <div className="dg-swatches" role="group" aria-label="Colour">
        {COLOURS.map((hex, i) =>
          i === ERASER ? null : (
            <button
              key={hex}
              type="button"
              className={`dg-swatch dg-c${i}`}
              aria-label={COLOUR_NAMES[i]}
              aria-pressed={colour === i}
              onClick={() => setColour(i)}
            />
          ),
        )}
      </div>
      <div className="dg-pens">
        <div className="dg-sizes" role="group" aria-label="Pen size">
          {SIZES.map((_, i) => (
            <button
              key={i}
              type="button"
              className="dg-size"
              aria-label={SIZE_NAMES[i]}
              aria-pressed={size === i}
              onClick={() => setSize(i)}
            >
              <span className={`dg-dot dg-w${i}`} aria-hidden="true" />
            </button>
          ))}
        </div>
        <button type="button" className="dg-tool" aria-pressed={colour === ERASER} onClick={() => setColour(ERASER)}>
          <span aria-hidden="true">🧽</span> Eraser
        </button>
        <button type="button" className="dg-tool" onClick={() => tool("undo")}>
          <span aria-hidden="true">↩</span> Undo
        </button>
        <button type="button" className="dg-tool" onClick={() => tool("clear")}>
          <span aria-hidden="true">🗑</span> Clear
        </button>
      </div>
    </Card>
  );
}

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
