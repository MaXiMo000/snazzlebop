import { useEffect, useRef, useState } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { BombView } from "../types";

interface Props {
  view: BombView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

export function Bomb({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const [text, setText] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const name = (pid: string) => nameOf(view.players, pid);
  const n = view.order.length;
  // You sit at the bottom of the ring.
  const start = !tv && view.order.includes(you) ? view.order.indexOf(you) : 0;
  const seats = view.order.map((_, k) => view.order[(start + k) % n]!);
  const mine = !tv && view.phase === "pass" && view.holder === you;
  const at = view.holder ?? view.boom?.who ?? null;
  const seat = at ? seats.indexOf(at) : -1;

  useOnChange(view.holder, (_, holder) => {
    if (!holder) return;
    sfx.hop();
    if (holder === you && !tv) {
      setText("");
      input.current?.focus();
    }
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "boom" && view.boom) {
      sfx.buzz();
      show.stinger("BOOM!", view.boom.who === you && !tv ? "bad" : "good");
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger(view.winner === you && !tv ? "YOU SURVIVED!" : "LAST ONE STANDING!");
      if (view.winner === you && !tv) show.celebrate();
    }
  });
  // A tick while it's live. The pace is the same all the way: it gives nothing away about the fuse.
  useEffect(() => {
    if (view.phase !== "pass") return;
    const t = window.setInterval(() => sfx.tick(), 900);
    return () => window.clearInterval(t);
  }, [view.phase]);

  const sign =
    view.phase === "final"
      ? "Last one standing"
      : view.phase === "boom"
        ? `Round ${view.round} · boom!`
        : `Round ${view.round} · ${mine ? "YOU have the bomb!" : `${name(view.holder ?? "")} has the bomb`}`;
  const submit = () => {
    const t = text.trim();
    if (!t) return;
    send({ t: "act", a: "answer", text: t });
    setText("");
  };

  return (
    <div className={`seg-bomb stack bm ${mine ? "hot" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Hot Potato Bomb" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">Name {view.prompt}</span>
      </ShowHead>

      {view.phase !== "final" && (
        <Card tone="stage" className="bm-stage">
          <p className="bm-prompt">
            <span className="sign">Name…</span>
            <b>{view.prompt}</b>
          </p>
          <div className={`bm-ring seats-${n}`}>
            <ol className="bm-seats">
              {seats.map((pid, k) => (
                <li
                  key={pid}
                  className={`bm-seat lc-pos-${n}-${k} ${pid === at ? "on" : ""} ${view.lives[pid] ? "" : "out"}`}
                >
                  <Avatar pid={pid} name={name(pid)} tone={view.order.indexOf(pid)} className="bm-avatar" />
                  <span className="bm-name">{pid === you && !tv ? "You" : name(pid).split(/\s+/)[0]}</span>
                  <span className="bm-lives" aria-label={`${view.lives[pid]} lives`}>
                    {view.lives[pid] ? "❤️".repeat(Math.min(view.lives[pid]!, 5)) : "💀"}
                  </span>
                </li>
              ))}
            </ol>
            {seat >= 0 && (
              <span className={`bm-bomb lc-pos-${n}-${seat} ${view.phase === "boom" ? "boom" : ""}`} aria-hidden="true">
                {view.phase === "boom" ? "💥" : "💣"}
              </span>
            )}
            <p className="bm-count" aria-live="polite">
              {view.phase === "boom" && view.boom ? (
                <>
                  <b className="who">{view.boom.who === you && !tv ? "You" : name(view.boom.who).split(/\s+/)[0]}</b>
                  {view.boom.out ? " is out!" : " lost a life"}
                </>
              ) : (
                <>
                  <b>{view.count}</b> {view.count === 1 ? "pass" : "passes"}
                </>
              )}
            </p>
          </div>
        </Card>
      )}

      {mine && (
        <Card tone="soft" className="bm-answer">
          <form
            className="bm-form"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <label className="field" htmlFor="bm-input">
              Quick! Name {view.prompt}
            </label>
            <div className="bm-row">
              <input
                id="bm-input"
                ref={input}
                type="text"
                autoFocus
                autoComplete="off"
                autoCapitalize="none"
                enterKeyHint="send"
                maxLength={30}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <Btn type="submit" variant="go" disabled={text.trim().length < 2}>
                Pass it!
              </Btn>
            </div>
          </form>
        </Card>
      )}
      {!tv && view.phase === "pass" && !mine && (
        <p className="muted center" role="status">
          {view.lives[you] ? "Get an answer ready: you can’t repeat one already said." : "You’re out. Enjoy the show!"}
        </p>
      )}

      {view.phase !== "final" && view.answers.length > 0 && (
        <Card>
          <h3>Said so far</h3>
          <ol className="bm-said">
            {[...view.answers].reverse().map((a, i) => (
              <li key={`${view.count - i}`} className={i === 0 ? "new" : ""}>
                <b>{a.text}</b> <span className="muted">· {a.by === you && !tv ? "you" : name(a.by)}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}

      {view.phase === "final" && (
        <>
          <Card tone="stage" className="center">
            <p className="bm-trophy" aria-hidden="true">
              🏆
            </p>
            <h3>{view.winner ? `${view.winner === you && !tv ? "You" : name(view.winner)} survived!` : "Nobody survived!"}</h3>
          </Card>
          <Card>
            <h3>Final scores</h3>
            <ul className="score-rows">
              {[...view.players]
                .sort((a, b) => (view.scores?.[b.id] ?? 0) - (view.scores?.[a.id] ?? 0))
                .map((p) => (
                  <li key={p.id}>
                    <b>
                      {p.id === view.winner ? "👑 " : ""}
                      {p.name}
                      {p.id === you && !tv ? " (you)" : ""}
                    </b>
                    <span className="muted"> {view.passes[p.id] ?? 0} passes</span>
                    <span className="score-pts">{view.scores?.[p.id] ?? 0}</span>
                  </li>
                ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}
