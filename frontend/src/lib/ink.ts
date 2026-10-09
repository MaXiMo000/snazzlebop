import type { InkOp } from "../types";

/** A frame of pen strokes from the server: ops n, n+1, ... on canvas `id`, or a request to redraw. */
export interface InkFrame {
  t: "ink";
  id?: string;
  n?: number;
  ops?: InkOp[];
  resync?: boolean;
  /** the whole drawing, sent on request */
  full?: boolean;
}

// Strokes come over the room's socket but never touch the room state: the canvas listens here.
const listeners = new Set<(f: InkFrame) => void>();
export function onInk(fn: (f: InkFrame) => void): () => void {
  listeners.add(fn);
  return () => void listeners.delete(fn);
}
export function emitInk(frame: InkFrame) {
  if (frame.full && frame.id && frame.ops) {
    finished.set(frame.id, frame.ops);
    for (const fn of drawingListeners) fn(frame.id);
  }
  for (const fn of listeners) fn(frame);
}

// Whole drawings sent on request (album pages, the drawing to describe): kept for the page's life.
// Simplification: never evicted; a game holds at most 32 drawings.
const finished = new Map<string, InkOp[]>();
const drawingListeners = new Set<(id: string) => void>();
export function drawingOps(id: string): InkOp[] | null {
  return finished.get(id) ?? null;
}
export function onDrawing(fn: (id: string) => void): () => void {
  drawingListeners.add(fn);
  return () => void drawingListeners.delete(fn);
}

export const W = 800;
export const H = 600;
/** The palette (indices are what travel); 1 is the paper colour, so it doubles as the eraser. */
export const COLOURS = [
  "#1b1b1f",
  "#ffffff",
  "#8a8a93",
  "#7a4a2a",
  "#e0312f",
  "#f28a1a",
  "#f5cf1f",
  "#3cb043",
  "#1e6b35",
  "#5ec8f2",
  "#2f5fd0",
  "#8a3fc4",
  "#f07ab8",
  "#f2c39a",
];
export const COLOUR_NAMES = [
  "Black",
  "White",
  "Grey",
  "Brown",
  "Red",
  "Orange",
  "Yellow",
  "Green",
  "Dark green",
  "Sky blue",
  "Blue",
  "Purple",
  "Pink",
  "Peach",
];
export const SIZES = [4, 9, 18, 36];

export interface Stroke {
  c: number;
  w: number;
  p: number[];
}

/** Replays operations onto a list of strokes (undo removes the last stroke, clear removes all). */
export function apply(strokes: Stroke[], op: InkOp): void {
  if (op.op === "line") strokes.push({ c: op.c, w: op.w, p: [...op.p] });
  else if (op.op === "more") strokes[strokes.length - 1]?.p.push(...op.p);
  else if (op.op === "undo") strokes.pop();
  else strokes.length = 0;
}

/** One stroke, as a smooth curve through its points (quadratic pieces between midpoints). */
function drawStroke(ctx: CanvasRenderingContext2D, s: Stroke): void {
  const colour = COLOURS[s.c] ?? COLOURS[0]!;
  const size = SIZES[s.w] ?? SIZES[0]!;
  const p = s.p;
  if (p.length === 2) {
    ctx.fillStyle = colour;
    ctx.beginPath();
    ctx.arc(p[0]!, p[1]!, size / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  ctx.strokeStyle = colour;
  ctx.lineWidth = size;
  ctx.beginPath();
  ctx.moveTo(p[0]!, p[1]!);
  for (let i = 2; i < p.length - 2; i += 2) {
    ctx.quadraticCurveTo(p[i]!, p[i + 1]!, (p[i]! + p[i + 2]!) / 2, (p[i + 1]! + p[i + 3]!) / 2);
  }
  ctx.lineTo(p[p.length - 2]!, p[p.length - 1]!);
  ctx.stroke();
}

function prepare(ctx: CanvasRenderingContext2D, blank: boolean): void {
  const { width, height } = ctx.canvas;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  if (blank) {
    ctx.fillStyle = COLOURS[1]!;
    ctx.fillRect(0, 0, width, height);
  }
  ctx.setTransform(width / W, 0, 0, height / H, 0, 0);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
}

/**
 * Paints the strokes onto a canvas. Finished strokes (all but the last) are kept on an offscreen
 * bitmap, so each frame costs one image copy plus the stroke being drawn, however big the drawing gets.
 * Call `invalidate()` after an undo or clear (the finished strokes changed).
 */
export class Painter {
  private cache = document.createElement("canvas");
  private baked = -1; // how many strokes the cache holds (-1: rebuild)

  invalidate(): void {
    this.baked = -1;
  }

  paint(ctx: CanvasRenderingContext2D, strokes: Stroke[]): void {
    const { width, height } = ctx.canvas;
    const cache = this.cache.getContext("2d");
    if (!cache) return;
    if (this.cache.width !== width || this.cache.height !== height) {
      this.cache.width = width;
      this.cache.height = height;
      this.baked = -1;
    }
    const done = Math.max(0, strokes.length - 1);
    if (this.baked < 0 || this.baked > done) {
      prepare(cache, true);
      this.baked = 0;
    } else prepare(cache, false);
    for (; this.baked < done; this.baked++) drawStroke(cache, strokes[this.baked]!);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(this.cache, 0, 0);
    prepare(ctx, false);
    const last = strokes[strokes.length - 1];
    if (last) drawStroke(ctx, last);
  }
}
