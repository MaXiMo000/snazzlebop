import type { InkOp } from "../types";

/** A frame of pen strokes from the server: ops n, n+1, ... on canvas `id`, or a request to redraw. */
export interface InkFrame {
  t: "ink";
  id?: string;
  n?: number;
  ops?: InkOp[];
  resync?: boolean;
}

// Strokes come over the room's socket but never touch the room state: the canvas listens here.
const listeners = new Set<(f: InkFrame) => void>();
export function onInk(fn: (f: InkFrame) => void): () => void {
  listeners.add(fn);
  return () => void listeners.delete(fn);
}
export function emitInk(frame: InkFrame) {
  for (const fn of listeners) fn(frame);
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

export function paint(ctx: CanvasRenderingContext2D, strokes: Stroke[]): void {
  const { width, height } = ctx.canvas;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = COLOURS[1]!;
  ctx.fillRect(0, 0, width, height);
  ctx.setTransform(width / W, 0, 0, height / H, 0, 0);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const s of strokes) {
    const colour = COLOURS[s.c] ?? COLOURS[0]!;
    const size = SIZES[s.w] ?? SIZES[0]!;
    if (s.p.length === 2) {
      ctx.fillStyle = colour;
      ctx.beginPath();
      ctx.arc(s.p[0]!, s.p[1]!, size / 2, 0, Math.PI * 2);
      ctx.fill();
      continue;
    }
    ctx.strokeStyle = colour;
    ctx.lineWidth = size;
    ctx.beginPath();
    ctx.moveTo(s.p[0]!, s.p[1]!);
    for (let i = 2; i < s.p.length; i += 2) ctx.lineTo(s.p[i]!, s.p[i + 1]!);
    ctx.stroke();
  }
}
