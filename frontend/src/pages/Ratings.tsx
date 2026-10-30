import { useEffect, useId, useState } from "react";
import { Alert, errText } from "../components/auth";
import { Select } from "../components/Select";
import { SEGMENT_ICON } from "../components/show";
import { Btn, Card, Loading } from "../components/ui";
import { refreshAccount, useAccount } from "../lib/account";
import { myClubs } from "../lib/clubs";
import type { ClubList, MyPlaces } from "../lib/contract";
import { myPlaces } from "../lib/places";
import { myRatings, ratingBoard, setPlaceBoards, type MyRatings, type Period, type RatingBoard, type Scope } from "../lib/ratings";
import type { GameCard } from "../types";
import { Fold } from "../components/sheet";

type Go = (path: string) => void;

export const TIER_ICON: Record<string, string> = { Bronze: "🥉", Silver: "🥈", Gold: "🥇", Platinum: "💠", Diamond: "💎", Provisional: "🧭" };
const day = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
const icon = (game: string) => SEGMENT_ICON[game as GameCard["id"]] ?? "🎲";

export function TierChip({ tier }: { tier: string }) {
  return (
    <span className="chip paper">
      <span aria-hidden="true">{TIER_ICON[tier] ?? "🏅"}</span> {tier === "Provisional" ? "Placement" : tier}
    </span>
  );
}

/** /ratings: your rating in each ranked game, and the leaderboards (everyone, a club, a place). */
export function Ratings({ go }: { go: Go }) {
  const { user, loaded } = useAccount();
  const [mine, setMine] = useState<MyRatings | null>(null);
  const [clubs, setClubs] = useState<ClubList["clubs"]>([]);
  const [places, setPlaces] = useState<MyPlaces["places"]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Ratings · Snazzlebop";
    if (!user) return;
    myRatings().then(
      (r) => {
        setMine(r);
        if (r.rewards.length) void refreshAccount(); // the top bar shows the new balance
      },
      (e) => setError(errText(e)),
    );
    myClubs().then((r) => setClubs(r.clubs), () => undefined);
    myPlaces().then((r) => setPlaces(r.places.filter((p) => p.status === "verified")), () => undefined);
  }, [user]);

  if (!loaded) return <Loading page />;
  if (!user)
    return (
      <Card tone="stage" className="center">
        <p className="sign">Ratings</p>
        <p className="space-top">Sign in to play ranked games, earn a rating in each one and climb your club's leaderboard.</p>
        <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
          Sign in
        </Btn>
      </Card>
    );

  const season = mine?.season;
  return (
    <div className="stack enter ratings-page">
      <Card tone="stage" className="center">
        <p className="sign">Ranked</p>
        <h1 className="space-top prose-title">Your ratings</h1>
        {season && (
          <p className="space-top">
            Season {season.number} <span className="no-break">· {day(season.starts)} to {day(season.ends)}</span>
          </p>
        )}
      </Card>
      <Alert text={error} />
      {mine && mine.rewards.length > 0 && (
        <Alert
          calm
          text={`Season rewards: ${mine.rewards
            .map((r) => `+${r.coins} coins for ${r.tier} in ${mine.games.find((g) => g.game === r.game)?.title ?? r.game}`)
            .join(", ")}. Every rating has come halfway back for the new season.`}
        />
      )}

      <Card aria-labelledby="my-ratings-h">
        <h2 id="my-ratings-h">Every ranked game</h2>
        {mine === null ? (
          <Loading />
        ) : (
          <ul className="rating-grid">
            {mine.games.map((g) => (
              <li key={g.game} className={`rating-tile seg-${g.game}`}>
                <span className="rating-game">
                  <span aria-hidden="true">{icon(g.game)} </span>
                  {g.title}
                </span>
                {g.placement_left > 0 ? (
                  <span className="rating-num muted">
                    {g.placement_left} placement {g.placement_left === 1 ? "game" : "games"} to go
                  </span>
                ) : (
                  <span className="rating-num">
                    <b>{g.rating}</b> <span className="muted">· {g.games} played</span>
                  </span>
                )}
                <TierChip tier={g.tier} />
              </li>
            ))}
          </ul>
        )}
      </Card>

      {mine && <Board games={mine.games} clubs={clubs} places={places} placeBoards={mine.place_boards} onPlaceBoards={(on) => setMine({ ...mine, place_boards: on })} />}

      <Fold icon="💡" title="How ranked works" hint="The rules, in short">
        <ul className="evidence">
          <li>The host ticks Ranked game before starting. Everyone has to be signed in, and the game uses its standard settings with no power-ups.</li>
          <li>Your rating moves by where you finish and who you beat: beating stronger players counts for more. Leaving early counts as last place.</li>
          <li>Your first five games in each one are placement games. After that you get a number and a tier, from Bronze to Diamond.</li>
          <li>Seasons last eight weeks. A new season brings every rating halfway back to the start, so everyone has something to climb, and pays a reward for the tier you ended on: 20 coins for Bronze up to 200 for Diamond.</li>
          <li>To keep it fair, the same two players only count five times a day, and a rating moves at most 150 points a day.</li>
        </ul>
      </Fold>
    </div>
  );
}

function Board({
  games,
  clubs,
  places,
  placeBoards,
  onPlaceBoards,
}: {
  games: MyRatings["games"];
  clubs: ClubList["clubs"];
  places: MyPlaces["places"];
  placeBoards: boolean;
  onPlaceBoards: (on: boolean) => void;
}) {
  const id = useId();
  // Open on the game you play most.
  const [game, setGame] = useState(() => [...games].sort((a, b) => b.games - a.games)[0]?.game ?? "");
  const [who, setWho] = useState("everyone:");
  const [period, setPeriod] = useState<Period>("season");
  const [board, setBoard] = useState<RatingBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scope, slug] = who.split(":") as [Scope, string];

  useEffect(() => {
    if (!game) return;
    setBoard(null);
    setError(null);
    ratingBoard(game, scope, slug, period).then(setBoard, (e) => setError(errText(e)));
  }, [game, scope, slug, period]);

  const place = places.find((p) => p.slug === slug);
  return (
    <Card aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`}>Leaderboard</h2>
      <div className="board-pickers">
        <div>
          <label className="field" htmlFor={`${id}-game`}>
            Game
          </label>
          <Select id={`${id}-game`} value={game} onChange={(e) => setGame(e.target.value)}>
            {games.map((g) => (
              <option key={g.game} value={g.game}>
                {g.title}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label className="field" htmlFor={`${id}-who`}>
            Who
          </label>
          <Select id={`${id}-who`} value={who} onChange={(e) => setWho(e.target.value)}>
            <option value="everyone:">Everyone</option>
            {clubs.map((c) => (
              <option key={c.slug} value={`club:${c.slug}`}>
                {c.name}
              </option>
            ))}
            {places.map((p) => (
              <option key={p.slug} value={`place:${p.slug}`}>
                {p.name}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <div className="auth-tabs board-period space-top" role="group" aria-label="Period">
        {(["season", "week"] as Period[]).map((p) => (
          <button key={p} type="button" className={`auth-tab ${period === p ? "on" : ""}`} aria-pressed={period === p} onClick={() => setPeriod(p)}>
            {p === "season" ? "This season" : "This week's climbers"}
          </button>
        ))}
      </div>
      <Alert text={error} />
      {board === null && !error ? (
        <Loading />
      ) : board && board.rows.length ? (
        <ol className="score-rows space-top">
          {board.rows.map((r, i) => (
            <li key={r.username} className={r.you ? "on" : ""}>
              <b>
                {i === 0 ? "👑 " : `${i + 1}. `}
                {r.username}
                {r.you ? " (you)" : ""}
              </b>
              <span className="score-tally">
                <span aria-label={r.tier}>{TIER_ICON[r.tier] ?? ""}</span>
                <span className="score-pts">{period === "week" && r.gain != null ? (r.gain > 0 ? `+${r.gain}` : `${r.gain}`) : r.rating}</span>
              </span>
            </li>
          ))}
        </ol>
      ) : board ? (
        <p className="muted space-top">
          {period === "week" ? "Nobody's played this one ranked this week yet." : "Nobody has finished their placement games in this one yet."} Be first!
        </p>
      ) : null}
      {places.length > 0 && (
        <div className="space-top">
          <label className="check">
            <input
              type="checkbox"
              checked={placeBoards}
              disabled={busy}
              onChange={(e) => {
                const on = e.target.checked;
                setBusy(true);
                setPlaceBoards(on)
                  .then(() => {
                    onPlaceBoards(on);
                    if (place) setWho(`place:${place.slug}`);
                    void ratingBoard(game, scope, slug, period).then(setBoard, () => undefined);
                  })
                  .catch((err: unknown) => setError(errText(err)))
                  .finally(() => setBusy(false));
              }}
            />
            <span>Show me on the leaderboards of places I'm verified at</span>
          </label>
        </div>
      )}
    </Card>
  );
}
