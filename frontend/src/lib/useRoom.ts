import { useCallback, useEffect, useRef, useState } from "react";
import type { RoomState } from "../types";
import { emitInk, type InkFrame } from "./ink";
import { emitCallPass, type CallPass } from "./callPass";

/**
 * connecting -> open, then on a drop: reconnecting (with backoff) -> open again,
 * or "lost" after MAX_RETRIES (the player can retry). "closed" = the room or seat is gone (1008; a flood close is 4008 and reconnects),
 * "kicked" = the host removed this player (4001). Those two are final.
 */
export type Status = "connecting" | "open" | "reconnecting" | "lost" | "closed" | "kicked";

export interface RoomConnection {
  state: RoomState | null;
  receivedAt: number;
  status: Status;
  attempt: number;
  /** true for a few seconds after a dropped connection comes back */
  recovered: boolean;
  error: string | null;
  send: (msg: Record<string, unknown>) => void;
  retry: () => void;
  clearError: () => void;
}

const MAX_RETRIES = 8;
const KICKED = 4001;

/** One WebSocket per room. The token is sent as the first message, never in the URL. */
export function useRoom(code: string, token: string | null): RoomConnection {
  const [state, setState] = useState<RoomState | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const [status, setStatus] = useState<Status>("connecting");
  const [attempt, setAttempt] = useState(0);
  const [recovered, setRecovered] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0); // bump to start over after "lost"
  const wsRef = useRef<WebSocket | null>(null);
  // Survives a manual retry (which restarts the effect), so the comeback is still recognised.
  const dropped = useRef(false);

  useEffect(() => {
    if (!token) return;
    let stopped = false;
    let retries = 0;
    let pingTimer: number | undefined;
    let retryTimer: number | undefined;
    let probeTimer: number | undefined;
    let recoveredTimer: number | undefined;

    const connect = () => {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${scheme}://${window.location.host}/ws/${encodeURIComponent(code)}`);
      wsRef.current = ws;
      setStatus(retries === 0 && !dropped.current ? "connecting" : "reconnecting");

      ws.onopen = () => {
        ws.send(JSON.stringify({ t: "auth", token }));
        pingTimer = window.setInterval(() => probe(), 25_000);
      };
      ws.onmessage = (ev) => {
        window.clearTimeout(probeTimer);
        try {
          const msg = JSON.parse(String(ev.data)) as { t: string; message?: string };
          if (msg.t === "state") {
            if (dropped.current) {
              dropped.current = false;
              setRecovered(true);
              window.clearTimeout(recoveredTimer);
              recoveredTimer = window.setTimeout(() => setRecovered(false), 3000);
            }
            retries = 0;
            setAttempt(0);
            setStatus("open");
            setState(msg as unknown as RoomState);
            setReceivedAt(performance.now());
          } else if (msg.t === "call") {
            emitCallPass(msg as unknown as CallPass);
          } else if (msg.t === "ink") {
            emitInk(msg as unknown as InkFrame);
          } else if (msg.t === "error") {
            setError(msg.message ?? "Something went wrong");
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = (ev) => {
        window.clearInterval(pingTimer);
        if (stopped) return;
        // Retrying won't help: the room/seat is gone (1008) or the host removed us (4001).
        if (ev.code === KICKED) return setStatus("kicked");
        if (ev.code === 1008) return setStatus("closed");
        // 4008 = too many messages too fast: just reconnect (the server rate limits the handshake too).
        if (retries >= MAX_RETRIES) return setStatus("lost");
        dropped.current = true;
        retries += 1;
        setAttempt(retries);
        setStatus("reconnecting");
        const delay = Math.min(8000, 400 * 2 ** retries) + Math.random() * 300;
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    // A socket can die silently while a phone sleeps: ping, and drop it if nothing answers in 5 s.
    const probe = () => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({ t: "ping" }));
      window.clearTimeout(probeTimer);
      probeTimer = window.setTimeout(() => {
        // A dead socket can take a minute to report its close: let it go and dial again now.
        const onclose = ws.onclose;
        ws.onclose = null;
        ws.onmessage = null;
        ws.close(4000);
        onclose?.call(ws, new CloseEvent("close", { code: 4000 }));
      }, 5000);
    };
    // Back on screen or back online: check the socket now, and skip any backoff wait.
    const wake = () => {
      if (document.visibilityState !== "visible" || stopped) return;
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) return probe();
      if (ws && ws.readyState === WebSocket.CONNECTING) return;
      window.clearTimeout(retryTimer);
      retries = 0;
      connect();
    };
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("online", wake);

    connect();
    return () => {
      stopped = true;
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("online", wake);
      window.clearInterval(pingTimer);
      window.clearTimeout(probeTimer);
      window.clearTimeout(retryTimer);
      window.clearTimeout(recoveredTimer);
      wsRef.current?.close(1000);
    };
  }, [code, token, generation]);

  // Never drop a tap silently: if the socket is down (a phone waking up, a network blip), say so.
  const send = useCallback((msg: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
    else setError("Reconnecting… that tap didn't reach the studio. Try again in a moment.");
  }, []);
  const retry = useCallback(() => setGeneration((g) => g + 1), []);
  const clearError = useCallback(() => setError(null), []);
  return { state, receivedAt, status, attempt, recovered, error, send, retry, clearError };
}

/** Seconds left, counted down locally from the server's relative `remaining`. */
export function useCountdown(remaining: number | null | undefined, receivedAt: number): number | null {
  const [now, setNow] = useState(performance.now());
  useEffect(() => {
    if (remaining == null) return;
    const id = window.setInterval(() => setNow(performance.now()), 250);
    return () => window.clearInterval(id);
  }, [remaining, receivedAt]);
  if (remaining == null) return null;
  return Math.max(0, Math.ceil(remaining - (now - receivedAt) / 1000));
}
