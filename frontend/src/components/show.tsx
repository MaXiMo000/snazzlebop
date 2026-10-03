import { useEffect, useRef, useState } from "react";
import { Season } from "./extras";
import { Btn, Card, nameOf } from "./ui";
import { useShow } from "./fx";
import { sfx } from "../lib/sfx";
import type { GameCard, Highlight, Reaction, RoomState, ShowState } from "../types";
import { MarketFinale } from "./market";

type Send = (msg: Record<string, unknown>) => void;

export const SEGMENT_ICON: Record<GameCard["id"] | "jackpot", string> = {
  frenemy: "📡",
  alibi: "🔎",
  price: "💰",
  telepathy: "🧠",
  mural: "🖼️",
  blackjack: "🃏",
  crossword: "✏️",
  dice: "🎲",
  split: "🤝",
  chicken: "🐔",
  wits: "🧮",
  codes: "🔐",
  roulette: "🎡",
  lonely: "🐺",
  boxes: "📦",
  codewords: "🕵️",
  jackpot: "💎",
};

// ---- live reactions ----------------------------------------------------------------------------
const REACTIONS: [string, string][] = [
  ["😂", "Laugh"],
  ["😱", "Gasp"],
  ["👏", "Applause"],
  ["🔥", "On fire"],
  ["🤯", "Mind blown"],
  ["💀", "I can't"],
];
const COOLDOWN_MS = 900; // the server ignores taps closer than 0.8 s anyway

export function ReactionBar({ send }: { send: Send }) {
  const [cooling, setCooling] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <div className="react-bar" role="group" aria-label="Send a reaction to the room">
      {REACTIONS.map(([e, label]) => (
        <button
          key={e}
          type="button"
          className="react-btn"
          aria-label={label}
          disabled={cooling}
          onClick={() => {
            send({ t: "react", e });
            sfx.pop();
            setCooling(true);
            timer.current = window.setTimeout(() => setCooling(false), COOLDOWN_MS);
          }}
        >
          <span aria-hidden="true">{e}</span>
        </button>
      ))}
    </div>
  );
}

/** Emoji that float up the screen as the room reacts. Decorative: screen readers skip it. */
export function ReactionOverlay({ reactions }: { reactions: Reaction[] }) {
  const seen = useRef<number>(Math.max(0, ...reactions.map((r) => r.id)));
  const [flying, setFlying] = useState<Reaction[]>([]);
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);
  useEffect(() => {
    const fresh = reactions.filter((r) => r.id > seen.current);
    if (!fresh.length) return;
    seen.current = Math.max(...fresh.map((r) => r.id));
    setFlying((f) => [...f, ...fresh].slice(-16));
    const ids = new Set(fresh.map((r) => r.id));
    // Each batch removes itself. (Clearing this on the next batch left earlier emoji stuck on screen.)
    timers.current.push(window.setTimeout(() => setFlying((f) => f.filter((r) => !ids.has(r.id))), 2600));
  }, [reactions]);
  if (!flying.length) return null;
  return (
    <div className="react-overlay" aria-hidden="true">
      {flying.map((r) => (
        <span key={r.id} className={`floater lane-${r.id % 8}`}>
          <span className="floater-emoji">{r.e}</span>
          <span className="floater-name">{r.by}</span>
        </span>
      ))}
    </div>
  );
}

// ---- the crowd ---------------------------------------------------------------------------------
export function CrowdPanel({ state, send }: { state: RoomState; send: Send }) {
  const { crowd } = state;
  const audience = state.role === "audience";
  const contestants = crowd.contestants;
  const backed = Object.entries(crowd.picks).sort((a, b) => b[1] - a[1]);
  if (!crowd.members.length && !audience) return null;
  const ranked = [...crowd.members].sort((a, b) => b.points - a.points);
  return (
    <Card tone="soft" aria-labelledby="crowd-h">
      <h3 id="crowd-h">
        <span aria-hidden="true">🎟️ </span>The crowd ({crowd.members.filter((m) => m.connected).length} watching)
      </h3>
      {audience && crowd.open && contestants.length > 0 && (
        <div className="space-top">
          <p className="lead">Who wins this one? A point if you call it.</p>
          <div className="row" role="group" aria-label="Predict the winner">
            {contestants.map((p) => (
              <Btn
                key={p.id}
                size="small"
                variant="gold"
                aria-pressed={crowd.you_picked === p.id}
                onClick={() => {
                  sfx.pop();
                  send({ t: "predict", target: p.id });
                }}
              >
                {p.name}
              </Btn>
            ))}
          </div>
        </div>
      )}
      {audience && !crowd.open && crowd.you_picked && state.room.phase === "game" && (
        <p className="space-top">
          You backed <b>{nameOf(contestants, crowd.you_picked)}</b>. Fingers crossed!
        </p>
      )}
      {!audience && backed.length > 0 && state.room.phase === "game" && (
        <p className="space-top">
          Crowd favourite: <b>{nameOf(contestants, backed[0]![0])}</b> ({backed[0]![1]}{" "}
          {backed[0]![1] === 1 ? "fan" : "fans"})
        </p>
      )}
      {ranked.length > 0 && (
        <ul className="crowd-list space-top" aria-label="Crowd prediction points">
          {ranked.map((m) => (
            <li key={m.id} className={`chip ${m.id === state.you ? "teal" : "paper"} ${m.connected ? "" : "away"}`}>
              {m.name}
              {m.id === state.you ? " (you)" : ""} · {m.points}
              <span className="sr-only"> correct calls{m.connected ? "" : ", offline"}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---- planning a show (host, lobby) -------------------------------------------------------------
export function ThemePicker({ state, send }: { state: RoomState; send: Send }) {
  const themes = Object.entries(state.themes);
  if (!themes.length) return null;
  return (
    <div>
      <label className="field" htmlFor="theme-pick">
        Show pack
      </label>
      <select
        id="theme-pick"
        value={state.room.theme}
        onChange={(e) => send({ t: "theme", theme: e.target.value })}
        aria-describedby="theme-hint"
      >
        <option value="">Everything (no theme)</option>
        {themes.map(([id, label]) => (
          <option key={id} value={id}>
            {label}
          </option>
        ))}
      </select>
      <p id="theme-hint" className="muted">
        Themed prompts and items come first; the big general pool tops up the rest.
      </p>
    </div>
  );
}

export function ShowBuilder({ state, send }: { state: RoomState; send: Send }) {
  const [picked, setPicked] = useState<GameCard["id"][]>([]);
  const [jackpot, setJackpot] = useState(true);
  const [market, setMarket] = useState(false);
  const online = state.players.filter((p) => p.connected).length;
  const byId = new Map(state.games.map((g) => [g.id, g]));
  const playable = (id: GameCard["id"]) => {
    const g = byId.get(id);
    return !!g && online >= g.min_players && online <= g.max_players;
  };
  const ready = picked.length >= 2 && picked.length <= 6 && playable(picked[0]!);
  const unplayable = picked.filter((id) => !playable(id));
  return (
    <Card tone="stage" aria-labelledby="builder-h">
      <h3 id="builder-h">Plan a show night</h3>
      <p className="space-top">
        Pick 2-6 games in the order you want them. One scoreboard for the whole night, a highlight reel at the end
        {jackpot ? ", and a Jackpot finale where everyone bets their score" : ""}
        {market ? ". The Stock Exchange lets everyone trade shares in each other before every game" : ""}.
      </p>
      <div className="builder-games space-top" role="group" aria-label="Games in this show, in order">
        {state.games.filter((g) => g.show).map((g) => {
          const at = picked.indexOf(g.id);
          return (
            <Btn
              key={g.id}
              size="small"
              variant="ghost"
              aria-pressed={at >= 0}
              disabled={at < 0 && picked.length >= 6}
              onClick={() => setPicked((p) => (at >= 0 ? p.filter((x) => x !== g.id) : [...p, g.id]))}
            >
              {at >= 0 ? <span className="order">{at + 1}</span> : <span aria-hidden="true">{SEGMENT_ICON[g.id]}</span>}
              {g.title}
              {at >= 0 && <span className="sr-only">, number {at + 1} in the show</span>}
            </Btn>
          );
        })}
      </div>
      <div className="row space-top">
        <Btn size="small" variant="ghost" aria-pressed={jackpot} onClick={() => setJackpot((j) => !j)}>
          <span aria-hidden="true">💎 </span>Jackpot finale: {jackpot ? "on" : "off"}
        </Btn>
        <Btn size="small" variant="ghost" aria-pressed={market} onClick={() => setMarket((m) => !m)}>
          <span aria-hidden="true">📈 </span>Friend Stock Exchange: {market ? "on" : "off"}
        </Btn>
      </div>
      {unplayable.length > 0 && (
        <p className="muted space-top">
          {unplayable.map((id) => byId.get(id)?.title).join(", ")} can't run with {online} online right now
          {playable(picked[0] ?? "frenemy") ? "; you can skip it when it comes up" : ""}.
        </p>
      )}
      <Btn
        className="space-top"
        variant="gold"
        size="big"
        block
        disabled={!ready}
        onClick={() => send({ t: "show", games: picked, jackpot, market })}
      >
        {picked.length < 2 ? "Pick at least 2 games" : `Start the show (${picked.length} games)`}
      </Btn>
    </Card>
  );
}

// ---- between games -------------------------------------------------------------------------------
export function ShowStrip({ show }: { show: ShowState }) {
  const total = show.playlist.length + (show.jackpot ? 1 : 0);
  const done = show.games.length;
  return (
    <nav className="show-strip" aria-label={`Show progress: ${done} of ${total} segments done`}>
      <ol>
        {show.playlist.map((g, i) => (
          <li key={g.id} className={i < done ? "done" : i === show.started - 1 && !show.finished ? "now" : ""}>
            <span aria-hidden="true">{SEGMENT_ICON[g.id]}</span> {g.title}
          </li>
        ))}
        {show.jackpot && (
          <li className={show.games.some((g) => g.game === "jackpot") ? "done" : show.next === null && !show.finished ? "now" : ""}>
            <span aria-hidden="true">💎</span> Jackpot
          </li>
        )}
      </ol>
    </nav>
  );
}

export function HostLine({ quip }: { quip: string }) {
  if (!quip) return null;
  return (
    <Card tone="stage" className="center host-line">
      <p className="sign">The host says</p>
      <p className="lead space-top">“{quip}”</p>
    </Card>
  );
}

export function Highlights({ items, title = "Highlights" }: { items: Highlight[]; title?: string }) {
  if (!items.length) return null;
  return (
    <Card aria-label={title}>
      <h3>{title}</h3>
      <ul className="highlight-list space-top">
        {items.map((h, i) => (
          <li key={`${h.title}-${i}`} className="highlight-item">
            <span className="highlight-icon" aria-hidden="true">
              {h.icon}
            </span>
            <span>
              <b>{h.title}</b>
              {h.game ? <span className="muted"> · {h.game}</span> : null}
              <br />
              {h.text}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function ShowHostBar({ state, send }: { state: RoomState; send: Send }) {
  const show = state.show!;
  const nextTitle =
    show.next === "jackpot"
      ? "Jackpot finale"
      : show.next
        ? show.playlist.find((g) => g.id === show.next)?.title ?? show.next
        : "the grand finale";
  return (
    <Card tone="soft">
      <div className="row between">
        <p className="muted">You’re the host.</p>
        <div className="row">
          {show.next && show.next !== "jackpot" && (
            <Btn variant="ghost" size="small" onClick={() => send({ t: "next", skip: true })}>
              Skip {nextTitle}
            </Btn>
          )}
          <Btn variant="go" size="big" onClick={() => send({ t: "next" })}>
            Next: {nextTitle} <span aria-hidden="true">▶</span>
          </Btn>
        </div>
      </div>
      <p className="space-top">
        <Btn
          variant="ghost"
          size="small"
          onClick={() => {
            if (window.confirm("End the show now and go back to the lobby?")) send({ t: "lobby" });
          }}
        >
          End the show
        </Btn>
      </p>
    </Card>
  );
}

// ---- the finale ----------------------------------------------------------------------------------
export function Finale({ state, isHost, send }: { state: RoomState; isHost: boolean; send: Send }) {
  const show = state.show!;
  const fx = useShow();
  const ranked = [...state.players].sort((a, b) => b.total - a.total);
  const champ = ranked[0];
  const { stinger, celebrate } = fx;
  useEffect(() => {
    sfx.fanfare();
    stinger("THAT'S THE SHOW!");
    celebrate();
  }, [stinger, celebrate]); // both are stable: this runs once, when the finale opens
  return (
    <div className="stack enter finale">
      {fx.node}
      <Card tone="stage" className="center">
        <p className="sign">{state.room.title ? `${state.room.title}: the results` : "Tonight’s champion"}</p>
        {champ && (
          <>
            <p className="trophy space-top" aria-hidden="true">
              🏆
            </p>
            <h2>
              <span className="burst">{champ.name}</span>
            </h2>
            <p className="lead">{champ.total} points</p>
          </>
        )}
      </Card>
      <HostLine quip={state.quip} />
      <Card aria-labelledby="standings-h">
        <h3 id="standings-h">Final standings</h3>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Points per game">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Contestant</th>
                {show.games.map((g, i) => (
                  <th scope="col" key={`${g.game}-${i}`}>
                    <span aria-hidden="true">{SEGMENT_ICON[g.game as GameCard["id"]] ?? "🎲"} </span>
                    {g.title}
                  </th>
                ))}
                <th scope="col">Total</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((p, i) => (
                <tr key={p.id} className={i === 0 ? "winner-row" : ""}>
                  <td>{i + 1}</td>
                  <th scope="row">
                    {p.name}
                    {p.id === state.you ? " (you)" : ""}
                  </th>
                  {show.games.map((g, j) => (
                    <td key={`${g.game}-${j}`}>{g.scores[p.id] ?? "–"}</td>
                  ))}
                  <td>
                    <b>{p.total}</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {state.market && <MarketFinale m={state.market} players={state.players} you={state.you} />}
      <Highlights items={show.awards} title="Awards" />
      <Highlights items={show.reel} title="Highlight reel" />
      <Season state={state} />
      {isHost ? (
        <div className="stack-sm">
          {show.can_rematch && (
            <Btn variant="gold" size="big" block className="rematch" onClick={() => send({ t: "rematch" })}>
              <span>🔁 Rematch</span>
              <small>Same games, next show of the season</small>
            </Btn>
          )}
          <Btn variant="go" size="big" block onClick={() => send({ t: "lobby" })}>
            Back to the lobby
          </Btn>
        </div>
      ) : (
        state.role === "player" && <p className="muted center">Thanks for playing! The host takes it from here.</p>
      )}
    </div>
  );
}
