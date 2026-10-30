import { useEffect, useState } from "react";
import { Card } from "../components/ui";
import { siteInfo } from "../lib/safety";
import { inApp } from "../lib/app";

type Go = (path: string) => void;

function Link({ to, go, children }: { to: string; go: Go; children: string }) {
  return (
    <a
      href={to}
      onClick={(e) => {
        e.preventDefault();
        go(to);
      }}
    >
      {children}
    </a>
  );
}

/** Who makes the site, why, how it stays free, and how to get in touch. */
export function About({ go }: { go: Go }) {
  const [contact, setContact] = useState<string | null>(null);
  const [operator, setOperator] = useState<string | null>(null);
  useEffect(() => {
    document.title = "About · Snazzlebop";
    siteInfo().then(
      (s) => {
        setContact(s.privacy_contact);
        setOperator(s.operator);
      },
      () => undefined,
    );
  }, []);

  return (
    <div className="stack enter prose-page">
      <Card tone="stage" className="center">
        <p className="sign">About</p>
        <h1 className="space-top prose-title">A game show for your friends</h1>
        <p className="space-top">Snazzlebop turns any get-together into a TV game show, with your friends as the contestants.</p>
      </Card>

      <Card aria-labelledby="ab-what">
        <h2 id="ab-what">What it is</h2>
        <p>
          Snazzlebop is a party game show you play in the browser. One person hosts on a laptop or a TV, and everyone else joins from
          their phone with a five-letter code. There's nothing to install and no sign-up needed to play.
        </p>
        <p>
          There are more than 30 games: quick party games and ice-breakers, quizzes and word games, bluffing and mind games, nerve-testing
          game-show rounds, and the board and card classics everyone already knows. Each game teaches its rules in a few seconds,
          and the show keeps score across a whole night. See them all on the <Link to="/games" go={go}>games page</Link>.
        </p>
      </Card>

      <Card aria-labelledby="ab-why">
        <h2 id="ab-why">Why we made it</h2>
        <p>
          Game nights work best when everyone is looking at each other, not at a rulebook. Snazzlebop puts the scoreboard, the timer
          and the rules on the screen, so the host gets to play too. It's built for friends in the same room, and just as well for a
          group on a video call.
        </p>
      </Card>

      <Card aria-labelledby="ab-free">
        <h2 id="ab-free">How it stays free</h2>
        <p>
          Every game is free. An optional free account adds coins, daily quests, ratings, clubs and voice and video calls. A small ad
          may show in the lobby, on the results screen or at the bottom of the home page, never during a game.
          {!inApp && (
            <>
              {" "}
              <Link to="/plus" go={go}>
                Snazzlebop Plus
              </Link>{" "}
              removes ads and adds a few extras for the price of a coffee a month.
            </>
          )}
        </p>
      </Card>

      <Card aria-labelledby="ab-safe">
        <h2 id="ab-safe">Safe and fair</h2>
        <p>
          Hosts can remove anyone from their room, anyone can report a problem, and blocking is silent. Coins have no cash value and
          are never staked. Read the <Link to="/terms" go={go}>terms</Link>, the <Link to="/privacy" go={go}>privacy notice</Link> and{" "}
          <Link to="/safety" go={go}>safety and data</Link>.
        </p>
      </Card>

      <Card aria-labelledby="ab-contact">
        <h2 id="ab-contact">Contact</h2>
        <p>
          {operator ? <>Snazzlebop is made by {operator}. </> : null}
          {contact ? (
            <>
              Questions, ideas or a problem: write to <b className="prose-contact">{contact}</b>.
            </>
          ) : (
            "Questions, ideas or a problem: use Report a problem in any lobby."
          )}
        </p>
      </Card>
    </div>
  );
}
