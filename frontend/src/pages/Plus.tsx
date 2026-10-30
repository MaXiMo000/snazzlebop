import { useEffect, useState } from "react";
import { Alert, errText } from "../components/auth";
import { PARTY } from "../components/party";
import { Btn, Card } from "../components/ui";
import { refreshAccount, useAccount } from "../lib/account";
import { billingConfig, buyPlus, manageLink, myPlus, plusPrice, type BillingConfig, type MyPlus } from "../lib/billing";
import { inApp } from "../lib/app";

type Go = (path: string) => void;
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });

/** /plus: Snazzlebop Plus, a monthly membership. No ads, coins and party items each month, every emote
 * pack and a badge. Paddle sells it (worldwide, in the buyer's currency) and the server turns it on
 * only when Paddle confirms the payment. */
export function Plus({ go }: { go: Go }) {
  const { user, loaded } = useAccount();
  const [cfg, setCfg] = useState<BillingConfig | null>(null);
  const [mine, setMine] = useState<MyPlus | null>(null);
  const [price, setPrice] = useState<string | null | undefined>(undefined); // undefined: still asking Paddle
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const thanks = new URLSearchParams(location.search).has("thanks");

  useEffect(() => {
    document.title = "Plus · Snazzlebop";
    billingConfig().then(setCfg, () => setCfg(null));
  }, []);
  useEffect(() => {
    if (cfg?.payments) void plusPrice(cfg).then(setPrice);
  }, [cfg]);
  useEffect(() => {
    if (!user) return;
    void myPlus().then(setMine, () => undefined);
    if (!thanks) return;
    // Paddle tells the server a moment after the checkout closes: look again a few times.
    let n = 0;
    const t = window.setInterval(() => {
      n += 1;
      void refreshAccount();
      void myPlus().then(setMine, () => undefined);
      if (n >= 6) window.clearInterval(t);
    }, 2500);
    return () => window.clearInterval(t);
  }, [user, thanks]);

  const perks = cfg?.perks;
  const items = perks ? Object.entries(perks.items).map(([id, n]) => `${n}× ${PARTY.find(([p]) => p === id)?.[2] ?? id}`) : [];
  const buy = async () => {
    if (!cfg) return;
    setBusy(true);
    setNote(null);
    try {
      await buyPlus(cfg, document.documentElement.dataset.theme !== "light", () => {
        setNote({ ok: true, text: "Payment done! Plus turns on in a moment." });
        void refreshAccount();
      });
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    } finally {
      setBusy(false);
    }
  };
  const manage = async () => {
    setBusy(true);
    try {
      location.assign((await manageLink()).url);
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
      setBusy(false);
    }
  };

  return (
    <div className="stack enter plus-page">
      <Card tone="stage" className="center">
        <p className="sign">Snazzlebop Plus</p>
        <h1 className="space-top prose-title">No ads, more fun</h1>
        <p className="space-top plus-price">
          {cfg?.payments ? (
            <>
              {price === undefined ? "…" : price === null ? "A small price" : <b>{price}</b>} a month, in your own currency. Cancel any time.
            </>
          ) : inApp ? (
            "No ads and a few extras, for members."
          ) : (
            "Coming soon."
          )}
        </p>
      </Card>
      {thanks && !mine?.active && <Alert text="Thanks! Your payment is being confirmed: Plus turns on in a moment." calm />}
      {note && <Alert text={note.text} calm={note.ok} />}

      <Card aria-labelledby="perks-h">
        <h2 id="perks-h">What you get</h2>
        <ul className="plus-perks">
          <li>
            <span aria-hidden="true">🚫</span> No ads, anywhere
          </li>
          <li>
            <span aria-hidden="true">🪙</span> {perks?.coins ?? 300} coins every month
          </li>
          {items.length > 0 && (
            <li>
              <span aria-hidden="true">🎉</span>
              <span>
                Every month:{" "}
                {items.map((it, i) => (
                  <span key={it}>
                    <span className="no-break">{it}</span>
                    {i < items.length - 1 ? ", " : ""}
                  </span>
                ))}
              </span>
            </li>
          )}
          <li>
            <span aria-hidden="true">👻</span> Every emote pack, while you're a member
          </li>
          <li>
            <span aria-hidden="true">⭐</span> A Plus badge by your name in every room
          </li>
          <li>
            <span aria-hidden="true">⚡</span> Two power-ups in each casual game (never ranked or battles)
          </li>
          <li>
            <span aria-hidden="true">🔆</span> The Plus spotlight avatar frame
          </li>
        </ul>
        {!loaded ? null : !user ? (
          inApp ? null : (
          <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
            Sign in to join
          </Btn>
          )
        ) : mine?.gift ? (
          <p className="space-top">
            <span className="chip teal">Plus</span> A gift from Snazzlebop: every perk, nothing to pay or renew.
          </p>
        ) : mine?.active ? (
          <div className="space-top stack-sm">
            <p>
              <span className="chip teal">Plus</span> {mine.status === "canceled" ? "Ends" : "Renews"} on {mine.until ? day(mine.until) : "…"}.
            </p>
            {(mine.source === "app_store" || mine.source === "play_store") && (
              <p className="muted">
                Bought in the app: change or cancel it in {mine.source === "app_store" ? "the App Store" : "Google Play"}, under
                Subscriptions.
              </p>
            )}
            {mine.can_manage && !inApp && (
              <Btn variant="ghost" disabled={busy} onClick={() => void manage()}>
                Change or cancel
              </Btn>
            )}
          </div>
        ) : cfg?.payments ? (
          <Btn className="space-top" variant="gold" disabled={busy} onClick={() => void buy()}>
            Join Plus
          </Btn>
        ) : null}
      </Card>

      <Card aria-labelledby="plus-how-h">
        <h2 id="plus-how-h">Good to know</h2>
        <ul className="evidence">
          <li>Plus never changes who wins: ranked games and battles stay the same for everyone.</li>
          {!inApp && (
            <>
              <li>Payments are handled by Paddle, our reseller, in your own currency. We never see your card.</li>
              <li>It renews each month until you cancel. Cancel any time and you keep Plus to the end of the month you paid for.</li>
            </>
          )}
          <li>Ads only ever appear in the lobby and on the results screen, never during a game.</li>
        </ul>
      </Card>
    </div>
  );
}
