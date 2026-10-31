import { useEffect, useRef, useState } from "react";
import { refreshAccount, useAccount } from "../lib/account";
import { billingConfig, buyCoins, localPrices, type BillingConfig } from "../lib/billing";
import { Alert, errText } from "./auth";
import { Btn, Card } from "./ui";

const BEST = 1500; // the pack marked best value
const USD: Record<number, string> = { 500: "$1.99", 1500: "$4.99", 4000: "$9.99" }; // until Paddle answers

/** Coin packs for money, through Paddle's checkout. Shown only where payments are on (never in the store
 * apps). Coins arrive when Paddle's signed payment notice reaches the server, usually within seconds. */
export function CoinStore() {
  const { user } = useAccount();
  const [cfg, setCfg] = useState<BillingConfig | null>(null);
  const [prices, setPrices] = useState<(string | null)[] | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef(0);
  useEffect(() => {
    void billingConfig().then((c) => {
      setCfg(c);
      if (c.payments && c.coin_packs.length) void localPrices(c, c.coin_packs.map((p) => p.price)).then(setPrices);
    }, () => undefined);
    return () => window.clearTimeout(timer.current);
  }, []);
  if (!user || !cfg?.payments || !cfg.coin_packs.length) return null;

  // after paying: check the balance every 2 s for up to 30 s, until the coins land
  const watch = (before: number, tries = 15) => {
    timer.current = window.setTimeout(async () => {
      const now = await refreshAccount();
      if ((now?.coins ?? before) > before || tries <= 1) setWaiting(false);
      else watch(before, tries - 1);
    }, 2000);
  };
  const buy = async (coins: number) => {
    setError(null);
    try {
      const before = user.coins;
      await buyCoins(cfg, coins, document.documentElement.dataset.theme !== "light", () => {
        setWaiting(true);
        watch(before);
      });
    } catch (e) {
      setError(errText(e));
    }
  };
  return (
    <Card aria-labelledby="coinstore-h" className="coinstore">
      <h2 id="coinstore-h">Get coins</h2>
      <p className="muted">For looks, emote packs and power-ups. Paid securely through Paddle, in your own currency.</p>
      <ul className="coin-packs">
        {cfg.coin_packs.map((p, i) => (
          <li key={p.price} className={`coin-pack ${p.coins === BEST ? "best" : ""}`}>
            {p.coins === BEST && <span className="coin-pack-flag">Best value</span>}
            <span className="coin-pack-pile" aria-hidden="true">
              {"🪙".repeat(i + 1)}
            </span>
            <b className="coin-pack-amount">{p.coins.toLocaleString()} coins</b>
            <Btn variant={p.coins === BEST ? "gold" : "go"} disabled={waiting} onClick={() => void buy(p.coins)}>
              {prices?.[i] ?? USD[p.coins] ?? "Buy"}
            </Btn>
          </li>
        ))}
      </ul>
      {waiting && (
        <p className="alert calm space-top" role="status">
          Payment done! Your coins are on their way: they appear here in a few seconds.
        </p>
      )}
      <p className="muted coin-fine">
        Coins have no cash value and can't be traded, transferred or cashed out. Refunds within 14 days take the coins back.
      </p>
      {error && <Alert text={error} />}
    </Card>
  );
}
