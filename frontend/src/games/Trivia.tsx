import { useEffect, useState } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useCountUp, useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { TriviaView } from "../types";

interface Props {
  view: TriviaView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const STYLE_LABEL: Record<TriviaView["style"], string> = {
  classic: "Classic: speed scores",
  fastest: "Fastest finger: first right takes 1,000",
  survival: "Survival: 3 lives",
  wager: "High stakes: bet on yourself",
  draft: "Category draft",
};
const LEVEL_LABEL = ["", "Easy", "Medium", "Hard"];
// Each choice has a shape as well as a colour, so nobody depends on telling colours apart.
const MARKS = ["▲", "◆", "●", "■"];
const fmt = (n: number) => n.toLocaleString("en-US");
/** "Tech & inventions": the "&" never starts a line. */
const glue = (label: string) => label.replace(/ &/g, "\u00a0&");
const signed = (n: number) => (n > 0 ? `+${fmt(n)}` : n < 0 ? `−${fmt(-n)}` : "0");

/** The share of the question clock left, 1 → 0, updated smoothly (for the bar under the question). */
function useClockShare(remaining: number | null, receivedAt: number, limit: number): number {
  const [now, setNow] = useState(performance.now());
  useEffect(() => {
    if (remaining == null) return;
    const id = window.setInterval(() => setNow(performance.now()), 100);
    return () => window.clearInterval(id);
  }, [remaining, receivedAt]);
  if (remaining == null || limit <= 0) return 0;
  return Math.max(0, Math.min(1, (remaining - (now - receivedAt) / 1000) / limit));
}

export function Trivia({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const me = tv ? null : view.you;
  const name = (pid: string) => (pid === you && !tv ? "You" : nameOf(view.players, pid));
  const r = view.result;

  useOnChange(view.phase, (_, phase) => {
    if (phase === "question") sfx.pop();
    else if (phase === "reveal" && r) {
      const mine = r.gains[you] ?? 0;
      const picked = r.picks[you];
      if (tv || !me || me.out) sfx.ding();
      else if (picked === r.right) {
        sfx.fanfare();
        show.stinger(r.first === you && view.style === "fastest" ? "FIRST!" : mine > 0 ? signed(mine) : "RIGHT!");
      } else {
        sfx.buzz();
        show.stinger(picked === undefined ? "TOO SLOW!" : "WRONG!", "bad");
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE QUIZ!");
      show.celebrate();
    }
  });
  useOnChange(view.answered.length, (was, now) => {
    if (now > was && tv) sfx.tick();
  });

  const counter = view.rounds ? `Question ${view.round} of ${view.rounds}` : `Question ${view.round}`;
  const sign =
    view.phase === "final"
      ? "Final scores"
      : `${counter} · ${{ pick: "Pick a category", wager: "Place your bet", question: "Answer now", reveal: "The answer" }[view.phase]}`;

  return (
    <div className={`seg-trivia stack tq ${tv ? "big tv-cols" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Trivia Tonight" remaining={view.phase === "final" ? null : view.remaining} receivedAt={receivedAt}>
        <p className="tq-tags">
          <span className="chip plum">{STYLE_LABEL[view.style]}</span>
          {view.category && view.phase !== "final" && (
            <span className="chip paper">
              <span aria-hidden="true">{view.category.icon}</span> {glue(view.category.label)}
            </span>
          )}
          {view.level && view.phase !== "final" && (
            <span className={`chip tq-level l${view.level}`}>
              <span aria-hidden="true">{"★".repeat(view.level) + "☆".repeat(3 - view.level)}</span> {LEVEL_LABEL[view.level]}
            </span>
          )}
        </p>
        {me && view.phase !== "final" && <YouLine view={view} />}
      </ShowHead>

      {view.phase !== "final" && (
        <div className={`stack ${tv ? "tv-main" : ""}`}>
          {view.phase === "pick" && view.pick && <Pick view={view} you={you} tv={tv} name={name} send={send} />}
          {view.phase === "wager" && <Wager view={view} tv={tv} name={name} send={send} />}
          {(view.phase === "question" || view.phase === "reveal") && view.question && (
            <QuestionStage view={view} you={you} tv={tv} receivedAt={receivedAt} send={send} />
          )}
        </div>
      )}
      {view.phase === "question" && <Answered view={view} you={you} tv={tv} />}
      {/* The TV shows the round's gains in the scores beside the board instead of a second list. */}
      {view.phase === "reveal" && r && !tv && <Reveal view={view} tv={tv} name={name} />}
      {view.phase === "final" ? <Final view={view} you={you} tv={tv} name={name} /> : <Standings view={view} you={you} tv={tv} />}
    </div>
  );
}

/** Your own state under the header: streak, lives, or that you're out. */
function YouLine({ view }: { view: TriviaView }) {
  const me = view.you!;
  return (
    <p className="tq-you">
      {me.lives !== null && (
        <span className="tq-lives" role="img" aria-label={`${me.lives} of 3 lives left`}>
          {"❤️".repeat(me.lives)}
          {"🤍".repeat(Math.max(0, 3 - me.lives))}
        </span>
      )}
      {me.out && <span className="chip cherry">You’re out: cheer them on!</span>}
      {me.streak >= 2 && (
        <span className="chip tq-streak">
          <span aria-hidden="true">🔥</span> {me.streak} in a row
        </span>
      )}
    </p>
  );
}

function Pick({ view, you, tv, name, send }: { view: TriviaView; you: string; tv: boolean; name: (p: string) => string; send: Props["send"] }) {
  const p = view.pick!;
  const mine = !tv && p.picker === you;
  return (
    <Card tone="stage" className="center">
      <p className="sign">{mine ? "Your pick!" : `${name(p.picker)} is picking`}</p>
      <h3 className="space-top">{mine ? "Choose the next question’s category" : "Which category will it be?"}</h3>
      <div className="tq-offers space-top" role="group" aria-label="Categories">
        {p.offers.map((o) =>
          mine ? (
            <button
              key={o.id}
              type="button"
              className="tq-offer"
              onClick={() => {
                sfx.pop();
                send({ t: "act", a: "pick", cat: o.id });
              }}
            >
              <span className="tq-offer-icon" aria-hidden="true">
                {o.icon}
              </span>
              <span className="tq-offer-label">{glue(o.label)}</span>
            </button>
          ) : (
            <div key={o.id} className="tq-offer idle">
              <span className="tq-offer-icon" aria-hidden="true">
                {o.icon}
              </span>
              <span className="tq-offer-label">{glue(o.label)}</span>
            </div>
          ),
        )}
      </div>
    </Card>
  );
}

function Wager({ view, tv, name, send }: { view: TriviaView; tv: boolean; name: (p: string) => string; send: Props["send"] }) {
  const me = tv ? null : view.you;
  const max = me?.max_wager ?? 0;
  const [bet, setBet] = useState(Math.round(max / 2 / 50) * 50);
  const placed = me?.wager !== null && me?.wager !== undefined;
  return (
    <Card tone="stage" className="center">
      <p className="sign">The next question</p>
      {view.category && (
        <p className="tq-bigcat space-top">
          <span aria-hidden="true">{view.category.icon}</span> {glue(view.category.label)}
        </p>
      )}
      {view.level && <p className="lead">{LEVEL_LABEL[view.level]} question</p>}
      {me && !placed && (
        <form
          className="tq-wager space-top"
          onSubmit={(e) => {
            e.preventDefault();
            sfx.pop();
            send({ t: "act", a: "wager", amount: bet });
          }}
        >
          <label className="field" htmlFor="tq-bet">
            Your bet: <b>{fmt(bet)}</b> of {fmt(max)}
          </label>
          <input id="tq-bet" type="range" min={0} max={max} step={10} value={bet} onChange={(e) => setBet(Number(e.target.value))} />
          <div className="row center">
            <Btn variant="ghost" onClick={() => setBet(0)}>
              Play safe (0)
            </Btn>
            <Btn variant="ghost" onClick={() => setBet(Math.round(max / 2))}>
              Half
            </Btn>
            <Btn variant="danger" onClick={() => setBet(max)}>
              All in!
            </Btn>
          </div>
          <Btn type="submit" variant="accent" size="big" block>
            Bet {fmt(bet)}
          </Btn>
          <p className="muted">Right: +100 and your bet back as winnings. Wrong or too slow: you lose it.</p>
        </form>
      )}
      {me && placed && <h3 className="space-top">Bet locked: {fmt(me.wager!)}</h3>}
      <p className="muted space-top" aria-live="polite">
        {view.wagered.length} of {view.players.length} bets in
        {view.wagered.length > 0 && `: ${view.wagered.map(name).join(", ")}`}
      </p>
    </Card>
  );
}

function QuestionStage({ view, you, tv, receivedAt, send }: { view: TriviaView; you: string; tv: boolean; receivedAt: number; send: Props["send"] }) {
  const q = view.question!;
  const r = view.phase === "reveal" ? view.result : undefined;
  const share = useClockShare(view.phase === "question" ? view.remaining : null, receivedAt, view.limit);
  const me = tv ? null : view.you;
  const mine = r ? r.picks[you] : me?.answer;
  const canAnswer = !!me && !me.out && view.phase === "question" && me.answer === null;
  const pickers = (i: number) => (r ? view.players.filter((p) => r.picks[p.id] === i) : []);
  return (
    <>
      <Card tone="stage" className="tq-q center">
        <h3 className="prompt">{q.q}</h3>
        {view.phase === "question" && (
          <progress className={`tq-clock ${share < 0.25 ? "low" : ""}`} max={1000} value={Math.round(share * 1000)} aria-hidden="true" />
        )}
      </Card>
      <div className={`tq-choices ${q.tf ? "tf" : ""}`} role="group" aria-label="Answers">
        {q.choices.map((c, i) => {
          const state = r ? (i === r.right ? "right" : mine === i ? "wrong" : "dim") : mine === i ? "mine" : mine != null ? "dim" : "";
          const who = pickers(i);
          return (
            <button
              key={i}
              type="button"
              className={`tq-choice c${q.tf ? (i === 0 ? "t" : "f") : i} ${state}`}
              disabled={!canAnswer}
              aria-pressed={mine === i}
              onClick={() => {
                if (!canAnswer) return;
                sfx.pop();
                send({ t: "act", a: "answer", choice: i });
              }}
            >
              <span className="tq-mark" aria-hidden="true">
                {q.tf ? (i === 0 ? "✓" : "✗") : MARKS[i]}
              </span>
              <span className="tq-text">{c}</span>
              {state === "right" && <span className="sr-only">, the right answer</span>}
              {state === "wrong" && <span className="sr-only">, your answer: wrong</span>}
              {state === "mine" && <span className="tq-lock">Locked in</span>}
              {r && who.length > 0 && (
                <span className="tq-who" aria-label={`${who.length} picked this`}>
                  {who.slice(0, 8).map((p) => (
                    <Avatar key={p.id} pid={p.id} name={p.name} className="tiny" />
                  ))}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {me?.out && view.phase === "question" && <p className="center muted">You’re out of lives, but you can still play along in your head.</p>}
    </>
  );
}

/** Who's locked in (never what): avatars tick over as answers arrive. */
function Answered({ view, you, tv }: { view: TriviaView; you: string; tv: boolean }) {
  const playing = view.players.filter((p) => view.style !== "survival" || (view.lives[p.id] ?? 0) > 0);
  const done = playing.filter((p) => view.answered.includes(p.id)).length;
  return (
    <Card tone="soft">
      <p className="center" aria-live="polite">
        <b>{done}</b> of {playing.length} locked in
      </p>
      <ul className="tq-locks space-top" aria-label="Players">
        {playing.map((p) => {
          const locked = view.answered.includes(p.id);
          return (
            <li key={p.id} className={locked ? "locked" : ""}>
              <Avatar pid={p.id} name={p.name} />
              <span className="tq-lock-name">{p.id === you && !tv ? "You" : p.name.split(/\s+/)[0]}</span>
              <span aria-hidden="true">{locked ? "✅" : "🤔"}</span>
              <span className="sr-only">{locked ? ", locked in" : ", thinking"}</span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Reveal({ view, tv, name }: { view: TriviaView; tv: boolean; name: (p: string) => string }) {
  const r = view.result!;
  const playing = view.players.filter((p) => r.gains[p.id] !== 0 || r.picks[p.id] !== undefined || (view.lives[p.id] ?? 1) > 0 || r.out.includes(p.id));
  const rows = [...playing].sort((a, b) => (r.gains[b.id] ?? 0) - (r.gains[a.id] ?? 0) || (r.times[a.id] ?? 1e9) - (r.times[b.id] ?? 1e9));
  const rightCount = Object.values(r.picks).filter((c) => c === r.right).length;
  return (
    <Card>
      <h3>
        {rightCount === 0 ? "Nobody got it!" : rightCount === Object.keys(r.picks).length && rightCount === playing.length ? "Everyone got it!" : `${rightCount} got it right`}
      </h3>
      <ul className="tq-rows space-top">
        {rows.map((p) => {
          const pick = r.picks[p.id];
          const ok = pick === r.right;
          return (
            <li key={p.id} className={ok ? "ok" : pick === undefined ? "none" : "no"}>
              <Avatar pid={p.id} name={p.name} />
              <span className="tq-row-name">
                <b>{name(p.id)}</b>
                <span className="muted">
                  {pick === undefined ? "no answer" : ok ? `right in ${((r.times[p.id] ?? 0) / 1000).toFixed(1)} s` : "wrong"}
                  {r.first === p.id && view.style === "fastest" ? " · first!" : ""}
                  {view.style === "wager" && r.wagers[p.id] ? ` · bet ${fmt(r.wagers[p.id]!)}` : ""}
                </span>
              </span>
              {r.out.includes(p.id) ? (
                <span className="chip cherry">Out!</span>
              ) : view.style === "survival" && !ok ? (
                <span className="chip cherry">−1 life</span>
              ) : (
                <span className={`chip ${(r.gains[p.id] ?? 0) > 0 ? "teal" : (r.gains[p.id] ?? 0) < 0 ? "cherry" : ""}`}>{signed(r.gains[p.id] ?? 0)}</span>
              )}
            </li>
          );
        })}
      </ul>
      {!tv && view.you && view.you.streak >= 3 && view.style !== "survival" && (
        <p className="tq-fire space-top">
          <span aria-hidden="true">🔥</span> {view.you.streak} in a row: streak bonus!
        </p>
      )}
    </Card>
  );
}

function Score({ value }: { value: number }) {
  return <>{fmt(useCountUp(value))}</>;
}

function Standings({ view, you, tv }: { view: TriviaView; you: string; tv: boolean }) {
  const gains = tv && view.phase === "reveal" ? view.result?.gains : undefined;
  const rows = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  return (
    <Card>
      <h3>Scores</h3>
      <ol className="score-rows tq-scores">
        {rows.map((p) => {
          const lives = view.lives[p.id];
          const out = view.style === "survival" && lives === 0;
          return (
            <li key={p.id} className={out ? "out" : ""}>
              <b>
                <Avatar pid={p.id} name={p.name} className="tiny" /> {p.name}
                {p.id === you && !tv ? " (you)" : ""}
                {view.streaks[p.id] ? (
                  <span className="tq-mini" aria-label={`${view.streaks[p.id]} in a row`}>
                    {" "}
                    🔥{view.streaks[p.id]}
                  </span>
                ) : null}
                {lives !== undefined && (
                  <span className="tq-mini" role="img" aria-label={out ? "out" : `${lives} lives`}>
                    {" "}
                    {out ? "💀" : "❤️".repeat(lives)}
                  </span>
                )}
                {gains && gains[p.id] !== undefined && gains[p.id] !== 0 && (
                  <span className={`chip ${gains[p.id]! > 0 ? "teal" : "cherry"}`}>{signed(gains[p.id]!)}</span>
                )}
              </b>
              <span className="score-pts">
                <Score value={view.scores[p.id] ?? 0} />
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

function Final({ view, you, tv, name }: { view: TriviaView; you: string; tv: boolean; name: (p: string) => string }) {
  const rows = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  const asked = view.history?.length ?? 0;
  const medal = ["🥇", "🥈", "🥉"];
  const tied = rows.filter((p) => (view.scores[p.id] ?? 0) === (view.scores[rows[0]?.id ?? ""] ?? 0)).length > 1;
  return (
    <>
      <Card className={tv ? "tv-main" : ""}>
        <p className="sign center">
          {!rows[0] || tied ? "It’s a tie at the top!" : `${name(rows[0].id)} ${rows[0].id === you && !tv ? "win" : "wins"} the quiz!`}
        </p>
        <ol className="tq-podium space-top">
          {rows.map((p, i) => (
            <li key={p.id} className={i < 3 ? `place p${i + 1}` : "place"}>
              <span className="tq-seat">
                <Avatar pid={p.id} name={p.name} className="lg" />
                <span className="tq-medal" aria-hidden="true">
                  {medal[i] ?? i + 1}
                </span>
              </span>
              <b className="tq-podium-name">
                <span className="sr-only">{i + 1}. </span>
                {p.name}
                {p.id === you && !tv ? " (you)" : ""}
              </b>
              <span className="tq-podium-stats muted">
                {view.correct?.[p.id] ?? 0} of {asked} right
                {(view.best_streak?.[p.id] ?? 0) >= 2 ? ` · best streak ${view.best_streak![p.id]}` : ""}
              </span>
              <span className="score-pts">{fmt(view.scores[p.id] ?? 0)}</span>
            </li>
          ))}
        </ol>
      </Card>
      <Card>
        <details className="how-to">
          <summary>Every question and answer ({asked})</summary>
          <ol className="tq-history">
            {(view.history ?? []).map((h, i) => (
              <li key={i}>
                <span className="tq-hq">{h.q}</span>
                <span className="tq-ha">
                  <b>{h.a}</b>
                  <span className="muted"> · {h.right.length ? h.right.map(name).join(", ") : "nobody"}</span>
                </span>
              </li>
            ))}
          </ol>
        </details>
      </Card>
    </>
  );
}
