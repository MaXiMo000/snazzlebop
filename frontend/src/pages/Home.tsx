import { useEffect, useState } from "react";
import { ApiError, createRoom, joinRoom } from "../lib/api";
import { Btn, Card } from "../components/ui";
import { useAccount } from "../lib/account";
import { Friends, InstallApp } from "../components/friends";
import { HappeningNow } from "../components/happening";
import { YourCorner } from "../components/nav";

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
  const host = () => {
    if (!nameOk) return;
    void wrap(async () => {
      const r = await createRoom(name.trim());
      go(`/r/${r.code}`);
    });
  };
  const join = () => {
    if (!nameOk || code.length < 3) return;
    void wrap(async () => {
      const c = code.toUpperCase();
      await joinRoom(c, name.trim());
      go(`/r/${c}`);
    });
  };

  return (
    <div className="stack enter">
      <section className="hero" aria-labelledby="show-title">
        <h1 id="show-title">Snazzlebop!</h1>
        <p className="tagline">The party game show where your friends are the contestants</p>
      </section>

      {user && <HappeningNow name={name} go={go} />}

      <Card tone="stage" className="center">
        <p className="lead">
          Thirty-seven games. One room code. <span className="no-break">No sign-up needed.</span>
        </p>
        <p className="muted">Grab up to 8 friends, put the show on the big screen, play from your phones.</p>
      </Card>

      <YourCorner go={go} />

      <Card aria-labelledby="name-h">
        <h2 id="name-h">First, your name</h2>
        <label className="field" htmlFor="host-name">
          What should the show call you?
        </label>
        <input
          id="host-name"
          type="text"
          value={name}
          maxLength={16}
          autoComplete="nickname"
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            // Enter: join the room whose code is typed below, or start a new one.
            if (e.key !== "Enter" || busy) return;
            e.preventDefault();
            if (code.length >= 3) join();
            else host();
          }}
          placeholder="Up to 16 characters"
        />
      </Card>

      {user && <Friends name={name} go={go} />}

      <div className="grid">
        <Card aria-labelledby="host-h">
          <h2 id="host-h">Host a show</h2>
          <form
            className="stack-sm"
            onSubmit={(e) => {
              e.preventDefault();
              host();
            }}
          >
            <p className="muted">Start a room and get a code for your friends.</p>
            <Btn type="submit" size="big" block disabled={busy || !nameOk}>
              {nameOk ? "Create room" : "Type your name first"}
            </Btn>
          </form>
        </Card>

        <Card aria-labelledby="join-h">
          <h2 id="join-h">Join a show</h2>
          <form
            className="stack-sm"
            onSubmit={(e) => {
              e.preventDefault();
              join();
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
              {nameOk ? "Join" : "Type your name first"}
            </Btn>
            <p id="join-hint" className="muted">
              The host sees the code on their screen. An invite link works too.
            </p>
          </form>
        </Card>
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <Card tone="soft" aria-labelledby="how-h">
        <h2 id="how-h">How it works</h2>
        <ol className="how-steps">
          <li>
            <span>
              <b>One of you hosts.</b> You get a five-letter room code.
            </span>
          </li>
          <li>
            <span>
              <b>Everyone joins on their phone</b> with the code or the invite link. No app, no sign-up.
            </span>
          </li>
          <li>
            <span>
              <b>Optional: the big screen.</b> Open TV mode on a laptop or smart TV so the room watches together.
            </span>
          </li>
          <li>
            <span>
              <b>Pick a game.</b> The rules show before every game, and you can play one game or a whole show night.
            </span>
          </li>
        </ol>
      </Card>

      <InstallApp />

      <Card tone="soft" aria-labelledby="lineup-h">
        <h2 id="lineup-h">Tonight’s lineup</h2>
        <ul className="lineup">
          <li>
            <b>Trivia Tonight</b>: the quiz show. 1,300+ questions, 15 categories, five ways to play. Speed counts!
          </li>
          <li>
            <b>Would You Rather</b>: one friend in the hot seat. Answer, then guess what they’d pick.
          </li>
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
          <li>
            <b>Reaction Duel</b> (classic): wait… wait… TAP! Fastest finger wins, but watch out for fake-outs.
          </li>
          <li>
            <b>Snakes and Ladders</b> (classic): roll and race to 100. Ladders shoot you up, snakes send you sliding back down.
          </li>
          <li>
            <b>Battleships</b> (classic): two hidden fleets. Call your shots and sink them all, one on one or in two teams.
          </li>
          <li>
            <b>Four in a Row</b> (classic): drop your discs and line up four before they do. Best of three.
          </li>
          <li>
            <b>Letter Lists</b> (classic): one letter, six categories, one clock. Only answers nobody else wrote score.
          </li>
          <li>
            <b>Hangman</b> (classic): take turns setting a word. Guess letters, steal the solve, beat the drawing.
          </li>
          <li>
            <b>Five Dice</b> (classic): roll, hold, roll again. Fill your scorecard and chase five of a kind.
          </li>
          <li>
            <b>On Your Head</b> (classic): phone on your forehead, friends shout clues. Tilt to answer.
          </li>
          <li>
            <b>Imposter</b> (classic): everyone gets the secret word but one. Give a clue, then vote out the faker.
          </li>
        </ul>
      </Card>
    </div>
  );
}
