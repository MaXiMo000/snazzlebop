import { useEffect, useId, useState, type FormEvent } from "react";
import { fetchGames } from "../lib/api";
import { DUEL_GAMES, DUEL_PRIZE, FINISH_PRIZE, GROUP_PRIZE, startBattle } from "../lib/battles";
import { heldBack } from "../lib/fairplay";
import type { ClubDetail } from "../lib/contract";
import type { GameCard, RoomState } from "../types";
import { Alert, errText } from "./auth";
import { Select } from "./Select";
import { Btn, Card } from "./ui";

type Go = (path: string) => void;
type Kind = "duel" | "group";

/** Club page: challenge a member to a duel, or open a group battle. Free to enter; the platform pays. */
export function ClubBattles({ c, me, go }: { c: ClubDetail; me: string; go: Go }) {
  const id = useId();
  const [kind, setKind] = useState<Kind>("duel");
  const [games, setGames] = useState<GameCard[]>([]);
  const [opponent, setOpponent] = useState("");
  const [game, setGame] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => void fetchGames().then(setGames, () => undefined), []);

  const allowed = (g: GameCard) => !c.rules.games.length || c.rules.games.includes(g.id);
  const duelOrder = DUEL_GAMES as readonly string[];
  const duelGames = games.filter((g) => duelOrder.includes(g.id) && allowed(g)).sort((a, b) => duelOrder.indexOf(a.id) - duelOrder.indexOf(b.id));
  const groupGames = games.filter((g) => g.max_players >= 3 && allowed(g)).sort((a, b) => a.title.localeCompare(b.title));
  const choices = kind === "duel" ? duelGames : groupGames;
  const others = c.members.filter((m) => m.username !== me);
  const pickedGame = choices.some((g) => g.id === game) ? game : (choices[0]?.id ?? "");
  const pickedRival = others.some((m) => m.username === opponent) ? opponent : (others[0]?.username ?? "");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const code = await startBattle(c.slug, {
        name: me.slice(0, 20),
        kind,
        game: pickedGame,
        ...(kind === "duel" ? { opponent: pickedRival } : {}),
      });
      go(`/r/${code}`);
    } catch (err) {
      setError(errText(err));
      setBusy(false);
    }
  };

  return (
    <Card aria-labelledby={`${id}-h`}>
      <h3 id={`${id}-h`}>
        <span aria-hidden="true">⚔️ </span>Battles
      </h3>
      <p className="muted">
        Free to enter: nobody bets anything. The winner gets {kind === "duel" ? DUEL_PRIZE : GROUP_PRIZE} coins from us, and everyone who
        finishes gets {FINISH_PRIZE}.
      </p>
      <div className="auth-tabs board-period space-top" role="group" aria-label="Kind of battle">
        {(["duel", "group"] as Kind[]).map((k) => (
          <button key={k} type="button" className={`auth-tab ${kind === k ? "on" : ""}`} aria-pressed={kind === k} onClick={() => setKind(k)}>
            {k === "duel" ? "Duel" : "Group battle"}
          </button>
        ))}
      </div>
      <form className="stack-sm space-top" onSubmit={(e) => void submit(e)}>
        {kind === "duel" && (
          <div>
            <label className="field" htmlFor={`${id}-who`}>
              Challenge
            </label>
            {others.length ? (
              <Select id={`${id}-who`} value={pickedRival} onChange={(e) => setOpponent(e.target.value)}>
                {others.map((m) => (
                  <option key={m.username} value={m.username}>
                    {m.username}
                  </option>
                ))}
              </Select>
            ) : (
              <p className="muted">Invite someone to the club first.</p>
            )}
          </div>
        )}
        <div>
          <label className="field" htmlFor={`${id}-game`}>
            Game
          </label>
          <Select id={`${id}-game`} value={pickedGame} onChange={(e) => setGame(e.target.value)}>
            {choices.map((g) => (
              <option key={g.id} value={g.id}>
                {g.title}
              </option>
            ))}
          </Select>
        </div>
        <p className="muted acct-hint">
          {kind === "duel"
            ? "They get a notification with a link to your room. The duel starts when you're both there."
            : "Your room shows on this page with a Battle badge. Start when three or more are in, each signed in."}
        </p>
        <Alert text={error} />
        <Btn type="submit" variant="gold" disabled={busy || !pickedGame || (kind === "duel" && !pickedRival)}>
          {kind === "duel" ? "Send the challenge" : "Open a battle room"}
        </Btn>
      </form>
      <a
        className="club-mod-link space-top"
        href="/battles"
        onClick={(e) => {
          e.preventDefault();
          go("/battles");
        }}
      >
        <span aria-hidden="true">🏆</span>
        <span>
          <b>Your battle record</b>
          <span className="muted"> · trophies and head-to-heads</span>
        </span>
      </a>
    </Card>
  );
}

/** Room lobby: this room's first game is a battle. */
export function BattleBanner({ state }: { state: RoomState }) {
  const b = state.battle;
  if (!b.game) return null;
  const title = state.games.find((g) => g.id === b.game)?.title ?? b.game;
  return (
    <Card tone="soft" className="battle-banner" aria-labelledby="battle-banner-h">
      <h3 id="battle-banner-h">
        <span aria-hidden="true">⚔️ </span>
        {b.kind === "duel" ? "A duel" : "A group battle"}: {title}
      </h3>
      <p>
        {b.kind === "duel"
          ? `Starts when both players are here (and only them). The winner gets ${DUEL_PRIZE} coins, the other ${FINISH_PRIZE}.`
          : `Starts with three or more players, each signed in. First place gets ${GROUP_PRIZE} coins, everyone who finishes ${FINISH_PRIZE}.`}
      </p>
    </Card>
  );
}

/** Results: the battle's prizes. */
export function BattleNews({ state }: { state: RoomState }) {
  const news = Object.entries(state.battle.news);
  if (!news.length) return null;
  news.sort((a, b) => a[1].place - b[1].place);
  const name = (pid: string) => state.players.find((p) => p.id === pid)?.name ?? "?";
  const mine = state.battle.news[state.you];
  return (
    <Card tone="soft" aria-labelledby="battle-news-h">
      <h3 id="battle-news-h">
        <span aria-hidden="true">⚔️ </span>Battle prizes
      </h3>
      {mine && (
        <p className="lead coin-mine">
          {mine.place === 1 ? "You won the battle" : "You finished the battle"}: <b>+{mine.prize}</b>
          {mine.note && <span className="muted"> ({heldBack(mine.note)})</span>}
        </p>
      )}
      <ul className="evidence">
        {news.map(([pid, n]) => (
          <li key={pid}>
            <b>{name(pid)}</b> {n.place === 1 ? "🏆 " : ""}+{n.prize}
            {n.note ? <span className="muted"> · {heldBack(n.note)}</span> : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}
