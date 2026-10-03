import { useEffect, useState } from "react";
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
import { Alibi } from "../games/Alibi";
import { Frenemy } from "../games/Frenemy";
import { Blackjack } from "../games/Blackjack";
import { Crossword } from "../games/Crossword";
import { Jackpot } from "../games/Jackpot";
import { Split } from "../games/Split";
import { Dice } from "../games/Dice";
import { Mural } from "../games/Mural";
import { Price } from "../games/Price";
import { Telepathy } from "../games/Telepathy";
import type { GameCard, RoomState, Session } from "../types";

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
        <p>{status === "kicked" ? "The host removed you from this room." : "This room has ended, or your seat expired."}</p>
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
      <ReactionOverlay reactions={state.reactions} />
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
      {(phase === "game" || phase === "results") && state.game && (
        <>
          <GameRouter state={state} receivedAt={receivedAt} send={send} />
          {phase === "results" && (
            <>
              <HostLine quip={state.quip} />
              <Highlights items={state.highlights} />
            </>
          )}
          <ReactionBar send={send} />
          <CrowdPanel state={state} send={send} />
          <Contestants players={state.players} you={state.you} title={state.show ? "Show scoreboard" : "Scoreboard"} />
          {isHost ? (
            phase === "game" ? (
              <Card tone="soft">
                <div className="row between">
                  <p className="muted">You’re the host.</p>
                  <Btn variant="ghost" onClick={() => send({ t: "skip", stage: state.stage })}>
                    Skip wait <span aria-hidden="true">⏭</span>
                  </Btn>
                </div>
              </Card>
            ) : state.show && !state.show.finished ? (
              <ShowHostBar state={state} send={send} />
            ) : (
              <Card tone="soft">
                <div className="row between">
                  <p className="muted">You’re the host.</p>
                  <Btn variant="go" size="big" onClick={() => send({ t: "lobby" })}>
                    Play another game
                  </Btn>
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
  const { state, receivedAt, status } = useRoom(code, session?.token ?? null);
  const noop = () => undefined;

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
      {status !== "open" && (
        <p className="alert calm" role="status">
          Signal lost. Reconnecting…
        </p>
      )}
      {state.show && phase !== "lobby" && phase !== "finale" && <ShowStrip show={state.show} />}
      {phase === "finale" && state.show ? (
        <Finale state={state} isHost={false} send={noop} />
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
            <GameRouter state={state} receivedAt={receivedAt} send={noop} />
            {phase === "results" && (
              <>
                <HostLine quip={state.quip} />
                <Highlights items={state.highlights} />
              </>
            )}
          </div>
          <div className="stack">
            <Contestants players={state.players} you="" title={state.show ? "Show scoreboard" : "Scoreboard"} />
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
  },
};

/** Start button, plus a picker for each option the game declares (first value = default). */
function StartGame({ game, enough, send }: { game: GameCard; enough: boolean; send: Send }) {
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const options = Object.entries(game.options ?? {});
  const picked = Object.fromEntries(options.map(([k, vals]) => [k, chosen[k] ?? vals[0]!]));
  return (
    <>
      {options.map(([key, values]) => (
        <div key={key} className="space-top">
          <label className="field" htmlFor={`opt-${game.id}-${key}`}>
            {key === "mode" ? "Mode" : key}
          </label>
          <select
            id={`opt-${game.id}-${key}`}
            value={picked[key]}
            onChange={(e) => setChosen((c) => ({ ...c, [key]: e.target.value }))}
          >
            {values.map((v) => (
              <option key={v} value={v}>
                {OPTION_LABELS[key]?.[v] ?? v}
              </option>
            ))}
          </select>
        </div>
      ))}
      <Btn
        className="space-top"
        variant="accent"
        block
        disabled={!enough}
        onClick={() => send({ t: "start", game: game.id, ...(options.length ? { options: picked } : {}) })}
      >
        {enough ? "Start!" : `Need ${game.min_players}+ online`}
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

      <Contestants
        players={state.players}
        you={state.you}
        title={`In the room (${online} online)`}
        onKick={isHost ? (id) => send({ t: "kick", target: id }) : undefined}
      />
      {isHost && <HostTools state={state} send={send} />}
      {isHost && <ShowBuilder state={state} send={send} />}

      <h2>{isHost ? "Or play a single game" : "Waiting for the host to pick a game…"}</h2>
      <div className="grid">
        {state.games.map((g) => {
          const enough = online >= g.min_players && online <= g.max_players;
          return (
            <Card as="article" key={g.id} className={`segment-card seg-${g.id} game-card`} aria-labelledby={`seg-${g.id}`}>
              <div className="band">
                <span className="chip plum">
                  {g.min_players === g.max_players ? g.min_players : `${g.min_players}-${g.max_players}`} players
                </span>
                <h3 id={`seg-${g.id}`}>
                  <span aria-hidden="true">{SEGMENT_ICON[g.id]} </span>
                  {g.title}
                </h3>
              </div>
              <div className="body">
                <p>{g.blurb}</p>
                {isHost && <StartGame game={g} enough={enough} send={send} />}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
