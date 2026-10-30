import { useEffect } from "react";
import { refreshAccount, useAccount } from "../lib/account";
import { sfx } from "../lib/sfx";
import type { RoomState } from "../types";
import { Btn } from "./ui";

type Send = (msg: Record<string, unknown>) => void;

/** During a casual game: this game's own power-ups, one per game (two from level 10 or with Plus). The room sees that you used one;
 * anything it shows you (a struck answer, a die) is yours alone. */
export function GamePowers({ state, send }: { state: RoomState; send: Send }) {
  const { user } = useAccount();
  const p = state.powers;
  useEffect(() => {
    if (p.used) void refreshAccount(); // the count on your account went down
  }, [p.used]);
  if (!user || state.room.phase !== "game" || (!p.offer.length && !p.mine)) return null;
  const owned = (id: string) => user.powerups[id] ?? 0;
  const mine = p.offer.filter((item) => owned(item.id) > 0);
  // Compact: what it showed you, or the ones you own as a row; a single line about the shop otherwise.
  return (
    <section className="power-strip" aria-labelledby="powers-h">
      <h3 id="powers-h" className="power-strip-title">
        <span aria-hidden="true">⚡ </span>Power-ups
      </h3>
      {p.mine && (
        <p className="power-result" role="status">
          <span aria-hidden="true">👁️ </span>
          {p.mine}
        </p>
      )}
      {p.used ? (
        <p className="muted">{p.slots > 1 ? `You've used all ${p.slots} this game.` : "You've used yours this game."}</p>
      ) : mine.length ? (
        <>
          <ul className="power-row">
            {mine.map((item) => (
              <li key={item.id}>
                <Btn
                  variant="gold"
                  size="small"
                  title={item.text}
                  aria-describedby={`power-${item.id}-text`}
                  onClick={() => {
                    sfx.pop();
                    send({ t: "power", item: item.id });
                  }}
                >
                  <span aria-hidden="true">{item.icon} </span>
                  {item.name} <span className="power-count">×{owned(item.id)}</span>
                </Btn>
                <span id={`power-${item.id}-text`} className="sr-only">
                  {item.text}
                </span>
              </li>
            ))}
          </ul>
          <p className="muted power-note">
            {p.slots > 1 ? (
              <>
                <span className="keep">
                  {p.left} of {p.slots} left
                </span>{" "}
                this game.
              </>
            ) : (
              "One per game."
            )}{" "}
            Everyone sees when you use one.
          </p>
        </>
      ) : (
        <p className="muted power-note">
          For this game: {p.offer.map((item) => item.name).join(", ")}. Get them in the shop on your account page.
        </p>
      )}
    </section>
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
