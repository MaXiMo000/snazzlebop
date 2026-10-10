import { useEffect, useRef, useState } from "react";
import { sfx } from "../lib/sfx";
import { Avatar, toneOf } from "./avatar";

export type EntranceInfo = { id: number; pid: string; name: string; kind?: "belt" };

const INTROS = [
  "The one, the only…",
  "Hide your points, it’s…",
  "Fresh from the green room…",
  "The crowd goes wild for…",
  "Nobody asked, but here’s…",
  "Straight off a winning streak…",
  "Lock up the trophies, it’s…",
];
const SEEN = "snazzlebop:entrance";

function seed(name: string) {
  let h = 7;
  for (const ch of name) h = (h * 31 + ch.codePointAt(0)!) >>> 0;
  return h;
}

/**
 * A walk-on: when a name on the server's private list joins, every screen (the TV too) gets a title card
 * in that person's colour with their own little jingle. Each walk-on plays once per screen.
 */
export function Entrance({ entrance, you, room }: { entrance: EntranceInfo | null | undefined; you: string; room: string }) {
  const [show, setShow] = useState<EntranceInfo | null>(null);
  const first = useRef(true);
  const id = entrance?.id ?? 0;
  useEffect(() => {
    const wasFirst = first.current;
    first.current = false;
    if (!entrance) return;
    // On arrival only your own walk-on plays (and not again after a reload); later ones play for everyone.
    const key = `${SEEN}:${room}`;
    let seen = 0;
    try {
      seen = Number(sessionStorage.getItem(key)) || 0;
      sessionStorage.setItem(key, String(Math.max(seen, entrance.id)));
    } catch {
      /* storage blocked: it may replay after a reload */
    }
    if (entrance.id <= seen || (wasFirst && entrance.pid !== you)) return;
    setShow(entrance);
    if (entrance.kind === "belt") sfx.fanfare();
    else sfx.jingle(seed(entrance.name));
    const t = window.setTimeout(() => setShow(null), 4200);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  if (!show) return null;
  const h = seed(show.name);
  return (
    <div key={show.id} className={`entrance tone-${toneOf(show.pid)}`} role="status">
      <span className="entrance-rays" aria-hidden="true" />
      <div className="entrance-card">
        <Avatar pid={show.pid} name={show.name} className="xl" />
        <p className="entrance-intro">
          {show.kind === "belt" ? "👑 The belt goes to tonight’s champion…" : INTROS[h % INTROS.length]}
        </p>
        <p className="entrance-name">{show.name}!</p>
      </div>
    </div>
  );
}
