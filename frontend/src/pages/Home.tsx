import { useEffect, useState } from "react";
import { ApiError, createRoom, joinRoom } from "../lib/api";
import { Btn, Card } from "../components/ui";

export function Home({ go }: { go: (path: string) => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Snazzlebop: party game show for friends";
  }, []);

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const nameOk = name.trim().length >= 1;

  return (
    <div className="stack enter">
      <section className="hero" aria-labelledby="show-title">
        <h1 id="show-title">Snazzlebop!</h1>
        <p className="tagline">The party game show where your friends are the contestants</p>
      </section>

      <Card tone="stage" className="center">
        <p className="lead">Seven games. One room code. Zero sign-ups.</p>
        <p className="muted">Grab 3 to 8 friends, put the show on the big screen, play from your phones.</p>
      </Card>

      <div className="grid">
        <Card aria-labelledby="host-h">
          <h2 id="host-h">Host a show</h2>
          <form
            className="stack-sm"
            onSubmit={(e) => {
              e.preventDefault();
              if (!nameOk) return;
              void wrap(async () => {
                const r = await createRoom(name.trim());
                go(`/r/${r.code}`);
              });
            }}
          >
            <div>
              <label className="field" htmlFor="host-name">
                Your name
              </label>
              <input
                id="host-name"
                type="text"
                value={name}
                maxLength={16}
                autoComplete="nickname"
                onChange={(e) => setName(e.target.value)}
                placeholder="Up to 16 characters"
              />
            </div>
            <Btn type="submit" size="big" block disabled={busy || !nameOk}>
              Create room
            </Btn>
          </form>
        </Card>

        <Card aria-labelledby="join-h">
          <h2 id="join-h">Join a show</h2>
          <form
            className="stack-sm"
            onSubmit={(e) => {
              e.preventDefault();
              if (!nameOk || code.length < 3) return;
              void wrap(async () => {
                const c = code.toUpperCase();
                await joinRoom(c, name.trim());
                go(`/r/${c}`);
              });
            }}
          >
            <div>
              <label className="field" htmlFor="join-code">
                Room code
              </label>
              <input
                id="join-code"
                className="code-input"
                type="text"
                value={code}
                maxLength={8}
                autoCapitalize="characters"
                autoComplete="off"
                spellCheck={false}
                aria-describedby="join-hint"
                onChange={(e) => setCode(e.target.value.replace(/[^a-zA-Z]/g, ""))}
                placeholder="ABCDE"
              />
            </div>
            <Btn type="submit" variant="go" size="big" block disabled={busy || !nameOk || code.length < 3}>
              Join
            </Btn>
            <p id="join-hint" className="muted">
              Uses the name you typed under “Host a show”.
            </p>
          </form>
        </Card>
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <Card tone="soft" aria-labelledby="lineup-h">
        <h2 id="lineup-h">Tonight’s lineup</h2>
        <ul className="lineup">
          <li>
            <b>Frenemy Radar</b>: rank your friends on silly traits, then find out how wrong your self-image is.
          </li>
          <li>
            <b>Alibi</b>: one of you is the killer with a fake story. Grill each other, catch the contradiction.
          </li>
          <li>
            <b>Price Is Weird</b>: guess what absurd things cost, sabotage a rival, survive the rigged round.
          </li>
          <li>
            <b>Telepathy Tax</b>: match some minds, but if the majority thinks alike, everyone pays the tax.
          </li>
          <li>
            <b>Mole in the Mural</b>: everyone knows the secret tile except the Mole. Hint carefully, then unmask them.
          </li>
          <li>
            <b>Blackjack Showdown</b>: the whole room against the dealer. Five hands, biggest stack wins.
          </li>
          <li>
            <b>Crossword Race</b>: a fresh grid every game. First to solve a clue takes the points.
          </li>
        </ul>
      </Card>
    </div>
  );
}
