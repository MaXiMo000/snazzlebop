import { useEffect, useState } from "react";
import { Alert, errText } from "../components/auth";
import { Btn, Card } from "../components/ui";
import { useAccount } from "../lib/account";
import { myBattles, type BattleRecord } from "../lib/battles";

type Go = (path: string) => void;
const ORDINAL = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"];
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });

/** /battles: your trophies, head-to-head records, recent battles and challenges waiting for you. */
export function Battles({ go }: { go: Go }) {
  const { user, loaded } = useAccount();
  const [data, setData] = useState<BattleRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Battles · Snazzlebop";
    if (user) myBattles().then(setData, (e) => setError(errText(e)));
  }, [user]);

  if (!loaded) return <p className="muted center">Loading…</p>;
  if (!user)
    return (
      <Card tone="stage" className="center">
        <p className="sign">Battles</p>
        <p className="space-top">Sign in to challenge your clubmates, win trophies and keep a head-to-head record.</p>
        <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
          Sign in
        </Btn>
      </Card>
    );

  return (
    <div className="stack enter battles-page">
      <Card tone="stage" className="center">
        <p className="sign">Battles</p>
        <h1 className="space-top prose-title">Your record</h1>
        {data && (
          <p className="battle-stats space-top">
            <span>
              <b>{data.trophies}</b> {data.trophies === 1 ? "trophy" : "trophies"}
            </span>
            <span>
              <b>{data.played}</b> played
            </span>
            <span>
              <b>🪙 {data.prizes}</b> won
            </span>
          </p>
        )}
      </Card>
      <Alert text={error} />
      {data && (
        <Card tone="soft" aria-labelledby="format-h">
          <h2 id="format-h">
            <span aria-hidden="true">🔥 </span>
            {data.format.title}
          </h2>
          <p>
            This week's featured battles: {data.format.features.toLowerCase()}. Their winners get {Math.round((data.format.bonus - 1) * 100)}% more coins. A new format
            every Monday.
          </p>
        </Card>
      )}

      {data && data.challenges.length > 0 && (
        <Card aria-labelledby="challenges-h">
          <h2 id="challenges-h">Challenges for you</h2>
          <ul className="club-rooms">
            {data.challenges.map((c) => (
              <li key={c.room}>
                <span className="club-room-text">
                  <b>
                    {c.by} · {c.title}
                  </b>
                  <span className="muted">{c.open ? `Waiting in room ${c.room}` : "The room has closed"}</span>
                </span>
                {c.open && (
                  <Btn size="small" variant="go" onClick={() => go(`/r/${c.room}`)}>
                    Join<span className="sr-only"> {c.by}'s duel</span>
                  </Btn>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card aria-labelledby="h2h-h">
        <h2 id="h2h-h">Head to head</h2>
        {data === null ? (
          <p className="muted">Loading…</p>
        ) : data.head_to_head.length ? (
          <ul className="score-rows">
            {data.head_to_head.map((r) => (
              <li key={r.username}>
                <b>{r.username}</b>
                <span className="score-tally">
                  <span>
                    {r.won}–{r.lost}
                    {r.drawn ? `–${r.drawn}` : ""}
                  </span>
                  <span className="score-pts">{r.won > r.lost ? "ahead" : r.won < r.lost ? "behind" : "level"}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No duels yet. Challenge a clubmate from your club's page.</p>
        )}
      </Card>

      <Card aria-labelledby="recent-h">
        <h2 id="recent-h">Recent battles</h2>
        {data && data.recent.length ? (
          <ul className="club-rooms coin-history">
            {data.recent.map((r, i) => (
              <li key={i}>
                <span className="club-room-text">
                  <b>
                    {r.place === 1 ? "🏆 " : ""}
                    {r.title}
                  </b>
                  <span className="muted coin-detail">
                    <span>
                      {r.kind === "duel" ? `vs ${r.against[0] ?? "?"}` : `${ORDINAL[r.place] ?? `#${r.place}`} of ${r.players}`}
                    </span>
                    <span className="no-break">{day(r.at)}</span>
                  </span>
                </span>
                <span className={`chip ${r.prize ? "teal" : "paper"}`}>+{r.prize}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">Your battles show up here once you've played one.</p>
        )}
      </Card>

      <Card aria-labelledby="battle-how-h">
        <h2 id="battle-how-h">How battles work</h2>
        <ul className="evidence">
          <li>Challenge a clubmate to a duel, or open a group battle for three to eight. Nobody puts anything in.</li>
          <li>The platform pays the prizes: 40 coins for winning a duel, 60 for first in a group, 10 for everyone who finishes. The week's featured format pays its winners more.</li>
          <li>
            Up to 10 battle prizes a day. The same group of people gets paid for three battles a day, and accounts on the same device never do.
          </li>
          <li>Prizes start once an account is 3 days old with a confirmed email (or Google). A battle that ends within 45 seconds pays nothing.</li>
          <li>Tick Ranked game before starting and the battle counts for your rating too.</li>
        </ul>
      </Card>
    </div>
  );
}
