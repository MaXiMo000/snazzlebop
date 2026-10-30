import { useEffect, useState } from "react";
import { Card } from "../components/ui";
import { billingConfig, type BillingConfig } from "../lib/billing";
import { siteInfo } from "../lib/safety";

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

/** The terms: who can use the site, house rules, what coins are (and aren't), Plus billing and refunds. */
export function Terms({ go }: { go: Go }) {
  const [contact, setContact] = useState<string | null>(null);
  const [operator, setOperator] = useState<string | null>(null);
  const [billing, setBilling] = useState<BillingConfig | null>(null);
  useEffect(() => void billingConfig().then(setBilling, () => undefined), []);
  useEffect(() => {
    document.title = "Terms · Snazzlebop";
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
        <p className="sign">Terms</p>
        <h1 className="space-top prose-title">The house rules</h1>
        <p className="space-top">Short version: be kind, play fair, and coins are just for fun.</p>
      </Card>

      <Card aria-labelledby="tm-who">
        <h2 id="tm-who">Who can play</h2>
        <ul className="prose-list">
          {operator && <li>Snazzlebop is run by {operator}.</li>}
          <li>Anyone can play as a guest with just a name for the room.</li>
          <li>To make an account you must be 18 or older.</li>
          <li>By using Snazzlebop you agree to these terms and to how we handle data in the <Link to="/privacy" go={go}>privacy notice</Link>.</li>
        </ul>
      </Card>

      <Card aria-labelledby="tm-play">
        <h2 id="tm-play">Playing nicely</h2>
        <ul className="prose-list">
          <li>No harassment, hate, threats, sexual content or sharing someone's private details in names, chat, drawings or calls.</li>
          <li>No cheating: no bots, scripts, multiple accounts to farm coins or ratings, or deliberately losing to someone.</li>
          <li>Don't try to break, overload or get around the site's protections.</li>
          <li>Hosts can remove players from their rooms, and we can remove names, messages or accounts that break these rules. Report problems from the lobby, or see <Link to="/safety" go={go}>Safety and data</Link>.</li>
        </ul>
      </Card>

      <Card aria-labelledby="tm-coins">
        <h2 id="tm-coins">Coins, power-ups and ratings</h2>
        <ul className="prose-list">
          <li>Coins are earned by playing and spent in the power-up shop. They have no cash value: they can't be bought and sold between players, exchanged for money or prizes, or cashed out.</li>
          <li>No game takes coins as an entry fee or a stake.</li>
          <li>We may adjust coins, power-ups or ratings gained by cheating or by a bug, and we may change prices and rewards over time.</li>
        </ul>
      </Card>

      {billing?.payments && (
        <Card aria-labelledby="tm-plus">
          <h2 id="tm-plus">Snazzlebop Plus</h2>
          <ul className="prose-list">
            <li>Plus is a monthly subscription sold by Paddle.com, our reseller and merchant of record, which handles payment, tax and invoices in your currency. Paddle's buyer terms also apply.</li>
            <li>It renews each month until you cancel. Cancel any time from the <Link to="/plus" go={go}>Plus page</Link>: you keep Plus until the end of the month you paid for.</li>
            <li>Refunds: you can ask for a full refund of any payment within 14 days of it, no questions asked{contact ? <>: write to {contact}</> : null}. Refunds go back through Paddle to the way you paid. Where the law gives you more rights, those apply.</li>
            <li>Plus never changes who wins: ranked games and battles are the same for everyone.</li>
          </ul>
        </Card>
      )}

      <Card aria-labelledby="tm-content">
        <h2 id="tm-content">Your stuff and ours</h2>
        <ul className="prose-list">
          <li>Names, messages and drawings you add stay yours. You let us show them to the people in your rooms and clubs while the game needs them.</li>
          <li>The games, art and site are ours; please don't copy them.</li>
        </ul>
      </Card>

      <Card aria-labelledby="tm-service">
        <h2 id="tm-service">The service</h2>
        <ul className="prose-list">
          <li>Snazzlebop is offered as it is. We work to keep it running and safe, but games can be interrupted, and features change.</li>
          <li>You can delete your account at any time from your account page.</li>
          <li>If these terms change in a way that matters, we'll say so on the site before it takes effect.</li>
          {contact && <li>Questions: {contact}</li>}
        </ul>
      </Card>
    </div>
  );
}
