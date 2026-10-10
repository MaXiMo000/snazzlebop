import { useEffect, useRef, useState } from "react";
import { sfx } from "../lib/sfx";
import type { RoomState } from "../types";
import { Avatar } from "./avatar";
import { Btn, Card, nameOf } from "./ui";

type Send = (msg: Record<string, unknown>) => void;
const SPIN_MS = 4300;

/** The loser's wheel: eight numbered slices; the pointer lands on the forfeit the server picked. */
function Wheel({ state, tv }: { state: RoomState; tv: boolean }) {
  const wheel = state.night.wheel;
  const first = useRef(true);
  const [landed, setLanded] = useState(true);
  const n = wheel?.n ?? 0;
  useEffect(() => {
    if (first.current) {
      first.current = false; // a spin from before this screen opened: show where it stopped
      return;
    }
    if (!n) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setLanded(true);
      sfx.fanfare();
      return;
    }
    setLanded(false);
    sfx.spin();
    const t = window.setTimeout(() => {
      setLanded(true);
      sfx.fanfare();
    }, SPIN_MS);
    return () => window.clearTimeout(t);
  }, [n]);
  if (!wheel) return null;
  const who = wheel.pid === state.you && !tv ? "You" : wheel.name;
  return (
    <div className="fw">
      <div className="fw-stage" aria-hidden="true">
        <span className="fw-pointer" />
        <div key={wheel.n} className={`fw-wheel ${landed ? `at-${wheel.pick}` : `to-${wheel.pick}`}`}>
          {wheel.options.map((_, i) => (
            <span key={i} className={`fw-num n${i}`}>
              {i + 1}
            </span>
          ))}
        </div>
      </div>
      <div className="fw-text">
        <p className="fw-who">
          <Avatar pid={wheel.pid} name={wheel.name} /> <b>{who}</b> {landed ? "must…" : "is spinning…"}
        </p>
        {landed ? (
          <p key={wheel.n} className="fw-result" role="status">
            {wheel.options[wheel.pick]}
          </p>
        ) : (
          <p className="muted">Round and round it goes…</p>
        )}
        <ol className="fw-list">
          {wheel.options.map((o, i) => (
            <li key={i} className={landed && i === wheel.pick ? "hit" : ""}>
              {o}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

/**
 * Between games: the champion's belt (the host crowns tonight's leader, who wears a crown on their face
 * in this host's rooms until someone takes it) and the forfeit wheel for whoever is last.
 */
export function Night({ state, send, isHost = false, tv = false }: { state: RoomState; send?: Send; isHost?: boolean; tv?: boolean }) {
  const night = state.night;
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);
  if (!night || !["lobby", "results", "finale"].includes(state.room.phase)) return null;
  const name = (pid: string) => nameOf(state.players, pid);
  const canSpin = !tv && !!night.last && (isHost || night.last === state.you);
  if (tv && !night.wheel && !night.belt.name) return null;
  if (!tv && !night.belt.name && !night.leader && !night.last && !night.wheel && !isHost) return null;
  return (
    <Card className="night" aria-labelledby="night-h">
      <h3 id="night-h">Belt and forfeits</h3>
      <p className="night-belt">
        <span aria-hidden="true">👑</span>{" "}
        {night.belt.name ? (
          <>
            Reigning champion: <b>{night.belt.name}</b>
            {night.belt.holder ? "" : " (not here tonight)"}
          </>
        ) : (
          "Nobody holds the belt yet."
        )}
      </p>
      {isHost && send && (
        <p className="night-row">
          <Btn variant="gold" disabled={!night.leader || night.leader === night.belt.holder} onClick={() => send({ t: "crown" })}>
            {night.leader ? `Crown ${name(night.leader)}` : "Crown tonight’s champion"}
          </Btn>
          {!night.leader ? (
            <span className="muted">Needs a clear leader on the scoreboard.</span>
          ) : (
            night.leader === night.belt.holder && <span className="muted">Still the champion.</span>
          )}
        </p>
      )}
      <Wheel state={state} tv={tv} />
      {canSpin && send && (
        <p className="night-row">
          <Btn variant="go" onClick={() => send({ t: "wheel" })}>
            🎡 {night.last === state.you ? "Spin your forfeit" : `Spin ${name(night.last!)}’s forfeit`}
          </Btn>
        </p>
      )}
      {!tv && !canSpin && night.last && !night.wheel && (
        <p className="muted">
          Last place ({name(night.last)}) can spin the forfeit wheel.
        </p>
      )}
      {isHost && send && (
        <div className="night-edit">
          <Btn variant="ghost" size="small" aria-expanded={editing} onClick={() => setEditing(!editing)}>
            ✏️ Your group’s forfeits ({night.forfeits.length})
          </Btn>
          {editing && (
            <>
              {night.forfeits.length === 0 && <p className="muted">None yet: the wheel uses ours until you add your own.</p>}
              <ul className="night-forfeits">
                {night.forfeits.map((f, i) => (
                  <li key={f}>
                    <span>{f}</span>
                    <button type="button" className="friend-x" aria-label={`Remove “${f}”`} onClick={() => send({ t: "forfeit", del: i })}>
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
              <form
                className="friend-add"
                onSubmit={(e) => {
                  e.preventDefault();
                  const t = text.trim();
                  if (!t) return;
                  send({ t: "forfeit", add: t });
                  setText("");
                }}
              >
                <label className="sr-only" htmlFor="forfeit-new">
                  A new forfeit
                </label>
                <input
                  id="forfeit-new"
                  type="text"
                  maxLength={80}
                  autoComplete="off"
                  value={text}
                  placeholder="e.g. Sing on the call"
                  onChange={(e) => setText(e.target.value)}
                />
                <Btn type="submit" disabled={!text.trim()}>
                  Add
                </Btn>
              </form>
            </>
          )}
        </div>
      )}
    </Card>
  );
}
