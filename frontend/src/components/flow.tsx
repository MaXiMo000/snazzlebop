import { useEffect, useRef, useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "./ui";
import { SEGMENT_ICON } from "./show";
import { sfx } from "../lib/sfx";
import { TeamsCard } from "./teams";
import { OPTION_LABELS } from "../lib/options";
import { Sheet } from "./sheet";
import type { GameCard, RoomState } from "../types";

type Send = (msg: Record<string, unknown>) => void;

const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/** When a new round, phase or game starts, bring everyone back to the top so nobody misses it. */
export function useScrollToTopOn(key: string) {
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    // Leave the user alone while they're typing into a field that still exists.
    const el = document.activeElement;
    if (el instanceof HTMLInputElement && el.isConnected && el.type !== "checkbox") return;
    window.scrollTo({ top: 0, behavior: reduced() ? "auto" : "smooth" });
  }, [key]);
}

/** "How to play" before a game: rules, a countdown, Ready for everyone, Start now for the host. */
export function IntroScreen({ state, receivedAt, send, readOnly }: { state: RoomState; receivedAt: number; send: Send; readOnly: boolean }) {
  const intro = state.intro!;
  const isHost = state.room.host === state.you;
  const imReady = intro.ready.includes(state.you);
  const waitingOn = state.players.filter((p) => p.connected && !intro.ready.includes(p.id));
  const chosen = [...(state.ranked.on ? ["Ranked", "Standard settings"] : []), ...Object.entries(intro.options).map(([k, v]) => OPTION_LABELS[k]?.[v] ?? v)];
  return (
    <div className={`seg-${intro.game} stack enter`}>
      <ShowHead sign="Up next · how to play" title={intro.title} remaining={intro.closes_in} receivedAt={receivedAt}>
        {chosen.length > 0 && (
          <p className="intro-options">
            {chosen.map((label) => (
              <span key={label} className="chip plum">
                {label}
              </span>
            ))}
          </p>
        )}
      </ShowHead>
      <section className="intro-rules" aria-labelledby="rules-h">
        <div className="intro-title">
          <span className="intro-icon" aria-hidden="true">
            {SEGMENT_ICON[intro.game as GameCard["id"]] ?? "💎"}
          </span>
          <h3 id="rules-h">How to play</h3>
        </div>
        <ol className="how-steps intro-steps">
          {intro.how_to.map((line) => (
            <li key={line}>
              <span>{line}</span>
            </li>
          ))}
        </ol>
      </section>
      <TeamsCard state={state} send={send} readOnly={readOnly} />
      {!readOnly && (
        <Card tone="soft" className="center intro-ready">
          {imReady ? (
            <p className="lead">You’re ready! Waiting for {waitingOn.length ? waitingOn.map((p) => p.name).join(", ") : "the others"}…</p>
          ) : (
            <Btn
              variant="go"
              size="big"
              block
              onClick={() => {
                sfx.pop();
                send({ t: "ready" });
              }}
            >
              Got it, I’m ready!
            </Btn>
          )}
          <ul className="ready-people" aria-label="Who's ready">
            {state.players
              .filter((p) => p.connected)
              .map((p) => (
                <li key={p.id} className={intro.ready.includes(p.id) ? "on" : ""}>
                  <span aria-hidden="true">{intro.ready.includes(p.id) ? "✓" : "…"}</span> {p.id === state.you ? "You" : p.name}
                  <span className="sr-only">{intro.ready.includes(p.id) ? ", ready" : ", reading"}</span>
                </li>
              ))}
          </ul>
          <progress className="coin-meter ready-meter" max={Math.max(1, intro.needed)} value={intro.ready.length} aria-label={`${intro.ready.length} of ${intro.needed} ready`} />
          <p className="muted space-top" aria-live="polite">
            {intro.ready.length} of {intro.needed} ready. It starts when everyone is, or when the clock runs out.
          </p>
          {isHost && (
            <Btn variant="ghost" className="space-top" onClick={() => send({ t: "skip" })}>
              Start now ▶
            </Btn>
          )}
        </Card>
      )}
      {readOnly && (
        <p className="center lead" aria-live="polite">
          {intro.ready.length} of {intro.needed} contestants ready
        </p>
      )}
    </div>
  );
}

const READY_LABEL: Record<string, string> = {
  // Short enough for one line on a 360px phone.
  briefing: "Got it, go ▶",
  talk: "Done talking ▶",
  ready: "Ready to run ▶",
  peek: "Seen it, bid ▶",
  teams: "Teams set, deal ▶",
  album: "Next page ▶",
  roles: "Got my role ▶",
  cards: "Seen my card ▶",
  dawn: "Onward ▶",
  review: "Done reading ▶",
  hand_over: "Next hand ▶",
  sold: "Next box ▶",
};

/** On results screens: everyone taps Ready to move on together instead of waiting for the clock. */
export function ReadyBar({ state, send }: { state: RoomState; send: Send }) {
  const r = state.ready;
  if (!r?.open || state.role !== "player" || !state.crowd.contestants.some((c) => c.id === state.you)) return null;
  const voted = r.votes.includes(state.you);
  return (
    <div className="ready-bar" role="region" aria-label="Move on">
      <Btn
        variant={voted ? "ghost" : "go"}
        disabled={voted}
        onClick={() => {
          sfx.pop();
          send({ t: "ready", stage: r.stage });
        }}
      >
        {voted ? "Waiting for the others…" : READY_LABEL[state.game?.phase ?? ""] ?? "Next round ▶"}
      </Btn>
      <span className="chip plum" aria-live="polite">
        {r.votes.length}/{r.needed} ready
      </span>
    </div>
  );
}

/** The rules, one tap away during a game. */
export function HowToPlay({ lines }: { lines: string[] }) {
  const [open, setOpen] = useState(false);
  if (!lines.length) return null;
  // A small button by the game, not a bar above it: the rules open in a sheet when wanted.
  return (
    <div className="rules-row">
      <button type="button" className="rules-btn" aria-haspopup="dialog" onClick={() => setOpen(true)}>
        <span aria-hidden="true">❓</span> Rules
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} labelledBy="rules-sheet-h">
        <h2 id="rules-sheet-h">How to play</h2>
        <ol className="how-steps space-top">
          {lines.map((line) => (
            <li key={line}>
              <span>{line}</span>
            </li>
          ))}
        </ol>
      </Sheet>
    </div>
  );
}

/** Lobby: the last show's final standings stay up until the next game starts. */
export function LastStandings({ state }: { state: RoomState }) {
  const rows = state.last_standings;
  if (!rows?.length) return null;
  return (
    <Card aria-labelledby="last-h">
      <h3 id="last-h">🏆 Last show’s final standings</h3>
      <ol className="evidence">
        {rows.map((r, i) => (
          <li key={r.id}>
            {i === 0 ? "👑 " : ""}
            <b>{nameOf(state.players, r.id) === "?" ? r.name : nameOf(state.players, r.id)}</b>
            {r.id === state.you ? " (you)" : ""}: {r.total} points
          </li>
        ))}
      </ol>
    </Card>
  );
}
