import { useEffect, useState } from "react";
import { Alert, errText } from "../components/auth";
import { Btn, Card } from "../components/ui";
import { refreshAccount, useAccount } from "../lib/account";
import type { Progress } from "../lib/contract";
import { claimQuest, claimSeason, claimWeekly, myProgress, rerollQuest } from "../lib/quests";
import { sfx } from "../lib/sfx";
import { Fold } from "../components/sheet";

type Go = (path: string) => void;
type Quest = Progress["quests"][number];

const KIND: Record<string, [string, string]> = {
  social: ["🤝", "Social"],
  games: ["🎲", "Games"],
  skill: ["🏆", "Skill"],
  club: ["🏠", "Club"],
  fun: ["🎉", "Fun"],
};
const longDay = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "long", timeZone: "UTC" });
const day = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { weekday: "long", timeZone: "UTC" });

/** /quests: your level, today's three quests (one always social), your streak and this week's challenges. */
export function Quests({ go }: { go: Go }) {
  const { user, loaded } = useAccount();
  const [data, setData] = useState<Progress | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    document.title = "Quests · Snazzlebop";
    if (user) myProgress().then(setData, (e) => setNote({ ok: false, text: errText(e) }));
  }, [user]);

  if (!loaded) return <p className="muted center">Loading…</p>;
  if (!user)
    return (
      <Card tone="stage" className="center">
        <p className="sign">Quests</p>
        <p className="space-top">Sign in to level up, get three new quests every day and win power-ups.</p>
        <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
          Sign in
        </Btn>
      </Card>
    );

  const act = async (key: string, fn: () => Promise<Progress>, done: (before: Progress | null, next: Progress) => string) => {
    setBusy(key);
    setNote(null);
    try {
      const before = data;
      const next = await fn();
      setData(next);
      sfx.ding();
      await refreshAccount(); // coins (and any gift) on the account
      setNote({ ok: true, text: done(before, next) });
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    } finally {
      setBusy("");
    }
  };
  const levelUp = (before: Progress | null, next: Progress) =>
    before && next.level > before.level ? ` Level ${next.level}: a power-up and coins are yours.` : "";
  const claim = (q: Quest) =>
    void act(q.id, () => claimQuest(q.id), (before, next) => {
      const streak = next.streak > (before?.streak ?? 0) && next.streak % next.streak_every === 0 ? ` A ${next.streak}-day streak: bonus coins and a confetti cannon!` : "";
      return `“${q.title}” done: +${next.reward.xp} XP and ${next.reward.coins} coins.${levelUp(before, next)}${streak}`;
    });
  const swap = (q: Quest) => void act(`swap-${q.id}`, () => rerollQuest(q.id), () => `Swapped “${q.title}” for another ${KIND[q.kind]?.[1].toLowerCase() ?? ""} quest.`);
  const claimWeek = (q: Quest) =>
    void act(q.id, () => claimWeekly(q.id), (before, next) => `“${q.title}” done: +${next.weekly.reward.xp} XP and ${next.weekly.reward.coins} coins.${levelUp(before, next)}`);

  const claimSeasonal = (q: Quest) =>
    void act(q.id, () => claimSeason(q.id), (before, next) => {
      const badge = next.season.badges.length > (before?.season.badges.length ?? 0) ? ` Every season challenge done: the Season ${next.season.season} badge is yours!` : "";
      return `“${q.title}” done: +${next.season.reward.xp} XP and ${next.season.reward.coins} coins.${levelUp(before, next)}${badge}`;
    });

  const row = (q: Quest, reward: { xp: number; coins: number }, onClaim: (q: Quest) => void, canSwap: boolean) => {
    const done = q.progress >= q.target;
    const [icon, kind] = KIND[q.kind] ?? ["🎯", q.kind];
    return (
      <li key={q.id} className={`quest ${q.claimed ? "claimed" : done ? "done" : ""}`}>
        <span className="quest-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="quest-text">
          <b>{q.title}</b>
          <span className="muted coin-detail">
            <span>{kind}</span>
            <span>
              {q.progress} of {q.target}
            </span>
            <span className="no-break">
              +{reward.xp} XP · 🪙 {reward.coins}
            </span>
          </span>
          <progress className="coin-meter" max={q.target} value={q.progress} aria-label={`${q.progress} of ${q.target}`} />
        </span>
        <span className="quest-actions">
          {q.claimed ? (
            <span className="chip teal">Claimed</span>
          ) : (
            <Btn size="small" variant={done ? "go" : "ghost"} disabled={!done || busy === q.id} onClick={() => onClaim(q)}>
              Claim<span className="sr-only"> {q.title}</span>
            </Btn>
          )}
          {canSwap && !q.claimed && !done && (
            <Btn size="small" variant="ghost" disabled={busy === `swap-${q.id}`} onClick={() => swap(q)}>
              Swap<span className="sr-only"> {q.title}</span>
            </Btn>
          )}
        </span>
      </li>
    );
  };

  const span = data ? Math.max(1, data.next_xp - data.level_xp) : 1;
  const into = data ? data.xp - data.level_xp : 0;
  return (
    <div className="stack enter quests-page">
      <Card tone="stage" className="center">
        <p className="sign">Your level</p>
        <p className="level-big space-top" aria-label={data ? `Level ${data.level}` : "Level"}>
          {data?.level ?? "…"}
        </p>
        {data && (
          <>
            <progress className="coin-meter level-meter" max={span} value={into} aria-label={`${into} of ${span} XP to level ${data.level + 1}`} />
            <p className="space-top">
              <b>{data.next_xp - data.xp} XP</b> to level {data.level + 1}
            </p>
            <p className="streak space-top">
              <span aria-hidden="true">🔥 </span>
              {data.streak ? (
                <>
                  <b>{data.streak}-day streak.</b>{" "}
                  <span className="no-break">
                    Bonus in {data.streak_every - (data.streak % data.streak_every)} {data.streak_every - (data.streak % data.streak_every) === 1 ? "day" : "days"}.
                  </span>
                </>
              ) : (
                <>Finish all three quests today to start a streak.</>
              )}
            </p>
          </>
        )}
      </Card>
      {note && <Alert text={note.text} calm={note.ok} />}

      <Card aria-labelledby="quests-h">
        <h2 id="quests-h">Today's quests</h2>
        {data === null ? <p className="muted">Loading…</p> : <ul className="quest-list">{data.quests.map((q) => row(q, data.reward, claim, data.reroll_left))}</ul>}
        <p className="muted space-top">
          New quests every day at midnight (UTC), never the same one twice in a week. {data?.reroll_left ? "You can swap one today." : "You've swapped one today."}
        </p>
      </Card>

      {data && (
        <Card aria-labelledby="weekly-h">
          <h2 id="weekly-h">This week's challenges</h2>
          <p className="muted">Bigger goals, until the end of {day(data.weekly.ends)}.</p>
          <ul className="quest-list">{data.weekly.challenges.map((q) => row(q, data.weekly.reward, claimWeek, false))}</ul>
        </Card>
      )}

      {data && (
        <Card aria-labelledby="season-h">
          <h2 id="season-h">Season {data.season.season} challenges</h2>
          <p className="muted">
            Five long goals for this ratings season, until {longDay(data.season.ends)}. Finish all five for the season's badge.
          </p>
          {data.season.badges.length > 0 && (
            <p className="season-badges space-top" aria-label="Your season badges">
              {data.season.badges.map((n) => (
                <span key={n} className="chip">
                  🏅 Season {n}
                </span>
              ))}
            </p>
          )}
          <ul className="quest-list">{data.season.challenges.map((q) => row(q, data.season.reward, claimSeasonal, false))}</ul>
        </Card>
      )}

      <Fold icon="💡" title="How XP works" hint="The rules, in short">
        <ul className="evidence">
          <li>Finish a game with other signed-in players: 10 XP, 15 for a win, and 25 more for your first win of the day.</li>
          <li>
            Up to {data?.daily_cap ?? 400} XP a day from games{data ? ` (${data.today_xp} so far today)` : ""}. Quests and challenges add XP on top.
          </li>
          <li>Every level pays 30 coins and a power-up. Every 7 days in a row with all three quests done pays 100 coins and a confetti cannon.</li>
          <li>Only fair games count: not ones that end in seconds, the same group over and over, or accounts on one device.</li>
        </ul>
      </Fold>
    </div>
  );
}
