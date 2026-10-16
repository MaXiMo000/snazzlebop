import { useEffect, useRef } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { OnHeadView } from "../types";

interface Props {
  view: OnHeadView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

type Orientation = { requestPermission?: () => Promise<string> };

/** Forehead mode: on iPhones the tilt sensor needs permission, asked from the tap that turns it on. */
async function allowTilt(): Promise<void> {
  const ask = (window.DeviceOrientationEvent as unknown as Orientation | undefined)?.requestPermission;
  if (ask) {
    try {
      await ask();
    } catch {
      /* no tilt: the buttons still work */
    }
  }
}

/** Tilt down (screen to the floor) = got it, tilt up (screen to the ceiling) = pass; back to level re-arms. */
function useTilt(active: boolean, onGot: () => void, onPass: () => void) {
  const base = useRef<number | null>(null);
  const armed = useRef(true);
  const handlers = useRef({ onGot, onPass });
  handlers.current = { onGot, onPass };
  useEffect(() => {
    if (!active) return;
    base.current = null;
    armed.current = true;
    const move = (e: DeviceOrientationEvent) => {
      if (e.beta == null) return;
      if (base.current == null) base.current = e.beta;
      const d = e.beta - base.current;
      if (armed.current && d > 50) {
        armed.current = false;
        handlers.current.onGot();
      } else if (armed.current && d < -50) {
        armed.current = false;
        handlers.current.onPass();
      } else if (Math.abs(d) < 20) armed.current = true;
    };
    window.addEventListener("deviceorientation", move);
    return () => window.removeEventListener("deviceorientation", move);
  }, [active]);
}

export function OnHead({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const mine = !tv && view.guesser === you;
  // A name never breaks across lines ("Bartholomew X" stays together in the big signs).
  const guesser = nameOf(view.players, view.guesser).replace(/ /g, "\u00a0");
  const mark = (kind: "got" | "pass") => {
    if (kind === "got") sfx.ding();
    else sfx.buzz();
    send({ t: "act", a: kind, n: view.n });
  };
  const forehead = mine && view.forehead && view.phase === "play";
  useTilt(forehead, () => mark("got"), () => mark("pass"));
  useOnChange(view.count, (was, now) => {
    if (now > was && (tv || mine)) sfx.ding();
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "play") show.stinger(mine ? "GO!" : `${guesser.toUpperCase()} IS GUESSING!`);
    else if (phase === "result") {
      sfx.fanfare();
      show.stinger(`${view.count} GOT!`);
    } else if (phase === "final") {
      sfx.fanfare();
      show.celebrate();
    }
  });
  const sign =
    view.phase === "final"
      ? "Final scores"
      : `Turn ${view.round} of ${view.rounds} · ${view.phase === "ready" ? "Get ready" : view.phase === "play" ? `${mine ? "You’re" : `${guesser} is`} guessing` : "Time!"}`;

  return (
    <div className={`seg-onhead stack oh ${tv ? "big" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="On Your Head" remaining={view.phase === "final" ? null : view.remaining} receivedAt={receivedAt}>
        {view.phase === "play" && (
          <p className="oh-count">
            <b>{view.count}</b> got so far
          </p>
        )}
      </ShowHead>

      {view.phase === "ready" && (
        <Card tone="stage" className="center">
          <Avatar pid={view.guesser} name={guesser} className="xl" />
          <p className="sign space-top">{mine ? "You’re up!" : `${guesser} is up next`}</p>
          <p className="lead space-top">
            {mine
              ? "Your friends see the words and give clues. Guess as many as you can!"
              : `Get your clues ready: describe each word without saying it. ${tv ? "" : "Tap Got it when they get it."}`}
          </p>
          {mine && <ForeheadSwitch on={view.forehead} send={send} />}
        </Card>
      )}

      {view.phase === "play" && !mine && !tv && view.word && (
        <Card tone="stage" className="oh-clue center">
          <p className="sign">Describe this to {guesser}</p>
          <p key={view.n} className="oh-word">
            {view.word}
          </p>
          <div className="oh-marks">
            <Btn variant="danger" size="big" onClick={() => mark("pass")}>
              Pass <span aria-hidden="true">✗</span>
            </Btn>
            <Btn variant="go" size="big" onClick={() => mark("got")}>
              Got it! <span aria-hidden="true">✓</span>
            </Btn>
          </div>
        </Card>
      )}

      {view.phase === "play" && (mine || tv) && !forehead && (
        <Card tone="stage" className="center">
          <p className="oh-guess">{mine ? "GUESS!" : `${guesser.toUpperCase()} IS GUESSING`}</p>
          <p className="lead">{mine ? "Listen to the clues and shout your answer." : "Clue-givers: describe it, don’t say it!"}</p>
          {mine && <ForeheadSwitch on={view.forehead} send={send} />}
        </Card>
      )}

      {forehead && view.word && (
        <div className="oh-forehead" role="dialog" aria-label="Forehead mode">
          <p key={view.n} className="oh-head-word">
            {view.word}
          </p>
          <p className="oh-head-hint" aria-hidden="true">
            Tilt down: got it · Tilt up: pass
          </p>
          <div className="oh-head-marks">
            <button type="button" className="oh-head-btn pass" onClick={() => mark("pass")}>
              Pass
            </button>
            <button type="button" className="oh-head-btn got" onClick={() => mark("got")}>
              Got it
            </button>
          </div>
          <button type="button" className="oh-head-exit" onClick={() => send({ t: "act", a: "forehead", on: false })}>
            Exit forehead mode
          </button>
        </div>
      )}

      {view.phase === "result" && (
        <Card>
          <h3>
            {guesser} got {view.got.length}!
          </h3>
          <ul className="oh-words space-top">
            {view.got.map((w, i) => (
              <li key={`g${i}`} className="got">
                <span aria-hidden="true">✓</span> {w}
              </li>
            ))}
            {view.passed.map((w, i) => (
              <li key={`p${i}`} className="passed">
                <span aria-hidden="true">✗</span> {w}
                <span className="sr-only"> (passed)</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Scores view={view} you={you} tv={tv} />
    </div>
  );
}

function ForeheadSwitch({ on, send }: { on: boolean; send: Props["send"] }) {
  return (
    <div className="oh-switch space-top">
      <Btn
        variant={on ? "gold" : "ghost"}
        aria-pressed={on}
        onClick={async () => {
          if (!on) await allowTilt();
          send({ t: "act", a: "forehead", on: !on });
        }}
      >
        <span aria-hidden="true">📱</span> {on ? "Forehead: on" : "Forehead"}
        <span className="sr-only"> mode</span>
      </Btn>
      <p className="muted">
        {on ? "When the turn starts, hold the phone to your forehead, screen facing out." : "Hold your phone to your head and tilt to answer."}
      </p>
    </div>
  );
}

function Scores({ view, you, tv }: { view: OnHeadView; you: string; tv: boolean }) {
  const rows = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  const top = view.scores[rows[0]?.id ?? ""] ?? 0;
  const tied = rows.filter((p) => (view.scores[p.id] ?? 0) === top).length > 1;
  return (
    <Card>
      <h3>{view.phase === "final" ? (tied || top === 0 ? "A tie at the top!" : `${nameOf(view.players, rows[0]!.id)} wins!`) : "Scores"}</h3>
      <ol className="score-rows">
        {rows.map((p, i) => (
          <li key={p.id}>
            <b>
              {view.phase === "final" && i === 0 && !tied && top > 0 ? "👑 " : ""}
              {p.name}
              {p.id === you && !tv ? " (you)" : ""}
            </b>
            <span className="score-pts">{view.scores[p.id] ?? 0}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
