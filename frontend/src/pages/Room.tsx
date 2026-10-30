import { lazy, Suspense, useEffect, useState } from "react";
import { OPTION_LABELS } from "../lib/options";
import { AvatarPicker, FaceHost } from "../components/avatar";
import { CallHost, CallStrip } from "../components/call";
import { Entrance } from "../components/entrance";
import { Night } from "../components/night";
import { Recap } from "../components/recap";
import { ChatDock, ChatTicker } from "../components/chat";
import { ApiError, audienceSeat, clearSession, joinRoom, loadSession, tvSeat } from "../lib/api";
import { useRoom } from "../lib/useRoom";
import { InviteFriends } from "../components/invite";
import { ReportInRoom } from "../components/report";
import { Btn, Card, Contestants, CopyButton, ErrorBanner, FlapCode } from "../components/ui";
import {
  CrowdPanel,
  Finale,
  Highlights,
  HostLine,
  ReactionBar,
  ReactionOverlay,
  ShowBuilder,
  ShowHostBar,
  ShowStrip,
  ThemePicker,
} from "../components/show";
import { MarketFloor, MarketMoves } from "../components/market";
import { BoostPanel, CardReveal, CoinNews, MvpVote, PowerCard, RatingNews, Rivals } from "../components/extras";
import { BattleBanner, BattleNews } from "../components/battle";
import { GamePowers, PowerNews } from "../components/powers";
import { PartyBar, PartyOverlay } from "../components/party";
import { useAccount } from "../lib/account";
import { TeamBadge, TeamResult } from "../components/teams";
import { HowToPlay, IntroScreen, LastStandings, ReadyBar, useScrollToTopOn } from "../components/flow";
import { JumpScare } from "../components/JumpScare";
import type { GameCard, RoomState, Session } from "../types";
import { Select } from "../components/Select";
import { AdSlot } from "../components/ad";
import { Fold, Sheet } from "../components/sheet";
import { Podium } from "../components/podium";
import { Mascot } from "../components/mascot";
import { fitsRoom, GameInfo, GameTile } from "../components/gamecards";

// Each game's screen loads when it's played, so the first page load stays small.
const Alibi = lazy(() => import("../games/Alibi").then((m) => ({ default: m.Alibi })));
const Frenemy = lazy(() => import("../games/Frenemy").then((m) => ({ default: m.Frenemy })));
const Blackjack = lazy(() => import("../games/Blackjack").then((m) => ({ default: m.Blackjack })));
const Crossword = lazy(() => import("../games/Crossword").then((m) => ({ default: m.Crossword })));
const Jackpot = lazy(() => import("../games/Jackpot").then((m) => ({ default: m.Jackpot })));
const Codewords = lazy(() => import("../games/Codewords").then((m) => ({ default: m.Codewords })));
const TruthDare = lazy(() => import("../games/TruthDare").then((m) => ({ default: m.TruthDare })));
const WordRace = lazy(() => import("../games/WordRace").then((m) => ({ default: m.WordRace })));
const DrawGuess = lazy(() => import("../games/DrawGuess").then((m) => ({ default: m.DrawGuess })));
const Telephone = lazy(() => import("../games/Telephone").then((m) => ({ default: m.Telephone })));
const Tycoon = lazy(() => import("../games/Tycoon").then((m) => ({ default: m.Tycoon })));
const LastCard = lazy(() => import("../games/LastCard").then((m) => ({ default: m.LastCard })));
const Ludo = lazy(() => import("../games/Ludo").then((m) => ({ default: m.Ludo })));
const Chess = lazy(() => import("../games/Chess").then((m) => ({ default: m.Chess })));
const Boxes = lazy(() => import("../games/Boxes").then((m) => ({ default: m.Boxes })));
const Lonely = lazy(() => import("../games/Lonely").then((m) => ({ default: m.Lonely })));
const Imposter = lazy(() => import("../games/Imposter").then((m) => ({ default: m.Imposter })));
const Ships = lazy(() => import("../games/Ships").then((m) => ({ default: m.Ships })));
const Snakes = lazy(() => import("../games/Snakes").then((m) => ({ default: m.Snakes })));
const Reflex = lazy(() => import("../games/Reflex").then((m) => ({ default: m.Reflex })));
const Trivia = lazy(() => import("../games/Trivia").then((m) => ({ default: m.Trivia })));
const Rather = lazy(() => import("../games/Rather").then((m) => ({ default: m.Rather })));
const Four = lazy(() => import("../games/Four").then((m) => ({ default: m.Four })));
const Lists = lazy(() => import("../games/Lists").then((m) => ({ default: m.Lists })));
const Hangman = lazy(() => import("../games/Hangman").then((m) => ({ default: m.Hangman })));
const FiveDice = lazy(() => import("../games/FiveDice").then((m) => ({ default: m.FiveDice })));
const OnHead = lazy(() => import("../games/OnHead").then((m) => ({ default: m.OnHead })));
const Bomb = lazy(() => import("../games/Bomb").then((m) => ({ default: m.Bomb })));
const Mafia = lazy(() => import("../games/Mafia").then((m) => ({ default: m.Mafia })));
const Roulette = lazy(() => import("../games/Roulette").then((m) => ({ default: m.Roulette })));
const Codes = lazy(() => import("../games/Codes").then((m) => ({ default: m.Codes })));
const Wits = lazy(() => import("../games/Wits").then((m) => ({ default: m.Wits })));
const Chicken = lazy(() => import("../games/Chicken").then((m) => ({ default: m.Chicken })));
const Split = lazy(() => import("../games/Split").then((m) => ({ default: m.Split })));
const Dice = lazy(() => import("../games/Dice").then((m) => ({ default: m.Dice })));
const Mural = lazy(() => import("../games/Mural").then((m) => ({ default: m.Mural })));
const Price = lazy(() => import("../games/Price").then((m) => ({ default: m.Price })));
const Telepathy = lazy(() => import("../games/Telepathy").then((m) => ({ default: m.Telepathy })));

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
  if (error?.code === "room_not_found")
    return (
      <Card className="center room-gone" aria-labelledby="gone-h">
        <Mascot size={120} mood="wow" />
        <h2 id="gone-h" className="space-top">
          This show has ended
        </h2>
        <p className="muted">
          Room {code} isn’t on air: it may have finished, or the code has a typo. Ask the host for a fresh link, or start your own.
        </p>
        <Btn className="space-top" variant="gold" onClick={() => go("/")}>
          Back to the home page
        </Btn>
      </Card>
    );
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
      <PartyOverlay state={state} />
      <FaceHost all={state.faces} champion={state.night?.belt.holder} you={state.you} send={send} />
      <Entrance entrance={state.entrance} you={state.you} room={code} />
      {state.chat && <ChatDock chat={state.chat} you={state.you} send={send} />}
      <CallHost
        available={!!state.call?.available}
        allowed={!!state.call?.allowed}
        hush={state.call?.hush}
        host={isHost}
        send={send}
      />
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
      {phase === "lobby" && <AdSlot go={go} />}
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
          <PowerNews state={state} />
          <div className={`game-stage ${phase === "results" ? "with-podium" : ""}`}>
            <GameRouter state={state} receivedAt={receivedAt} send={send} />
            {phase === "results" && !state.teams?.news && <Podium state={state} />}
          </div>
          {phase === "game" && <ReadyBar state={state} send={send} />}
          {phase === "game" && state.role === "player" && <GamePowers state={state} send={send} />}
          {phase === "game" && state.role === "player" && <PowerCard state={state} send={send} />}
          {phase === "game" && state.role === "player" && !state.ranked.on && !state.battle.game && <BoostPanel state={state} send={send} />}
          {phase === "game" && state.role !== "player" && <CardsDown state={state} />}
          <Rivals state={state} />
          {phase === "results" && (
            <>
              <HostLine quip={state.quip} />
              <CardReveal state={state} />
              <CoinNews state={state} />
              <RatingNews state={state} />
              <BattleNews state={state} />
              <Highlights items={state.highlights} />
              {state.market && <MarketMoves m={state.market} players={state.players} you={state.you} />}
              <MvpVote state={state} send={send} />
              <AdSlot go={go} />
            </>
          )}
          <ReactionBar send={send} />
          <CrowdPanel state={state} send={send} />
          {phase === "results" ? (
            <Contestants players={state.players} you={state.you} title={state.show ? "Show scoreboard" : "Scoreboard"} />
          ) : (
            // During a game the game shows its own scores: the room's running total folds away.
            <Fold icon="🏆" title={state.show ? "Show scoreboard" : "Room scoreboard"} hint={leaderLine(state.players)}>
              <Contestants players={state.players} you={state.you} title={state.show ? "Show scoreboard" : "Scoreboard"} />
            </Fold>
          )}
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
      <PartyBar state={state} send={send} />
      {!audience && phase !== "lobby" && <Night state={state} send={send} isHost={isHost} />}
      <Recap state={state} send={send} />
    </div>
  );
}

/** "Ana leads with 1,200": the folded scoreboard's summary. */
function leaderLine(players: RoomState["players"]): string {
  const top = [...players].sort((a, b) => b.total - a.total)[0];
  return top && top.total > 0 ? `${top.name} leads with ${top.total.toLocaleString()}` : "Everyone on 0 so far";
}

function GameRouter(props: { state: RoomState; receivedAt: number; send: Send }) {
  return (
    <Suspense fallback={<p className="muted center game-loading">Loading the game…</p>}>
      <GameScreen {...props} />
    </Suspense>
  );
}

function GameScreen({ state, receivedAt, send }: { state: RoomState; receivedAt: number; send: Send }) {
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
    case "mafia":
      return <Mafia view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "bomb":
      return <Bomb view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "reflex":
      return <Reflex view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "snakes":
      return <Snakes view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "ships":
      return <Ships view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "onhead":
      return <OnHead view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "fivedice":
      return <FiveDice view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "hangman":
      return <Hangman view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "lists":
      return <Lists view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "four":
      return <Four view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "rather":
      return <Rather view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "trivia":
      return <Trivia view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
    case "imposter":
      return <Imposter view={g} you={state.you} receivedAt={receivedAt} send={send} tv={tv} />;
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
      <PartyOverlay state={state} />
      <FaceHost all={state.faces} champion={state.night?.belt.holder} you={state.you} />
      <Entrance entrance={state.entrance} you={state.you} room={code} />
      {state.chat && <ChatTicker chat={state.chat} />}
      <CallHost available={!!state.call?.available} allowed={!!state.call?.allowed} send={watch} auto />
      <CallStrip tv />
      <Night state={state} tv />
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
          <Card tone="stage" className="center tv-lobby">
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
            <PowerNews state={state} />
            <GameRouter state={state} receivedAt={receivedAt} send={watch} />
            {phase === "game" && <CardsDown state={state} />}
            {phase === "results" && (
              <>
                <HostLine quip={state.quip} />
                <CardReveal state={state} />
                <CoinNews state={state} />
                <RatingNews state={state} />
                <BattleNews state={state} />
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
      {/* One row of actions; a panel one of them opens (invite, report) takes the full width under it. */}
      <div className="room-actions">
        <CopyButton text={link} label="Copy invite link" />
        <a className="btn small ghost" href={`/r/${state.room.code}?tv=1`} target="_blank" rel="noopener noreferrer">
          <span aria-hidden="true">📺 </span>TV mode<span className="sr-only"> (opens in a new tab)</span>
        </a>
        {state.role === "player" && <InviteFriends code={state.room.code} />}
        {state.role === "player" && <ReportInRoom code={state.room.code} players={state.players} you={state.you} />}
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
    <div className="host-bar" role="group" aria-label="Host controls">
      <span className="host-bar-label">
        <span aria-hidden="true">🎙️</span> You're the host
      </span>
      <Btn variant="ghost" size="small" onClick={() => send({ t: "skip", stage: state.stage })}>
        Skip wait <span aria-hidden="true">⏭</span>
      </Btn>
      <Btn variant={sure ? "danger" : "ghost"} size="small" onClick={() => (sure ? send({ t: "lobby" }) : setSure(true))}>
        {sure ? `Tap again to end ${what}` : `End ${what}`}
      </Btn>
    </div>
  );
}

/** Start button, plus a picker for each option the game declares (first value = default). */
function StartGame({
  game,
  enough,
  online,
  send,
  prefix,
  teamsFirst,
  rankedReady,
}: {
  game: GameCard;
  enough: boolean;
  online: number;
  send: Send;
  prefix: string;
  teamsFirst: boolean;
  rankedReady: boolean;
}) {
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [teamsPick, setTeams] = useState(teamsFirst);
  const [ranked, setRanked] = useState(false);
  const teams = teamsPick && !ranked;
  const teamsOk = online >= 4;
  const rankedMin = game.ranked_min ?? 2;
  // Ranked games use the standard settings: no options to pick.
  const options = ranked ? [] : Object.entries(game.options ?? {});
  const picked = Object.fromEntries(options.map(([k, vals]) => [k, chosen[k] ?? vals[0]!]));
  // What will start, in short ("Classic · 10 questions"): the full choices fold away until wanted.
  const short = (label: string) => label.replace(/ \(.*\)$/, "");
  const now = [
    ...options.map(([k, vals]) => short(OPTION_LABELS[k]?.[picked[k] ?? vals[0]!] ?? picked[k] ?? "")),
    ...(game.teams && !ranked ? [teams ? "Two teams" : "Everyone for themselves"] : []),
    ...(ranked ? ["Ranked", "Standard settings"] : []),
  ];
  const rankedBlock = !ranked ? "" : !rankedReady ? "Everyone must be signed in" : online < rankedMin ? `Ranked needs ${rankedMin}+ online` : "";
  return (
    <>
      {(now.length > 0 || game.ranked) && (
        <details className="game-options">
          <summary>
            <span className="game-options-title">
              <span aria-hidden="true">⚙️</span> Game options
            </span>
            <span className="game-options-now">
              {now.map((label, i) => (
                <span key={i}>{label}</span>
              ))}
            </span>
          </summary>
          {game.ranked && (
            <div className="space-top">
              <label className="check">
                <input type="checkbox" checked={ranked} onChange={(e) => setRanked(e.target.checked)} />
                <span>Ranked game</span>
              </label>
              <p className="muted acct-hint">
                Rated for everyone, with the standard settings and no power-ups. Every player signs in, {rankedMin}+ players.
              </p>
            </div>
          )}
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
          {game.teams && !ranked && (
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
        </details>
      )}
      <Btn
        className="space-top start-game"
        variant="accent"
        block
        disabled={!enough || (teams && !teamsOk) || !!rankedBlock}
        onClick={() =>
          send({ t: "start", game: game.id, ...(options.length ? { options: picked } : {}), ...(teams ? { teams: true } : {}), ...(ranked ? { ranked: true } : {}) })
        }
      >
        {!enough
          ? online > game.max_players
            ? `Up to ${game.max_players} players`
            : `Need ${game.min_players}+ online`
          : rankedBlock || (teams && !teamsOk ? "Teams need 4+ online" : teams ? "Start in teams!" : ranked ? "Start ranked!" : "Start!")}
        <span className="sr-only"> {game.title}</span>
      </Btn>
    </>
  );
}

/** "all" shows every shelf as its own section, "start" the newcomers' picks, else one category. */
type ShelfPick = "all" | "start" | string;
// Team games: those with a Teams switch, plus the games that are played in two teams anyway (Codewords).
const teamGame = (g: GameCard) => g.teams || (!g.show && !g.classic);

/** The game picker: compact tiles by category; a tile opens the game's sheet (rules, options, Start). */
function GameShelf({ state, online, isHost, send }: { state: RoomState; online: number; isHost: boolean; send: Send }) {
  const [pick, setPick] = useState<ShelfPick>("all");
  const [fits, setFits] = useState(false);
  const [teams, setTeams] = useState(false);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const q = query.trim().toLowerCase();
  const passes = (g: GameCard) =>
    (!fits || fitsRoom(g, online)) && (!teams || teamGame(g)) && (!q || g.title.toLowerCase().includes(q) || g.blurb.toLowerCase().includes(q));
  const featured = state.games.filter((g) => g.featured !== null && passes(g)).sort((a, b) => (a.featured ?? 0) - (b.featured ?? 0));
  const sections =
    pick === "start"
      ? [{ id: "start", title: "Start here", blurb: "Learned in a minute and great with people you just met.", games: featured }]
      : state.categories
          .filter((c) => pick === "all" || pick === c.id)
          .map((c) => ({ id: c.id, title: c.title, blurb: c.blurb, games: state.games.filter((g) => g.category === c.id && passes(g)) }))
          .filter((s) => s.games.length > 0);
  const count = (id: ShelfPick) => (id === "start" ? featured.length : state.games.filter((g) => (id === "all" || g.category === id) && passes(g)).length);
  const chips: [ShelfPick, string][] = [["all", "All"], ["start", "⭐ Start here"], ...state.categories.map((c): [string, string] => [c.id, c.label])];
  const game = state.games.find((g) => g.id === open) ?? null;
  const surprise = () => {
    const pool = state.games.filter((g) => fitsRoom(g, online));
    const g = pool[Math.floor(Math.random() * pool.length)];
    if (g) setOpen(g.id);
  };
  return (
    <section className="shelf" aria-labelledby="games-h">
      <div className="shelf-head">
        <div>
          <h2 id="games-h">{isHost ? "Pick a game" : "The games"}</h2>
          <p className="muted">{isHost ? `${online} online. Tap a game for its rules and to start it.` : "The host picks one. Tap any game to read how it works."}</p>
        </div>
        {isHost && (
          <Btn variant="gold" onClick={surprise}>
            <span aria-hidden="true">🎲</span> Surprise me
          </Btn>
        )}
      </div>
      <div className="shelf-tools">
        <label className="sr-only" htmlFor="shelf-search">
          Find a game
        </label>
        <input
          id="shelf-search"
          type="text"
          className="shelf-search"
          placeholder="🔎 Find a game…"
          autoComplete="off"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="shelf-filters scroll-row" role="group" aria-label="Shelf">
          {chips.map(([id, label]) => (
            <button key={id} type="button" className="shelf-chip" aria-pressed={pick === id} onClick={() => setPick(id)}>
              {label}
              <span className="shelf-count">{count(id)}</span>
            </button>
          ))}
        </div>
        <div className="shelf-filters" role="group" aria-label="Only show">
          <button type="button" className="shelf-chip toggle" aria-pressed={fits} onClick={() => setFits((v) => !v)}>
            <span aria-hidden="true">{fits ? "✓" : "+"}</span> Fits {online} {online === 1 ? "player" : "players"}
          </button>
          <button type="button" className="shelf-chip toggle" aria-pressed={teams} onClick={() => setTeams((v) => !v)}>
            <span aria-hidden="true">{teams ? "✓" : "+"}</span> Team games
          </button>
        </div>
      </div>
      {sections.length === 0 ? (
        <div className="empty-state">
          <span aria-hidden="true">🔍</span>
          <p>No game matches that. Try another shelf or filter.</p>
        </div>
      ) : (
        sections.map((s) => (
          <section key={s.id} className="shelf-section" aria-labelledby={`shelf-${s.id}`}>
            <div className="shelf-section-head">
              <h3 id={`shelf-${s.id}`}>{s.title}</h3>
              <p className="muted shelf-blurb">{s.blurb}</p>
            </div>
            <div className="tile-grid">
              {s.games.map((g) => (
                <GameTile key={g.id} g={g} dim={!fitsRoom(g, online)} onOpen={() => setOpen(g.id)} />
              ))}
            </div>
          </section>
        ))
      )}
      <Sheet open={!!game} onClose={() => setOpen(null)} labelledBy="game-sheet-h" className={game ? `seg-${game.id}` : ""}>
        {game && (
          <GameSheet
            key={game.id}
            g={game}
            online={online}
            isHost={isHost}
            send={send}
            teamsFirst={teams && game.teams}
            rankedReady={state.ranked.ready}
          />
        )}
      </Sheet>
    </section>
  );
}

/** One game, opened from its tile: the shared game info, and for the host its options and Start. */
function GameSheet({
  g,
  online,
  isHost,
  send,
  teamsFirst,
  rankedReady,
}: {
  g: GameCard;
  online: number;
  isHost: boolean;
  send: Send;
  teamsFirst: boolean;
  rankedReady: boolean;
}) {
  return (
    <GameInfo g={g}>
      {isHost ? (
        <StartGame game={g} enough={fitsRoom(g, online)} online={online} send={send} prefix="sheet-" teamsFirst={teamsFirst} rankedReady={rankedReady} />
      ) : (
        <p className="muted center space-top">The host starts the game. The full rules show again before it begins.</p>
      )}
    </GameInfo>
  );
}

function Lobby({ state, isHost, send }: { state: RoomState; isHost: boolean; send: Send }) {
  const online = state.players.filter((p) => p.connected).length;
  return (
    <div className="lobby stack enter">
      <RoomSign state={state} />
      <LastStandings state={state} />
      <BattleBanner state={state} />
      <div className="lobby-layout">
        <div className="lobby-side stack">
          <Contestants
            players={state.players}
            you={state.you}
            title={`In the room (${online} online)`}
            onKick={isHost ? (id) => send({ t: "kick", target: id }) : undefined}
          />
          <AvatarPicker you={state.you} name={state.players.find((p) => p.id === state.you)?.name ?? "?"} send={send} />
          <Night state={state} send={send} isHost={isHost} />
          {isHost && (
            <Fold icon="📺" title="Plan a show night" hint="2-6 games on one scoreboard, a finale and a highlight reel">
              <ShowBuilder state={state} send={send} />
            </Fold>
          )}
          {isHost && (
            <Fold icon="🛠️" title="Host tools" hint="Show title, lock the room, show pack, audience">
              <HostTools state={state} send={send} />
            </Fold>
          )}
        </div>
        <GameShelf state={state} online={online} isHost={isHost} send={send} />
      </div>
    </div>
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
