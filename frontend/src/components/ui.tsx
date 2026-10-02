import { useEffect, useState, type ReactNode } from "react";
import { useCountdown } from "../lib/useRoom";
import type { PlayerInfo } from "../types";

export function Panel({
  children,
  className = "",
  themed = false,
  as: Tag = "section",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  themed?: boolean;
  as?: "section" | "div" | "article";
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <Tag className={`panel ${themed ? "themed" : ""} ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function Btn({
  color,
  size,
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  color?: "pink" | "cyan" | "lime" | "purple" | "ghost";
  size?: "small" | "big";
}) {
  return <button type="button" className={`btn ${color ?? ""} ${size ?? ""} ${className}`} {...props} />;
}

export function Timer({ remaining, receivedAt }: { remaining: number | null | undefined; receivedAt: number }) {
  const left = useCountdown(remaining, receivedAt);
  if (left == null) return null;
  return (
    <div className={`timer ${left <= 5 ? "urgent" : ""}`} role="timer" aria-label={`${left} seconds left`}>
      {left}
    </div>
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
    <div className="error" role="alert" onClick={onClose}>
      {message}
    </div>
  );
}

export function Scoreboard({ players, you, title = "Scoreboard" }: { players: PlayerInfo[]; you: string; title?: string }) {
  const sorted = [...players].sort((a, b) => b.total - a.total);
  return (
    <Panel>
      <h3>{title}</h3>
      <ul className="players">
        {sorted.map((p, i) => (
          <li key={p.id} className={`player ${p.id === you ? "you" : ""}`}>
            <span className={`dot ${p.connected ? "" : "off"}`} aria-label={p.connected ? "online" : "offline"} />
            <span>
              {i === 0 && p.total > 0 ? "👑 " : ""}
              {p.name}
              {p.host ? " ★" : ""}
            </span>
            <span className="pts">{p.total}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Btn
      size="small"
      color="cyan"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          window.setTimeout(() => setDone(false), 1600);
        } catch {
          /* clipboard blocked: the code is selectable on screen anyway */
        }
      }}
    >
      {done ? "Copied!" : label}
    </Btn>
  );
}

export function nameOf(players: { id: string; name: string }[], id: string): string {
  return players.find((p) => p.id === id)?.name ?? "?";
}

export function money(n: number): string {
  return "$" + n.toLocaleString("en-US");
}
