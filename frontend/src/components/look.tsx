import { useEffect, useState } from "react";
import { request } from "../lib/api";
import { Alert, errText } from "./auth";
import { Card, Loading, initials } from "./ui";

type Option = { id: string; name: string; level: number; plus: boolean; unlocked: boolean };
type MyLook = {
  level: number;
  plus: boolean;
  slots: number;
  slot_level: number;
  frame: string;
  win: string;
  frames: Option[];
  wins: Option[];
};

const WIN_ICON: Record<string, string> = { confetti: "🎉", fireworks: "🎆", spotlight: "🔦", disco: "🪩", rocket: "🚀", crown: "👑" };

/** Profile: what your level has unlocked (power-up slots, avatar frames, victory animations), and your
 * pick. Locked ones show the level that opens them; the server checks every pick. */
export function YourLook({ username }: { username: string }) {
  const [look, setLook] = useState<MyLook | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void request<MyLook>("/api/me/look").then(setLook, (e) => setError(errText(e)));
  }, []);
  const pick = (next: { frame?: string; win?: string }) => {
    if (!look) return;
    const body = { frame: next.frame ?? look.frame, win: next.win ?? look.win };
    setLook({ ...look, ...body });
    request<MyLook>("/api/me/look", { method: "POST", body: JSON.stringify(body) }).then(
      (r) => (setLook(r), setError(null)),
      (e) => (setError(errText(e)), void request<MyLook>("/api/me/look").then(setLook, () => undefined)),
    );
  };
  const lock = (o: Option) => (o.plus ? "Plus" : `Level ${o.level}`);
  return (
    <Card aria-labelledby="look-h">
      <h2 id="look-h">Your look</h2>
      {!look ? (
        error ? (
          <Alert text={error} />
        ) : (
          <Loading />
        )
      ) : (
        <>
          <div className="look-head">
            <span className={`avatar lg tone-3 ${look.frame === "none" ? "" : `frame-${look.frame}`}`} aria-hidden="true">
              {initials(username)}
            </span>
            <p>
              <b>Level {look.level}.</b>{" "}
              {look.slots > 1 ? (
                <>
                  You can use <span className="keep">{look.slots} power-ups</span> in each casual game.
                </>
              ) : (
                <>
                  One power-up per game; a second slot opens at <span className="keep">level {look.slot_level}</span>.
                </>
              )}
            </p>
          </div>
          <h3 className="space-top">Avatar frame</h3>
          <div className="look-grid" role="group" aria-label="Avatar frame">
            {look.frames.map((o) => (
              <button
                key={o.id}
                type="button"
                className="look-option"
                aria-pressed={look.frame === o.id}
                disabled={!o.unlocked}
                onClick={() => pick({ frame: o.id })}
              >
                <span className={`avatar tone-3 ${o.id === "none" ? "" : `frame-${o.id}`}`} aria-hidden="true">
                  {initials(username)}
                </span>
                <span>{o.name}</span>
                {!o.unlocked && <span className="look-lock">🔒 {lock(o)}</span>}
              </button>
            ))}
          </div>
          <h3 className="space-top">Victory animation</h3>
          <p className="muted">What the room sees on the podium when you win.</p>
          <div className="look-grid" role="group" aria-label="Victory animation">
            {look.wins.map((o) => (
              <button
                key={o.id}
                type="button"
                className="look-option"
                aria-pressed={look.win === o.id}
                disabled={!o.unlocked}
                onClick={() => pick({ win: o.id })}
              >
                <span className="look-icon" aria-hidden="true">
                  {WIN_ICON[o.id] ?? "✨"}
                </span>
                <span>{o.name}</span>
                {!o.unlocked && <span className="look-lock">🔒 {lock(o)}</span>}
              </button>
            ))}
          </div>
          {error && <Alert text={error} />}
        </>
      )}
    </Card>
  );
}
