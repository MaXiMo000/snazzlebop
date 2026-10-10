import { useEffect, useState } from "react";
import { ApiError, createRoom, joinRoom } from "../lib/api";
import { Btn, Card } from "../components/ui";
import { useAccount } from "../lib/account";
import { Friends, InstallApp } from "../components/friends";

export function Home({ go }: { go: (path: string) => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const { user } = useAccount();
  useEffect(() => {
    if (user) setName((n) => n || user.username.slice(0, 16));
  }, [user]);
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
        <p className="lead">Twenty-four games. One room code. No sign-up needed.</p>
        <p className="muted">Grab 3 to 8 friends, put the show on the big screen, play from your phones.</p>
      </Card>

      {user && <Friends name={name} go={go} />}

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

      <InstallApp />

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
            <b>Price Is Weird</b>: guess what absurd things cost, sabotage a rival, survive the Showcase.
          </li>
          <li>
            <b>Telepathy Tax</b>: match some minds, but if the majority thinks alike, everyone pays the tax.
          </li>
          <li>
            <b>Mole in the Mural</b>: everyone knows the secret painting except the Mole. Hint carefully, unmask them.
          </li>
          <li>
            <b>Blackjack Showdown</b>: you or the whole room against the dealer, with side bets and a Chaos card.
          </li>
          <li>
            <b>Crossword Race</b>: a fresh grid every game. First to solve a clue takes the points.
          </li>
          <li>
            <b>Liar's Dice</b>: secret dice, bold bids. Call LIAR! and hope you're right.
          </li>
          <li>
            <b>Split or Steal</b>: share the pot or take it all. Everyone remembers what you did.
          </li>
          <li>
            <b>Chicken Run</b>: the pot climbs every second. Cash out before the hidden bomb.
          </li>
          <li>
            <b>Wager Wits</b>: guess a number, then bet on whoever's closest. No knowledge required.
          </li>
          <li>
            <b>Code Crackers</b>: hide a secret code, then race to crack everyone else's.
          </li>
          <li>
            <b>Roulette Royale</b>: bet on the wheel while one of you secretly owns the House.
          </li>
          <li>
            <b>Lowest Lonely Number</b>: pick 1-20; the lowest number nobody else picked wins.
          </li>
          <li>
            <b>Mystery Box Auction</b>: bid on sealed boxes. You peeked inside one. Bombs included.
          </li>
          <li>
            <b>Codewords</b> (teams): Spymasters give one-word clues; find your team’s words, dodge the assassin.
          </li>
          <li>
            <b>Truth or Dare</b> (classic): spin the bottle, pick your poison, and let the room judge you.
          </li>
          <li>
            <b>Word Race</b> (classic): everyone hunts the same five-letter word in six tries. Fewest guesses wins.
          </li>
          <li>
            <b>Last Card</b> (classic): match colours and numbers, skip, reverse, draw four. Shout before you're caught!
          </li>
          <li>
            <b>Ludo</b> (classic): roll a six to get out, knock rivals back to their yard, race every token home.
          </li>
          <li>
            <b>Chess</b> (classic): the real rules and chess clocks. One on one, or the whole room in two teams.
          </li>
          <li>
            <b>Mafia Night</b> (classic): secret roles, quiet nights, loud days. Find the Mafia before they outnumber the town.
          </li>
          <li>
            <b>Hot Potato Bomb</b> (classic): answer the prompt to pass the ticking bomb. Hold it when it blows and you lose a life.
          </li>
        </ul>
      </Card>
    </div>
  );
}
