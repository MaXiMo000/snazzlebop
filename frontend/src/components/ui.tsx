import { useEffect, useState, useSyncExternalStore, type HTMLAttributes, type ReactNode } from "react";
import { useCountdown } from "../lib/useRoom";
import { sfx, sound } from "../lib/sfx";
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
          <p className="sign" aria-live="polite">
            {sign}
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
    <div role="alert">
      <button type="button" className="alert" onClick={onClose}>
        {message} <span className="sr-only">(dismiss)</span>
      </button>
    </div>
  );
}

function Contestant({ p, you, leader }: { p: PlayerInfo; you: boolean; leader: boolean }) {
  const pts = useCountUp(p.total);
  return (
    <li className={`contestant ${you ? "you" : ""} ${p.connected ? "" : "away"}`}>
      <span className="lamp" aria-hidden="true" />
      <span>
        {leader ? "👑 " : ""}
        {p.name}
        {you ? " (you)" : ""}
        {p.host ? <span title="Host"> ★</span> : null}
        <span className="sr-only">
          {p.host ? ", host" : ""}
          {p.connected ? "" : ", offline"}
        </span>
      </span>
      <span className="pts">
        <span aria-hidden="true">{pts}</span>
        <span className="sr-only">{p.total} points</span>
      </span>
    </li>
  );
}

export function Contestants({ players, you, title }: { players: PlayerInfo[]; you: string; title: string }) {
  const sorted = [...players].sort((a, b) => b.total - a.total);
  const top = sorted[0];
  return (
    <Card>
      <h3>{title}</h3>
      <ul className="contestants">
        {sorted.map((p) => (
          <Contestant key={p.id} p={p} you={p.id === you} leader={!!top && top.total > 0 && p.id === top.id} />
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
      <span aria-hidden="true">{on ? "🔊" : "🔇"}</span> Sound
    </Btn>
  );
}

export function nameOf(players: { id: string; name: string }[], id: string): string {
  return players.find((p) => p.id === id)?.name ?? "?";
}

export function money(n: number): string {
  return "$" + n.toLocaleString("en-US");
}
