import { Fragment, useEffect, useState, useSyncExternalStore, type HTMLAttributes, type ReactNode } from "react";
import { useCountdown } from "../lib/useRoom";
import { sfx, sound } from "../lib/sfx";
import { theme } from "../lib/theme";
import { useCountUp, useOnChange } from "./fx";
import type { PlayerInfo } from "../types";

type Tone = "plain" | "stage" | "accent" | "soft";

export function Card({
  children,
  tone = "plain",
  className = "",
  as: Tag = "section",
  ...rest
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  as?: "section" | "div" | "article";
} & HTMLAttributes<HTMLElement>) {
  return (
    <Tag className={`card ${tone === "plain" ? "" : tone} ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function Btn({
  variant,
  size,
  block,
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "go" | "gold" | "danger" | "ghost" | "accent";
  size?: "small" | "big";
  block?: boolean;
}) {
  return (
    <button type="button" className={`btn ${variant ?? ""} ${size ?? ""} ${block ? "block" : ""} ${className}`} {...props} />
  );
}

/** Studio clock. Pulses and ticks through the last five seconds. */
export function Timer({ remaining, receivedAt }: { remaining: number | null | undefined; receivedAt: number }) {
  const left = useCountdown(remaining, receivedAt);
  useOnChange(left, (_, next) => {
    if (next != null && next > 0 && next <= 5) sfx.tick();
  });
  if (left == null) return null;
  return (
    <div className={`timer ${left <= 5 ? "urgent" : ""}`} role="timer" aria-label={`${left} seconds left`}>
      {left}
    </div>
  );
}

/** Segment header: lit sign (phase, announced politely), title, studio clock. */
export function ShowHead({
  sign,
  title,
  remaining,
  receivedAt,
  children,
}: {
  sign: string;
  title: string;
  remaining: number | null | undefined;
  receivedAt: number;
  children?: ReactNode;
}) {
  return (
    <Card tone="accent">
      <div className="show-head">
        <div className="grow">
          {/* "Hand 1 of 5 · Players' turn": a narrow screen breaks between the parts, never inside one
              or after a dangling dot. */}
          <p className="sign" aria-live="polite">
            {sign.split(" · ").map((part, i) => (
              <Fragment key={i}>
                {i > 0 && " "}
                <span className="sign-part">{i > 0 ? `· ${part}` : part}</span>
              </Fragment>
            ))}
          </p>
          <h2>{title}</h2>
          {children}
        </div>
        <Timer remaining={remaining} receivedAt={receivedAt} />
      </div>
    </Card>
  );
}

export function ErrorBanner({ message, onClose }: { message: string | null; onClose: () => void }) {
  useEffect(() => {
    if (!message) return;
    const id = window.setTimeout(onClose, 4500);
    return () => window.clearTimeout(id);
  }, [message, onClose]);
  if (!message) return null;
  return (
    <div role="alert" className="toast">
      <button type="button" className="alert" onClick={onClose}>
        {message} <span className="sr-only">(dismiss)</span>
      </button>
    </div>
  );
}

function Contestant({ p, you, leader, onKick }: { p: PlayerInfo; you: boolean; leader: boolean; onKick?: () => void }) {
  const pts = useCountUp(p.total);
  return (
    <li className={`contestant ${you ? "you" : ""} ${p.connected ? "" : "away"}`}>
      <span className="lamp" aria-hidden="true" />
      {/* The name never breaks inside; the crown, "(you)" and the host star wrap around it as pieces. */}
      <span className="who">
        {leader && <span aria-hidden="true">👑</span>}
        <span className="nm">{p.name}</span>
        {you && <span>(you)</span>}
        {p.host ? <span title="Host">★</span> : null}
        <span className="sr-only">
          {p.host ? ", host" : ""}
          {p.connected ? "" : ", offline"}
        </span>
      </span>
      <span className="pts">
        <span aria-hidden="true">{pts}</span>
        <span className="sr-only">{p.total} points</span>
      </span>
      {onKick && (
        <button
          type="button"
          className="kick"
          aria-label={`Remove ${p.name} from the room`}
          onClick={() => {
            if (window.confirm(`Remove ${p.name} from the room?`)) onKick();
          }}
        >
          <span aria-hidden="true">✕</span>
        </button>
      )}
    </li>
  );
}

export function Contestants({
  players,
  you,
  title,
  onKick,
}: {
  players: PlayerInfo[];
  you: string;
  title: string;
  /** host only, between games: remove a player */
  onKick?: (id: string) => void;
}) {
  const sorted = [...players].sort((a, b) => b.total - a.total);
  const top = sorted[0];
  return (
    <Card>
      <h3>{title}</h3>
      <ul className="contestants">
        {sorted.map((p) => (
          <Contestant
            key={p.id}
            p={p}
            you={p.id === you}
            leader={!!top && top.total > 0 && p.id === top.id}
            onKick={onKick && p.id !== you ? () => onKick(p.id) : undefined}
          />
        ))}
      </ul>
    </Card>
  );
}

/** Room code on a split-flap board; screen readers get it spelled out. */
export function FlapCode({ code }: { code: string }) {
  return (
    <span className="flap">
      <span className="sr-only">Room code {code.split("").join(" ")}</span>
      {code.split("").map((ch, i) => (
        <span key={i} aria-hidden="true">
          {ch}
        </span>
      ))}
    </span>
  );
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <Btn
      size="small"
      variant="gold"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          sfx.pop();
          window.setTimeout(() => setDone(false), 1600);
        } catch {
          /* clipboard blocked: the code is on screen anyway */
        }
      }}
    >
      <span aria-live="polite">{done ? "Copied!" : label}</span>
    </Btn>
  );
}

export function SoundToggle() {
  const on = useSyncExternalStore(sound.subscribe, sound.get);
  return (
    <Btn size="small" variant="ghost" aria-pressed={on} onClick={() => sound.set(!on)}>
      <span aria-hidden="true">{on ? "🔊" : "🔇"}</span> <span className="btn-label">Sound</span>
    </Btn>
  );
}

export function ThemeToggle() {
  const now = useSyncExternalStore(theme.subscribe, theme.get);
  const dark = now === "dark";
  return (
    <Btn size="small" variant="ghost" className="theme-toggle" aria-pressed={!dark} onClick={() => theme.set(dark ? "light" : "dark")}>
      <span className="knob" aria-hidden="true">
        {dark ? "🌙" : "☀️"}
      </span>{" "}
      <span className="btn-label">Light mode</span>
    </Btn>
  );
}

export function nameOf(players: { id: string; name: string }[], id: string): string {
  return players.find((p) => p.id === id)?.name ?? "?";
}

/** "Ana" / "Ana & Bo" / "Ana, Bo & Cy": ties of any size read like a sentence. */
export function nameList(names: string[]): string {
  return names.length < 2 ? (names[0] ?? "") : `${names.slice(0, -1).join(", ")} & ${names[names.length - 1]}`;
}

export function money(n: number): string {
  return "$" + n.toLocaleString("en-US");
}
