import { useEffect, useRef, useState } from "react";
import { ApiError, createRoom, fetchGames, joinRoom, request } from "../lib/api";
import { Btn, Card } from "../components/ui";
import { useAccount } from "../lib/account";
import { Friends, InstallApp } from "../components/friends";
import { HappeningNow } from "../components/happening";
import { YourCorner } from "../components/nav";
import { GameInfo, GameTile } from "../components/gamecards";
import { Sheet } from "../components/sheet";
import { Mascot } from "../components/mascot";
import { AdSlot } from "../components/ad";
import type { GameCard } from "../types";

type Category = { id: string; label: string; title: string; blurb: string };

const STEPS: [string, string, string][] = [
  ["🎤", "One of you hosts", "You get a five-letter room code."],
  ["📱", "Everyone joins on their phone", "With the code or the invite link. No app, no sign-up."],
  ["📺", "Put it on the big screen", "Optional: TV mode on a laptop or smart TV, so the room watches together."],
  ["🎲", "Pick a game, or a whole show", "The rules show before every game. One game, or a night of them on one scoreboard."],
];

export function Home({ go }: { go: (path: string) => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [mode, setMode] = useState<"host" | "join">("host");
  const { user } = useAccount();
  const nameRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (user) setName((n) => n || user.username.slice(0, 16));
  }, [user]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Snazzlebop: Free Party Games to Play With Friends Online";
  }, []);

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const nameOk = name.trim().length >= 1;
  const host = () => {
    if (!nameOk) return;
    void wrap(async () => {
      const r = await createRoom(name.trim());
      go(`/r/${r.code}`);
    });
  };
  const join = () => {
    if (!nameOk || code.length < 3) return;
    void wrap(async () => {
      const c = code.toUpperCase();
      await joinRoom(c, name.trim());
      go(`/r/${c}`);
    });
  };
  const toPlay = () => {
    nameRef.current?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    nameRef.current?.focus({ preventScroll: true });
  };

  return (
    <div className="home stack enter">
      <div className="home-top">
      <section className="hero home-hero" aria-labelledby="show-title">
        <Mascot className="home-mascot" size={150} />
        <h1 id="show-title">Snazzlebop!</h1>
        <p className="tagline">The party game show where your friends are the contestants</p>
        <ul className="home-facts" aria-label="At a glance">
          <li>
            <span aria-hidden="true">🎲</span> 37 games
          </li>
          <li>
            <span aria-hidden="true">👥</span> Up to 8 + audience
          </li>
          <li>
            <span aria-hidden="true">✨</span> No sign-up
          </li>
        </ul>
      </section>

      <Card className="play-card" aria-labelledby="play-h">
        <h2 id="play-h" className="sr-only">
          Play now
        </h2>
        <label className="field" htmlFor="host-name">
          Your name
        </label>
        <input
          ref={nameRef}
          id="host-name"
          type="text"
          value={name}
          maxLength={16}
          autoComplete="nickname"
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            // Enter: join the room whose code is typed below, or start a new one.
            if (e.key !== "Enter" || busy) return;
            e.preventDefault();
            if (code.length >= 3) join();
            else host();
          }}
          placeholder="e.g. Sam"
          aria-describedby="name-hint"
        />
        <p id="name-hint" className="muted play-hint">
          {nameOk ? "That's what the show calls you." : "Needed to host or join."}
        </p>
        <div className="auth-tabs play-tabs" role="tablist" aria-label="Host or join">
          {(["host", "join"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              id={`tab-${m}`}
              aria-selected={mode === m}
              aria-controls={`panel-${m}`}
              className={`auth-tab ${mode === m ? "on" : ""}`}
              onClick={() => setMode(m)}
            >
              {m === "host" ? "🎤 Host" : "🎟️ Join"}
            </button>
          ))}
        </div>
        {mode === "host" ? (
          <form
            id="panel-host"
            role="tabpanel"
            aria-labelledby="tab-host"
            className="play-panel"
            onSubmit={(e) => {
              e.preventDefault();
              host();
            }}
          >
            <p className="muted">Start a room and get a five-letter code for your friends. They join on their phones.</p>
            <Btn type="submit" size="big" block disabled={busy || !nameOk}>
              Create room
            </Btn>
          </form>
        ) : (
          <form
            id="panel-join"
            role="tabpanel"
            aria-labelledby="tab-join"
            className="play-panel"
            onSubmit={(e) => {
              e.preventDefault();
              join();
            }}
          >
            <label className="field" htmlFor="join-code">
              Room code
            </label>
            <input
              id="join-code"
              className="code-input"
              type="text"
              value={code}
              maxLength={8}
              autoCapitalize="characters"
              autoComplete="off"
              spellCheck={false}
              aria-describedby="join-hint"
              onChange={(e) => setCode(e.target.value.replace(/[^a-zA-Z]/g, ""))}
              placeholder="ABCDE"
            />
            <Btn type="submit" variant="go" size="big" block disabled={busy || !nameOk || code.length < 3}>
              Join
            </Btn>
            <p id="join-hint" className="muted">
              The host sees the code on their screen. An invite link works too.
            </p>
          </form>
        )}
        {error && (
          <p className="alert space-top" role="alert">
            {error}
          </p>
        )}
      </Card>
      </div>

      {user && <HappeningNow name={name} go={go} />}
      <YourCorner go={go} />
      {user && <Friends name={name} go={go} />}

      <Gallery onPlay={toPlay} />

      <section className="how-band" aria-labelledby="how-h">
        <h2 id="how-h">How it works</h2>
        <ol className="how-cards">
          {STEPS.map(([icon, title, text], i) => (
            <li key={title}>
              <span className="how-card-n" aria-hidden="true">
                {i + 1}
              </span>
              <span className="how-card-icon" aria-hidden="true">
                {icon}
              </span>
              <b>{title}</b>
              <span className="muted">{text}</span>
            </li>
          ))}
        </ol>
      </section>

      <InstallApp />
      <AdSlot go={go} lazy />
    </div>
  );
}

/** Every game, by shelf: tap one for what it is and how it's played. */
function Gallery({ onPlay }: { onPlay: () => void }) {
  const [games, setGames] = useState<GameCard[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [pick, setPick] = useState("start");
  const [open, setOpen] = useState<GameCard | null>(null);
  useEffect(() => {
    void fetchGames().then(setGames, () => undefined);
    void request<Category[]>("/api/categories").then(setCats, () => undefined);
  }, []);
  if (!games.length) return null;
  const shown =
    pick === "start"
      ? games.filter((g) => g.featured !== null).sort((a, b) => (a.featured ?? 0) - (b.featured ?? 0))
      : games.filter((g) => pick === "all" || g.category === pick);
  const chips: [string, string][] = [["start", "⭐ Start here"], ...cats.map((c): [string, string] => [c.id, c.label]), ["all", `All ${games.length}`]];
  const cat = cats.find((c) => c.id === pick);
  return (
    <section className="gallery" aria-labelledby="gallery-h">
      <div className="gallery-head">
        <h2 id="gallery-h">The games</h2>
        <p className="muted">{pick === "start" ? "Learned in a minute and great with people you just met." : (cat?.blurb ?? "Every game in the show.")}</p>
      </div>
      <div className="shelf-filters scroll-row" role="group" aria-label="Shelf">
        {chips.map(([id, label]) => (
          <button key={id} type="button" className="shelf-chip" aria-pressed={pick === id} onClick={() => setPick(id)}>
            {label}
          </button>
        ))}
      </div>
      <div className="tile-grid" key={pick}>
        {shown.map((g) => (
          <GameTile key={g.id} g={g} onOpen={() => setOpen(g)} />
        ))}
      </div>
      <Sheet open={!!open} onClose={() => setOpen(null)} labelledBy="game-sheet-h" className={open ? `seg-${open.id}` : ""}>
        {open && (
          <GameInfo g={open}>
            <Btn
              className="space-top"
              variant="accent"
              block
              onClick={() => {
                setOpen(null);
                window.setTimeout(onPlay, 50);
              }}
            >
              Host a room to play
            </Btn>
          </GameInfo>
        )}
      </Sheet>
    </section>
  );
}
