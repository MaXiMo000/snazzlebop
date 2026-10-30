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

/** The privacy notice: what's kept, why, for how long, who else touches it, and your rights. */
export function Privacy({ go }: { go: Go }) {
  const [contact, setContact] = useState<string | null>(null);
  const [operator, setOperator] = useState<string | null>(null);
  const [billing, setBilling] = useState<BillingConfig | null>(null);
  useEffect(() => void billingConfig().then(setBilling, () => undefined), []);
  useEffect(() => {
    document.title = "Privacy · Snazzlebop";
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
        <p className="sign">Privacy</p>
        <h1 className="space-top prose-title">What we keep, and why</h1>
        <p className="space-top">Short version: as little as we can, never sold, never used for ads that follow you around.</p>
        {operator && <p className="space-top">Snazzlebop is run by {operator}, who is responsible for your data here.</p>}
      </Card>

      <Card aria-labelledby="pv-play">
        <h2 id="pv-play">Playing without an account</h2>
        <p>You pick a name for each room. The room (players, scores, chat) lives on our server while you play and is cleared after a few hours of no use. Your network address is used, briefly and in memory only, to stop abuse such as flooding.</p>
      </Card>

      <Card aria-labelledby="pv-account">
        <h2 id="pv-account">With an account</h2>
        <ul className="prose-list">
          <li><b>Your account:</b> username, a scrambled form of your password (we can't read it), and your recovery code in scrambled form.</li>
          <li><b>Email, if you add one:</b> to sign in, reset your password and warn you about changes. Never shown to other players, never used for marketing.</li>
          <li><b>Your games:</b> places, points and coins, for your stats and the season tables.</li>
          <li><b>Clubs and friends:</b> which you're in and who you added, so they can see your rooms and when you're around. You can appear offline.</li>
          <li><b>Notifications:</b> your inbox, your settings, and for each device you turn pushes on, the address its browser gives us for them.</li>
          <li><b>Security:</b> a scrambled marker per browser you sign in from, so we can warn you about new ones; your authenticator setting if you use one.</li>
          <li><b>Safety:</b> people you block, and reports you make or that are made about you (with the chat lines that prompted them).</li>
        </ul>
      </Card>

      <Card aria-labelledby="pv-others">
        <h2 id="pv-others">Who else handles it</h2>
        <ul className="prose-list">
          <li>Our hosting provider runs the servers and database.</li>
          <li>If email is on, an email delivery service sends our messages.</li>
          <li>Pushes travel through your browser maker's push service (Google, Mozilla, Apple or Microsoft). They're encrypted: only your device can read them.</li>
          <li>Voice and video calls, if used, go through our call provider while the call lasts. We don't record them.</li>
          {billing?.payments && (
            <li>
              Snazzlebop Plus is sold by Paddle, our reseller: they take the payment and handle tax, and keep what that needs (your email, country and payment details). We
              only learn that your account has Plus and until when; we never see your card.
            </li>
          )}
          {billing?.ads && (
            <li>
              Ads come from Google AdSense, only in the lobby, on the results screen and at the bottom of the home page, never during a game and never for Plus members. Google may use cookies to choose and measure them; where the law requires it, you're asked first and can say no.
            </li>
          )}
          <li>If we use a support or ticketing tool to handle reports, a report goes to it with the reported person's name and what they said, but no emails, and the person who reported only as an anonymous reference.</li>
        </ul>
        <p className="space-top">
          We don't sell personal data.{" "}
          {billing?.ads ? "Apart from the ads described above, there are no third-party trackers on the site." : "There are no third-party trackers on the site."}
        </p>
      </Card>

      <Card aria-labelledby="pv-rights">
        <h2 id="pv-rights">Your rights</h2>
        <ul className="prose-list">
          <li><b>See it:</b> download everything we keep about your account on the <Link to="/safety" go={go}>Safety and data</Link> page.</li>
          <li><b>Fix it:</b> change your email or password on your <Link to="/account" go={go}>account page</Link>.</li>
          <li><b>Delete it:</b> deleting your account removes it and everything tied to it straight away. Other people's game results stay correct but no longer point to you.</li>
          <li><b>Ask us:</b> {contact ? <>write to <b className="prose-contact">{contact}</b>. We answer within 30 days.</> : "use the contact on this page once it's set up for this site."}</li>
          <li><b>Complain:</b> if we don't sort it out, you can go to your data protection authority (in India, the Data Protection Board of India; in the EU or UK, your national regulator).</li>
        </ul>
      </Card>

      <Card aria-labelledby="pv-age">
        <h2 id="pv-age">Age</h2>
        <p>Accounts are for people 18 and over. Playing in a room with friends needs no account.</p>
      </Card>
    </div>
  );
}
