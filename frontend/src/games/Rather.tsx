import { useState } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useCountUp, useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { RatherResult, RatherView } from "../types";

interface Props {
  view: RatherView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const SIDES = ["a", "b"] as const;

export function Rather({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const me = tv ? null : view.you;
  const name = (pid: string) => (pid === you && !tv ? "You" : nameOf(view.players, pid));
  const hotName = nameOf(view.players, view.hot);
  const r = view.result;

  useOnChange(view.phase, (_, phase) => {
    if (phase === "reveal" && r) {
      if (!tv && r.right.includes(you)) {
        sfx.fanfare();
        show.stinger("MIND READER!");
      } else if (!tv && r.hot === you && r.right.length > 0) {
        sfx.fanfare();
        show.stinger(`+${r.gains[you] ?? 0}`);
      } else sfx.ding();
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });

  const sign =
    view.phase === "final"
      ? "Final scores"
      : `Round ${view.round} of ${view.rounds} · ${view.phase === "pick" ? "Answer" : "The reveal"}`;
  return (
    <div className={`seg-rather stack yr ${tv ? "big tv-cols" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Would You Rather" remaining={view.phase === "final" ? null : view.remaining} receivedAt={receivedAt}>
        {view.phase !== "final" && (
          <p className="yr-tags">
            <span className="chip plum">
              <span aria-hidden="true">🔥</span> Hot seat: {view.hot === you && !tv ? "you!" : hotName}
            </span>
          </p>
        )}
      </ShowHead>

      <div className={`stack ${tv ? "tv-main" : ""}`}>
        {view.phase === "pick" && <HotSeat view={view} you={you} tv={tv} />}
        {view.phase === "pick" && (me ? <Answer key={view.round} view={view} send={send} hotName={hotName} /> : <Dilemma view={view} />)}
        {view.phase === "reveal" && r && <Reveal view={view} r={r} you={you} tv={tv} name={name} />}
        {view.phase === "final" && <Final view={view} you={you} tv={tv} name={name} />}
      </div>
      {view.phase === "pick" && <Locked view={view} you={you} tv={tv} />}
      {view.phase !== "final" && <Scores view={view} you={you} tv={tv} />}
    </div>
  );
}

function HotSeat({ view, you, tv }: { view: RatherView; you: string; tv: boolean }) {
  const mine = view.hot === you && !tv;
  const who = view.players.find((p) => p.id === view.hot);
  return (
    <Card tone="stage" className="yr-hot center">
      <Avatar pid={view.hot} name={who?.name ?? "?"} className="xl" />
      <p className="sign space-top">{mine ? "You’re in the hot seat!" : `${who?.name ?? "?"} is in the hot seat`}</p>
      <p className="lead space-top">{mine ? "Answer honestly: your friends are guessing what you’d pick." : `Answer for yourself, then guess what ${who?.name ?? "they"} picked.`}</p>
    </Card>
  );
}

/** The two choices, read-only (the TV, the audience). */
function Dilemma({ view, chosen }: { view: RatherView; chosen?: number | null }) {
  return (
    <div className="yr-pair" role="group" aria-label="Would you rather">
      {SIDES.map((side, i) => (
        <div key={side} className={`yr-choice ${side} ${chosen === i ? "chosen" : chosen != null ? "dim" : ""}`}>
          <span className="yr-letter" aria-hidden="true">
            {side.toUpperCase()}
          </span>
          <span className="yr-text">{view.dilemma[side]}</span>
        </div>
      ))}
      <span className="yr-or" aria-hidden="true">
        OR
      </span>
    </div>
  );
}

function Answer({ view, send, hotName }: { view: RatherView; send: Props["send"]; hotName: string }) {
  const me = view.you!;
  const [pick, setPick] = useState<number | null>(null);
  const [guess, setGuess] = useState<number | null>(null);
  const locked = me.pick !== null;
  const ready = pick !== null && (me.hot || guess !== null);
  if (locked) {
    return (
      <Card className="center">
        <p className="sign">Locked in</p>
        <p className="lead space-top">
          You’d rather <b>{me.pick === 0 ? view.dilemma.a : view.dilemma.b}</b>.
        </p>
        {!me.hot && me.guess !== null && (
          <p className="space-top">
            You think {hotName} would rather <b>{me.guess === 0 ? view.dilemma.a : view.dilemma.b}</b>.
          </p>
        )}
      </Card>
    );
  }
  return (
    <Card>
      <h3 id="yr-you">Would you rather…</h3>
      <Choices view={view} value={pick} onPick={setPick} label="yr-you" />
      {!me.hot && (
        <>
          <h3 id="yr-guess" className="space-top">
            What would {hotName} rather?
          </h3>
          <Choices view={view} value={guess} onPick={setGuess} label="yr-guess" />
        </>
      )}
      <Btn
        className="space-top"
        variant="accent"
        size="big"
        block
        disabled={!ready}
        onClick={() => {
          sfx.pop();
          send({ t: "act", a: "answer", pick, ...(me.hot ? {} : { guess }) });
        }}
      >
        {ready ? "Lock it in!" : me.hot ? "Pick one" : pick === null ? "Pick yours first" : `Now guess ${hotName}’s`}
      </Btn>
    </Card>
  );
}

function Choices({ view, value, onPick, label }: { view: RatherView; value: number | null; onPick: (n: number) => void; label: string }) {
  return (
    <div className="yr-pair space-top" role="group" aria-labelledby={label}>
      {SIDES.map((side, i) => (
        <button
          key={side}
          type="button"
          className={`yr-choice ${side} ${value === i ? "chosen" : value !== null ? "dim" : ""}`}
          aria-pressed={value === i}
          onClick={() => {
            sfx.tick();
            onPick(i);
          }}
        >
          <span className="yr-letter" aria-hidden="true">
            {side.toUpperCase()}
          </span>
          <span className="yr-text">{view.dilemma[side]}</span>
        </button>
      ))}
      <span className="yr-or" aria-hidden="true">
        OR
      </span>
    </div>
  );
}

/** Who has locked in (never what). */
function Locked({ view, you, tv }: { view: RatherView; you: string; tv: boolean }) {
  return (
    <Card tone="soft">
      <p className="center" aria-live="polite">
        <b>{view.locked.length}</b> of {view.players.length} locked in
      </p>
      <ul className="yr-locks space-top" aria-label="Players">
        {view.players.map((p) => {
          const done = view.locked.includes(p.id);
          return (
            <li key={p.id} className={done ? "done" : ""}>
              <Avatar pid={p.id} name={p.name} />
              <span className="yr-lock-name">{p.id === you && !tv ? "You" : p.name.split(/\s+/)[0]}</span>
              <span aria-hidden="true">{done ? "✅" : p.id === view.hot ? "🔥" : "🤔"}</span>
              <span className="sr-only">{done ? ", locked in" : ", still deciding"}</span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Reveal({ view, r, you, tv, name }: { view: RatherView; r: RatherResult; you: string; tv: boolean; name: (p: string) => string }) {
  const choice = r.choice === null ? null : view.dilemma[SIDES[r.choice]!];
  const total = Math.max(1, r.split[0] + r.split[1]);
  return (
    <>
      <Card tone="stage" className="center">
        <p className="sign">{r.hot === you && !tv ? "You said" : `${nameOf(view.players, r.hot)} would rather`}</p>
        <p className="yr-answer space-top">{choice ? choice : "…ran out of time!"}</p>
      </Card>
      <Dilemma view={view} chosen={r.choice} />
      <Card>
        <h3>How the room split</h3>
        <ul className="yr-split space-top">
          {SIDES.map((side, i) => {
            const who = view.players.filter((p) => r.picks[p.id] === i);
            return (
              <li key={side} className={side}>
                <span className="yr-split-head">
                  <b>{view.dilemma[side]}</b>
                  <span className="yr-split-n">{r.split[i]}</span>
                </span>
                <meter className={`yr-bar ${side}`} min={0} max={total} value={r.split[i]} aria-hidden="true" />
                <span className="yr-split-who">
                  {who.map((p) => (
                    <Avatar key={p.id} pid={p.id} name={p.name} className="tiny" />
                  ))}
                  <span className="sr-only">{who.map((p) => p.name).join(", ")}</span>
                </span>
              </li>
            );
          })}
        </ul>
      </Card>
      <Card>
        <h3>{r.choice === null ? "No answer, no points" : r.right.length ? `${r.right.length} read ${nameOf(view.players, r.hot)} right` : `Nobody saw that coming!`}</h3>
        <ul className="yr-rows space-top">
          {view.players
            .filter((p) => p.id !== r.hot)
            .map((p) => {
              const g = r.guesses[p.id];
              const ok = r.right.includes(p.id);
              return (
                <li key={p.id} className={ok ? "ok" : ""}>
                  <Avatar pid={p.id} name={p.name} />
                  <span className="yr-row-name">
                    <b>{name(p.id)}</b>
                    <span className="muted">{g === undefined ? "no guess" : `guessed ${g === 0 ? "A" : "B"}`}</span>
                  </span>
                  <span className={`chip ${ok ? "teal" : ""}`}>{ok ? `+${r.gains[p.id]}` : "0"}</span>
                </li>
              );
            })}
          <li className="hot">
            <Avatar pid={r.hot} name={nameOf(view.players, r.hot)} />
            <span className="yr-row-name">
              <b>{name(r.hot)}</b>
              <span className="muted">in the hot seat: 50 per right guess</span>
            </span>
            <span className={`chip ${(r.gains[r.hot] ?? 0) > 0 ? "teal" : ""}`}>+{r.gains[r.hot] ?? 0}</span>
          </li>
        </ul>
      </Card>
    </>
  );
}

function Score({ value }: { value: number }) {
  return <>{useCountUp(value)}</>;
}

function Scores({ view, you, tv }: { view: RatherView; you: string; tv: boolean }) {
  const rows = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  return (
    <Card>
      <h3>Scores</h3>
      <ol className="score-rows yr-scores">
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

function Final({ view, you, tv, name }: { view: RatherView; you: string; tv: boolean; name: (p: string) => string }) {
  const rows = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  const reads = (pid: string) => (view.history ?? []).filter((h) => h.right.includes(pid)).length;
  const top = view.scores[rows[0]?.id ?? ""] ?? 0;
  const tied = rows.filter((p) => (view.scores[p.id] ?? 0) === top).length > 1;
  const known = (pid: string) => (view.history ?? []).filter((h) => h.hot === pid).reduce((n, h) => n + h.right.length, 0);
  return (
    <>
      <Card>
        <p className="sign center">
          {!rows[0] || tied ? "It’s a tie: you all know each other!" : `${name(rows[0].id)} ${rows[0].id === you && !tv ? "know" : "knows"} the room best!`}
        </p>
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
                <span className="muted">
                  read {reads(p.id)} right · read by {known(p.id)}
                </span>
              </span>
              <span className="score-pts">{view.scores[p.id] ?? 0}</span>
            </li>
          ))}
        </ol>
      </Card>
      <Card>
        <details className="how-to">
          <summary>Every hot seat ({view.history?.length ?? 0})</summary>
          <ol className="yr-history">
            {(view.history ?? []).map((h, i) => (
              <li key={i}>
                <b>{nameOf(view.players, h.hot)}</b> would rather <b>{h.choice === null ? "…(no answer)" : h.choice === 0 ? h.a : h.b}</b>
                <span className="muted"> than {h.choice === 0 ? h.b : h.a} · {h.right.length} guessed it</span>
              </li>
            ))}
          </ol>
        </details>
      </Card>
    </>
  );
}
