import { useEffect, useRef } from "react";
import { Btn, Card, ShowHead, nameOf } from "./ui";
import { SEGMENT_ICON } from "./show";
import { sfx } from "../lib/sfx";
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
  const values = Object.values(intro.options);
  const mode = values.join(" · ");
  return (
    <div className={`seg-${intro.game} stack enter`}>
      <ShowHead sign="Up next · how to play" title={intro.title} remaining={intro.closes_in} receivedAt={receivedAt}>
        {mode && (
          <span className="chip plum">
            {mode}
            {values.length === 1 ? ("pace" in intro.options ? " pace" : " mode") : ""}
          </span>
        )}
      </ShowHead>
      <Card tone="stage">
        <p className="sign">
          <span aria-hidden="true">{SEGMENT_ICON[intro.game as GameCard["id"]] ?? "💎"} </span>The rules
        </p>
        <ol className="how-to-list space-top">
          {intro.how_to.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ol>
      </Card>
      {!readOnly && (
        <Card tone="soft" className="center">
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
  briefing: "I’ve read it, let’s go ▶",
  talk: "Done talking, let’s choose ▶",
  ready: "Ready to run ▶",
  peek: "Seen it, start the bidding ▶",
  teams: "Teams look good, deal ▶",
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
        {voted ? "Waiting for the others…" : READY_LABEL[state.game?.phase ?? ""] ?? "Ready for the next round ▶"}
      </Btn>
      <span className="chip plum" aria-live="polite">
        {r.votes.length}/{r.needed} ready
      </span>
    </div>
  );
}

/** The rules, one tap away during a game. */
export function HowToPlay({ lines }: { lines: string[] }) {
  if (!lines.length) return null;
  return (
    <details className="how-to card">
      <summary>❓ How to play</summary>
      <ol className="how-to-list">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ol>
    </details>
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
