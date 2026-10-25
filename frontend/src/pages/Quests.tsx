import { useEffect, useState } from "react";
import { Alert, errText } from "../components/auth";
import { Btn, Card } from "../components/ui";
import { refreshAccount, useAccount } from "../lib/account";
import type { Progress } from "../lib/contract";
import { claimQuest, myProgress } from "../lib/quests";
import { sfx } from "../lib/sfx";

type Go = (path: string) => void;

/** /quests: your level and today's three quests (one always means playing with someone new). */
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

  const claim = async (id: string, title: string) => {
    setBusy(id);
    setNote(null);
    try {
      const before = data?.level ?? 1;
      const next = await claimQuest(id);
      setData(next);
      sfx.ding();
      await refreshAccount(); // coins (and any level-up gift) on the account
      const up = next.level > before ? ` Level ${next.level}: a power-up and coins are yours.` : "";
      setNote({ ok: true, text: `“${title}” done: +${next.reward.xp} XP and ${next.reward.coins} coins.${up}` });
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    } finally {
      setBusy("");
    }
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
          </>
        )}
      </Card>
      {note && <Alert text={note.text} calm={note.ok} />}

      <Card aria-labelledby="quests-h">
        <h2 id="quests-h">Today's quests</h2>
        {data === null ? (
          <p className="muted">Loading…</p>
        ) : (
          <ul className="quest-list">
            {data.quests.map((q) => {
              const done = q.progress >= q.target;
              return (
                <li key={q.id} className={`quest ${q.claimed ? "claimed" : done ? "done" : ""}`}>
                  <span className="quest-icon" aria-hidden="true">
                    {q.social ? "🤝" : "🎯"}
                  </span>
                  <span className="quest-text">
                    <b>{q.title}</b>
                    <span className="muted coin-detail">
                      <span>
                        {q.progress} of {q.target}
                      </span>
                      <span className="no-break">
                        +{data.reward.xp} XP · 🪙 {data.reward.coins}
                      </span>
                    </span>
                    <progress className="coin-meter" max={q.target} value={q.progress} aria-label={`${q.progress} of ${q.target}`} />
                  </span>
                  {q.claimed ? (
                    <span className="chip teal">Claimed</span>
                  ) : (
                    <Btn size="small" variant={done ? "go" : "ghost"} disabled={!done || busy === q.id} onClick={() => void claim(q.id, q.title)}>
                      Claim<span className="sr-only"> {q.title}</span>
                    </Btn>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <p className="muted space-top">New quests every day at midnight (UTC).</p>
      </Card>

      <Card aria-labelledby="xp-h">
        <h2 id="xp-h">How XP works</h2>
        <ul className="evidence">
          <li>Finish a game with other signed-in players: 10 XP, 15 for a win, and 25 more for your first win of the day.</li>
          <li>
            Up to {data?.daily_cap ?? 400} XP a day from games{data ? ` (${data.today_xp} so far today)` : ""}. Quests add {data?.reward.xp ?? 50} each on
            top.
          </li>
          <li>Every level pays 30 coins and a power-up for one of the games.</li>
          <li>Only fair games count: not ones that end in seconds, the same group over and over, or accounts on one device.</li>
        </ul>
      </Card>
    </div>
  );
}
