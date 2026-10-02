import { useCallback, useEffect, useRef, useState } from "react";
import type { RoomState } from "../types";

export type Status = "connecting" | "open" | "reconnecting" | "closed";

export interface RoomConnection {
  state: RoomState | null;
  receivedAt: number;
  status: Status;
  error: string | null;
  send: (msg: Record<string, unknown>) => void;
  clearError: () => void;
}

const MAX_RETRIES = 8;

/** One WebSocket per room. The token is sent as the first message, never in the URL. */
export function useRoom(code: string, token: string | null): RoomConnection {
  const [state, setState] = useState<RoomState | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const [status, setStatus] = useState<Status>("connecting");
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!token) return;
    let stopped = false;
    let retries = 0;
    let pingTimer: number | undefined;
    let retryTimer: number | undefined;

    const connect = () => {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${scheme}://${window.location.host}/ws/${encodeURIComponent(code)}`);
      wsRef.current = ws;
      setStatus(retries === 0 ? "connecting" : "reconnecting");

      ws.onopen = () => {
        ws.send(JSON.stringify({ t: "auth", token }));
        pingTimer = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ t: "ping" }));
        }, 25_000);
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(String(ev.data)) as { t: string; message?: string };
          if (msg.t === "state") {
            retries = 0;
            setStatus("open");
            setState(msg as unknown as RoomState);
            setReceivedAt(performance.now());
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
        // 1008 = policy violation: bad/expired token, unknown room, rate limit. Retrying won't help.
        if (ev.code === 1008 || retries >= MAX_RETRIES) {
          setStatus("closed");
          return;
        }
        retries += 1;
        setStatus("reconnecting");
        const delay = Math.min(8000, 400 * 2 ** retries) + Math.random() * 300;
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stopped = true;
      window.clearInterval(pingTimer);
      window.clearTimeout(retryTimer);
      wsRef.current?.close(1000);
    };
  }, [code, token]);

  const send = useCallback((msg: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  }, []);

  const clearError = useCallback(() => setError(null), []);
  return { state, receivedAt, status, error, send, clearError };
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
