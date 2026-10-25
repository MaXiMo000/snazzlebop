import { useEffect } from "react";
import { refreshAccount, useAccount } from "../lib/account";
import { sfx } from "../lib/sfx";
import type { RoomState } from "../types";
import { Btn, Card } from "./ui";

type Send = (msg: Record<string, unknown>) => void;

/** During a casual game: this game's own power-ups, one per game. The room sees that you used one;
 * anything it shows you (a struck answer, a die) is yours alone. */
export function GamePowers({ state, send }: { state: RoomState; send: Send }) {
  const { user } = useAccount();
  const p = state.powers;
  useEffect(() => {
    if (p.used) void refreshAccount(); // the count on your account went down
  }, [p.used]);
  if (!user || state.room.phase !== "game" || (!p.offer.length && !p.mine)) return null;
  const owned = (id: string) => user.powerups[id] ?? 0;
  return (
    <Card tone="soft" className="boost-panel" aria-labelledby="powers-h">
      <h3 id="powers-h">
        <span aria-hidden="true">⚡ </span>Power-ups
      </h3>
      {p.mine && (
        <p className="lead" role="status">
          <span aria-hidden="true">👁️ </span>
          {p.mine}
        </p>
      )}
      {p.used ? (
        <p className="muted">You've used yours this game.</p>
      ) : (
        <>
          <p className="muted">One per game. Everyone sees when you use one.</p>
          <ul className="boost-list space-top">
            {p.offer.map((item) => (
              <li key={item.id}>
                <Btn
                  variant="gold"
                  block
                  disabled={owned(item.id) < 1}
                  onClick={() => {
                    sfx.pop();
                    send({ t: "power", item: item.id });
                  }}
                >
                  <span aria-hidden="true">{item.icon} </span>
                  {item.name} <span className="no-break">({owned(item.id)})</span>
                </Btn>
                <p className="muted acct-hint">{item.text}</p>
              </li>
            ))}
          </ul>
          {p.offer.every((item) => owned(item.id) < 1) && (
            <p className="muted space-top">Get these in the power-up shop on your account page.</p>
          )}
        </>
      )}
    </Card>
  );
}

/** Everyone (TV included): who used which power-up this game. */
export function PowerNews({ state }: { state: RoomState }) {
  const news = state.powers.news;
  if (!news.length) return null;
  const name = (pid: string) => state.players.find((x) => x.id === pid)?.name ?? "?";
  return (
    <ul className="power-news" aria-label="Power-ups used">
      {news.map((n, i) => (
        <li key={i} className="chip plum">
          <span aria-hidden="true">{n.icon} </span>
          {name(n.pid)} used {n.name}
        </li>
      ))}
    </ul>
  );
}
