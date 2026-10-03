import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { scream } from "../lib/scare";

/** Real photos dropped into src/assets/scares are bundled at build time and used first. */
const PHOTOS: string[] = Object.values(
  import.meta.glob<string>("../assets/scares/*.{jpg,jpeg,png,webp,JPG,JPEG,PNG,WEBP}", { eager: true, query: "?url", import: "default" }),
);

/** Drawn in code (no images from the internet): six kinds of ghost, every one randomised. */
type Kind = "wraith" | "onryo" | "skull" | "grinner" | "banshee" | "hollow";
const KINDS: Kind[] = ["wraith", "onryo", "skull", "grinner", "banshee", "hollow"];

interface Look {
  kind: Kind;
  photo: string | null;
  skin: string;
  shade: string;
  glow: string;
  tilt: number;
  eye: number;
  mouth: number;
  drips: number[];
  strands: number[];
  teeth: number;
}

const pick = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)]!;
const r = (a: number, b: number) => a + Math.random() * (b - a);

/** Go through every option before any comes back (a shuffled bag, remembered on this device). */
function fromBag<T extends string>(key: string, all: T[]): T {
  let bag: T[] = [];
  try {
    bag = (JSON.parse(localStorage.getItem(key) ?? "[]") as unknown[]).filter((k): k is T => all.includes(k as T));
  } catch {
    bag = [];
  }
  if (!bag.length) bag = [...all].sort(() => Math.random() - 0.5);
  const next = bag.shift()!;
  try {
    localStorage.setItem(key, JSON.stringify(bag));
  } catch {
    /* fine: then it is just random */
  }
  return next;
}

function roll(): Look {
  return {
    kind: fromBag("snazzlebop:ghost-bag", KINDS),
    photo: PHOTOS.length ? fromBag("snazzlebop:photo-bag", PHOTOS) : null,
    skin: pick(["#e8e4dc", "#c9d4c5", "#b8c2c9", "#d9cfc4", "#a9b8a6"]),
    shade: pick(["#5b6468", "#4f5a4c", "#5a4e57", "#3f4a55"]),
    glow: pick(["#ff1a1a", "#ff3b00", "#b6ff00", "#ffffff", "#ff0040"]),
    tilt: r(-9, 9),
    eye: r(0.9, 1.3),
    mouth: r(0.85, 1.35),
    drips: Array.from({ length: 3 + Math.floor(Math.random() * 5) }, () => r(110, 290)),
    strands: Array.from({ length: 28 }, () => r(-1, 1)),
    teeth: 8 + Math.floor(Math.random() * 9),
  };
}

/** A soft, deep eye socket with a pinprick of light in it, and a dark streak running down. */
function Socket({ id, cx, cy, rx, ry }: { id: string; cx: number; cy: number; rx: number; ry: number }) {
  return (
    <>
      <ellipse cx={cx} cy={cy} rx={rx * 1.35} ry={ry * 1.3} fill={`url(#${id}sock)`} />
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="#000" />
      <circle cx={cx + rx * 0.08} cy={cy + ry * 0.12} r={Math.max(rx, ry) * 0.42} fill={`url(#${id}glow)`} />
      <circle cx={cx + rx * 0.08} cy={cy + ry * 0.12} r={Math.max(rx, ry) * 0.09} fill="#fff" opacity="0.9" />
      <path
        d={`M${cx - rx * 0.3} ${cy + ry * 0.8} q ${rx * 0.1} ${ry * 2.2} ${-rx * 0.05} ${ry * 3.4}`}
        stroke="#000"
        strokeWidth={rx * 0.22}
        opacity="0.75"
        fill="none"
      />
    </>
  );
}

function Ghost({ look }: { look: Look }) {
  const id = useId().replace(/:/g, "");
  const { skin, shade, glow, eye, mouth } = look;
  const defs = (
    <defs>
      <radialGradient id={`${id}skin`} cx="50%" cy="34%" r="70%">
        <stop offset="0%" stopColor={skin} />
        <stop offset="55%" stopColor={shade} />
        <stop offset="100%" stopColor="#050505" />
      </radialGradient>
      <radialGradient id={`${id}sock`} cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#000" />
        <stop offset="60%" stopColor="#000" stopOpacity="0.7" />
        <stop offset="100%" stopColor="#000" stopOpacity="0" />
      </radialGradient>
      <radialGradient id={`${id}glow`} cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor={glow} />
        <stop offset="40%" stopColor={glow} stopOpacity="0.6" />
        <stop offset="100%" stopColor={glow} stopOpacity="0" />
      </radialGradient>
      <radialGradient id={`${id}void`} cx="50%" cy="40%" r="60%">
        <stop offset="0%" stopColor="#000" />
        <stop offset="80%" stopColor="#1a0000" />
        <stop offset="100%" stopColor="#3b0000" />
      </radialGradient>
      <linearGradient id={`${id}under`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#000" stopOpacity="0.75" />
        <stop offset="35%" stopColor="#000" stopOpacity="0" />
        <stop offset="80%" stopColor="#000" stopOpacity="0" />
        <stop offset="100%" stopColor="#000" stopOpacity="0.85" />
      </linearGradient>
      {/* Warped edges and blotchy skin, so nothing looks drawn with a ruler. */}
      <filter id={`${id}warp`} x="-10%" y="-10%" width="120%" height="120%">
        <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="3" seed={Math.floor(Math.abs(look.tilt) * 13) + 1} result="n" />
        <feDisplacementMap in="SourceGraphic" in2="n" scale="26" xChannelSelector="R" yChannelSelector="G" result="w" />
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" result="grain" />
        <feColorMatrix in="grain" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.5 0" result="g" />
        <feComposite in="g" in2="w" operator="in" result="gw" />
        <feMerge>
          <feMergeNode in="w" />
          <feMergeNode in="gw" />
        </feMerge>
      </filter>
    </defs>
  );
  const blood = (y: number) =>
    look.drips.map((x, i) => (
      <path
        key={i}
        d={`M${x} ${y} c 3 ${25 + i * 8} -3 ${50 + i * 12} 1 ${80 + i * 18} c 5 6 -6 6 -3 0 c 2 -20 -3 -50 -2 ${-(80 + i * 18)}z`}
        fill="#4a0000"
        opacity="0.92"
      />
    ));
  const svg = (body: ReactNode) => (
    <svg viewBox="0 0 400 500" className="ghost" aria-hidden="true">
      {defs}
      <g filter={`url(#${id}warp)`}>{body}</g>
      <rect width="400" height="500" fill={`url(#${id}under)`} />
    </svg>
  );
  const head = "M70 210 C60 70 340 70 330 210 C335 340 265 485 200 495 C135 485 65 340 70 210Z";

  switch (look.kind) {
    case "wraith":
      return svg(
        <>
          <path d={head} fill={`url(#${id}skin)`} />
          <Socket id={id} cx={145} cy={215} rx={40 * eye} ry={55 * eye} />
          <Socket id={id} cx={255} cy={215} rx={40 * eye} ry={55 * eye} />
          <ellipse cx="200" cy={360} rx={40 * mouth} ry={95 * mouth} fill={`url(#${id}void)`} />
          {blood(300)}
        </>,
      );
    case "onryo":
      return svg(
        <>
          <ellipse cx="200" cy="270" rx="140" ry="200" fill={`url(#${id}skin)`} />
          <circle cx="238" cy="236" r={34 * eye} fill="#f2ece4" />
          {Array.from({ length: 9 }, (_, i) => {
            const a = (i / 9) * Math.PI * 2;
            return (
              <path
                key={i}
                d={`M${238 + Math.cos(a) * 34 * eye} ${236 + Math.sin(a) * 34 * eye} l ${-Math.cos(a) * 14} ${-Math.sin(a) * 14} l ${Math.sin(a) * 4} ${Math.cos(a) * 4}`}
                stroke="#b30000"
                strokeWidth="2"
                fill="none"
              />
            );
          })}
          <circle cx="242" cy="242" r={11 * eye} fill="#000" />
          <path d="M140 380 Q200 400 260 375" stroke="#1a0000" strokeWidth="10" fill="none" />
          {look.strands.concat(look.strands).map((s, i) => {
            const x = 20 + i * 7.6;
            const covers = x < 220;
            return (
              <path
                key={i}
                d={`M${x} 20 C ${x + s * 50} 200 ${x - s * 40} 330 ${x + s * 30} 520`}
                stroke="#030303"
                strokeWidth={covers ? 11 : 6}
                fill="none"
                opacity={covers ? 0.98 : 0.8}
              />
            );
          })}
        </>,
      );
    case "skull":
      return svg(
        <>
          <path d="M60 220 C60 60 340 60 340 220 C340 300 305 330 295 365 L105 365 C95 330 60 300 60 220Z" fill={`url(#${id}skin)`} />
          <path d={`M110 355 L290 355 L285 ${430 + 40 * mouth} Q200 ${470 + 40 * mouth} 115 ${430 + 40 * mouth}Z`} fill={`url(#${id}skin)`} />
          <ellipse cx="200" cy={395 + 25 * mouth} rx="70" ry={28 * mouth} fill={`url(#${id}void)`} />
          <Socket id={id} cx={145} cy={215} rx={44 * eye} ry={42 * eye} />
          <Socket id={id} cx={255} cy={215} rx={44 * eye} ry={42 * eye} />
          <path d="M200 268 l-20 48 q20 10 40 0Z" fill="#000" />
          <path d="M190 80 l-14 50 l18 30 l-10 40" stroke="#111" strokeWidth="4" fill="none" />
          {Array.from({ length: look.teeth }, (_, i) => {
            const w = 140 / look.teeth;
            const h = 18 + ((i * 37) % 17) * mouth;
            return i % 5 === 3 ? null : <rect key={i} x={130 + i * w} y="358" width={w - 2} height={h} rx="3" fill="#d8cfb6" stroke="#2b2b2b" strokeWidth="2" />;
          })}
        </>,
      );
    case "grinner":
      return svg(
        <>
          <ellipse cx="200" cy="250" rx="170" ry="215" fill={`url(#${id}skin)`} />
          <circle cx="140" cy="190" r={30 * eye} fill="#efe9de" />
          <circle cx="260" cy="190" r={30 * eye} fill="#efe9de" />
          <circle cx="146" cy="186" r={5} fill="#000" />
          <circle cx="254" cy="186" r={5} fill="#000" />
          <path d="M110 160 q30 -22 62 -2 M228 158 q32 -22 62 4" stroke="#000" strokeWidth="8" fill="none" />
          <path d={`M50 285 Q200 ${395 + 60 * mouth} 350 285 Q200 ${340 + 25 * mouth} 50 285Z`} fill="#7a0010" />
          <path d={`M58 288 Q200 ${385 + 55 * mouth} 342 288 Q200 ${350 + 20 * mouth} 58 288Z`} fill={`url(#${id}void)`} />
          {Array.from({ length: look.teeth + 6 }, (_, i) => {
            const n = look.teeth + 6;
            const x = 66 + (i * 268) / n;
            return i % 2 === 0 ? (
              <path key={i} d={`M${x} 292 l${134 / n} ${34 * mouth} l${134 / n} ${-34 * mouth}Z`} fill="#efe6cf" />
            ) : (
              <path key={i} d={`M${x} ${352 + 22 * mouth} l${134 / n} ${-28 * mouth} l${134 / n} ${28 * mouth}Z`} fill="#e3d7b8" />
            );
          })}
          {blood(330)}
        </>,
      );
    case "banshee":
      return svg(
        <>
          <path d="M100 180 C100 50 300 50 300 180 L275 480 Q200 510 125 480Z" fill={`url(#${id}skin)`} />
          {/* Wild white hair streaming up and out behind the head. */}
          {look.strands.map((s, i) => (
            <path
              key={i}
              d={`M${110 + i * 6.5} 120 C ${110 + i * 6.5 + s * 60} 60 ${i * 15 + s * 40} 20 ${i * 15} -40`}
              stroke="#d9dee2"
              strokeWidth="5"
              fill="none"
              opacity="0.55"
            />
          ))}
          <ellipse cx="160" cy="205" rx={28 * eye} ry={34 * eye} fill="#f3f3f0" />
          <ellipse cx="240" cy="205" rx={28 * eye} ry={34 * eye} fill="#f3f3f0" />
          <path
            d={`M${160 - 28 * eye} 200 q${28 * eye} -14 ${56 * eye} 0 M${240 - 28 * eye} 200 q${28 * eye} -14 ${56 * eye} 0`}
            stroke="#8c0000"
            strokeWidth="2"
            fill="none"
          />
          <ellipse cx="200" cy="365" rx={50 * mouth} ry={105 * mouth} fill={`url(#${id}void)`} />
        </>,
      );
    default:
      return svg(
        <>
          <path d={head} fill={`url(#${id}skin)`} />
          <Socket id={id} cx={150} cy={225} rx={30 * eye} ry={20 * eye} />
          <Socket id={id} cx={250} cy={225} rx={30 * eye} ry={20 * eye} />
          <path d="M150 240 C140 300 160 360 148 470 M250 240 C262 320 240 380 255 480" stroke="#000" strokeWidth={14 * eye} fill="none" opacity="0.85" />
          <path d="M160 380 h80" stroke="#140000" strokeWidth="7" />
          {Array.from({ length: 6 }, (_, i) => (
            <path key={i} d={`M${165 + i * 14} 368 l8 24 M${173 + i * 14} 368 l-8 24`} stroke="#140000" strokeWidth="4" />
          ))}
          <path d="M110 110 l50 60 l-14 34 M300 130 l-36 46 l18 24" stroke="#0a0a0a" strokeWidth="5" fill="none" />
        </>,
      );
  }
}

const SEEN = (room: string, you: string) => `snazzlebop:scared:${room}:${you}`;

/** Fires when the server says this person is due another scare. Only they ever get the signal. */
export function JumpScare({ count, room, you }: { count: number; room: string; you: string }) {
  const [look, setLook] = useState<Look | null>(null);
  const seen = useMemo(() => {
    try {
      return Number(sessionStorage.getItem(SEEN(room, you)) ?? "0");
    } catch {
      return 0;
    }
  }, [room, you]);
  const done = useRef(seen);

  useEffect(() => {
    if (count <= done.current) return;
    done.current = count;
    try {
      sessionStorage.setItem(SEEN(room, you), String(count));
    } catch {
      /* fine: a refresh might replay it */
    }
    // A random pause first, so it never comes exactly when expected.
    const wait = window.setTimeout(() => {
      setLook(roll());
      scream();
    }, r(1400, 4200));
    return () => window.clearTimeout(wait);
  }, [count, room, you]);

  useEffect(() => {
    if (!look) return;
    const t = window.setTimeout(() => setLook(null), 2600);
    return () => window.clearTimeout(t);
  }, [look]);

  if (!look) return null;
  if (look.photo) {
    // A real photo: full screen, harsh black-and-white, lunging in with a glitchy flicker.
    return (
      <div className="jumpscare photo" aria-hidden="true" onClick={() => setLook(null)}>
        <img className="jumpscare-photo" src={look.photo} alt="" decoding="sync" />
        <img className="jumpscare-photo ghost-red" src={look.photo} alt="" decoding="sync" />
        <div className="jumpscare-grain" />
      </div>
    );
  }
  return (
    <div className="jumpscare" aria-hidden="true" onClick={() => setLook(null)}>
      <div className={`jumpscare-face tilt-${Math.round(look.tilt / 3) + 3}`}>
        <Ghost look={look} />
      </div>
    </div>
  );
}
