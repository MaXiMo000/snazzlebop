// Frenemy Radar result card, drawn on a canvas in the browser. Nothing is uploaded anywhere:
// the player shares it with the system share sheet or downloads a PNG.
// Only the sharer's own result goes on it: no room code, nobody else's numbers.

export interface CardData {
  name: string;
  blindSpot: number;
  verdict: string;
  awards: string[];
  rounds: { prompt: string; self: number; room: number }[];
}

const C = {
  plum: "#2b1b33",
  cream: "#fff1dc",
  bulb: "#ffe7a1",
  tangerine: "#ff6b2c",
  mustard: "#f2b705",
  cherry: "#c8203a",
  soft: "#e7d3c4",
};

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(" ");
  const lines: string[] = [];
  let line = "";
  for (const w of words) {
    const next = line ? `${line} ${w}` : w;
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line);
      line = w;
    } else line = next;
  }
  if (line) lines.push(line);
  return lines;
}

export async function drawCard(canvas: HTMLCanvasElement, d: CardData): Promise<void> {
  const W = 1080;
  const H = 1350;
  canvas.width = W;
  canvas.height = H;
  await Promise.all([document.fonts.load("80px Bungee"), document.fonts.load("600 40px 'Fredoka Variable'")]);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const display = "Bungee, 'Arial Black', sans-serif";
  const body = "'Fredoka Variable', 'Segoe UI', sans-serif";

  // Sunburst stage
  ctx.fillStyle = C.plum;
  ctx.fillRect(0, 0, W, H);
  ctx.save();
  ctx.translate(W / 2, 330);
  for (let i = 0; i < 36; i++) {
    ctx.rotate((Math.PI * 2) / 36);
    ctx.fillStyle = i % 2 ? "rgba(255,107,44,0.20)" : "rgba(242,183,5,0.14)";
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-60, -1400);
    ctx.lineTo(60, -1400);
    ctx.fill();
  }
  ctx.restore();

  // Marquee bulbs around the edge
  ctx.fillStyle = C.bulb;
  for (let x = 40; x <= W - 40; x += 44) {
    for (const y of [36, H - 36]) {
      ctx.beginPath();
      ctx.arc(x, y, 9, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  for (let y = 80; y <= H - 80; y += 44) {
    for (const x of [36, W - 36]) {
      ctx.beginPath();
      ctx.arc(x, y, 9, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  ctx.textAlign = "center";
  ctx.fillStyle = C.bulb;
  ctx.font = `44px ${display}`;
  ctx.fillText("SNAZZLEBOP! · FRENEMY RADAR", W / 2, 130);

  ctx.fillStyle = C.cream;
  ctx.font = `600 50px ${body}`;
  ctx.fillText(`${d.name}'s blind spot`, W / 2, 230);

  // Big score on a price-tag plate
  ctx.save();
  ctx.translate(W / 2, 360);
  ctx.rotate(-0.035);
  ctx.fillStyle = C.mustard;
  ctx.strokeStyle = C.plum;
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.roundRect(-230, -95, 460, 190, 30);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = C.plum;
  ctx.font = `150px ${display}`;
  ctx.fillText(`${Math.round(d.blindSpot)}%`, 0, 55);
  ctx.restore();

  ctx.fillStyle = C.bulb;
  ctx.font = `600 46px ${body}`;
  ctx.fillText(d.verdict, W / 2, 540);

  let y = 620;
  if (d.awards.length) {
    ctx.fillStyle = C.tangerine;
    ctx.font = `40px ${display}`;
    ctx.fillText(`🏆 ${d.awards.join(" · ")}`, W / 2, y);
    y += 70;
  }

  ctx.textAlign = "left";
  for (const r of d.rounds.slice(0, 3)) {
    ctx.fillStyle = "rgba(255,241,220,0.08)";
    ctx.beginPath();
    ctx.roundRect(90, y, W - 180, 150, 24);
    ctx.fill();
    ctx.fillStyle = C.cream;
    ctx.font = `600 34px ${body}`;
    const lines = wrap(ctx, r.prompt, W - 260).slice(0, 2);
    lines.forEach((l, i) => ctx.fillText(l, 125, y + 50 + i * 40));
    ctx.fillStyle = C.bulb;
    ctx.font = `600 32px ${body}`;
    ctx.fillText(`Me: #${r.self}   The room: #${r.room}`, 125, y + 130);
    y += 168;
  }

  ctx.textAlign = "center";
  ctx.fillStyle = C.soft;
  ctx.font = `600 30px ${body}`;
  ctx.fillText("A party game show for friends · no sign-up", W / 2, H - 80);
}

export async function shareCanvas(canvas: HTMLCanvasElement, filename: string): Promise<"shared" | "downloaded"> {
  const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/png"));
  if (!blob) throw new Error("Couldn't draw the card");
  const file = new File([blob], filename, { type: "image/png" });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: "My Frenemy Radar result" });
      return "shared";
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return "shared"; // user closed the sheet
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 5000);
  return "downloaded";
}
