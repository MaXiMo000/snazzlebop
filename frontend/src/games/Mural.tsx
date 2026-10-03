import { useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { MuralView } from "../types";

interface Props {
  view: MuralView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen: never sees the painting */
  tv?: boolean;
}

const SIGN: Record<string, string> = {
  briefing: "Briefing",
  hint: "Hint round",
  vote: "Find the Mole",
  mole_guess: "Last chance",
  final: "Unmasked",
};

export function Mural({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  useOnChange(view.phase, (_, phase) => {
    if (phase === "mole_guess") {
      sfx.ding();
      show.stinger("MOLE SPOTTED!");
    } else if (phase === "final" && view.result) {
      const r = view.result;
      const missed = r.caught.filter((m) => !r.stole.includes(m));
      const roomWon = missed.length > 0;
      const iWon = tv ? roomWon : r.moles.includes(you) ? !r.caught.includes(you) || r.stole.includes(you) : roomWon;
      show.stinger(r.stole.length ? "STOLEN!" : roomWon ? "GOTCHA!" : "THE MOLE ESCAPED!", roomWon ? "good" : "bad");
      if (iWon) {
        sfx.fanfare();
        show.celebrate();
      } else sfx.buzz();
    }
  });
  useOnChange(view.hints.length, (prev, next) => {
    if (next > prev) sfx.ding();
  });
  const sign = view.phase === "hint" ? `Hint round ${view.round} of ${view.rounds}` : (SIGN[view.phase] ?? view.phase);
  return (
    <div className="seg-mural stack">
      {show.node}
      <ShowHead sign={sign} title="Mole in the Mural" remaining={view.remaining} receivedAt={receivedAt} />
      {!tv && view.phase !== "final" && <Role view={view} />}
      <div key={`${view.phase}-${view.round}`} className="stack enter">
        {view.phase === "briefing" && (
          <Card tone="soft">
            <h3>How it works</h3>
            <p>
              Everyone knows which tile is the secret <b>painting</b>, except the Mole. Each hint round, pick a tile that
              shares a <b>colour</b> or a <b>kind</b> with the painting. Hints are revealed together. Then find the Mole.
            </p>
            {view.moles > 1 && (
              <p>
                <b>Two Moles tonight.</b> They don’t know about each other. The two most-voted players are accused.
              </p>
            )}
            <p className="muted">Careful: each Mole can secretly swap their hint with someone else’s once.</p>
          </Card>
        )}
        {view.phase === "mole_guess" && (
          <Card tone="stage" className="center">
            <p className="sign">Mole spotted</p>
            <p className="lead space-top">
              {view.caught.map((id) => nameOf(view.players, id)).join(" and ")}{" "}
              {view.caught.length > 1 ? "were Moles" : "was a Mole"}! One guess each at the painting to steal the win…
            </p>
          </Card>
        )}
        {view.phase === "final" && view.result && <Result view={view} you={you} tv={tv} />}
        <Board view={view} you={you} send={send} tv={tv} />
        {view.phase === "vote" && !tv && <Vote view={view} you={you} send={send} />}
        {view.phase === "vote" && tv && (
          <Card tone="soft" className="center">
            <p className="lead" aria-live="polite">
              {view.votes_in} of {view.players.length} votes in
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}

function Role({ view }: { view: MuralView }) {
  if (view.you.is_mole) {
    return (
      <Card tone="stage">
        <p className="sign">Top secret</p>
        <p className="space-top">
          You’re {view.moles > 1 ? "a" : "the"} <b>Mole</b>. You don’t know the painting. Watch the hints, blend in, and
          if they catch you, guess the painting to steal the win.
          {view.moles > 1 ? " There’s one other Mole, and neither of you knows who the other is." : ""}
        </p>
        {view.you.swap_with && (
          <p className="space-top">
            🔀 Your hint will swap places with <b>{nameOf(view.players, view.you.swap_with)}</b>’s in this round’s reveal.
          </p>
        )}
      </Card>
    );
  }
  const t = view.you.target != null ? view.mural[view.you.target] : null;
  return t ? (
    <Card tone="soft" className="center">
      <p>The painting is</p>
      <p className="lead">
        <span aria-hidden="true">{t.emoji} </span>
        <b>{t.name}</b> · {t.color} · {t.kind}
      </p>
    </Card>
  ) : null;
}

function Board({ view, you, send, tv }: { view: MuralView; you: string; send: Props["send"]; tv: boolean }) {
  const [chosen, setChosen] = useState<number | null>(null);
  const hinting = !tv && view.phase === "hint" && view.your_hint === null;
  const guessing = !tv && view.phase === "mole_guess" && view.caught.includes(you) && !view.you.guessed;
  const used = new Set(view.your_hints); // your real hints: the public ones may show a swap
  const final = view.result;
  const badges = (i: number) =>
    view.hints.flatMap((h, r) =>
      Object.entries(h)
        .filter(([, tile]) => tile === i)
        .map(([pid]) => ({ pid, r })),
    );
  const pickable = hinting || guessing;
  return (
    <Card>
      <h3>The mural</h3>
      <div className="mural" role="group" aria-label="The mural, 16 tiles">
        {view.mural.map((t, i) => {
          const isTarget = (final ? final.target : view.you.target) === i;
          const mine = view.your_hint === i;
          return (
            <button
              key={i}
              type="button"
              className={`tile ${isTarget ? "target" : ""} ${mine ? "mine" : ""} ${
                final && Object.values(final.guesses).includes(i) ? "guessed" : ""
              }`}
              aria-pressed={pickable ? chosen === i : undefined}
              disabled={!pickable || (hinting && used.has(i))}
              onClick={() => setChosen(i)}
            >
              <span className="emoji" aria-hidden="true">
                {t.emoji}
              </span>
              <span className="tile-name">{t.name}</span>
              <span className="tile-tags">
                {t.color} · {t.kind}
              </span>
              {isTarget && <span className="sr-only"> (the painting)</span>}
              {badges(i).length > 0 && (
                <span className="tile-hints">
                  {badges(i).map(({ pid, r }) => (
                    <span key={`${pid}-${r}`} className="chip paper">
                      {nameOf(view.players, pid)}
                    </span>
                  ))}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {view.phase === "hint" && (
        <div className="row space-top">
          {hinting ? (
            <Btn
              variant="accent"
              size="big"
              disabled={chosen === null}
              onClick={() => {
                sfx.pop();
                send({ t: "act", a: "hint", tile: chosen });
                setChosen(null);
              }}
            >
              {chosen === null ? "Pick a tile" : `Hint: ${view.mural[chosen]!.name}`}
            </Btn>
          ) : null}
          <p className="muted" aria-live="polite">
            {view.your_hint !== null && !tv ? `Your hint: ${view.mural[view.your_hint]!.name}. ` : ""}
            {view.hinted.length} of {view.players.length} hints in
          </p>
        </div>
      )}
      {view.swapped_rounds.length > 0 && (
        <p className="space-top">
          <span className="chip cherry">
            🔀 A Mole swapped two hints in round {view.swapped_rounds.join(" and ")}. Who? That’s for you to work out.
          </span>
        </p>
      )}
      {!tv && view.phase === "hint" && view.you.can_swap && <Swap view={view} you={you} send={send} />}
      {guessing && (
        <div className="row space-top">
          <Btn
            variant="danger"
            size="big"
            disabled={chosen === null}
            onClick={() => send({ t: "act", a: "guess", tile: chosen })}
          >
            {chosen === null ? "Pick your guess" : `It’s the ${view.mural[chosen]!.name}!`}
          </Btn>
        </div>
      )}
    </Card>
  );
}

function Swap({ view, you, send }: { view: MuralView; you: string; send: Props["send"] }) {
  const [target, setTarget] = useState("");
  return (
    <div className="ask-form space-top">
      <div>
        <label className="field" htmlFor="swap-target">
          Switcheroo (once): swap your hint with
        </label>
        <select id="swap-target" value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Pick a player…</option>
          {view.players
            .filter((p) => p.id !== you)
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
        </select>
      </div>
      <Btn
        variant="danger"
        disabled={!target}
        onClick={() => {
          sfx.pop();
          send({ t: "act", a: "swap", target });
        }}
      >
        Swap hints
      </Btn>
    </div>
  );
}

function Vote({ view, you, send }: { view: MuralView; you: string; send: Props["send"] }) {
  return (
    <Card>
      <h3>Who’s the Mole?</h3>
      <p>
        {view.moles > 1
          ? "The two most-voted players are accused. A tie at second place accuses only the top one."
          : "Most votes wins. If the Mole isn’t the single top pick, they escape."}{" "}
        <span aria-live="polite">
          {view.votes_in}/{view.players.length} votes in.
        </span>
      </p>
      <div className="vote-grid">
        {view.players
          .filter((p) => p.id !== you)
          .map((p) => (
            <Btn
              key={p.id}
              variant="danger"
              aria-pressed={view.you_voted === p.id}
              onClick={() => {
                sfx.pop();
                send({ t: "act", a: "vote", target: p.id });
              }}
            >
              {p.name}
              {view.you_voted === p.id ? " ✓" : ""}
            </Btn>
          ))}
      </div>
    </Card>
  );
}

function Result({ view, you, tv }: { view: MuralView; you: string; tv: boolean }) {
  const r = view.result!;
  const painting = view.mural[r.target]!;
  const missed = r.caught.filter((m) => !r.stole.includes(m));
  const iWon = r.moles.includes(you) ? !r.caught.includes(you) || r.stole.includes(you) : missed.length > 0;
  const personal = tv ? "" : iWon ? " 🎉 You win this one." : " Better luck next time.";
  const fate = (m: string) =>
    !r.caught.includes(m)
      ? "escaped"
      : r.stole.includes(m)
        ? "was caught but named the painting and stole the win"
        : `was caught, and guessed ${r.guesses[m] != null ? `the ${view.mural[r.guesses[m]!]!.name}` : "nothing"}`;
  return (
    <Card tone="stage" className="center">
      <p className="sign">{r.stole.length ? "Stolen!" : missed.length ? "Gotcha!" : "The Mole escaped!"}</p>
      <p className="lead space-top">
        The painting was the{" "}
        <b>
          <span aria-hidden="true">{painting.emoji} </span>
          {painting.name}
        </b>
        .
      </p>
      <ul className="evidence">
        {r.moles.map((m) => (
          <li key={m}>
            🕶️ <b>{nameOf(view.players, m)}</b> {fate(m)}.
          </li>
        ))}
        {r.swaps.map((s) => (
          <li key={s.by}>
            🔀 {nameOf(view.players, s.by)} swapped hints with {nameOf(view.players, s.with)} in round {s.round + 1}.
          </li>
        ))}
      </ul>
      <p>{personal}</p>
    </Card>
  );
}
