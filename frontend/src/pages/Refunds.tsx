import { useEffect, useState } from "react";
import { Card } from "../components/ui";
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

/** The refund policy for Plus and coin packs: 14 days, no questions asked, refunded through Paddle. */
export function Refunds({ go }: { go: Go }) {
  const [contact, setContact] = useState<string | null>(null);
  const [operator, setOperator] = useState<string | null>(null);
  useEffect(() => {
    document.title = "Refunds · Snazzlebop";
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
        <p className="sign">Refunds</p>
        <h1 className="space-top prose-title">Changed your mind? No problem</h1>
        <p className="space-top">Every payment, for Snazzlebop Plus or a coin pack, can be refunded in full within 14 days, no questions asked.</p>
      </Card>

      <Card aria-labelledby="rf-policy">
        <h2 id="rf-policy">The policy</h2>
        <ul className="prose-list">
          <li>
            <b>14 days, in full:</b> ask within 14 days of any payment (a Plus month, a renewal or a coin pack) and you get that
            payment back in full. You don't need to give a reason.
          </li>
          <li>
            <b>Coin packs:</b> a refund takes that pack's coins back off your balance, as far as your balance goes.
          </li>
          <li>
            <b>After 14 days:</b> you can still cancel at any time, and Plus stays on until the end of the month you paid for. We
            look at later requests case by case, for example if something went wrong with the service.
          </li>
          <li>
            <b>Your legal rights</b> come first: where the law gives you more (for example a longer cooling-off period), that
            applies.
          </li>
        </ul>
      </Card>

      <Card aria-labelledby="rf-how">
        <h2 id="rf-how">How to ask for a refund</h2>
        <ul className="prose-list">
          <li>
            {contact ? (
              <>
                Write to <b className="prose-contact">{contact}</b> from the email you paid with, or with your receipt number.
              </>
            ) : (
              "Use the contact on the About page, with the email you paid with or your receipt number."
            )}
          </li>
          <li>
            Or reply to your payment receipt from Paddle, or use the link in it to reach Paddle's buyer support at paddle.net.
          </li>
          <li>Refunds go back to the way you paid, usually within 5-10 business days depending on your bank.</li>
        </ul>
      </Card>

      <Card aria-labelledby="rf-who">
        <h2 id="rf-who">Who handles payments</h2>
        <p>
          Snazzlebop Plus is sold by Paddle.com, our reseller and merchant of record, who handles payment, tax, invoices and
          refunds{operator ? <> for {operator}</> : null}. See the <Link to="/terms" go={go}>terms</Link> and the{" "}
          <Link to="/privacy" go={go}>privacy notice</Link> for the rest.
        </p>
      </Card>
    </div>
  );
}
