import { useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { CodesView } from "../types";

interface Props {
  view: CodesView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const FRUIT = ["🍎", "🍌", "🍇", "🍒", "🍋", "🥝"];
const FRUIT_NAME = ["apple", "banana", "grapes", "cherries", "lemon", "kiwi"];

function Code({ code, label }: { code: number[]; label: string }) {
  return (
    <span className="code" role="img" aria-label={`${label}: ${code.map((c) => FRUIT_NAME[c]).join(", ")}`}>
      {code.map((c, i) => (
        <span key={i} className="code-cell" aria-hidden="true">
          {FRUIT[c]}
        </span>
      ))}
    </span>
  );
}

/** Builds a code one symbol at a time from the fruit palette. */
function Composer({ length, onDone, action, disabled = false }: { length: number; onDone: (c: number[]) => void; action: string; disabled?: boolean }) {
  const [code, setCode] = useState<number[]>([]);
  return (
    <div className="stack-sm">
      <p className="code composing" aria-live="polite">
        {Array.from({ length }, (_, i) => (
          <span key={i} className="code-cell">
            <span aria-hidden="true">{code[i] !== undefined ? FRUIT[code[i]!] : "·"}</span>
          </span>
        ))}
        <span className="sr-only">{code.length ? code.map((c) => FRUIT_NAME[c]).join(", ") : "empty"}</span>
      </p>
      <div className="row" role="group" aria-label="Pick a symbol">
        {FRUIT.map((f, i) => (
          <Btn key={f} size="small" variant="ghost" aria-label={FRUIT_NAME[i]} disabled={code.length >= length} onClick={() => setCode((c) => [...c, i])}>
            <span aria-hidden="true" className="fruit">
              {f}
            </span>
          </Btn>
        ))}
      </div>
      <div className="row">
        <Btn
          variant="accent"
          disabled={code.length !== length || disabled}
          onClick={() => {
            sfx.pop();
            onDone(code);
            setCode([]);
          }}
        >
          {action}
        </Btn>
        <Btn variant="ghost" disabled={!code.length} onClick={() => setCode((c) => c.slice(0, -1))}>
          Undo
        </Btn>
      </div>
    </div>
  );
}

export function Codes({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const crackedByMe = Object.entries(view.cracked)
    .filter(([, who]) => who.includes(you))
    .map(([owner]) => owner);
  useOnChange(crackedByMe.length, (prev, next) => {
    if (next > prev && !tv) {
      sfx.fanfare();
      show.stinger("CRACKED!");
    }
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "final") {
      sfx.fanfare();
      show.stinger("TIME'S UP!");
      show.celebrate();
    }
  });
  const targets = view.players.filter((p) => p.id !== you && !crackedByMe.includes(p.id));
  const [target, setTarget] = useState<string>("");
  const [decoy, setDecoy] = useState(false);
  const current = targets.find((p) => p.id === target)?.id ?? targets[0]?.id ?? "";
  const sign = view.phase === "set" ? "Set your secret code" : view.phase === "crack" ? "Crack them all!" : "Codes revealed";
  return (
    <div className="seg-codes stack">
      {show.node}
      <ShowHead sign={sign} title="Code Crackers" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">● right fruit, right place · ○ right fruit, wrong place</span>
      </ShowHead>

      {!tv && view.phase === "set" && (
        <Card tone="soft">
          {view.you.code.length ? (
            <p className="lead center">
              Your code is set: <Code code={view.you.code} label="Your code" />. Waiting for {view.players.length - view.set.length} more…
            </p>
          ) : (
            <>
              <h3>Hide your code</h3>
              <p className="muted">Four fruit, repeats allowed. Make it hard to guess!</p>
              <label className="check">
                <input type="checkbox" checked={decoy} onChange={(e) => setDecoy(e.target.checked)} />
                <span>🎭 Arm a decoy: the first guess on my code gets fake clues</span>
              </label>
              <Composer length={view.length} action="Lock my code" onDone={(code) => send({ t: "act", a: "set", code, decoy })} />
            </>
          )}
        </Card>
      )}
      {tv && view.phase === "set" && (
        <Card tone="soft" className="center">
          <p className="lead">
            {view.set.length} of {view.players.length} codes hidden
          </p>
        </Card>
      )}

      {!tv && view.phase === "crack" && (
        <Card tone="soft">
          <p>
            Your code: <Code code={view.you.code} label="Your code" />
            {view.you.decoy ? " · 🎭 decoy armed" : view.decoy_sprung.includes(you) ? " · 🎭 your decoy fooled someone!" : ""}
          </p>
          {targets.length === 0 ? (
            <p className="lead">You’ve cracked every code! 🎉</p>
          ) : (
            <>
              <div className="row space-top" role="group" aria-label="Whose code to crack">
                {targets.map((p) => (
                  <Btn key={p.id} size="small" variant="ghost" aria-pressed={current === p.id} onClick={() => setTarget(p.id)}>
                    {p.name}
                  </Btn>
                ))}
              </div>
              <h3 className="space-top">Cracking {nameOf(view.players, current)}</h3>
              {(view.you.hints[current] ?? []).length > 0 && (
                <p>
                  Hints:{" "}
                  {(view.you.hints[current] ?? []).map((h) => `position ${h.pos + 1} is ${FRUIT_NAME[h.symbol]}`).join(" · ")}
                </p>
              )}
              {(view.you.hints[current] ?? []).length < view.max_hints && (
                <Btn size="small" variant="ghost" onClick={() => send({ t: "act", a: "hint", target: current })}>
                  💡 Buy a hint (−{view.hint_cost})
                </Btn>
              )}
              <ol className="guess-list">
                {(view.you.guesses[current] ?? []).map((g, i) => (
                  <li key={i}>
                    <Code code={g.code} label={`Guess ${i + 1}`} />
                    <span className="pegs" role="img" aria-label={`${g.hits} right place, ${g.near} wrong place`}>
                      <span aria-hidden="true">
                        {"●".repeat(g.hits)}
                        {"○".repeat(g.near)}
                      </span>
                    </span>
                    {g.decoy && <span className="chip cherry">🎭 decoy! ignore this one</span>}
                  </li>
                ))}
              </ol>
              <Composer
                length={view.length}
                action="Guess"
                onDone={(code) => send({ t: "act", a: "guess", target: current, code })}
              />
            </>
          )}
        </Card>
      )}

      <Card>
        <h3>Who’s cracked whom</h3>
        <ul className="evidence">
          {view.players.map((p) => {
            const by = view.cracked[p.id] ?? [];
            return (
              <li key={p.id}>
                <b>{p.name}</b>
                {p.id === you ? " (you)" : ""}’s code{" "}
                {view.codes?.[p.id] ? <Code code={view.codes[p.id]!} label={`${p.name}'s code`} /> : null}:{" "}
                {by.length ? `cracked by ${by.map((id) => nameOf(view.players, id)).join(", ")}` : "uncracked"} ·{" "}
                <span className="muted">
                  {view.guess_counts[p.id] ?? 0} guesses, {view.hint_counts[p.id] ?? 0} hints
                  {view.decoy_sprung.includes(p.id) ? " · 🎭 decoy sprung" : ""}
                </span>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}
