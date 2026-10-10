import { useEffect, useState } from "react";
import { CallHost, CallStrip } from "../components/call";
import { ChatDock, ChatTicker } from "../components/chat";
import { ApiError, audienceSeat, clearSession, joinRoom, loadSession, tvSeat } from "../lib/api";
import { useRoom } from "../lib/useRoom";
import { Btn, Card, Contestants, CopyButton, ErrorBanner, FlapCode } from "../components/ui";
import {
  CrowdPanel,
  Finale,
  Highlights,
  HostLine,
  ReactionBar,
  ReactionOverlay,
  SEGMENT_ICON,
  ShowBuilder,
  ShowHostBar,
  ShowStrip,
  ThemePicker,
} from "../components/show";
import { MarketFloor, MarketMoves } from "../components/market";
import { BoostPanel, CardReveal, CoinNews, MvpVote, PowerCard, Rivals } from "../components/extras";
import { useAccount } from "../lib/account";
import { TeamBadge, TeamResult } from "../components/teams";
import { HowToPlay, IntroScreen, LastStandings, ReadyBar, useScrollToTopOn } from "../components/flow";
import { JumpScare } from "../components/JumpScare";
import { Alibi } from "../games/Alibi";
import { Frenemy } from "../games/Frenemy";
import { Blackjack } from "../games/Blackjack";
import { Crossword } from "../games/Crossword";
import { Jackpot } from "../games/Jackpot";
import { Codewords } from "../games/Codewords";
import { TruthDare } from "../games/TruthDare";
import { WordRace } from "../games/WordRace";
import { DrawGuess } from "../games/DrawGuess";
import { Telephone } from "../games/Telephone";
import { Tycoon } from "../games/Tycoon";
import { LastCard } from "../games/LastCard";
import { Ludo } from "../games/Ludo";
import { Chess } from "../games/Chess";
import { Boxes } from "../games/Boxes";
import { Lonely } from "../games/Lonely";
import { Roulette } from "../games/Roulette";
import { Codes } from "../games/Codes";
import { Wits } from "../games/Wits";
import { Chicken } from "../games/Chicken";
import { Split } from "../games/Split";
import { Dice } from "../games/Dice";
import { Mural } from "../games/Mural";
import { Price } from "../games/Price";
import { Telepathy } from "../games/Telepathy";
import type { GameCard, RoomState, Session } from "../types";
import { Select } from "../components/Select";

type Send = (m: Record<string, unknown>) => void;

export function Room({ code, go, tv = false }: { code: string; go: (path: string) => void; tv?: boolean }) {
  if (tv) return <TvRoom code={code} go={go} />;
  return <PlayerRoom code={code} go={go} />;
}

function PlayerRoom({ code, go }: { code: string; go: (path: string) => void }) {
  const [session, setSession] = useState<Session | null>(() => loadSession(code));
  if (!session) return <JoinGate code={code} onJoined={setSession} go={go} />;
  return <Live code={code} session={session} go={go} onLeave={() => setSession(null)} />;
}

/** Seats are full or the game has started: the crowd is still open (unless the host locked the room). */
const CROWD_OK = new Set(["room_full", "in_progress"]);

function JoinGate({ code, onJoined, go }: { code: string; onJoined: (s: Session) => void; go: (p: string) => void }) {
  const [name, setName] = useState("");
  const { user } = useAccount();
  useEffect(() => {
    if (user) setName((n) => n || user.username.slice(0, 16));
  }, [user]);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    document.title = `Join ${code} · Snazzlebop`;
  }, [code]);
  const attempt = async (as: "player" | "audience") => {
    setBusy(true);
    setError(null);
    try {
      onJoined(await (as === "player" ? joinRoom(code, name.trim()) : audienceSeat(code, name.trim())));
    } catch (err) {
      setError(err instanceof ApiError ? { code: err.code, message: err.message } : { code: "error", message: "Something went wrong" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="stack enter">
      <Card tone="stage" className="center">
        <p className="sign">You’re invited</p>
        <h2 className="space-top">Join room {code}</h2>
        <FlapCode code={code} />
      </Card>
      <Card>
        <form
          className="stack-sm"
          onSubmit={(e) => {
            e.preventDefault();
            void attempt("player");
          }}
        >
          <div>
            <label className="field" htmlFor="join-name">
              Your name
            </label>
            <input
              id="join-name"
              type="text"
              maxLength={16}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="nickname"
              placeholder="Up to 16 characters"
            />
          </div>
          {error && (
            <p className="alert" role="alert">
              {error.message}
              {CROWD_OK.has(error.code) ? ". You can still join the audience!" : ""}
            </p>
          )}
          <div className="row">
            <Btn type="submit" variant="go" size="big" disabled={busy || !name.trim()}>
              Join as a contestant
            </Btn>
            <Btn
              variant={error && CROWD_OK.has(error.code) ? "gold" : "ghost"}
              disabled={busy || !name.trim()}
              onClick={() => void attempt("audience")}
            >
              <span aria-hidden="true">🎟️ </span>Join the audience
            </Btn>
            <Btn variant="ghost" onClick={() => go("/")}>
              Back
            </Btn>
          </div>
          <p className="muted">The audience reacts live and predicts winners. Seats are for up to 8 contestants.</p>
        </form>
      </Card>
    </div>
  );
}

function Live({ code, session, go, onLeave }: { code: string; session: Session; go: (p: string) => void; onLeave: () => void }) {
  const { state, receivedAt, status, attempt, recovered, error, send, retry, clearError } = useRoom(code, session.token);
  useScrollToTopOn(`${state?.room.phase}:${state?.stage}:${state?.intro?.game ?? ""}`);

  useEffect(() => {
    document.title = `Room ${code} · Snazzlebop`;
  }, [code]);

  if (status === "lost") {
    return (
      <Card tone="stage" className="center enter">
        <h2>Signal lost</h2>
        <p>We couldn’t reconnect. Your seat is still saved on this device.</p>
        <div className="row center">
          <Btn variant="gold" onClick={retry}>
            Try again
          </Btn>
          <Btn variant="ghost" onClick={() => go("/")}>
            Home
          </Btn>
        </div>
      </Card>
    );
  }
  if (status === "closed" || status === "kicked") {
    return (
      <Card tone="stage" className="center enter">
        <h2>{status === "kicked" ? "You’ve been removed" : "That’s a wrap"}</h2>
        <p>
          {status === "kicked"
            ? "The host removed you from this room."
            : "This room has ended. The server may have restarted (for example for an update), or your seat expired. Start a new room to keep playing."}
        </p>
        <Btn
          variant="gold"
          onClick={() => {
            clearSession(code);
            onLeave();
            go("/");
          }}
        >
          Back to the lobby
        </Btn>
      </Card>
    );
  }
  if (!state) {
    return (
      <Card tone="stage" className="center">
        <h2>Warming up the studio…</h2>
        <p className="muted">Grabbing your seat.</p>
      </Card>
    );
  }

  const isHost = state.room.host === state.you;
  const phase = state.room.phase;
  const audience = state.role === "audience";
  return (
    <div className="stack">
      <JumpScare count={state.scare} room={code} you={state.you} />
      <ReactionOverlay reactions={state.reactions} />
      {state.chat && <ChatDock chat={state.chat} you={state.you} send={send} />}
      <CallHost available={!!state.call?.available} allowed={!!state.call?.allowed} send={send} />
      <CallStrip />
      {status === "reconnecting" && (
        <div className="alert calm row between" role="status">
          <span>Signal lost. Reconnecting{attempt > 1 ? ` (try ${attempt})` : ""}…</span>
          <Btn size="small" variant="ghost" onClick={retry}>
            Try now
          </Btn>
        </div>
      )}
      {recovered && (
        <p className="alert calm" role="status">
          Back on air! 📺
        </p>
      )}
      <ErrorBanner message={error} onClose={clearError} />
      {audience && (
        <p className="chip plum audience-badge">
          <span aria-hidden="true">🎟️</span> You’re in the audience
        </p>
      )}
      {state.show && phase !== "lobby" && phase !== "finale" && <ShowStrip show={state.show} />}
      {phase === "lobby" &&
        (audience ? <AudienceLobby state={state} /> : <Lobby state={state} isHost={isHost} send={send} />)}
      {phase === "finale" && state.show && <Finale state={state} isHost={isHost} send={send} />}
      {phase === "intro" && state.intro && (
        <>
          <IntroScreen state={state} receivedAt={receivedAt} send={send} readOnly={audience} />
          <ReactionBar send={send} />
          <Contestants players={state.players} you={state.you} title={state.show ? "Show scoreboard" : "Scoreboard"} />
        </>
      )}
      {phase === "market" && state.market && (
        <>
          <MarketFloor state={state} receivedAt={receivedAt} send={send} />
          <ReactionBar send={send} />
          <Contestants players={state.players} you={state.you} title="Show scoreboard" />
        </>
      )}
      {(phase === "game" || phase === "results") && state.game && (
        <>
          <HowToPlay lines={state.how_to} />
          {/* a team game: your team above the game; at the results, the team score is the headline */}
          <TeamBadge state={state} />
          {phase === "results" && <TeamResult state={state} />}
          <GameRouter state={state} receivedAt={receivedAt} send={send} />
          {phase === "game" && <ReadyBar state={state} send={send} />}
          {phase === "game" && state.role === "player" && <PowerCard state={state} send={send} />}
          {phase === "game" && state.role === "player" && <BoostPanel state={state} send={send} />}
          {phase === "game" && state.role !== "player" && <CardsDown state={state} />}
          <Rivals state={state} />
          {phase === "results" && (
            <>
              <HostLine quip={state.quip} />
              <CardReveal state={state} />
              <CoinNews state={state} />
              <Highlights items={state.highlights} />
              {state.market && <MarketMoves m={state.market} players={state.players} you={state.you} />}
              <MvpVote state={state} send={send} />
            </>
          )}
          <ReactionBar send={send} />
          <CrowdPanel state={state} send={send} />
          <Contestants players={state.players} you={state.you} title={state.show ? "Show scoreboard" : "Scoreboard"} />
          {isHost ? (
            phase === "game" ? (
              <HostGameBar state={state} send={send} />
            ) : state.show && !state.show.finished ? (
              <ShowHostBar state={state} send={send} />
            ) : (
              <Card tone="soft">
                <div className="row between">
                  <p className="muted">You’re the host.</p>
                  <div className="row">
                    {state.game.game !== "jackpot" && (
                      <Btn variant="gold" size="big" onClick={() => send({ t: "start", game: state.game!.game })}>
                        🔁 Play again
                      </Btn>
                    )}
                    <Btn variant="go" size="big" onClick={() => send({ t: "lobby" })}>
                      Play another game
                    </Btn>
                  </div>
                </div>
              </Card>
            )
          ) : (
            phase === "results" && (
              <p className="muted center">{state.show ? "The host rolls the next segment…" : "The host is picking the next segment…"}</p>
            )
          )}
        </>
      )}
      {phase === "finale" && <ReactionBar send={send} />}
    </div>
  );
}

function GameRouter({ state, receivedAt, send }: { state: RoomState; receivedAt: number; send: Send }) {
  const g = state.game!;
  const players = state.players.map((p) => ({ id: p.id, name: p.name }));
  const tv = state.role !== "player"; // TV and audience get the read-only screens
  switch (g.game) {
    case "frenemy":
      return <Frenemy view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "alibi":
      return <Alibi view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "price":
      return <Price view={g} you={state.you} players={players} receivedAt={receivedAt} send={send} tv={tv} />;
    case "telepathy":
      return <Telepathy view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "mural":
      return <Mural view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "blackjack":
      return <Blackjack view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "crossword":
      return <Crossword view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "dice":
      return <Dice view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "split":
      return <Split view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "chicken":
      return <Chicken view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "wits":
      return <Wits view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "codes":
      return <Codes view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "roulette":
      return <Roulette view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "lonely":
      return <Lonely view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "boxes":
      return <Boxes view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "codewords":
      return <Codewords view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "truthdare":
      return <TruthDare view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "wordrace":
      return <WordRace view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "lastcard":
      return <LastCard view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "ludo":
      return <Ludo view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "chess":
      return <Chess view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "drawguess":
      return <DrawGuess view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "telephone":
      return <Telephone view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "tycoon":
      return <Tycoon view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "jackpot":
      return <Jackpot view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
  }
}

/** TV mode: a read-only big-screen view of the public state, for the living-room telly. */
function TvRoom({ code, go }: { code: string; go: (p: string) => void }) {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    document.title = `TV · Room ${code} · Snazzlebop`;
    tvSeat(code)
      .then(setSession)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Something went wrong"));
  }, [code]);
  const { state, receivedAt, status, send } = useRoom(code, session?.token ?? null);
  const noop = () => undefined;
  // The TV only watches, but it may ask for a drawing (a reconnect mid-drawing, an album page).
  const watch = (msg: Record<string, unknown>) => {
    if (msg.t === "inksync" || msg.t === "call") send(msg); // a drawing, or a watch-only call pass
  };
  useScrollToTopOn(`${state?.room.phase}:${state?.stage}:${state?.intro?.game ?? ""}`);

  if (error || status === "closed" || status === "lost" || status === "kicked") {
    return (
      <Card tone="stage" className="center enter">
        <h2>Off air</h2>
        <p>{error ?? "This room has ended, or a newer TV took over this screen."}</p>
        <Btn
          variant="gold"
          onClick={() => {
            clearSession(`tv:${code}`);
            go("/");
          }}
        >
          Back to the lobby
        </Btn>
      </Card>
    );
  }
  if (!state) {
    return (
      <Card tone="stage" className="center">
        <h2>Tuning in…</h2>
      </Card>
    );
  }
  const online = state.players.filter((p) => p.connected).length;
  const watching = state.crowd.members.filter((m) => m.connected).length;
  const phase = state.room.phase;
  return (
    <div className="tv stack">
      <h1 className="sr-only">Snazzlebop TV, room {code}</h1>
      <ReactionOverlay reactions={state.reactions} />
      {state.chat && <ChatTicker chat={state.chat} />}
      <CallHost available={!!state.call?.available} allowed={!!state.call?.allowed} send={watch} auto />
      <CallStrip tv />
      {status !== "open" && (
        <p className="alert calm" role="status">
          Signal lost. Reconnecting…
        </p>
      )}
      {state.show && phase !== "lobby" && phase !== "finale" && <ShowStrip show={state.show} />}
      {phase === "finale" && state.show ? (
        <Finale state={state} isHost={false} send={noop} />
      ) : phase === "intro" && state.intro ? (
        <div className="tv-split">
          <IntroScreen state={state} receivedAt={receivedAt} send={noop} readOnly />
          <Contestants players={state.players} you="" title={state.show ? "Show scoreboard" : "Scoreboard"} />
        </div>
      ) : phase === "market" && state.market ? (
        <div className="tv-split">
          <MarketFloor state={state} receivedAt={receivedAt} send={noop} tv />
          <Contestants players={state.players} you="" title="Show scoreboard" />
        </div>
      ) : phase === "lobby" || !state.game ? (
        <div className="tv-split">
          <Card tone="stage" className="center">
            <p className="sign">{state.room.title ? `Tonight: ${state.room.title}` : "Now seating contestants"}</p>
            <p className="lead space-top">
              Join at <b>{window.location.host}</b> with code
            </p>
            <FlapCode code={state.room.code} />
            <p className="space-top">
              {online < 3 ? "Grab a few more friends: most games need 3 or more." : "The host picks the first game…"}
            </p>
            {state.room.theme && <p className="chip space-top">Show pack: {state.themes[state.room.theme]}</p>}
          </Card>
          <Contestants players={state.players} you="" title={`Contestants (${online} online)`} />
        </div>
      ) : (
        <div className="tv-split">
          <div className="stack">
            <TeamBadge state={state} tv />
            <GameRouter state={state} receivedAt={receivedAt} send={watch} />
            {phase === "game" && <CardsDown state={state} />}
            {phase === "results" && (
              <>
                <HostLine quip={state.quip} />
                <CardReveal state={state} />
                <CoinNews state={state} />
                <Highlights items={state.highlights} />
                {state.market && <MarketMoves m={state.market} players={state.players} you="" />}
                <MvpVote state={state} send={noop} />
              </>
            )}
          </div>
          <div className="stack">
            {phase === "results" && <TeamResult state={state} />}
            <Contestants players={state.players} you="" title={state.show ? "Show scoreboard" : "Scoreboard"} />
            <Rivals state={state} />
            {watching > 0 && <p className="chip plum">🎟️ {watching} in the audience</p>}
          </div>
        </div>
      )}
      <p className="muted center">
        TV mode is read-only. Room <b>{state.room.code}</b>
      </p>
    </div>
  );
}

function HostTools({ state, send }: { state: RoomState; send: Send }) {
  const [title, setTitle] = useState(state.room.title);
  return (
    <Card tone="soft" aria-labelledby="host-tools-h">
      <h3 id="host-tools-h">Host tools</h3>
      <form
        className="ask-form"
        onSubmit={(e) => {
          e.preventDefault();
          send({ t: "title", title: title.trim() });
        }}
      >
        <div>
          <label className="field" htmlFor="show-title">
            Show title
          </label>
          <input
            id="show-title"
            type="text"
            maxLength={32}
            value={title}
            placeholder="e.g. Friday Night Showdown"
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <Btn type="submit" variant="ghost">
          Rename
        </Btn>
        <Btn
          variant={state.room.locked ? "danger" : "ghost"}
          aria-pressed={state.room.locked}
          onClick={() => send({ t: "lock", locked: !state.room.locked })}
        >
          <span aria-hidden="true">{state.room.locked ? "🔒 " : "🔓 "}</span>Lock room
        </Btn>
      </form>
      <p className="muted space-top">
        {state.room.locked ? "Locked: nobody new can join, not even the audience." : "Open: anyone with the code can join."}{" "}
        Tap ✕ on a contestant to remove them.
      </p>
      <div className="space-top">
        <ThemePicker state={state} send={send} />
      </div>
      {state.crowd.members.length > 0 && (
        <div className="space-top">
          <h4>Audience</h4>
          <ul className="crowd-list">
            {state.crowd.members.map((m) => (
              <li key={m.id} className="chip paper">
                {m.name}
                <button
                  type="button"
                  className="kick small"
                  aria-label={`Remove ${m.name} from the audience`}
                  onClick={() => {
                    if (window.confirm(`Remove ${m.name} from the audience?`)) send({ t: "kick", target: m.id });
                  }}
                >
                  <span aria-hidden="true">✕</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function RoomSign({ state }: { state: RoomState }) {
  const link = `${window.location.origin}/r/${state.room.code}`;
  return (
    <Card tone="stage" className="center">
      <p className="sign">{state.room.title ? `Tonight: ${state.room.title}` : "Now seating contestants"}</p>
      <div className="space-top">
        <FlapCode code={state.room.code} />
      </div>
      <p className="space-top">Friends type this code on the home page, or open the invite link.</p>
      <div className="row center">
        <CopyButton text={link} label="Copy invite link" />
        <a className="btn small ghost" href={`/r/${state.room.code}?tv=1`} target="_blank" rel="noopener noreferrer">
          Open TV mode<span className="sr-only"> (opens in a new tab)</span>
        </a>
      </div>
      {state.room.theme && <p className="chip space-top">Show pack: {state.themes[state.room.theme]}</p>}
    </Card>
  );
}

function AudienceLobby({ state }: { state: RoomState }) {
  const online = state.players.filter((p) => p.connected).length;
  return (
    <div className="stack enter">
      <LastStandings state={state} />
      <RoomSign state={state} />
      <Contestants players={state.players} you="" title={`Contestants (${online} online)`} />
      <Card tone="soft" className="center">
        <p className="lead">The host is setting up the next game.</p>
        <p className="muted">When it starts, back a contestant to win. Every correct call is a point for you.</p>
      </Card>
    </div>
  );
}

const OPTION_LABELS: Record<string, Record<string, string>> = {
  mode: {
    classic: "Classic (5 hands)",
    tournament: "Tournament (knockouts, 3+ players)",
    race: "Everyone for themselves",
    teams: "Two teams (4+ players)",
    normal: "Normal",
    hard: "Hard (every hint must be used)",
  },
  hands: {
    "1": "1 hand",
    "3": "3 hands (most points wins)",
  },
  stacking: {
    off: "Off (official rules)",
    on: "On (+2 on +2, +4 on +4)",
  },
  clock: {
    "10": "10 minutes each",
    "5": "5 minutes each (blitz)",
    "3+2": "3 minutes + 2 s a move",
    "15+10": "15 minutes + 10 s a move",
  },
  tokens: {
    "4": "4 tokens each (classic)",
    "2": "2 tokens each (quick game)",
  },
  rounds: {
    "3": "3 words",
    "5": "5 words",
    "1": "1 word",
  },
  turns: {
    "2": "Everyone draws twice",
    "1": "Everyone draws once",
    "3": "Everyone draws 3 times",
  },
  time: {
    "80": "80 seconds to draw",
    "60": "60 seconds (quick)",
    "100": "100 seconds (relaxed)",
    "90": "90 seconds to draw",
    "120": "2 minutes (relaxed)",
  },
  pace: {
    relaxed: "Relaxed (2½ min clues, 3 min guessing)",
    speedy: "Speedy (75 s clues, 90 s guessing)",
  },
  heat: {
    mild: "😇 Mild (party-safe)",
    cheeky: "😈 Cheeky (bold and embarrassing, never rude)",
  },
  length: {
    standard: "Standard (2 turns each)",
    quick: "Quick (1 turn each)",
    marathon: "Marathon (3 turns each)",
    "45": "45 minutes (then the richest wins)",
    "30": "30 minutes",
    "60": "1 hour",
    "0": "No limit (until one is left)",
  },
};

/** The host during a game: skip the current wait, or end the game (two taps) and go back to the lobby. */
function HostGameBar({ state, send }: { state: RoomState; send: Send }) {
  const [sure, setSure] = useState(false);
  useEffect(() => {
    if (!sure) return;
    const id = window.setTimeout(() => setSure(false), 4000);
    return () => window.clearTimeout(id);
  }, [sure]);
  const what = state.show ? "the show" : "the game";
  return (
    <Card tone="soft">
      <div className="row between">
        <p className="muted">You’re the host.</p>
        <div className="row">
          <Btn variant="ghost" onClick={() => send({ t: "skip", stage: state.stage })}>
            Skip wait <span aria-hidden="true">⏭</span>
          </Btn>
          <Btn variant={sure ? "danger" : "ghost"} onClick={() => (sure ? send({ t: "lobby" }) : setSure(true))}>
            {sure ? `Tap again to end ${what}` : `End ${what}`}
          </Btn>
        </div>
      </div>
    </Card>
  );
}

/** Start button, plus a picker for each option the game declares (first value = default). */
function StartGame({ game, enough, online, send, prefix, teamsFirst }: { game: GameCard; enough: boolean; online: number; send: Send; prefix: string; teamsFirst: boolean }) {
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [teams, setTeams] = useState(teamsFirst);
  const teamsOk = online >= 4;
  const options = Object.entries(game.options ?? {});
  const picked = Object.fromEntries(options.map(([k, vals]) => [k, chosen[k] ?? vals[0]!]));
  return (
    <>
      {options.map(([key, values]) => (
        <div key={key} className="space-top">
          <label className="field" htmlFor={`${prefix}opt-${game.id}-${key}`}>
            {key.charAt(0).toUpperCase() + key.slice(1)}
          </label>
          <Select
            id={`${prefix}opt-${game.id}-${key}`}
            value={picked[key] ?? values[0] ?? ""}
            onChange={(e) => setChosen((c) => ({ ...c, [key]: e.target.value }))}
          >
            {values.map((v) => (
              <option key={v} value={v}>
                {OPTION_LABELS[key]?.[v] ?? v}
              </option>
            ))}
          </Select>
        </div>
      ))}
      {game.teams && (
        <div className="space-top">
          <label className="field" htmlFor={`${prefix}teams-${game.id}`}>
            Play
          </label>
          <Select id={`${prefix}teams-${game.id}`} value={teams ? "teams" : "solo"} onChange={(e) => setTeams(e.target.value === "teams")}>
            <option value="solo">Everyone for themselves</option>
            <option value="teams">{game.id === "ludo" ? "Two teams (exactly 4: 2 v 2)" : "Two teams (4+ players)"}</option>
          </Select>
        </div>
      )}
      <Btn
        className="space-top"
        variant="accent"
        block
        disabled={!enough || (teams && !teamsOk)}
        onClick={() => send({ t: "start", game: game.id, ...(options.length ? { options: picked } : {}), ...(teams ? { teams: true } : {}) })}
      >
        {!enough ? `Need ${game.min_players}+ online` : teams && !teamsOk ? "Teams need 4+ online" : teams ? "Start in teams!" : "Start!"}
        <span className="sr-only"> {game.title}</span>
      </Btn>
    </>
  );
}

function Lobby({ state, isHost, send }: { state: RoomState; isHost: boolean; send: Send }) {
  const online = state.players.filter((p) => p.connected).length;
  return (
    <div className="stack enter">
      <RoomSign state={state} />
      <LastStandings state={state} />

      <Contestants
        players={state.players}
        you={state.you}
        title={`In the room (${online} online)`}
        onKick={isHost ? (id) => send({ t: "kick", target: id }) : undefined}
      />
      {isHost && <HostTools state={state} send={send} />}
      {isHost && <ShowBuilder state={state} send={send} />}

      {state.games.some((g) => g.classic) && (
        <Card tone="stage" aria-labelledby="classics-h">
          <p className="sign" id="classics-h">
            The classics
          </p>
          <p className="lead space-top">The games everyone knows, with a Snazzlebop twist. Played on their own, not in a show night.</p>
          <div className="grid space-top">
            {state.games
              .filter((g) => g.classic)
              .map((g) => (
                <GameCardTile key={g.id} g={g} online={online} isHost={isHost} send={send} />
              ))}
          </div>
        </Card>
      )}

      {state.games.some((g) => (!g.show && !g.classic) || g.teams) && (
        <Card tone="stage" aria-labelledby="team-games-h">
          <p className="sign" id="team-games-h">
            Team games
          </p>
          <p className="lead space-top">Split into two teams and play head to head: the bigger combined score wins. Played on their own, not in a show night.</p>
          <div className="grid space-top">
            {state.games
              .filter((g) => (!g.show && !g.classic) || g.teams)
              .map((g) => (
                <GameCardTile key={g.id} g={g} online={online} isHost={isHost} send={send} prefix="team-" teamsFirst={g.teams} />
              ))}
          </div>
        </Card>
      )}

      <h2>{isHost ? "Or play a single game" : "Waiting for the host to pick a game…"}</h2>
      <div className="grid">
        {state.games
          .filter((g) => g.show)
          .map((g) => (
            <GameCardTile key={g.id} g={g} online={online} isHost={isHost} send={send} />
          ))}
      </div>
    </div>
  );
}

function GameCardTile({ g, online, isHost, send, prefix = "", teamsFirst = false }: { g: GameCard; online: number; isHost: boolean; send: Send; prefix?: string; teamsFirst?: boolean }) {
  const enough = online >= g.min_players && online <= g.max_players;
  return (
    <Card as="article" key={g.id} className={`segment-card seg-${g.id} game-card`} aria-labelledby={`${prefix}seg-${g.id}`}>
      <div className="band">
        <span className="chip plum">
          {g.min_players === g.max_players ? g.min_players : `${g.min_players}-${g.max_players}`} players
        </span>
        <h3 id={`${prefix}seg-${g.id}`}>
          <span aria-hidden="true">{SEGMENT_ICON[g.id]} </span>
          {g.title}
        </h3>
      </div>
      <div className="body">
        <p>{g.blurb}</p>
        {isHost && <StartGame game={g} enough={enough} online={online} send={send} prefix={prefix} teamsFirst={teamsFirst} />}
      </div>
    </Card>
  );
}

/** For screens that can't play cards: just the suspense. */
function CardsDown({ state }: { state: RoomState }) {
  const n = state.cards?.in_play ?? 0;
  if (!n) return null;
  return (
    <p className="chip plum wrap" aria-live="polite">
      🃏 {n} power {n === 1 ? "card" : "cards"} played this game. Revealed at the results!
    </p>
  );
}
