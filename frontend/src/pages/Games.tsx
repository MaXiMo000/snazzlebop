import { useEffect, useState } from "react";
import { fetchGames, request } from "../lib/api";
import { Btn, Card, Loading } from "../components/ui";
import { GameTile, playersLabel } from "../components/gamecards";
import { SEGMENT_ICON } from "../components/show";
import type { GameCard } from "../types";

type Go = (path: string) => void;
type Category = { id: string; label: string; title: string; blurb: string };

function useCatalogue() {
  const [games, setGames] = useState<GameCard[] | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  useEffect(() => {
    void fetchGames().then(setGames, () => setGames([]));
    void request<Category[]>("/api/categories").then(setCats, () => undefined);
  }, []);
  return { games, cats };
}

/** Every game by shelf, each with its own page of rules. */
export function GamesIndex({ go }: { go: Go }) {
  const { games, cats } = useCatalogue();
  useEffect(() => {
    document.title = "All games · Snazzlebop";
  }, []);
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
            <h2 id={`games-${c.id}`}>{c.title}</h2>
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

/** One game: what it is, who it's for, and how it's played. */
export function GamePage({ id, go }: { id: string; go: Go }) {
  const { games } = useCatalogue();
  const g = games?.find((x) => x.id === id);
  useEffect(() => {
    if (g) document.title = `${g.title}: how to play · Snazzlebop`;
  }, [g]);
  if (games === null) return <Loading page />;
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
