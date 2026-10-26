import { useCallback, useEffect, useState } from "react";
import { joinRoom, request } from "../lib/api";
import type { Happening } from "../lib/contract";
import { Btn, Card } from "./ui";

/** The home page's "Happening now", for signed-in players: live rooms in your clubs (open lobbies
 * first) and battle challenges waiting for you. Hidden when nothing's on. */
export function HappeningNow({ name, go }: { name: string; go: (path: string) => void }) {
  const [now, setNow] = useState<Happening | null>(null);
  const load = useCallback(() => request<Happening>("/api/me/happening").then(setNow, () => undefined), []);
  useEffect(() => {
    void load();
    const t = window.setInterval(() => document.visibilityState === "visible" && void load(), 20000);
    return () => window.clearInterval(t);
  }, [load]);
  if (!now || (!now.rooms.length && !now.challenges)) return null;
  const join = async (code: string) => {
    try {
      await joinRoom(code, name.trim());
    } catch {
      /* no name typed, or it's taken: the room page asks for one */
    }
    go(`/r/${code}`);
  };
  return (
    <Card tone="soft" aria-labelledby="now-h" className="happening">
      <h2 id="now-h">
        <span aria-hidden="true">🔴 </span>Happening now
      </h2>
      {now.challenges > 0 && (
        <a
          className="happening-challenges"
          href="/battles"
          onClick={(e) => {
            e.preventDefault();
            go("/battles");
          }}
        >
          <span aria-hidden="true">⚔️</span>
          <span>
            <b>
              {now.challenges} battle {now.challenges === 1 ? "challenge" : "challenges"}
            </b>{" "}
            waiting for you
          </span>
        </a>
      )}
      {now.rooms.length > 0 && (
        <ul className="friend-live">
          {now.rooms.map((r) => (
            <li key={r.code}>
              <span className="friend-live-text">
                <span className="friend-dot" aria-hidden="true" />
                <span>
                  <b>{r.club}</b> <span className="muted">· {r.host}</span>
                  <span className="muted happening-detail">
                    {r.battle ? "A battle" : r.game ?? "In the lobby"} · {r.players} {r.players === 1 ? "player" : "players"}
                  </span>
                </span>
              </span>
              <Btn variant={r.open ? "go" : "ghost"} size="small" onClick={() => void join(r.code)}>
                {r.open ? "Join" : "Watch"}
                <span className="sr-only">
                  {" "}
                  {r.club} room
                </span>
              </Btn>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
