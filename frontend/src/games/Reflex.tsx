import { Avatar } from "../components/avatar";
import { Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { ReflexView } from "../types";

interface Props {
  view: ReflexView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

export function Reflex({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const name = (pid: string) => nameOf(view.players, pid);
  const me = tv ? null : view.you;
  const live = view.phase === "wait" || view.phase === "go";
  const r = view.result;

  useOnChange(view.phase, (_, phase) => {
    if (phase === "go") sfx.ding();
    else if (phase === "result" && r) {
      if (r.winner === you && !tv) {
        sfx.fanfare();
        show.stinger(`${r.times[you]} ms!`);
      } else if (!r.winner) {
        sfx.buzz();
        show.stinger("NOBODY!", "bad");
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE DUEL!");
      show.celebrate();
    }
  });
  useOnChange(view.fake?.n ?? 0, (_, n) => {
    if (n) sfx.pop();
  });
  useOnChange(view.early.length, (was, now) => {
    if (now > was) sfx.buzz();
  });

  const tap = () => {
    if (!me || !live || me.early || me.tapped) return;
    send({ t: "act", a: "tap" });
  };
  // What the pad says. Only the exact word TAP! (always green) counts.
  const pad = me?.early
    ? { cls: "early", word: "Too early!", sub: "−50. Sit this one out." }
    : me?.tapped
      ? { cls: "done", word: "Got it!", sub: "Waiting for the others…" }
      : view.phase === "go"
        ? { cls: "go", word: "TAP!", sub: "" }
        : view.fake
          ? { cls: `fake t${view.fake.tone}`, word: view.fake.word, sub: "" }
          : { cls: "wait", word: "Wait…", sub: "Only tap on TAP!" };
  const sign =
    view.phase === "final"
      ? "Final scores"
      : `Round ${view.round} of ${view.rounds} · ${view.phase === "result" ? "Result" : view.phase === "go" ? "Go!" : "Wait for it"}`;
  const slowest = r ? Math.max(1, ...Object.values(r.times)) : 1;

  return (
    <div className="seg-reflex stack rx">
      {show.node}
      <ShowHead sign={sign} title="Reaction Duel" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">Only the exact word TAP! counts</span>
      </ShowHead>

      {live &&
        (tv ? (
          <div key={`${view.phase}:${view.fake?.n ?? 0}`} className={`rx-pad big ${pad.cls}`} role="status">
            <span className="rx-word">{pad.word}</span>
          </div>
        ) : (
          <button
            type="button"
            className={`rx-pad ${pad.cls}`}
            disabled={!me || me.early || me.tapped}
            onPointerDown={(e) => {
              if (e.button === 0) tap();
            }}
            onKeyDown={(e) => {
              if ((e.key === " " || e.key === "Enter") && !e.repeat) {
                e.preventDefault();
                tap();
              }
            }}
          >
            <span key={`${view.phase}:${view.fake?.n ?? 0}:${pad.cls}`} className="rx-word" aria-live="assertive">
              {pad.word}
            </span>
            {pad.sub && <span className="rx-sub">{pad.sub}</span>}
          </button>
        ))}

      {live && (
        <ul className="rx-people" aria-label="Players">
          {view.players.map((p) => {
            const early = view.early.includes(p.id);
            const tapped = view.tapped.includes(p.id);
            return (
              <li key={p.id} className={early ? "early" : tapped ? "tapped" : ""}>
                <Avatar pid={p.id} name={p.name} />
                <span className="rx-name">{p.id === you && !tv ? "You" : p.name.split(/\s+/)[0]}</span>
                <span className="rx-state" aria-hidden="true">
                  {early ? "❌" : tapped ? "✅" : "👀"}
                </span>
                <span className="sr-only">{early ? ", tapped too early" : tapped ? ", tapped" : ", waiting"}</span>
              </li>
            );
          })}
        </ul>
      )}

      {view.phase === "result" && r && (
        <Card tone="stage">
          <p className="sign center">{r.winner ? `${r.winner === you && !tv ? "You were" : `${name(r.winner)} was`} fastest` : "Nobody tapped in time"}</p>
          <ol className="rx-times space-top">
            {Object.entries(r.times).map(([pid, ms], i) => (
              <li key={pid} className={`rx-time w${Math.max(1, Math.round((ms / slowest) * 10))} ${i === 0 ? "first" : ""}`}>
                <span className="rx-time-who">
                  <Avatar pid={pid} name={name(pid)} />
                  <b>{pid === you && !tv ? "You" : name(pid)}</b>
                </span>
                <span className="rx-bar" aria-hidden="true" />
                <span className="rx-ms">
                  {ms} ms <span className="rx-pts">+{r.points[pid]}</span>
                </span>
              </li>
            ))}
          </ol>
          {r.early.length > 0 && (
            <p className="rx-fell space-top">
              🙈 Fell for it: <b>{r.early.map((p) => (p === you && !tv ? "you" : name(p))).join(", ")}</b> (−50)
            </p>
          )}
        </Card>
      )}

      <Card>
        <h3>{view.phase === "final" ? "Final scores" : "Scores"}</h3>
        <ul className="score-rows">
          {[...view.players]
            .sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0))
            .map((p, i) => (
              <li key={p.id}>
                <b>
                  {view.phase === "final" && i === 0 ? "👑 " : ""}
                  {p.name}
                  {p.id === you && !tv ? " (you)" : ""}
                  {view.best?.[p.id] !== undefined && <span className="rx-best muted">best {view.best[p.id]} ms</span>}
                </b>
                <span className="score-pts">{view.scores[p.id] ?? 0}</span>
              </li>
            ))}
        </ul>
      </Card>
    </div>
  );
}
