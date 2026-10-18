import { useState } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useCountUp, useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { ImposterResult, ImposterView } from "../types";

interface Props {
  view: ImposterView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const STEP: Record<ImposterView["phase"], string> = {
  cards: "Check your card",
  clue: "Clues",
  vote: "Vote",
  guess: "Last chance",
  result: "The reveal",
  final: "Final scores",
};

export function Imposter({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const me = tv ? null : view.you;
  const name = (pid: string) => (pid === you && !tv ? "You" : nameOf(view.players, pid));
  const r = view.result;

  useOnChange(view.turn === you && !tv, (_, mine) => {
    if (mine) sfx.ding();
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "vote") sfx.ding();
    else if (phase === "guess") {
      sfx.buzz();
      show.stinger("CAUGHT!");
    } else if (phase === "result" && r) {
      const crew = !tv && r.imposter !== you;
      const won = r.caught && !r.stole ? crew || tv : !crew && !tv;
      if (won) sfx.fanfare();
      else sfx.buzz();
      show.stinger(r.stole ? "STOLEN!" : r.caught ? "IMPOSTER CAUGHT!" : "THE IMPOSTER ESCAPES!", won ? "good" : "bad");
      if (won && !tv) show.celebrate();
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });

  const sign = view.phase === "final" ? STEP.final : `Round ${view.round} of ${view.rounds} · ${STEP[view.phase]}`;
  return (
    <div className={`seg-imposter stack ip ${tv ? "big tv-cols" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Imposter" remaining={view.phase === "final" ? null : view.remaining} receivedAt={receivedAt}>
        {view.phase !== "final" && (
          <p className="ip-tags">
            <span className="chip plum">Category: {view.category}</span>
            {view.twist === "undercover" && <span className="chip cherry">Undercover: one word is different</span>}
          </p>
        )}
      </ShowHead>

      <div className={`stack ${tv ? "tv-main" : ""}`}>
        {me && !["result", "final"].includes(view.phase) && <SecretCard key={view.round} view={view} />}
        {tv && ["cards", "clue"].includes(view.phase) && (
          <Card tone="stage" className="center">
            <p className="ip-big">🕵️</p>
            <p className="sign space-top">One of you is faking it</p>
            <p className="lead space-top">The category is {view.category}.</p>
          </Card>
        )}
        {view.phase === "vote" && <Vote view={view} you={you} tv={tv} send={send} />}
        {["clue", "vote", "guess"].includes(view.phase) && <Clues view={view} you={you} tv={tv} send={send} name={name} />}
        {view.phase === "guess" && <Guess view={view} you={you} tv={tv} send={send} />}
        {view.phase === "result" && r && <Reveal view={view} r={r} you={you} tv={tv} name={name} />}
        {view.phase === "final" && <Final view={view} you={you} tv={tv} name={name} />}
      </div>
      {view.phase !== "final" && <Scores view={view} you={you} tv={tv} />}
    </div>
  );
}

/** Your card: the word, or the news that you're the imposter. Hidden until you look (friends sit close). */
function SecretCard({ view }: { view: ImposterView }) {
  const me = view.you!;
  const [open, setOpen] = useState(false);
  return (
    <Card tone="stage" className={`ip-card center ${me.imposter ? "fake" : ""}`}>
      {open ? (
        me.imposter ? (
          <>
            <p className="ip-big" aria-hidden="true">
              🕵️
            </p>
            <p className="sign space-top">You’re the imposter!</p>
            <p className="lead space-top">
              You don’t know the word. The category is <b>{view.category}</b>: listen to the clues and blend in.
            </p>
          </>
        ) : (
          <>
            <p className="sign">Your secret word</p>
            <p className="ip-word space-top">{me.word}</p>
            <p className="space-top">
              {view.twist === "undercover"
                ? "Someone has a different word, and they don’t know it. Could it be you?"
                : "One of you doesn’t have this word. Don’t make it easy for them!"}
            </p>
          </>
        )
      ) : (
        <p className="lead">Make sure nobody can see your screen.</p>
      )}
      <Btn className="space-top" variant="ghost" aria-pressed={open} onClick={() => setOpen((o) => !o)}>
        {open ? "🙈 Hide my card" : "👀 Show my card"}
      </Btn>
    </Card>
  );
}

function Clues({ view, you, tv, send, name }: { view: ImposterView; you: string; tv: boolean; send: Props["send"]; name: (p: string) => string }) {
  const [text, setText] = useState("");
  const mine = !tv && view.phase === "clue" && view.turn === you;
  return (
    <Card>
      <h3>{view.phase === "clue" ? (mine ? "Your turn: give a clue" : `${nameOf(view.players, view.turn ?? "")} is thinking…`) : "The clues"}</h3>
      <ol className="ip-clues space-top">
        {view.order.map((pid, i) => {
          const c = view.clues[i];
          const now = view.phase === "clue" && i === view.clues.length;
          return (
            <li key={i} className={now ? "now" : c ? "" : "later"}>
              <Avatar pid={pid} name={nameOf(view.players, pid)} className="tiny" />
              <span className="ip-clue-who">
                <span className="ip-clue-name">{name(pid)}</span>
                <span className="ip-clue-text">{c ? (c.text ? `“${c.text}”` : "passed") : now ? "…" : ""}</span>
              </span>
            </li>
          );
        })}
      </ol>
      {mine && (
        <form
          className="ask-form space-top"
          onSubmit={(e) => {
            e.preventDefault();
            if (!text.trim()) return;
            sfx.pop();
            send({ t: "act", a: "clue", text });
            setText("");
          }}
        >
          <div>
            <label className="field" htmlFor="ip-clue">
              One word (don’t say the word itself)
            </label>
            <input id="ip-clue" type="text" autoComplete="off" maxLength={24} value={text} onChange={(e) => setText(e.target.value)} placeholder="Your clue" />
          </div>
          <Btn type="submit" variant="accent" disabled={!text.trim()}>
            Give clue
          </Btn>
        </form>
      )}
    </Card>
  );
}

function Vote({ view, you, tv, send }: { view: ImposterView; you: string; tv: boolean; send: Props["send"] }) {
  const mine = tv ? null : view.you;
  return (
    <Card tone="soft">
      <h3>{mine ? (mine.vote ? `You voted for ${nameOf(view.players, mine.vote)}` : "Who is the imposter?") : "Who is the imposter?"}</h3>
      <p className="muted" aria-live="polite">
        {view.voted.length} of {view.players.length} have voted
      </p>
      <ul className="ip-votes space-top" aria-label="Players">
        {view.players.map((p) => {
          const done = view.voted.includes(p.id);
          const canVote = mine && !mine.vote && p.id !== you;
          return (
            <li key={p.id}>
              {canVote ? (
                <button
                  type="button"
                  className="ip-vote"
                  onClick={() => {
                    sfx.tick();
                    send({ t: "act", a: "vote", target: p.id });
                  }}
                >
                  <Avatar pid={p.id} name={p.name} />
                  <span className="ip-vote-name">{p.name}</span>
                  <span className="sr-only">: vote for them{done ? " (they've voted)" : ""}</span>
                  <span aria-hidden="true">{done ? "✅" : "🤔"}</span>
                </button>
              ) : (
                <span className={`ip-vote static ${mine?.vote === p.id ? "picked" : ""}`}>
                  <Avatar pid={p.id} name={p.name} />
                  <span className="ip-vote-name">{p.id === you && !tv ? "You" : p.name}</span>
                  <span aria-hidden="true">{done ? "✅" : "🤔"}</span>
                  <span className="sr-only">{done ? ", has voted" : ", still deciding"}</span>
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Guess({ view, you, tv, send }: { view: ImposterView; you: string; tv: boolean; send: Props["send"] }) {
  const [text, setText] = useState("");
  const who = view.accused ?? "";
  const mine = !tv && who === you;
  return (
    <Card tone="stage" className="center">
      <Avatar pid={who} name={nameOf(view.players, who)} className="xl" />
      <p className="sign space-top">{mine ? "You’ve been caught!" : `${nameOf(view.players, who)} was the imposter!`}</p>
      <p className="lead space-top">{mine ? "One guess at the word: get it right and you steal the round." : "One guess at the word to steal the round…"}</p>
      {mine && (
        <form
          className="ask-form space-top"
          onSubmit={(e) => {
            e.preventDefault();
            if (!text.trim()) return;
            send({ t: "act", a: "guess", text });
          }}
        >
          <div>
            <label className="field" htmlFor="ip-guess">
              The secret word ({view.category})
            </label>
            <input id="ip-guess" type="text" autoComplete="off" maxLength={30} value={text} onChange={(e) => setText(e.target.value)} placeholder="Your guess" />
          </div>
          <Btn type="submit" variant="accent" disabled={!text.trim()}>
            Guess!
          </Btn>
        </form>
      )}
    </Card>
  );
}

function Reveal({ view, r, you, tv, name }: { view: ImposterView; r: ImposterResult; you: string; tv: boolean; name: (p: string) => string }) {
  const imp = nameOf(view.players, r.imposter);
  const headline = r.stole
    ? `${imp} guessed “${r.guess}” and stole it!`
    : r.caught
      ? r.guess
        ? `${imp} guessed “${r.guess}”: wrong! The crew wins.`
        : `Caught! The crew wins.`
      : r.accused
        ? `The room voted out ${nameOf(view.players, r.accused)}, but they were innocent!`
        : "The vote was split: nobody was caught.";
  return (
    <>
      <Card tone="stage" className="center">
        <Avatar pid={r.imposter} name={imp} className="xl" />
        <p className="sign space-top">{r.imposter === you && !tv ? "You were the imposter" : `${imp} was the imposter`}</p>
        <p className="lead space-top">
          The word was <b className="ip-word-inline">{r.word}</b>
          {r.close && (
            <>
              {" "}
              ({r.imposter === you && !tv ? "you" : imp} had <b className="ip-word-inline">{r.close}</b>)
            </>
          )}
        </p>
        <p className="lead space-top">{headline}</p>
      </Card>
      <Card>
        <h3>The votes</h3>
        <ul className="yr-rows space-top">
          {view.players.map((p) => {
            const target = r.votes[p.id];
            const right = target === r.imposter;
            const gain = r.gains[p.id] ?? 0;
            return (
              <li key={p.id} className={right ? "ok" : ""}>
                <Avatar pid={p.id} name={p.name} />
                <span className="yr-row-name">
                  <b>
                    {name(p.id)}
                    {p.id === r.imposter ? " 🕵️" : ""}
                  </b>
                  <span className="muted">{target ? `voted for ${name(target)}` : "didn’t vote"}</span>
                </span>
                <span className={`chip ${gain > 0 ? "teal" : ""}`}>+{gain}</span>
              </li>
            );
          })}
        </ul>
      </Card>
    </>
  );
}

function Score({ value }: { value: number }) {
  return <>{useCountUp(value)}</>;
}

function Scores({ view, you, tv }: { view: ImposterView; you: string; tv: boolean }) {
  const rows = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  return (
    <Card>
      <h3>Scores</h3>
      <ol className="score-rows">
        {rows.map((p) => (
          <li key={p.id}>
            <b>
              <Avatar pid={p.id} name={p.name} className="tiny" /> {p.name}
              {p.id === you && !tv ? " (you)" : ""}
            </b>
            <span className="score-pts">
              <Score value={view.scores[p.id] ?? 0} />
            </span>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function Final({ view, you, tv, name }: { view: ImposterView; you: string; tv: boolean; name: (p: string) => string }) {
  const rows = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  const top = view.scores[rows[0]?.id ?? ""] ?? 0;
  const tied = rows.filter((p) => (view.scores[p.id] ?? 0) === top).length > 1;
  return (
    <>
      <Card>
        <p className="sign center">{!rows[0] || tied ? "It’s a tie!" : `${name(rows[0].id)} ${rows[0].id === you && !tv ? "win" : "wins"}!`}</p>
        <ol className="yr-rows space-top">
          {rows.map((p, i) => (
            <li key={p.id} className={i === 0 && !tied ? "ok" : ""}>
              <Avatar pid={p.id} name={p.name} />
              <span className="yr-row-name">
                <b>
                  {i === 0 && !tied ? "👑 " : ""}
                  {p.name}
                  {p.id === you && !tv ? " (you)" : ""}
                </b>
              </span>
              <span className="score-pts">{view.scores[p.id] ?? 0}</span>
            </li>
          ))}
        </ol>
      </Card>
      <Card>
        <details className="how-to">
          <summary>Every round ({view.history?.length ?? 0})</summary>
          <ol className="yr-history">
            {(view.history ?? []).map((h, i) => (
              <li key={i}>
                <b>{nameOf(view.players, h.imposter)}</b> faked <b>{h.word}</b>
                <span className="muted">
                  {" "}
                  ({h.category}) · {h.stole ? "caught, but stole it" : h.caught ? "caught" : "escaped"}
                </span>
              </li>
            ))}
          </ol>
        </details>
      </Card>
    </>
  );
}
