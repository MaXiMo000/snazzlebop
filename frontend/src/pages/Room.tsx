import { useEffect, useState } from "react";
import { ApiError, clearSession, joinRoom, loadSession, tvSeat } from "../lib/api";
import { useRoom } from "../lib/useRoom";
import { Btn, Card, Contestants, CopyButton, ErrorBanner, FlapCode } from "../components/ui";
import { Alibi } from "../games/Alibi";
import { Frenemy } from "../games/Frenemy";
import { Blackjack } from "../games/Blackjack";
import { Crossword } from "../games/Crossword";
import { Mural } from "../games/Mural";
import { Price } from "../games/Price";
import { Telepathy } from "../games/Telepathy";
import type { GameCard, RoomState, Session } from "../types";

export function Room({ code, go, tv = false }: { code: string; go: (path: string) => void; tv?: boolean }) {
  if (tv) return <TvRoom code={code} go={go} />;
  return <PlayerRoom code={code} go={go} />;
}

function PlayerRoom({ code, go }: { code: string; go: (path: string) => void }) {
  const [session, setSession] = useState<Session | null>(() => loadSession(code));
  if (!session) return <JoinGate code={code} onJoined={setSession} go={go} />;
  return <Live code={code} session={session} go={go} onLeave={() => setSession(null)} />;
}

function JoinGate({ code, onJoined, go }: { code: string; onJoined: (s: Session) => void; go: (p: string) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    document.title = `Join ${code} · Snazzlebop`;
  }, [code]);
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
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              onJoined(await joinRoom(code, name.trim()));
            } catch (err) {
              setError(err instanceof ApiError ? err.message : "Something went wrong");
            } finally {
              setBusy(false);
            }
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
              {error}
            </p>
          )}
          <div className="row">
            <Btn type="submit" variant="go" size="big" disabled={busy || !name.trim()}>
              Join
            </Btn>
            <Btn variant="ghost" onClick={() => go("/")}>
              Back
            </Btn>
          </div>
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
  return (
    <div className="stack">
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
      {state.room.phase === "lobby" && <Lobby state={state} isHost={isHost} send={send} />}
      {state.room.phase !== "lobby" && state.game && (
        <>
          <GameRouter state={state} receivedAt={receivedAt} send={send} />
          <Contestants players={state.players} you={state.you} title="Scoreboard" />
          {isHost ? (
            <Card tone="soft">
              <div className="row between">
                <p className="muted">You’re the host.</p>
                {state.room.phase === "game" ? (
                  <Btn variant="ghost" onClick={() => send({ t: "skip", stage: state.stage })}>
                    Skip wait <span aria-hidden="true">⏭</span>
                  </Btn>
                ) : (
                  <Btn variant="go" size="big" onClick={() => send({ t: "lobby" })}>
                    Play another game
                  </Btn>
                )}
              </div>
            </Card>
          ) : (
            state.room.phase === "results" && <p className="muted center">The host is picking the next segment…</p>
          )}
        </>
      )}
    </div>
  );
}

function GameRouter({ state, receivedAt, send }: { state: RoomState; receivedAt: number; send: (m: Record<string, unknown>) => void }) {
  const g = state.game!;
  const players = state.players.map((p) => ({ id: p.id, name: p.name }));
  const tv = state.tv;
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
  return (
    <div className="tv stack">
      <h1 className="sr-only">Snazzlebop TV, room {code}</h1>
      {status !== "open" && (
        <p className="alert calm" role="status">
          Signal lost. Reconnecting…
        </p>
      )}
      {state.room.phase === "lobby" || !state.game ? (
        <div className="tv-split">
          <Card tone="stage" className="center">
            <p className="sign">{state.room.title ? `Tonight: ${state.room.title}` : "Now seating contestants"}</p>
            <p className="lead space-top">
              Join at <b>{window.location.host}</b> with code
            </p>
            <FlapCode code={state.room.code} />
            <p className="space-top">{online < 3 ? "Grab a few more friends: most games need 3 or more." : "The host picks the first game…"}</p>
          </Card>
          <Contestants players={state.players} you="" title={`Contestants (${online} online)`} />
        </div>
      ) : (
        <div className="tv-split">
          <GameRouter state={state} receivedAt={receivedAt} send={noop} />
          <Contestants players={state.players} you="" title="Scoreboard" />
        </div>
      )}
      <p className="muted center">
        TV mode is read-only. Room <b>{state.room.code}</b>
      </p>
    </div>
  );
}

const SEGMENT_ICON: Record<GameCard["id"], string> = { frenemy: "📡", alibi: "🔎", price: "💰", telepathy: "🧠", mural: "🖼️", blackjack: "🃏", crossword: "✏️" };

function HostTools({ state, send }: { state: RoomState; send: (m: Record<string, unknown>) => void }) {
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
        {state.room.locked ? "Locked: nobody new can join." : "Open: anyone with the code can join."} Tap ✕ on a
        contestant to remove them.
      </p>
    </Card>
  );
}

function Lobby({ state, isHost, send }: { state: RoomState; isHost: boolean; send: (m: Record<string, unknown>) => void }) {
  const online = state.players.filter((p) => p.connected).length;
  const link = `${window.location.origin}/r/${state.room.code}`;
  return (
    <div className="stack enter">
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
      </Card>

      <Contestants
        players={state.players}
        you={state.you}
        title={`In the room (${online} online)`}
        onKick={isHost ? (id) => send({ t: "kick", target: id }) : undefined}
      />
      {isHost && <HostTools state={state} send={send} />}

      <h2>{isHost ? "Pick a game" : "Waiting for the host to pick a game…"}</h2>
      <div className="grid">
        {state.games.map((g) => {
          const enough = online >= g.min_players && online <= g.max_players;
          return (
            <Card as="article" key={g.id} className={`segment-card seg-${g.id} game-card ${g.id}`} aria-labelledby={`seg-${g.id}`}>
              <div className="band">
                <span className="chip plum">
                  {g.min_players}-{g.max_players} players
                </span>
                <h3 id={`seg-${g.id}`}>
                  <span aria-hidden="true">{SEGMENT_ICON[g.id]} </span>
                  {g.title}
                </h3>
              </div>
              <div className="body">
                <p>{g.blurb}</p>
                {isHost && (
                  <Btn variant="accent" block disabled={!enough} onClick={() => send({ t: "start", game: g.id })}>
                    {enough ? "Start!" : `Need ${g.min_players}+ online`}
                    <span className="sr-only"> {g.title}</span>
                  </Btn>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
