import { useEffect, useState } from "react";
import { ApiError, clearSession, joinRoom, loadSession } from "../lib/api";
import { useRoom } from "../lib/useRoom";
import { Btn, CopyButton, ErrorBanner, Panel, Scoreboard } from "../components/ui";
import { Alibi } from "../games/Alibi";
import { Frenemy } from "../games/Frenemy";
import { Price } from "../games/Price";
import type { RoomState, Session } from "../types";

export function Room({ code, go }: { code: string; go: (path: string) => void }) {
  const [session, setSession] = useState<Session | null>(() => loadSession(code));
  if (!session) return <JoinGate code={code} onJoined={setSession} go={go} />;
  return <Live code={code} session={session} go={go} onLeave={() => setSession(null)} />;
}

function JoinGate({ code, onJoined, go }: { code: string; onJoined: (s: Session) => void; go: (p: string) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Panel className="tilt-r">
      <h2>Join room {code}</h2>
      <form
        className="stack"
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
          <input id="join-name" type="text" maxLength={16} value={name} onChange={(e) => setName(e.target.value)} autoComplete="nickname" />
        </div>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <div className="row">
          <Btn type="submit" color="lime" size="big" disabled={busy || !name.trim()}>
            Join
          </Btn>
          <Btn color="ghost" onClick={() => go("/")}>
            Back
          </Btn>
        </div>
      </form>
    </Panel>
  );
}

function Live({ code, session, go, onLeave }: { code: string; session: Session; go: (p: string) => void; onLeave: () => void }) {
  const { state, receivedAt, status, error, send, clearError } = useRoom(code, session.token);

  useEffect(() => {
    document.title = `Room ${code} · Snazzlebop`;
  }, [code]);

  if (status === "closed" && !state) {
    return (
      <Panel>
        <h2>Can't get in</h2>
        <p>That room has ended, or your seat expired.</p>
        <Btn
          onClick={() => {
            clearSession(code);
            onLeave();
            go("/");
          }}
        >
          Back home
        </Btn>
      </Panel>
    );
  }
  if (!state) {
    return (
      <Panel>
        <h2>Connecting…</h2>
        <p className="muted">Hang tight, grabbing your seat.</p>
      </Panel>
    );
  }

  const isHost = state.room.host === state.you;
  return (
    <>
      {status !== "open" && (
        <div className="error" role="status" style={{ marginBottom: 16 }}>
          Connection lost. Reconnecting…
        </div>
      )}
      <ErrorBanner message={error} onClose={clearError} />
      {state.room.phase === "lobby" && <Lobby state={state} isHost={isHost} send={send} />}
      {state.room.phase !== "lobby" && state.game && (
        <>
          <GameRouter state={state} receivedAt={receivedAt} send={send} />
          <Scoreboard players={state.players} you={state.you} title="Session scores" />
          {isHost && (
            <Panel>
              <div className="row">
                {state.room.phase === "game" ? (
                  <Btn color="ghost" onClick={() => send({ t: "skip" })}>
                    Skip wait ⏭
                  </Btn>
                ) : (
                  <Btn color="lime" size="big" onClick={() => send({ t: "lobby" })}>
                    Play another game
                  </Btn>
                )}
              </div>
            </Panel>
          )}
          {!isHost && state.room.phase === "results" && <p className="muted">Waiting for the host to pick the next game…</p>}
        </>
      )}
    </>
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

function Lobby({ state, isHost, send }: { state: RoomState; isHost: boolean; send: (m: Record<string, unknown>) => void }) {
  const online = state.players.filter((p) => p.connected).length;
  const link = `${window.location.origin}/r/${state.room.code}`;
  return (
    <div className="stack">
      <Panel themed className="halftone tilt-l">
        <p>Room code. Friends type this in, or open the link:</p>
        <div className="row">
          <span className="code" aria-label={`Room code ${state.room.code.split("").join(" ")}`}>
            {state.room.code}
          </span>
          <CopyButton text={link} label="Copy invite link" />
        </div>
      </Panel>

      <Scoreboard players={state.players} you={state.you} title={`In the room (${online} online)`} />

      <h2>{isHost ? "Pick a game" : "Waiting for the host to pick a game…"}</h2>
      <div className="grid">
        {state.games.map((g) => {
          const enough = online >= g.min_players && online <= g.max_players;
          return (
            <article key={g.id} className={`game-card ${g.id}`}>
              <h3>{g.title}</h3>
              <p>{g.blurb}</p>
              <span className="tag">
                {g.min_players}-{g.max_players} players
              </span>
              {isHost ? (
                <Btn color="lime" disabled={!enough} onClick={() => send({ t: "start", game: g.id })}>
                  {enough ? "Start!" : `Need ${g.min_players}+ online`}
                </Btn>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
