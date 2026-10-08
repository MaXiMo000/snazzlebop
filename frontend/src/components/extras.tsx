import { useState } from "react";
import { Btn, Card, nameOf } from "./ui";
import { sfx } from "../lib/sfx";
import { refreshAccount, useAccount } from "../lib/account";
import type { RoomState } from "../types";
import { Select } from "./Select";

type Send = (msg: Record<string, unknown>) => void;

/** Your power card during a show game (players), and how many cards are down (everyone). */
export function PowerCard({ state, send }: { state: RoomState; send: Send }) {
  const cards = state.cards;
  const g = state.game;
  const [target, setTarget] = useState("");
  if (!state.show || !cards || !g || state.room.phase !== "game" || g.game === "jackpot") return null;
  const me = cards.you;
  const mine = me?.card ? cards.catalog[me.card] : null;
  const rivals = state.players.filter((p) => p.id !== state.you && state.crowd.contestants.some((c) => c.id === p.id));
  const chosen = rivals.find((p) => p.id === target)?.id ?? rivals[0]?.id ?? "";
  return (
    <Card tone="soft" aria-labelledby="card-h">
      <div className="row between">
        <h3 id="card-h">
          <span aria-hidden="true">🃏 </span>Power cards
        </h3>
        {cards.in_play > 0 && (
          <span className="chip plum" aria-live="polite">
            {cards.in_play} in play this game
          </span>
        )}
      </div>
      {me && mine && me.card && (
        <div className="stack-sm space-top">
          <p>
            <span aria-hidden="true">{mine.icon} </span>
            <b>{mine.name}</b>: {mine.text}. Secret until the results. One card a show.
          </p>
          <div className="row">
            {me.card === "steal" && (
              <div>
                <label className="field" htmlFor="steal-target">
                  Steal from
                </label>
                <Select id="steal-target" value={chosen} onChange={(e) => setTarget(e.target.value)}>
                  {rivals.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </Select>
              </div>
            )}
            <Btn
              variant="gold"
              onClick={() => {
                sfx.pop();
                send({ t: "card", ...(me.card === "steal" ? { target: chosen } : {}) });
              }}
            >
              Play {mine.name}
            </Btn>
          </div>
        </div>
      )}
      {me && !me.card && me.played && (
        <p className="space-top">
          You played <b>{cards.catalog[me.played]?.name}</b>.
        </p>
      )}
      {me?.peek && (
        <p className="lead space-top" role="status">
          <span aria-hidden="true">👁️ </span>
          {me.peek}
        </p>
      )}
    </Card>
  );
}

const ORDINAL = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"];

/** During any game, for a signed-in player: use one power-up bought with coins. Secret until the results. */
export function BoostPanel({ state, send }: { state: RoomState; send: Send }) {
  const { user } = useAccount();
  const [target, setTarget] = useState("");
  const cards = state.cards;
  const g = state.game;
  const me = cards?.you;
  if (!cards || !me?.signed_in || !user || !g || state.room.phase !== "game" || g.game === "jackpot") return null;
  const owned = Object.entries(user.powerups).filter(([id, n]) => n > 0 && cards.catalog[id]);
  const rivals = state.players.filter((p) => p.id !== state.you && state.crowd.contestants.some((c) => c.id === p.id));
  const chosen = rivals.find((p) => p.id === target)?.id ?? rivals[0]?.id ?? "";
  if (me.boost) {
    const c = cards.catalog[me.boost];
    return (
      <Card tone="soft" className="boost-panel" role="status">
        <p>
          <span aria-hidden="true">⚡ </span>You used <b>{c?.name}</b> this game. Revealed at the results!
        </p>
        {me.peek && (
          <p className="lead space-top">
            <span aria-hidden="true">👁️ </span>
            {me.peek}
          </p>
        )}
      </Card>
    );
  }
  if (!owned.length) return null;
  return (
    <Card tone="soft" className="boost-panel" aria-labelledby="boost-h">
      <h3 id="boost-h">
        <span aria-hidden="true">⚡ </span>Your power-ups
      </h3>
      <p className="muted">One per game. Nobody sees which until the results.</p>
      {owned.some(([id]) => id === "steal") && rivals.length > 0 && (
        <div className="space-top">
          <label className="field" htmlFor="boost-target">
            Steal from
          </label>
          <Select id="boost-target" value={chosen} onChange={(e) => setTarget(e.target.value)}>
            {rivals.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </div>
      )}
      <ul className="boost-list space-top">
        {owned.map(([id, n]) => {
          const c = cards.catalog[id]!;
          return (
            <li key={id}>
              <Btn
                variant="gold"
                block
                onClick={() => {
                  sfx.pop();
                  send({ t: "boost", item: id, ...(id === "steal" ? { target: chosen } : {}) });
                  window.setTimeout(() => void refreshAccount(), 600);
                }}
              >
                <span aria-hidden="true">{c.icon}</span> {c.name}
                <small>×{n}</small>
              </Btn>
              <p className="muted boost-text">{c.text}</p>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/** Results: the coins each signed-in finisher just earned. */
export function CoinNews({ state }: { state: RoomState }) {
  const news = Object.entries(state.cards?.coins ?? {});
  if (!news.length) return null;
  news.sort((a, b) => a[1].place - b[1].place);
  const mine = state.cards?.coins[state.you];
  return (
    <Card tone="soft" aria-labelledby="coins-news-h">
      <h3 id="coins-news-h">🪙 Coins</h3>
      {mine && (
        <p className="lead coin-mine">
          You finished {ORDINAL[mine.place] ?? `#${mine.place}`}: <b>+{mine.coins}</b>
          {mine.coins === 0 ? " (today's limit reached)" : ""}
        </p>
      )}
      <ul className="evidence">
        {news.map(([pid, n]) => (
          <li key={pid}>
            <b>{nameOf(state.players, pid)}</b> {ORDINAL[n.place] ?? `#${n.place}`} · +{n.coins}
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Results: which cards were played this game, and what they did. */
export function CardReveal({ state }: { state: RoomState }) {
  const news = state.cards?.news ?? [];
  if (!news.length) return null;
  const catalog = state.cards!.catalog;
  return (
    <Card tone="soft" aria-labelledby="card-reveal-h">
      <h3 id="card-reveal-h">🃏 Cards on the table</h3>
      <ul className="evidence">
        {news.map((n, i) => (
          <li key={i}>
            <b>{nameOf(state.players, n.pid)}</b> played <span aria-hidden="true">{catalog[n.card]?.icon} </span>
            <b>{catalog[n.card]?.name}</b>
            {n.card === "double" && `: ${n.effect >= 0 ? "+" : ""}${n.effect} more`}
            {n.card === "shield" && (n.effect > 0 ? `: blocked a ${n.effect}-point loss` : ": nothing to block")}
            {n.card === "steal" && n.target && `: took ${n.effect} from ${nameOf(state.players, n.target)}`}
            {n.card === "peek" && ": had a sneaky look"}
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Rivals: your matchup during the game; who won each one at the results. */
export function Rivals({ state }: { state: RoomState }) {
  const r = state.rivals;
  const phase = state.room.phase;
  if (!r || (!r.pairs.length && !r.news.length)) return null;
  const mine = r.pairs.find((p) => p.includes(state.you));
  const rival = mine?.find((p) => p !== state.you);
  return (
    <Card tone="soft" aria-labelledby="rivals-h">
      <h3 id="rivals-h">⚔️ Rivals (+{r.bonus} for beating yours)</h3>
      {phase === "game" && rival && (
        <p className="lead">
          Your rival this game: <b>{nameOf(state.players, rival)}</b>
        </p>
      )}
      <ul className="evidence">
        {(phase === "results" && r.news.length ? r.news.map((n) => ({ players: n.players, winner: n.winner })) : r.pairs.map((p) => ({ players: p, winner: undefined }))).map(
          ({ players, winner }) => (
            <li key={players.join("-")}>
              {nameOf(state.players, players[0]!)} <span aria-hidden="true">⚔️</span>
              <span className="sr-only">versus</span> {nameOf(state.players, players[1]!)}
              {winner !== undefined && (winner ? ` · ${nameOf(state.players, winner)} wins +${r.bonus}` : " · a draw")}
            </li>
          ),
        )}
      </ul>
    </Card>
  );
}

/** The audience's MVP vote between show games. */
export function MvpVote({ state, send }: { state: RoomState; send: Send }) {
  const mvp = state.crowd.mvp;
  if (!mvp?.open) return null;
  const audience = state.role === "audience";
  const contestants = state.crowd.contestants;
  const votes = Object.entries(mvp.votes).sort((a, b) => b[1] - a[1]);
  if (!audience && !votes.length) return null;
  return (
    <Card tone="soft" aria-labelledby="mvp-h">
      <h3 id="mvp-h">⭐ Crowd MVP (+{mvp.bonus})</h3>
      {audience && (
        <div className="row" role="group" aria-label="Vote for the MVP">
          {contestants.map((p) => (
            <Btn
              key={p.id}
              size="small"
              variant="gold"
              aria-pressed={mvp.you_voted === p.id}
              onClick={() => {
                sfx.pop();
                send({ t: "mvp", target: p.id });
              }}
            >
              {p.name}
            </Btn>
          ))}
        </div>
      )}
      {votes.length > 0 && (
        <p className="space-top" aria-live="polite">
          {votes.map(([pid, n]) => `${nameOf(state.players, pid)} ${n}`).join(" · ")}
        </p>
      )}
    </Card>
  );
}

/** Finale: the room's running season table. */
export function Season({ state }: { state: RoomState }) {
  const season = state.season;
  if (!season) return null;
  const rows = Object.entries(season.table)
    .filter(([pid]) => state.players.some((p) => p.id === pid))
    .sort((a, b) => b[1].wins - a[1].wins || b[1].points - a[1].points);
  return (
    <Card aria-labelledby="season-h">
      <h3 id="season-h">
        📅 The season: {season.number} {season.number === 1 ? "show" : "shows"}
      </h3>
      <ol className="evidence">
        {rows.map(([pid, r]) => (
          <li key={pid}>
            <b>{nameOf(state.players, pid)}</b>
            {pid === state.you ? " (you)" : ""}: {r.wins} {r.wins === 1 ? "show" : "shows"} won · {r.points} points
          </li>
        ))}
      </ol>
    </Card>
  );
}
