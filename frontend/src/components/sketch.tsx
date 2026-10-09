import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Card } from "./ui";
import {
  COLOURS,
  COLOUR_NAMES,
  H,
  Painter,
  SIZES,
  W,
  apply,
  drawingOps,
  onDrawing,
  onInk,
  type Stroke,
} from "../lib/ink";
import type { InkOp } from "../types";

/** The canvas the latest snapshot names (strokes arrive separately) and how many operations it has. */
export type InkState = { id: string; count: number } | null;
type Send = (msg: Record<string, unknown>) => void;

const SIZE_NAMES = ["Fine", "Medium", "Thick", "Huge"];
export const ERASER = 1; // the paper colour
const FLUSH_MS = 200; // strokes go out in small batches (well under the socket's message rate)
const MAX_NUMS = 120; // numbers per message, as the server allows
const PLAYBACK_FRAMES = 10; // a received batch plays back over ~1/6 s (about one batch interval)
const MAX_PLAYBACK = 1200; // numbers; beyond this (catching up) the drawing appears at once
const REPLAY_FRAMES = 150; // a finished drawing replays over ~2.5 s

/**
 * The live canvas. Everyone replays the same operations: the artist's own as they draw, the rest from
 * the server's "ink" frames. A gap (missed frames, a reconnect, arriving late) asks for the whole drawing.
 */
export function Sketch({
  ink,
  drawing,
  send,
  label,
  pen: tools,
}: {
  ink: InkState;
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
  const want = useRef(""); // the canvas the latest snapshot named
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
        if (f.full && f.id !== want.current) return; // a finished drawing another view asked for
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
  want.current = id;
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
          aria-label={drawing ? "Your canvas: draw with your finger or mouse" : label}
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

export interface PenProps {
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

/** A finished drawing (read-only), fetched by id; `replay` draws it stroke by stroke, like a time-lapse. */
export function Drawing({
  id,
  send,
  label,
  replay = false,
}: {
  id: string;
  send: Send;
  label: string;
  replay?: boolean;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ops, setOps] = useState<InkOp[] | null>(() => drawingOps(id));

  useEffect(() => {
    setOps(drawingOps(id));
    const off = onDrawing((got) => got === id && setOps(drawingOps(id)));
    // Ask until it arrives (the page may be revealed a moment after this screen renders it).
    const ask = () => !drawingOps(id) && send({ t: "inksync", id });
    ask();
    const timer = window.setInterval(ask, 2000);
    return () => {
      off();
      window.clearInterval(timer);
    };
  }, [id, send]);

  useEffect(() => {
    const c = canvas.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx || !ops) return;
    const w = Math.round(c.clientWidth * Math.min(window.devicePixelRatio || 1, 2)) || W;
    c.width = w;
    c.height = Math.round((w * H) / W);
    const painter = new Painter();
    const strokes: Stroke[] = [];
    let total = 0;
    for (const op of ops) total += "p" in op ? op.p.length : 2;
    const still = !replay || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (still) {
      for (const op of ops) apply(strokes, op);
      painter.paint(ctx, strokes);
      return;
    }
    const queue = [...ops];
    const per = Math.max(2, Math.ceil(total / REPLAY_FRAMES / 2) * 2);
    let frame = 0;
    const step = () => {
      let budget = per;
      while (budget > 0 && queue.length) {
        const op = queue[0]!;
        if (!("p" in op) || op.p.length <= budget) {
          apply(strokes, op);
          if (op.op === "undo" || op.op === "clear") painter.invalidate();
          queue.shift();
          budget -= "p" in op ? op.p.length : 2;
        } else {
          apply(strokes, { ...op, p: op.p.slice(0, budget) });
          queue[0] = { op: "more", p: op.p.slice(budget) };
          budget = 0;
        }
      }
      painter.paint(ctx, strokes);
      if (queue.length) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [ops, replay]);

  return (
    <div className="dg-paper">
      <canvas ref={canvas} className="dg-canvas" width={W} height={H} role="img" aria-label={label} />
      {!ops && <p className="dg-loading muted">Loading the drawing…</p>}
    </div>
  );
}
