import { useEffect, useId, useState } from "react";
import { fetchGames } from "../lib/api";
import { goToMatch, muteClub, notUp, upForGame, type ClubDetail } from "../lib/clubs";
import { sfx } from "../lib/sfx";
import { Alert, errText } from "./auth";
import { Btn, Card } from "./ui";

const MINUTES = [30, 60, 120];
const until = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

/**
 * "Up for a game": say you're free and for how long. When enough of the club is up, everyone who wants
 * to hear about it is told, and the first one to tap through opens the room.
 */
export function UpForGame({
  c,
  name,
  go,
  update,
}: {
  c: ClubDetail;
  name: string;
  go: (path: string) => void;
  update: (next: ClubDetail) => void;
}) {
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [game, setGame] = useState("");
  const [minutes, setMinutes] = useState(60);
  const [seat, setSeat] = useState(name.slice(0, 20));
  const [muted, setMuted] = useState(c.muted);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  useEffect(() => {
    fetchGames().then((g) => setTitles(Object.fromEntries(g.map((x) => [x.id, x.title]))), () => undefined);
  }, []);
  useEffect(() => setMuted(c.muted), [c.muted]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const label = (g: string | null) => (g ? (titles[g] ?? g) : "any game");
  const choices = (c.rules.games.length ? c.rules.games : Object.keys(titles)).slice().sort((a, b) => label(a).localeCompare(label(b)));
  const { mine, match, count, needed } = c.up;

  return (
    <Card tone={match ? "stage" : "plain"} className="up-card" aria-labelledby={`${id}-h`}>
      {match ? (
        <>
          <p className="sign up-sign" id={`${id}-h`}>
            Game on!
          </p>
          <p className="space-top up-lead">
            {match.players} {match.players === 1 ? "person wants" : "people want"} to play {label(match.game)}.{" "}
            {match.room ? "The room is open." : "Be the first in and you're the host."}
          </p>
          <form
            className="club-start space-top"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                const code = await goToMatch(c.slug, seat.trim());
                sfx.ding();
                go(`/r/${code}`);
              });
            }}
          >
            <div>
              <label className="field" htmlFor={`${id}-seat`}>
                Your name in the game
              </label>
              <input id={`${id}-seat`} type="text" maxLength={20} value={seat} onChange={(e) => setSeat(e.target.value)} />
            </div>
            <Btn type="submit" variant="gold" disabled={busy || !seat.trim()}>
              {match.room ? "Join the game" : "Open the room"}
            </Btn>
          </form>
        </>
      ) : mine ? (
        <>
          <h3 id={`${id}-h`}>You're up for a game</h3>
          <p className="up-lead">
            Up for {label(mine.game)} until {until(mine.until)}.
          </p>
          <UpMeter count={count} needed={needed} />
          <p className="muted">When {needed} of you are up, everyone hears about it and the first one in opens the room.</p>
          <Btn className="space-top" variant="ghost" disabled={busy} onClick={() => void run(async () => update(await notUp(c.slug)))}>
            I'm not free any more
          </Btn>
        </>
      ) : (
        <>
          <h3 id={`${id}-h`}>Up for a game?</h3>
          <p className="muted">
            Say you're free. When {needed} of the club are up, everyone hears about it and a room opens. Nobody comes? It quietly runs out.
          </p>
          {count > 0 && <UpMeter count={count} needed={needed} />}
          <div className="up-form space-top">
            <div>
              <label className="field" htmlFor={`${id}-game`}>
                Game
              </label>
              <select id={`${id}-game`} className="select-button" value={game} onChange={(e) => setGame(e.target.value)}>
                <option value="">Any game</option>
                {choices.map((g) => (
                  <option key={g} value={g}>
                    {label(g)}
                  </option>
                ))}
              </select>
            </div>
            <fieldset className="up-minutes">
              <legend className="field">For the next</legend>
              <div className="auth-tabs up-tabs">
                {MINUTES.map((m) => (
                  <button key={m} type="button" className={`auth-tab ${minutes === m ? "on" : ""}`} aria-pressed={minutes === m} onClick={() => setMinutes(m)}>
                    {m === 120 ? "2 hours" : `${m} min`}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>
          <Btn
            className="space-top"
            variant="go"
            block
            disabled={busy}
            onClick={() =>
              void run(async () => {
                update(await upForGame(c.slug, game || null, minutes));
                sfx.pop();
              })
            }
          >
            I'm up for a game
          </Btn>
        </>
      )}
      <Alert text={error} />
      <label className="check space-top up-mute">
        <input
          type="checkbox"
          checked={!muted}
          disabled={busy}
          onChange={(e) =>
            void run(async () => {
              await muteClub(c.slug, !e.target.checked);
              setMuted(!e.target.checked);
            })
          }
        />
        <span>Tell me when a game is filling up here</span>
      </label>
    </Card>
  );
}

function UpMeter({ count, needed }: { count: number; needed: number }) {
  return (
    <p className="up-meter">
      <span className="up-dots" aria-hidden="true">
        {Array.from({ length: needed }, (_, i) => (
          <span key={i} className={i < count ? "on" : ""} />
        ))}
      </span>
      <span>
        {Math.min(count, needed)} of {needed} up so far
      </span>
    </p>
  );
}
