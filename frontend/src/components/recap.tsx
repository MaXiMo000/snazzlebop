import { useEffect, useRef, useState } from "react";
import { apply, drawingOps, H, onDrawing, Painter, W, type Stroke } from "../lib/ink";
import type { RoomState } from "../types";
import { FACES, toneOf } from "./avatar";
import { Btn, initials } from "./ui";

type Send = (msg: Record<string, unknown>) => void;
const CW = 1080;
const CH = 1350;

// The night's best-liked drawing (from Draw Telephone's final books), kept while this page is open so the
// recap can still show it after the room has moved on to another game.
let star: { id: string; by: string; likes: number } | null = null;
let starRoom = "";

function noteDrawings(state: RoomState, send: Send) {
  if (starRoom !== state.room.code) {
    starRoom = state.room.code;
    star = null;
  }
  const g = state.game;
  if (!g || g.game !== "telephone" || !g.books) return;
  for (const book of g.books)
    for (const page of book.pages)
      if (page.kind === "drawing" && page.drawing && page.by && page.likes >= (star?.likes ?? 0) && page.drawing !== star?.id) {
        star = { id: page.drawing, by: page.by, likes: page.likes };
        if (!drawingOps(page.drawing)) send({ t: "inksync", id: page.drawing });
      }
}

/** The line of the night: the one that reads most like the room was laughing. */
function bestLine(state: RoomState) {
  const score = (t: string) => (t.match(/😂|🤣|💀|😭|lol|lmao|haha|!/gi)?.length ?? 0) * 20 + Math.min(t.length, 60);
  return state.chat?.messages
    .filter((m) => !m.team && m.text.length <= 110 && m.text.trim().split(/\s+/).length >= 2)
    .reduce<{ name: string; text: string } | null>((best, m) => (!best || score(m.text) > score(best.text) ? m : best), null);
}

function toneColour(tone: number) {
  const el = document.createElement("i");
  el.className = `tone-${tone}`;
  document.body.append(el);
  const c = getComputedStyle(el).getPropertyValue("--tone").trim();
  el.remove();
  return c || "#8e44ad";
}

function fit(ctx: CanvasRenderingContext2D, text: string, max: number, size: number, family: string, weight = "400") {
  do ctx.font = `${weight} ${size}px ${family}`;
  while (ctx.measureText(text).width > max && (size -= 2) > 18);
}

function wrap(ctx: CanvasRenderingContext2D, text: string, max: number, limit: number) {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width <= max || !line) line = next;
    else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  if (lines.length > limit) {
    lines.length = limit;
    lines[limit - 1] = `${lines[limit - 1]!.replace(/.{0,2}$/, "")}…`;
  }
  return lines;
}

function paint(canvas: HTMLCanvasElement, state: RoomState) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const DISPLAY = '"Bungee", "Arial Black", sans-serif';
  const BODY = '"Fredoka", system-ui, sans-serif';
  const EMOJI = '"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif';
  const ranked = [...state.players].sort((a, b) => b.total - a.total);
  const winner = ranked[0];

  ctx.fillStyle = "#1b1024";
  ctx.fillRect(0, 0, CW, CH);
  ctx.save();
  ctx.translate(CW / 2, 400);
  ctx.fillStyle = "#2a1638";
  for (let i = 0; i < 18; i++) {
    ctx.rotate((Math.PI * 2) / 18);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-90, -1500);
    ctx.lineTo(90, -1500);
    ctx.fill();
  }
  ctx.restore();

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#fff3d6";
  ctx.font = `400 76px ${DISPLAY}`;
  ctx.fillText("SNAZZLEBOP!", CW / 2, 100);
  ctx.fillStyle = "#f2b705";
  ctx.font = `700 36px ${BODY}`;
  ctx.fillText(state.room.title ? state.room.title.toUpperCase() : "GAME NIGHT RECAP", CW / 2, 164);

  if (winner) {
    const colour = toneColour(toneOf(winner.id));
    ctx.font = `400 96px ${EMOJI}`;
    ctx.fillText("👑", CW / 2, 246);
    ctx.beginPath();
    ctx.arc(CW / 2, 384, 104, 0, Math.PI * 2);
    ctx.fillStyle = "#fff";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(CW / 2, 384, 93, 0, Math.PI * 2);
    ctx.fillStyle = colour;
    ctx.fill();
    const face = state.faces?.[winner.id]?.[0];
    ctx.fillStyle = "#fff";
    ctx.font = face === undefined ? `400 76px ${DISPLAY}` : `400 104px ${EMOJI}`;
    ctx.fillText(face === undefined ? initials(winner.name) : FACES[face]!, CW / 2, 391);
    ctx.fillStyle = "#fff";
    fit(ctx, winner.name.toUpperCase(), CW - 140, 80, DISPLAY);
    ctx.fillText(winner.name.toUpperCase(), CW / 2, 540);
    ctx.fillStyle = "#ffe9a8";
    ctx.font = `700 40px ${BODY}`;
    ctx.fillText(`Winner · ${winner.total.toLocaleString()} points`, CW / 2, 602);
  }

  // The rest of the table.
  let y = 680;
  ctx.font = `700 38px ${BODY}`;
  for (const [i, p] of ranked.slice(1, 5).entries()) {
    ctx.fillStyle = "#2c2038";
    ctx.beginPath();
    ctx.roundRect(120, y - 30, CW - 240, 60, 30);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.textAlign = "left";
    fit(ctx, `${i + 2}. ${p.name}`, CW - 520, 38, BODY, "700");
    ctx.fillText(`${i + 2}. ${p.name}`, 150, y + 2);
    ctx.textAlign = "right";
    ctx.font = `700 38px ${BODY}`;
    ctx.fillStyle = "#ffe9a8";
    ctx.fillText(p.total.toLocaleString(), CW - 150, y + 2);
    y += 66;
  }
  ctx.textAlign = "center";

  // The drawing of the night and the line of the night share the bottom.
  const ops = star ? drawingOps(star.id) : null;
  const line = bestLine(state);
  const top = Math.max(y, 950);
  if (ops && star) {
    const sheet = document.createElement("canvas");
    sheet.width = W;
    sheet.height = H;
    const sctx = sheet.getContext("2d");
    if (sctx) {
      const strokes: Stroke[] = [];
      for (const op of ops) apply(strokes, op);
      new Painter().paint(sctx, strokes);
      const w = line ? 380 : 400;
      const h = (w * H) / W;
      const x = line ? 70 : (CW - w) / 2;
      ctx.save();
      ctx.translate(x + w / 2, top + h / 2);
      ctx.rotate(-0.04);
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.roundRect(-w / 2 - 10, -h / 2 - 10, w + 20, h + 20, 18);
      ctx.fill();
      ctx.drawImage(sheet, -w / 2, -h / 2, w, h);
      ctx.restore();
      ctx.fillStyle = "#d9cbe8";
      const who = state.players.find((p) => p.id === star!.by)?.name ?? "";
      fit(ctx, `Drawing of the night${who ? ` · ${who}` : ""}`, w + 40, 28, BODY, "700");
      ctx.fillText(`Drawing of the night${who ? ` · ${who}` : ""}`, x + w / 2, top + h + 44);
    }
  }
  if (line) {
    const x = ops ? 520 : 120;
    const w = CW - x - (ops ? 70 : 120);
    ctx.font = `700 40px ${BODY}`;
    const lines = wrap(ctx, `“${line.text}”`, w - 60, 4);
    const h = lines.length * 50 + 60;
    ctx.fillStyle = "#fff3d6";
    ctx.beginPath();
    ctx.roundRect(x, top, w, h, 28);
    ctx.fill();
    ctx.fillStyle = "#2b1b33";
    lines.forEach((l, i) => ctx.fillText(l, x + w / 2, top + 56 + i * 50));
    ctx.fillStyle = "#d9cbe8";
    fit(ctx, `Line of the night · ${line.name}`, w, 28, BODY, "700");
    ctx.fillText(`Line of the night · ${line.name}`, x + w / 2, top + h + 34);
  }
  ctx.fillStyle = "#9b86ad";
  ctx.font = `700 28px ${BODY}`;
  ctx.fillText(window.location.host, CW / 2, CH - 36);
}

/** "Recap picture": the winner, the table, the best-liked drawing and a chat line, as one image to share. */
export function Recap({ state, send }: { state: RoomState; send: Send }) {
  const [open, setOpen] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => noteDrawings(state, send));
  const played = state.players.some((p) => p.total !== 0);
  useEffect(() => {
    if (!open || !canvas.current) return;
    const c = canvas.current;
    const draw = () => paint(c, state);
    void document.fonts.ready.then(draw);
    return onDrawing(draw); // the drawing may still be on its way
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  if (!played || !["results", "finale", "lobby"].includes(state.room.phase)) return null;

  const file = () =>
    new Promise<File | null>((done) =>
      canvas.current
        ? canvas.current.toBlob((b) => done(b && new File([b], "snazzlebop-recap.png", { type: "image/png" })), "image/png")
        : done(null),
    );
  const save = async () => {
    const f = await file();
    if (!f) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(f);
    a.download = f.name;
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };
  const share = async () => {
    const f = await file();
    if (!f) return;
    if (navigator.canShare?.({ files: [f] })) await navigator.share({ files: [f], title: "Snazzlebop recap" }).catch(() => undefined);
    else await save();
  };
  return (
    <>
      <p className="center recap-open">
        <Btn variant="gold" onClick={() => setOpen(true)}>
          📸 Recap picture
        </Btn>
      </p>
      {open && (
        <div className="recap" role="dialog" aria-modal="true" aria-label="Recap picture">
          <canvas ref={canvas} className="recap-canvas" width={CW} height={CH} role="img" aria-label="Tonight’s recap" />
          <div className="row center recap-actions">
            <Btn variant="go" onClick={() => void share()}>
              Share
            </Btn>
            <Btn onClick={() => void save()}>Save</Btn>
            <Btn variant="ghost" onClick={() => setOpen(false)}>
              Close
            </Btn>
          </div>
        </div>
      )}
    </>
  );
}
