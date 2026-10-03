import { useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { CodewordsView, CwColor, CwLog, CwTeam } from "../types";

interface Props {
  view: CodewordsView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const TEAM_NAME: Record<CwTeam, string> = { red: "Red", blue: "Blue" };
const ICON: Record<CwColor, string> = { red: "🟥", blue: "🟦", neutral: "😐", assassin: "☠️" };
const COLOR_NAME: Record<CwColor, string> = { red: "Red", blue: "Blue", neutral: "a bystander", assassin: "THE ASSASSIN" };
const other = (t: CwTeam): CwTeam => (t === "red" ? "blue" : "red");

export function Codewords({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const [picked, setPicked] = useState<number | null>(null);
  const myTeam = tv ? null : view.you.team;
  const spymaster = !tv && view.you.spymaster;
  const myTurn = !!myTeam && view.turn === myTeam;
  const canGuess = myTurn && !spymaster && view.phase === "guess";
  const last = view.log[view.log.length - 1];

  useOnChange(view.log.length, (prev, next) => {
    if (next <= prev || !last || last.type !== "guess") return;
    if (last.color === "assassin") {
      sfx.buzz();
      show.stinger("☠️ ASSASSIN!", "bad");
    } else if (last.color === last.team) {
      sfx.ding();
      show.stinger(`${ICON[last.color]} ${last.word}`);
    } else {
      sfx.buzz();
      show.stinger(`${ICON[last.color]} ${last.word}`, "bad");
    }
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "final") {
      sfx.fanfare();
      show.stinger(`${TEAM_NAME[view.winner ?? "red"].toUpperCase()} WINS!`);
      show.celebrate();
    }
    setPicked(null);
  });
  useOnChange(view.turn, () => setPicked(null));

  const sign =
    view.phase === "teams"
      ? "Pick your teams"
      : view.phase === "final"
        ? `${TEAM_NAME[view.winner ?? "red"]} team wins`
        : view.phase === "clue"
          ? `${TEAM_NAME[view.turn]} · Spymaster’s clue`
          : `${TEAM_NAME[view.turn]} · guessing`;

  return (
    <div className={`seg-codewords ${view.phase === "teams" ? "" : view.phase === "final" ? `cw-turn-${view.winner}` : `cw-turn-${view.turn}`} stack`}>
      {show.node}
      <ShowHead sign={sign} title="Codewords" remaining={view.remaining} receivedAt={receivedAt}>
        {view.phase !== "teams" && <Score view={view} />}
      </ShowHead>

      {view.phase === "teams" ? (
        <TeamSetup view={view} you={you} send={send} tv={tv} />
      ) : (
        <>
          <TurnBanner view={view} you={you} spymaster={spymaster} myTeam={myTeam} />
          {spymaster && myTurn && view.phase === "clue" && <ClueForm view={view} send={send} />}
          <Board view={view} you={you} spymaster={spymaster} canGuess={canGuess} picked={picked} setPicked={setPicked} send={send} />
          {canGuess && <GuessBar view={view} you={you} picked={picked} setPicked={setPicked} send={send} />}
          <Teams view={view} you={you} />
          <ClueLog view={view} />
        </>
      )}
    </div>
  );
}

function Score({ view }: { view: CodewordsView }) {
  return (
    <div className="cw-score" aria-label={`Words left: Red ${view.left.red}, Blue ${view.left.blue}`}>
      {(["red", "blue"] as CwTeam[]).map((t) => (
        <span key={t} className={`cw-pill ${t} ${view.turn === t && view.phase !== "final" ? "on" : ""}`}>
          {TEAM_NAME[t]} <b>{view.left[t]}</b> left
        </span>
      ))}
    </div>
  );
}

function members(view: CodewordsView, team: CwTeam) {
  return view.players.filter((p) => view.teams[p.id] === team);
}

/** Before the board: pick a side, pick a Spymaster. Balanced teams are already filled in. */
function TeamSetup({ view, you, send, tv }: { view: CodewordsView; you: string; send: Props["send"]; tv: boolean }) {
  const mine = view.teams[you];
  return (
    <>
      <div className="cw-teams">
        {(["red", "blue"] as CwTeam[]).map((t) => (
          <Card key={t} className={`cw-team-card ${t}`}>
            <h3>
              {ICON[t]} Team {TEAM_NAME[t]}
            </h3>
            <ul className="cw-members">
              {members(view, t).map((p) => (
                <li key={p.id}>
                  <b>
                    {p.name}
                    {p.id === you ? " (you)" : ""}
                  </b>
                  <span className="cw-role">{view.spymasters[t] === p.id ? "🕵️ Spymaster" : "🔎 Guesser"}</span>
                </li>
              ))}
            </ul>
            {!tv && (
              <div className="row">
                {mine !== t && (
                  <Btn size="small" variant="ghost" onClick={() => send({ t: "act", a: "team", team: t })}>
                    Join {TEAM_NAME[t]}
                  </Btn>
                )}
                {mine === t && view.spymasters[t] !== you && (
                  <Btn size="small" variant="ghost" onClick={() => send({ t: "act", a: "spymaster" })}>
                    🕵️ Be the Spymaster
                  </Btn>
                )}
              </div>
            )}
          </Card>
        ))}
      </div>
      <p className="center muted" aria-live="polite">
        {view.valid_teams
          ? "Teams look good. Everyone taps Ready (or the host skips) to deal the board."
          : "Each team needs a Spymaster and at least one guesser. If not, we'll balance it for you at the start."}
      </p>
    </>
  );
}

function TurnBanner({ view, you, spymaster, myTeam }: { view: CodewordsView; you: string; spymaster: boolean; myTeam: CwTeam | null }) {
  if (view.phase === "final") {
    const w = view.winner ?? "red";
    return (
      <Card tone="stage" className={`center cw-banner ${w}`}>
        <p className="sign">{view.how === "assassin" ? "☠️ The assassin struck" : "🏆 Every word found"}</p>
        <p className="cw-banner-big space-top">
          Team {TEAM_NAME[w]} wins{myTeam ? (myTeam === w ? " (that’s you!)" : "") : ""}
        </p>
        <p>{view.how === "assassin" ? `Team ${TEAM_NAME[other(w)]} touched the assassin.` : "Here’s the whole key."}</p>
      </Card>
    );
  }
  const spy = view.spymasters[view.turn];
  const role = myTeam ? (spymaster ? `You’re ${TEAM_NAME[myTeam]}’s Spymaster: only you see the colours.` : `You’re a ${TEAM_NAME[myTeam]} guesser.`) : "";
  return (
    <Card tone="stage" className={`center cw-banner ${view.turn}`}>
      {view.phase === "clue" ? (
        <>
          <p className="sign">{TEAM_NAME[view.turn]}’s turn</p>
          <p className="lead space-top">
            {spy === you ? "Give your team a clue below." : `Waiting for ${spy ? nameOf(view.players, spy) : "the Spymaster"}’s clue…`}
          </p>
        </>
      ) : (
        <>
          <p className="sign">Clue for {TEAM_NAME[view.turn]}</p>
          <p className="cw-clue space-top">
            {view.clue?.word} <span className="cw-count">{view.clue?.count === 0 ? "∞" : view.clue?.count}</span>
          </p>
          <p>{view.guesses_left === null ? "Unlimited guesses" : `${view.guesses_left} ${view.guesses_left === 1 ? "guess" : "guesses"} left`}</p>
        </>
      )}
      {role && <p className="muted space-top">{role}</p>}
    </Card>
  );
}

function ClueForm({ view, send }: { view: CodewordsView; send: Props["send"] }) {
  const [word, setWord] = useState("");
  const [count, setCount] = useState(1);
  const clean = word.trim().toUpperCase();
  const onBoard = view.board.some((c) => !c.revealed && clean && (c.word.includes(clean) || clean.includes(c.word)));
  const shape = /^[A-Z]+(-[A-Z]+)?$/.test(clean) && clean.length <= 20;
  const problem = !clean ? "" : !shape ? "One word, letters only." : onBoard ? "That's (part of) a word on the board." : "";
  return (
    <Card tone="soft">
      <form
        className="stack-sm"
        onSubmit={(e) => {
          e.preventDefault();
          if (!clean || problem) return;
          sfx.pop();
          send({ t: "act", a: "clue", word: clean, count });
          setWord("");
        }}
      >
        <label className="field" htmlFor="cw-clue">
          Your clue (one word)
        </label>
        <input
          id="cw-clue"
          type="text"
          autoComplete="off"
          autoCapitalize="characters"
          maxLength={20}
          value={word}
          placeholder="e.g. OCEAN"
          aria-invalid={!!problem}
          aria-describedby="cw-clue-help"
          onChange={(e) => setWord(e.target.value)}
        />
        <p id="cw-clue-help" className={problem ? "cw-problem" : "muted"}>
          {problem || "How many of your words does it point to?"}
        </p>
        <div className="cw-counts" role="group" aria-label="Number of words">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9, 0].map((n) => (
            <Btn key={n} size="small" variant="ghost" aria-pressed={count === n} aria-label={n === 0 ? "Unlimited" : String(n)} onClick={() => setCount(n)}>
              {n === 0 ? "∞" : n}
            </Btn>
          ))}
        </div>
        <Btn type="submit" variant="go" size="big" block disabled={!clean || !!problem}>
          Give clue: {clean || "…"} {count === 0 ? "∞" : count}
        </Btn>
      </form>
    </Card>
  );
}

function initials(name: string) {
  return name.slice(0, 2);
}

function Board({
  view,
  you,
  spymaster,
  canGuess,
  picked,
  setPicked,
  send,
}: {
  view: CodewordsView;
  you: string;
  spymaster: boolean;
  canGuess: boolean;
  picked: number | null;
  setPicked: (i: number | null) => void;
  send: Props["send"];
}) {
  return (
    <div className={`cw-board ${spymaster ? "key" : ""}`} role="group" aria-label="The 25 words">
      {view.board.map((c, i) => {
        const cls = [
          "cw-card",
          c.revealed ? `revealed ${c.color}` : c.color ? `hint ${c.color}` : "",
          c.word.length >= 10 ? "l10" : c.word.length === 9 ? "l9" : c.word.length === 8 ? "l8" : "",
          picked === i ? "picked" : "",
        ].join(" ");
        const label = `${c.word}${c.color ? `, ${COLOR_NAME[c.color]}` : ""}${c.revealed ? ", revealed" : ""}${
          c.marks.length ? `, considered by ${c.marks.map((m) => nameOf(view.players, m)).join(" and ")}` : ""
        }`;
        const inner = (
          <>
            {c.revealed && c.color && (
              <span className="cw-icon" aria-hidden="true">
                {ICON[c.color]}
              </span>
            )}
            <span className="cw-word" aria-hidden="true">
              {c.word}
            </span>
            {c.marks.length > 0 && (
              <span className="cw-marks" aria-hidden="true">
                {c.marks.map((m) => (
                  <span key={m} className="cw-mark">
                    {initials(nameOf(view.players, m))}
                  </span>
                ))}
              </span>
            )}
          </>
        );
        if (canGuess && !c.revealed) {
          return (
            <button
              key={i}
              type="button"
              className={cls}
              aria-label={label}
              aria-pressed={picked === i}
              onClick={() => {
                sfx.pop();
                const already = c.marks.includes(you);
                if (picked === i) {
                  setPicked(null);
                  if (already) send({ t: "act", a: "mark", card: i });
                } else {
                  setPicked(i);
                  if (!already) send({ t: "act", a: "mark", card: i });
                }
              }}
            >
              {inner}
            </button>
          );
        }
        return (
          <div key={i} className={cls} role="img" aria-label={label}>
            {inner}
          </div>
        );
      })}
    </div>
  );
}

/** Guessers: reveal the word you picked, or end the turn. Pinned to the bottom on phones. */
function GuessBar({
  view,
  you,
  picked,
  setPicked,
  send,
}: {
  view: CodewordsView;
  you: string;
  picked: number | null;
  setPicked: (i: number | null) => void;
  send: Props["send"];
}) {
  const card = picked !== null ? view.board[picked] : null;
  const live = card && !card.revealed;
  return (
    <div className="ready-bar cw-guess-bar" role="region" aria-label="Your guess">
      <Btn
        variant="go"
        disabled={!live}
        onClick={() => {
          if (picked === null) return;
          sfx.pop();
          send({ t: "act", a: "reveal", card: picked });
          setPicked(null);
        }}
      >
        {live ? `Reveal ${card!.word}` : "Tap a word to pick it"}
      </Btn>
      <Btn
        variant="ghost"
        disabled={view.guessed_this_turn === 0}
        onClick={() => {
          if (picked !== null && view.board[picked]?.marks.includes(you)) send({ t: "act", a: "mark", card: picked });
          setPicked(null);
          send({ t: "act", a: "pass" });
        }}
      >
        End turn
      </Btn>
    </div>
  );
}

function Teams({ view, you }: { view: CodewordsView; you: string }) {
  return (
    <div className="cw-teams">
      {(["red", "blue"] as CwTeam[]).map((t) => (
        <Card key={t} className={`cw-team-card ${t} ${view.turn === t && view.phase !== "final" ? "on" : ""}`}>
          <h3>
            {ICON[t]} {TEAM_NAME[t]} <span className="muted">{view.left[t]} left</span>
          </h3>
          <ul className="cw-members">
            {members(view, t).map((p) => (
              <li key={p.id}>
                <span className="cw-role">{view.spymasters[t] === p.id ? "🕵️" : "🔎"}</span>
                <b>{p.name}</b>
                {p.id === you ? " (you)" : ""}
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

/** Each clue with what was guessed from it. */
function ClueLog({ view }: { view: CodewordsView }) {
  const turns: { clue: Extract<CwLog, { type: "clue" }> | null; team: CwTeam; items: CwLog[] }[] = [];
  for (const e of view.log) {
    if (e.type === "clue") turns.push({ clue: e, team: e.team, items: [] });
    else if (e.type === "timeout") turns.push({ clue: null, team: e.team, items: [e] });
    else turns[turns.length - 1]?.items.push(e);
  }
  if (!turns.length) return null;
  return (
    <Card>
      <h3>Clues so far</h3>
      <ol className="cw-log">
        {[...turns].reverse().map((t, i) => (
          <li key={i} className={t.team}>
            <span className="cw-log-clue">
              {ICON[t.team]} {t.clue ? `${t.clue.word} ${t.clue.count === 0 ? "∞" : t.clue.count}` : "No clue in time"}
            </span>
            <span className="cw-log-guesses">
              {t.items
                .filter((e): e is Extract<CwLog, { type: "guess" }> => e.type === "guess")
                .map((e) => `${ICON[e.color]} ${e.word}`)
                .join("  ")}
              {t.items.some((e) => e.type === "pass") ? "  · ended turn" : ""}
            </span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
