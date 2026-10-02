import { useEffect, useState } from "react";
import { ApiError, clearSession, joinRoom, loadSession } from "../lib/api";
import { useRoom } from "../lib/useRoom";
import { Btn, Card, Contestants, CopyButton, ErrorBanner, FlapCode } from "../components/ui";
import { Alibi } from "../games/Alibi";
import { Frenemy } from "../games/Frenemy";
import { Price } from "../games/Price";
import type { GameCard, RoomState, Session } from "../types";

export function Room({ code, go }: { code: string; go: (path: string) => void }) {
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
  const { state, receivedAt, status, error, send, clearError } = useRoom(code, session.token);

  useEffect(() => {
    document.title = `Room ${code} · Snazzlebop`;
  }, [code]);

  if (status === "closed") {
    return (
      <Card tone="stage" className="center enter">
        <h2>That’s a wrap</h2>
        <p>This room has ended, or your seat expired.</p>
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
      {status !== "open" && (
        <p className="alert calm" role="status">
          Signal lost. Reconnecting…
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
  switch (g.game) {
    case "frenemy":
      return <Frenemy view={g} you={state.you} receivedAt={receivedAt} send={send} />;
    case "alibi":
      return <Alibi view={g} you={state.you} receivedAt={receivedAt} send={send} />;
    case "price":
      return <Price view={g} you={state.you} players={players} receivedAt={receivedAt} send={send} />;
  }
}

const SEGMENT_ICON: Record<GameCard["id"], string> = { frenemy: "📡", alibi: "🔎", price: "💰" };

function Lobby({ state, isHost, send }: { state: RoomState; isHost: boolean; send: (m: Record<string, unknown>) => void }) {
  const online = state.players.filter((p) => p.connected).length;
  const link = `${window.location.origin}/r/${state.room.code}`;
  return (
    <div className="stack enter">
      <Card tone="stage" className="center">
        <p className="sign">Now seating contestants</p>
        <div className="space-top">
          <FlapCode code={state.room.code} />
        </div>
        <p className="space-top">Friends type this code on the home page, or open the invite link.</p>
        <CopyButton text={link} label="Copy invite link" />
      </Card>

      <Contestants players={state.players} you={state.you} title={`In the room (${online} online)`} />

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
