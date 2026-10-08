import { useEffect, useRef, useState } from "react";
import { Btn, Card, ShowHead, nameList, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { WordRaceView, WrRow } from "../types";

interface Props {
  view: WordRaceView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const LENGTH = 5;
const PRAISE = ["GENIUS!", "MAGNIFICENT!", "IMPRESSIVE!", "SPLENDID!", "GREAT!", "PHEW!"];
const KEYS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];
const MARK_NAME: Record<string, string> = { g: "right spot", y: "wrong spot", x: "not in the word" };
const MEDAL = ["🥇", "🥈", "🥉"];

/** Best colour seen for each letter in your guesses: green beats yellow beats grey. */
function letterStatus(rows: WrRow[]): Record<string, string> {
  const rank: Record<string, number> = { x: 1, y: 2, g: 3 };
  const out: Record<string, string> = {};
  for (const r of rows) {
    if (!r.word) continue;
    [...r.word].forEach((ch, i) => {
      const m = r.marks[i]!;
      if ((rank[m] ?? 0) > (rank[out[ch] ?? ""] ?? 0)) out[ch] = m;
    });
  }
  return out;
}

export function WordRace({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const playing = !tv && view.you.playing;
  const mine = view.boards[you] ?? [];
  const [typed, setTyped] = useState("");
  const [shake, setShake] = useState(false);
  const pending = useRef<{ rows: number; timer: number } | null>(null);

  useEffect(() => () => window.clearTimeout(pending.current?.timer), []);

  useOnChange(mine.length, (prev, next) => {
    if (next <= prev) return;
    if (pending.current) window.clearTimeout(pending.current.timer);
    pending.current = null;
    setTyped("");
    const last = mine[next - 1]!;
    if (last.marks === "ggggg") {
      window.setTimeout(() => {
        sfx.fanfare();
        show.stinger(PRAISE[next - 1] ?? "SOLVED!");
        show.celebrate();
      }, 1500); // after the tiles have flipped
    } else {
      window.setTimeout(() => (next >= view.tries ? sfx.buzz() : sfx.pop()), 1500);
    }
  });
  useOnChange(view.solved.length, (prev, next) => {
    const who = view.solved[next - 1];
    if (next > prev && who && who !== you) {
      sfx.ding();
      show.stinger(`${nameOf(view.players, who).toUpperCase()} GOT IT!`);
    }
  });
  useOnChange(view.phase, (_, phase) => {
    setTyped("");
    if (phase === "reveal" && !tv && playing && !view.you.solved) {
      sfx.buzz();
      show.stinger(view.answer ?? "", "bad");
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });

  const canType = playing && view.phase === "play" && !view.you.done;
  const submit = () => {
    if (!canType) return;
    if (typed.length !== LENGTH) {
      setShake(true);
      window.setTimeout(() => setShake(false), 500);
      return;
    }
    send({ t: "act", a: "guess", word: typed });
    const rows = mine.length;
    // The server refuses words it doesn't know (the message shows in the banner): shake the row.
    pending.current = {
      rows,
      timer: window.setTimeout(() => {
        if (pending.current?.rows === rows) {
          setShake(true);
          sfx.buzz();
          window.setTimeout(() => setShake(false), 500);
        }
      }, 900),
    };
  };

  const sign =
    view.phase === "final"
      ? "Final scores"
      : view.phase === "reveal"
        ? `Word ${view.round} of ${view.rounds} · The word was…`
        : `Word ${view.round} of ${view.rounds} · ${
            !playing ? "Find the word" : view.you.solved ? "Solved!" : view.you.done ? "Out of guesses" : "Find the word"
          }`;

  return (
    <div className={`seg-wordrace stack ${tv && view.phase !== "play" ? "tv-cols" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Word Race" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">{view.hard ? "🔥 Hard mode: use every hint" : "6 tries · fewer guesses, more points"}</span>
      </ShowHead>

      {view.phase !== "final" && view.answer && <Answer word={view.answer} />}

      {playing && view.phase !== "final" && (
        <Card className="center">
          <Grid rows={mine} tries={view.tries} typed={canType ? typed : ""} shake={shake} />
          {view.phase === "play" &&
            (view.you.done ? (
              <p className="lead space-top" aria-live="polite">
                {view.you.solved ? `Solved in ${mine.length}! +${view.gained[you] ?? 0}` : "Out of guesses. Fingers crossed for the others…"}
              </p>
            ) : (
              <>
                <Letters rows={mine} />
                <form
                  className="wr-entry"
                  onSubmit={(e) => {
                    e.preventDefault();
                    submit();
                  }}
                >
                  <label className="sr-only" htmlFor="wr-guess">
                    Your guess, five letters
                  </label>
                  <input
                    id="wr-guess"
                    className="wr-input"
                    type="text"
                    inputMode="text"
                    autoComplete="off"
                    autoCorrect="off"
                    autoCapitalize="characters"
                    spellCheck={false}
                    enterKeyHint="go"
                    maxLength={LENGTH}
                    placeholder="Type a word"
                    value={typed}
                    onChange={(e) => setTyped(e.target.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, LENGTH))}
                  />
                  <Btn type="submit" variant="go" disabled={typed.length !== LENGTH}>
                    Guess ▶
                  </Btn>
                </form>
                <p className="muted space-top">
                  Guess {mine.length + 1} of {view.tries}
                </p>
              </>
            ))}
        </Card>
      )}

      {view.phase === "reveal" && <RoundScores view={view} you={you} />}

      {/* TV final: the standings take the stage; the last word's boards are in the history */}
      {!(tv && view.phase === "final") && <Racers view={view} you={you} tv={tv} />}

      {view.phase === "final" && view.history && <Words view={view} you={you} />}
    </div>
  );
}

/** Your six rows: guesses flip in tile by tile; the current row fills as you type. */
function Grid({ rows, tries, typed, shake }: { rows: WrRow[]; tries: number; typed: string; shake: boolean }) {
  return (
    <div className="wr-grid" role="group" aria-label="Your guesses">
      {Array.from({ length: tries }, (_, r) => {
        const row = rows[r];
        const current = r === rows.length;
        const letters = row ? (row.word ?? "") : current ? typed : "";
        return (
          <div key={r} className={`wr-row ${current && shake ? "shake" : ""}`}>
            {Array.from({ length: LENGTH }, (_, i) => {
              const ch = letters[i] ?? "";
              const m = row?.marks[i];
              return (
                <span key={i} className={`wr-tile ${m ? `m-${m} flip` : ch ? "filled" : ""}`}>
                  <span aria-hidden="true">{ch}</span>
                </span>
              );
            })}
            {row && (
              <span className="sr-only">
                {(row.word ?? "").split("").map((ch, i) => `${ch} ${MARK_NAME[row.marks[i]!]}`).join(", ")}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** What you know about each letter, laid out like a keyboard (a display, not buttons: you type with yours). */
function Letters({ rows }: { rows: WrRow[] }) {
  const status = letterStatus(rows);
  const by = (m: string) => Object.keys(status).filter((ch) => status[ch] === m).sort().join(" ") || "none";
  return (
    <div className="wr-letters">
      <div aria-hidden="true">
        {KEYS.map((row) => (
          <div key={row} className="wr-keys">
            {[...row].map((ch) => (
              <span key={ch} className={`wr-key ${status[ch] ? `m-${status[ch]}` : ""}`}>
                {ch}
              </span>
            ))}
          </div>
        ))}
      </div>
      <p className="sr-only">
        Placed: {by("g")}. In the word: {by("y")}. Not in the word: {by("x")}.
      </p>
    </div>
  );
}

function Answer({ word }: { word: string }) {
  return (
    <Card tone="stage" className="center">
      <p className="sign">The word was</p>
      <p className="sr-only">{word}</p>
      <div className="wr-row wr-answer space-top" aria-hidden="true">
        {[...word].map((ch, i) => (
          <span key={i} className="wr-tile m-g flip">
            <span>{ch}</span>
          </span>
        ))}
      </div>
    </Card>
  );
}

/** Everyone's colours as they go (letters stay secret until the reveal). */
function Racers({ view, you, tv }: { view: WordRaceView; you: string; tv: boolean }) {
  const others = view.players.filter((p) => tv || !view.you.playing || p.id !== you || view.phase !== "play");
  const rank = (id: string) => view.solved.indexOf(id);
  return (
    <Card className="tv-main">
      <h3>{view.phase === "play" ? "The race" : "Everyone’s guesses"}</h3>
      <ul className={`wr-racers ${tv ? "big" : ""}`}>
        {others.map((p) => {
          const rows = view.boards[p.id] ?? [];
          const r = rank(p.id);
          const out = r < 0 && rows.length >= view.tries;
          return (
            <li key={p.id} className={r >= 0 ? "solved" : out ? "out" : ""}>
              <p className="wr-racer-name">
                <b>
                  {p.name}
                  {p.id === you ? " (you)" : ""}
                </b>
                <span className="wr-racer-state">
                  {r >= 0 ? `${MEDAL[r] ?? "✅"} ${rows.length}/${view.tries}` : out ? "❌ out" : `${rows.length}/${view.tries}`}
                </span>
              </p>
              <div className="wr-mini" aria-hidden="true">
                {Array.from({ length: view.tries }, (_, i) => (
                  <div key={i} className="wr-mini-row">
                    {Array.from({ length: LENGTH }, (_, j) => (
                      <span key={j} className={`wr-dot ${rows[i] ? `m-${rows[i]!.marks[j]}` : ""}`} />
                    ))}
                  </div>
                ))}
              </div>
              {view.phase !== "play" && rows.some((row) => row.word) && (
                <p className="wr-words muted">{rows.map((row) => row.word).join("\u00a0· ")}</p>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function RoundScores({ view, you }: { view: WordRaceView; you: string }) {
  const solvers = view.solved;
  return (
    <Card tone="soft" className="center">
      <p className="lead">
        {solvers.length === 0
          ? "Nobody cracked it this time!"
          : `${nameList(solvers.map((p) => nameOf(view.players, p) + (p === you ? " (you)" : "")))} solved it.`}
      </p>
      <ul className="wr-points space-top">
        {solvers.map((p, i) => (
          <li key={p} className="chip">
            {MEDAL[i] ?? "✅"} {nameOf(view.players, p)} +{view.gained[p] ?? 0}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Words({ view, you }: { view: WordRaceView; you: string }) {
  const totals: Record<string, number> = {};
  for (const h of view.history!) for (const [p, v] of Object.entries(h.points)) totals[p] = (totals[p] ?? 0) + v;
  const ranked = [...view.players].sort((a, b) => (totals[b.id] ?? 0) - (totals[a.id] ?? 0));
  const top = ranked[0] ? (totals[ranked[0].id] ?? 0) : 0;
  return (
    <>
      <Card className="tv-main">
        <h3>Standings</h3>
        <ul className="score-rows">
          {ranked.map((p) => (
            <li key={p.id}>
              <b>
                {top > 0 && (totals[p.id] ?? 0) === top ? "👑 " : ""}
                {p.name}
                {p.id === you ? " (you)" : ""}
              </b>
              <span className="score-tally" aria-hidden="true">
                <span>
                  ✅ {view.wins[p.id] ?? 0}/{view.rounds}
                </span>
                <span className="score-pts">{totals[p.id] ?? 0}</span>
              </span>
              <span className="sr-only">
                {totals[p.id] ?? 0} points, solved {view.wins[p.id] ?? 0} of {view.rounds}
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <h3>The words</h3>
        <ul className="wr-history">
          {view.history!.map((h, i) => (
            <li key={i}>
              <span className="wr-history-word">{h.answer}</span>
              <span className="muted">
                {h.solved.length
                  ? h.solved.map((p) => `${nameOf(view.players, p)} (${h.tries[p]})`).join(", ")
                  : "nobody got it"}
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
