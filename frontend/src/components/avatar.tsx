import { useEffect, useState, useSyncExternalStore } from "react";
import { initials } from "./ui";

type Send = (msg: Record<string, unknown>) => void;
export type Faces = Record<string, number[]>;

/** The faces people can pick (the server only stores an index into this list). */
export const FACES = [
  ..."😀😎🤠🥳😈🤖👽👻",
  ..."🐱🐶🦊🐼🐸🐵🦄🐙",
  ..."🦖🐧🍕🌮⚡🔥🌈🎩",
];
export const TONES = 8;
const KEY = "snazzlebop:avatar";

// The room publishes everyone's picked look here, so any screen can draw an avatar from just an id.
let faces: Faces = {};
let belt: string | null = null; // who wears the champion's crown
const subs = new Set<() => void>();
const useFaces = () =>
  useSyncExternalStore(
    (fn) => {
      subs.add(fn);
      return () => void subs.delete(fn);
    },
    () => faces,
  );
const useBelt = () =>
  useSyncExternalStore(
    (fn) => {
      subs.add(fn);
      return () => void subs.delete(fn);
    },
    () => belt,
  );

function stored(): [number, number] | null {
  try {
    const [f, t] = (localStorage.getItem(KEY) ?? "").split(",").map(Number);
    return Number.isInteger(f) && Number.isInteger(t) && f! >= 0 && f! < FACES.length && t! >= 0 && t! < TONES
      ? [f!, t!]
      : null;
  } catch {
    return null;
  }
}

/** A stable colour for someone who hasn't picked one. */
function fallbackTone(pid: string) {
  let h = 0;
  for (const ch of pid) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % TONES;
}
export const toneOf = (pid: string, all: Faces = faces) => all[pid]?.[1] ?? fallbackTone(pid);

/** Mounted by the room page: shares the room's looks and sends this device's saved look once. */
export function FaceHost({
  all,
  champion = null,
  you,
  send,
}: {
  all: Faces | undefined;
  champion?: string | null;
  you: string;
  send?: Send;
}) {
  useEffect(() => {
    faces = all ?? {};
    belt = champion;
    for (const fn of subs) fn();
  }, [all, champion]);
  const mine = all?.[you];
  useEffect(() => {
    const want = stored();
    if (send && want && (mine?.[0] !== want[0] || mine?.[1] !== want[1])) send({ t: "avatar", face: want[0], tone: want[1] });
    // only when the seat changes: a pick is sent by the picker itself
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [you]);
  return null;
}

/** Someone's face: their picked emoji on their colour, or their initials. */
export function Avatar({
  pid,
  name,
  tone,
  className = "",
}: {
  pid: string;
  name: string;
  /** the colour to use until this person picks one (a game may want seats to differ) */
  tone?: number;
  className?: string;
}) {
  const all = useFaces();
  const champion = useBelt() === pid;
  const face = all[pid]?.[0];
  const colour = all[pid]?.[1] ?? (tone === undefined ? toneOf(pid, all) : tone % TONES);
  return (
    <span
      className={`avatar tone-${colour} ${face === undefined ? "" : "face"} ${champion ? "belt" : ""} ${className}`}
      aria-hidden="true"
    >
      {face === undefined ? initials(name) : FACES[face]}
    </span>
  );
}

/** Lobby: pick a face and a colour once; it's remembered on this device and used everywhere. */
export function AvatarPicker({ you, name, send }: { you: string; name: string; send: Send }) {
  const all = useFaces();
  const [open, setOpen] = useState(false);
  const mine = all[you];
  const pick = (face: number, tone: number) => {
    try {
      localStorage.setItem(KEY, `${face},${tone}`);
    } catch {
      /* not remembered: still set for this room */
    }
    send({ t: "avatar", face, tone });
  };
  const face = mine?.[0] ?? 0;
  const tone = toneOf(you, all);
  return (
    <div className="avatar-pick">
      <button type="button" className="avatar-pick-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Avatar pid={you} name={name} className="lg" />
        <span>{mine ? "Change your look" : "Pick your look"}</span>
      </button>
      {open && (
        <div className="avatar-pick-panel">
          <div className="avatar-faces" role="group" aria-label="Face">
            {FACES.map((f, i) => (
              <button
                key={f}
                type="button"
                className="avatar-face"
                aria-pressed={mine?.[0] === i}
                aria-label={`Face ${i + 1}`}
                onClick={() => pick(i, tone)}
              >
                <span aria-hidden="true">{f}</span>
              </button>
            ))}
          </div>
          <div className="avatar-tones" role="group" aria-label="Colour">
            {Array.from({ length: TONES }, (_, i) => (
              <button
                key={i}
                type="button"
                className={`avatar-tone tone-${i}`}
                aria-pressed={tone === i}
                aria-label={`Colour ${i + 1}`}
                onClick={() => pick(face, i)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
