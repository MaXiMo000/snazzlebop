import { useEffect, useRef } from "react";
import { sfx } from "../lib/sfx";
import type { RoomState } from "../types";
import { Avatar } from "./avatar";
import { useShow } from "./fx";

const PLACE = ["1st", "2nd", "3rd"];

/** Results: this game's top three on a podium, revealed third to first; confetti for the winner. */
export function Podium({ state }: { state: RoomState }) {
  // Only players who scored stand on it; equal points share a place.
  const spots = state.podium.filter((s) => s.points > 0);
  const placeOf = (pts: number) => spots.filter((x) => x.points > pts).length;
  const fx = useShow();
  const played = useRef(false);
  useEffect(() => {
    if (!spots.length || played.current) return;
    played.current = true;
    const t = window.setTimeout(() => {
      sfx.fanfare();
      if (spots[0] && spots[0].id === state.you) fx.celebrate();
    }, 1200);
    return () => window.clearTimeout(t);
  }, [spots, state.you, fx]);
  if (!spots.length) return null;
  const real = (pid: string) => state.players.find((p) => p.id === pid)?.name ?? "?";
  const name = (pid: string) => (pid === state.you ? "You" : real(pid));
  // Shown 2nd, 1st, 3rd so the winner stands in the middle, highest.
  const order = [1, 0, 2].filter((i) => spots[i]);
  return (
    <section className="card stage podium" aria-labelledby="podium-h">
      <p id="podium-h" className="sign">
        {spots.length > 1 && spots[0]!.points === spots[1]!.points ? "A tie at the top!" : "The winner"}
      </p>
      <ol className="podium-row">
        {order.map((i) => {
          const s = spots[i]!;
          const place = placeOf(s.points);
          return (
            <li key={s.id} className={`podium-spot p${i + 1}`}>
              <span className="podium-who">
                {place === 0 && (
                  <span className="podium-crown" aria-hidden="true">
                    👑
                  </span>
                )}
                <Avatar pid={s.id} name={real(s.id)} className="lg" />
                <b>{name(s.id)}</b>
                <span className="podium-pts">{s.points.toLocaleString()}</span>
              </span>
              <span className="podium-step" aria-hidden="true">
                {PLACE[place]}
              </span>
              <span className="sr-only">
                {PLACE[place]} place, {s.points} points
              </span>
            </li>
          );
        })}
      </ol>
      {fx.node}
    </section>
  );
}
