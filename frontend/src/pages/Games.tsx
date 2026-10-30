import { useEffect, useState } from "react";
import { fetchGames, request } from "../lib/api";
import { Btn, Card, Loading } from "../components/ui";
import { GameTile, playersLabel } from "../components/gamecards";
import { SEGMENT_ICON } from "../components/show";
import type { GameCard } from "../types";

type Go = (path: string) => void;
type Category = { id: string; label: string; title: string; blurb: string };
// What each shelf is called in searches (the server's pages.GENRE says the same).
// Each shelf's page title, in the words people search with (pages.SHELF_NAME on the server).
const SHELF_NAME: Record<string, string> = {
  party: "Party Games",
  quiz: "Quiz and Word Games",
  bluff: "Bluffing and Social Deduction Games",
  nerve: "Game Show Games",
  classics: "Classic Board and Card Games",
};
const GENRE: Record<string, string> = {
  party: "Party Game",
  quiz: "Quiz and Word Game",
  bluff: "Bluffing Game",
  nerve: "Game Show Game",
  classics: "Classic Game",
};

function useCatalogue() {
  const [games, setGames] = useState<GameCard[] | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [catsReady, setCatsReady] = useState(false);
  useEffect(() => {
    void fetchGames().then(setGames, () => setGames([]));
    void request<Category[]>("/api/categories")
      .then(setCats, () => undefined)
      .finally(() => setCatsReady(true));
  }, []);
  return { games, cats, catsReady };
}

/** Every game by shelf, each with its own page of rules. */
export function GamesIndex({ go }: { go: Go }) {
  const { games, cats } = useCatalogue();
  useEffect(() => {
    document.title = games ? `All ${games.length} Free Party Games Online · Snazzlebop` : "All games · Snazzlebop";
  }, [games]);
  if (games === null) return <Loading page />;
  return (
    <div className="stack enter">
      <Card tone="stage" className="center">
        <p className="sign">The games</p>
        <h1 className="space-top prose-title">All {games.length} games</h1>
        <p className="space-top">Party games, quizzes, bluffing, nerve and the classics. Tap one for its rules.</p>
      </Card>
      {cats.map((c) => {
        const rows = games.filter((g) => g.category === c.id);
        if (!rows.length) return null;
        return (
          <section key={c.id} className="shelf-section" aria-labelledby={`games-${c.id}`}>
            <h2 id={`games-${c.id}`}>
              <a
                href={`/games/${c.id}`}
                onClick={(e) => {
                  e.preventDefault();
                  go(`/games/${c.id}`);
                }}
              >
                {c.title}
              </a>
            </h2>
            <p className="muted shelf-blurb">{c.blurb}</p>
            <div className="tile-grid">
              {rows.map((g) => (
                <GameTile key={g.id} g={g} onOpen={() => go(`/games/${g.id}`)} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/** One shelf (party, quiz, bluff, nerve, classics): its games, at /games/<shelf>. */
function ShelfPage({ cat, games, go }: { cat: Category; games: GameCard[]; go: Go }) {
  const rows = games.filter((g) => g.category === cat.id);
  const name = SHELF_NAME[cat.id] ?? cat.title;
  useEffect(() => {
    document.title = `Free ${name} to Play Online With Friends · Snazzlebop`;
  }, [name]);
  return (
    <div className="stack enter">
      <Card tone="stage" className="center">
        <p className="sign">The games</p>
        <h1 className="space-top prose-title">{name} to play with friends</h1>
        <p className="space-top">{cat.blurb}</p>
      </Card>
      <div className="tile-grid">
        {rows.map((g) => (
          <GameTile key={g.id} g={g} onOpen={() => go(`/games/${g.id}`)} />
        ))}
      </div>
      <div className="row center">
        <Btn variant="gold" onClick={() => go("/")}>
          Host a room
        </Btn>
        <Btn variant="ghost" onClick={() => go("/games")}>
          All games
        </Btn>
      </div>
    </div>
  );
}

/** One game: what it is, who it's for, and how it's played (or one shelf, when the id names one). */
export function GamePage({ id, go }: { id: string; go: Go }) {
  const { games, cats, catsReady } = useCatalogue();
  const g = games?.find((x) => x.id === id);
  const shelf = cats.find((c) => c.id === id);
  useEffect(() => {
    if (g) document.title = `${g.title}: Free Online ${GENRE[g.category] ?? "Party Game"} for Friends · Snazzlebop`;
  }, [g]);
  if (games === null || (!g && !catsReady)) return <Loading page />;
  if (shelf) return <ShelfPage cat={shelf} games={games} go={go} />;
  if (!g)
    return (
      <Card className="center">
        <h1 className="prose-title">That game isn't in the show</h1>
        <Btn className="space-top" variant="gold" onClick={() => go("/games")}>
          See all games
        </Btn>
      </Card>
    );
  return (
    <div className={`stack enter seg-${g.id}`}>
      <Card tone="accent" className="center">
        <p className="game-page-icon" aria-hidden="true">
          {SEGMENT_ICON[g.id] ?? "🎲"}
        </p>
        <h1 className="prose-title">{g.title}</h1>
        <p className="space-top">{g.blurb}</p>
        <p className="space-top">
          <span className="chip plum">{playersLabel(g)} players</span>
        </p>
      </Card>
      <Card aria-labelledby="game-how-h">
        <h2 id="game-how-h">How to play</h2>
        <ol className="how-steps">
          {g.how_to.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </Card>
      <Card className="center">
        <p>Free in the browser: one person hosts on a laptop or TV, everyone else joins from their phone.</p>
        <div className="row center space-top">
          <Btn variant="gold" onClick={() => go("/")}>
            Host a room and play it
          </Btn>
          <Btn variant="ghost" onClick={() => go("/games")}>
            All games
          </Btn>
        </div>
      </Card>
    </div>
  );
}
