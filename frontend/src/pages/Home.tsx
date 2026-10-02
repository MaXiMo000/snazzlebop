import { useEffect, useState } from "react";
import { ApiError, createRoom, joinRoom } from "../lib/api";
import { Btn, Panel } from "../components/ui";

export function Home({ go }: { go: (path: string) => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Snazzlebop: party games for friends";
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
    <>
      <div className="marquee" aria-hidden="true">
        <span>★ NEW ROOM EVERY NIGHT ★ NO SIGNUP ★ BRING 3 TO 8 FRIENDS ★ SECRETS STAY SECRET ★ KAPOW ★</span>
      </div>
      <header className="stack" style={{ textAlign: "center", margin: "10px 0 30px" }}>
        <h1>
          <span className="burst">Snazzlebop!</span>
        </h1>
        <p style={{ fontSize: "1.3rem" }}>Party games that start arguments you'll enjoy.</p>
      </header>

      <div className="grid">
        <Panel className="tilt-l">
          <h2>Start a room</h2>
          <form
            className="stack"
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
              <input id="host-name" type="text" value={name} maxLength={16} autoComplete="nickname" onChange={(e) => setName(e.target.value)} placeholder="Max 16 characters" />
            </div>
            <Btn type="submit" color="lime" size="big" disabled={busy || !nameOk}>
              Create room
            </Btn>
          </form>
        </Panel>

        <Panel className="tilt-r">
          <h2>Join a room</h2>
          <form
            className="stack"
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
              <input id="join-code" type="text" value={code} maxLength={8} autoCapitalize="characters" autoComplete="off" onChange={(e) => setCode(e.target.value.replace(/[^a-zA-Z]/g, ""))} placeholder="ABCDE" />
            </div>
            <Btn type="submit" color="cyan" size="big" disabled={busy || !nameOk || code.length < 3}>
              Join
            </Btn>
            <p className="muted">Uses the name above.</p>
          </form>
        </Panel>
      </div>

      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}

      <Panel className="halftone" style={{ marginTop: 28 }}>
        <h2>The lineup</h2>
        <ul>
          <li>
            <b>Frenemy Radar</b>: rank your friends, then see how wrong your self-image is.
          </li>
          <li>
            <b>Alibi</b>: one of you is a killer with a fake story. Find the contradiction.
          </li>
          <li>
            <b>Price Is Weird</b>: guess the price of absurd things. Then the chaos spin hits.
          </li>
        </ul>
      </Panel>
    </>
  );
}
