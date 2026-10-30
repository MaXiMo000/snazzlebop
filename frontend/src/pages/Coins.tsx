import { useEffect, useState } from "react";
import { Alert, errText } from "../components/auth";
import { Btn, Card, Loading } from "../components/ui";
import { fetchGames } from "../lib/api";
import { myCoins, shopItems, useAccount } from "../lib/account";
import type { CoinHistory } from "../lib/contract";
import { Fold } from "../components/sheet";

type Go = (path: string) => void;
const ORDINAL = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"];
// Rewards that aren't from one game: [icon, what, detail]
const REWARDS: Record<string, [string, string, string]> = {
  quest: ["🎯", "Daily quest", "Quests"],
  weekly: ["🗓️", "Weekly challenge", "Quests"],
  streak: ["🔥", "Quest streak bonus", "Quests"],
  level: ["⭐", "Level up", "Levels"],
  battle: ["⚔️", "Battle prize", "Battles"],
  club_challenge: ["🏠", "Club challenge", "Clubs"],
  season_ch: ["🏅", "Season challenge", "Quests"],
};
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/** /coins: your balance, today's earnings against the daily limit, and every change, newest first. */
export function Coins({ go }: { go: Go }) {
  const { user, loaded } = useAccount();
  const [data, setData] = useState<CoinHistory | null>(null);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [items, setItems] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Your coins · Snazzlebop";
    if (!user) return;
    myCoins().then(setData, (e) => setError(errText(e)));
    fetchGames().then((g) => setTitles(Object.fromEntries(g.map((x) => [x.id, x.title]))), () => undefined);
    shopItems().then((r) => setItems(Object.fromEntries(r.items.map((i) => [i.id, i.name]))), () => undefined);
  }, [user, user?.coins]);

  if (!loaded) return <Loading page />;
  if (!user)
    return (
      <Card tone="stage" className="center">
        <p className="sign">Your coins</p>
        <p className="space-top">Sign in to earn coins for every game you finish and spend them in the power-up shop.</p>
        <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
          Sign in
        </Btn>
      </Card>
    );

  // [icon, what, a detail for the second line]
  const describe = (e: CoinHistory["entries"][number]): [string, string, string] => {
    if (e.reason === "place") return ["🏁", titles[e.game ?? ""] ?? "A game", `Finished ${ORDINAL[e.place ?? 0] ?? `#${e.place}`}`];
    if (e.reason === "shop") return ["🛒", `Bought ${items[e.ref ?? ""] ?? "a power-up"}`, "Power-up shop"];
    if (e.reason === "season") return ["🏆", `Season ${e.season} reward`, titles[e.ref ?? ""] ?? "Ranked"];
    if (e.reason === "opening") return ["📒", "Starting balance", "Before coin history began"];
    return REWARDS[e.reason] ?? ["🪙", "Coins", ""];
  };
  const left = data ? Math.max(0, data.daily_cap - data.earned_today) : 0;
  return (
    <div className="stack enter coins-page">
      <Card tone="stage" className="center">
        <p className="sign">Your coins</p>
        <p className="acct-coins space-top" aria-label={`${data?.balance ?? user.coins} coins`}>
          <span aria-hidden="true">🪙</span> {data?.balance ?? user.coins}
        </p>
        <div className="row center space-top">
          <Btn variant="gold" onClick={() => go("/account")}>
            Power-up shop
          </Btn>
          <Btn variant="ghost" onClick={() => go("/")}>
            Play a game
          </Btn>
        </div>
      </Card>
      <Alert text={error} />

      {data && (
        <Card aria-labelledby="coins-today-h">
          <h2 id="coins-today-h">Today</h2>
          <p className="space-top">
            <b>{data.earned_today}</b> of {data.daily_cap} coins earned by playing in the last 24 hours.{" "}
            {left > 0 ? <span className="no-break">{left} still to win.</span> : <span className="no-break">That's the limit for now.</span>}
          </p>
          <progress className="coin-meter space-top" max={data.daily_cap} value={data.earned_today} aria-label="Coins earned in the last 24 hours" />
        </Card>
      )}

      <Card aria-labelledby="coins-history-h">
        <h2 id="coins-history-h">History</h2>
        {data === null ? (
          <Loading />
        ) : data.entries.length ? (
          <ul className="club-rooms coin-history">
            {data.entries.map((e, i) => {
              const [icon, text, detail] = describe(e);
              return (
                <li key={i}>
                  <span className="club-room-text">
                    <b>
                      <span aria-hidden="true">{icon} </span>
                      {text}
                    </b>
                    <span className="muted coin-detail">
                      <span>{detail}</span>
                      <span className="no-break">{when(e.at)}</span>
                    </span>
                  </span>
                  <span className={`chip ${e.delta >= 0 ? "teal" : "cherry"}`}>{e.delta >= 0 ? `+${e.delta}` : `−${-e.delta}`}</span>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="empty-state">
            <span aria-hidden="true">🪙</span>
            <p>
              <b>No coins yet.</b> Finish a game with at least one other player to earn your first.
            </p>
          </div>
        )}
      </Card>

      <Fold icon="💡" title="How coins work" hint="The rules, in short">
        <ul className="evidence">
          <li>Finish a game with at least one other player: 1st 50, 2nd 30, 3rd 20, 4th 10, everyone else 5.</li>
          <li>Ties share the better place. Up to {data?.daily_cap ?? 600} coins a day from playing.</li>
          <li>Ranked ratings pay a reward when a season ends, from 20 coins for Bronze to 200 for Diamond.</li>
          <li>Your season points are the coins you earn this month. The table starts fresh every month.</li>
          <li>
            To keep it fair, a game pays nothing if it ends within 45 seconds, the same group of people stops earning after 5 games together in
            a day, and accounts on the same device never earn from each other.
          </li>
          <li>Place coins need another signed-in player in the game. Playing only with guests pays 5 coins for finishing.</li>
          <li>Coins can't be sold, traded or bet, and only come from playing (Plus adds a monthly bonus). Every change is recorded here.</li>
        </ul>
      </Fold>
    </div>
  );
}
