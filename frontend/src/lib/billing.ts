import { request } from "./api";
import { inApp } from "./app";
import type { Account, BillingConfig, MyPlus, PlusCheckout, PlusManage } from "./contract";

export type { BillingConfig, MyPlus } from "./contract";

// Paddle.js: just the calls this site makes (https://developer.paddle.com/paddle-js).
interface PaddleJs {
  Environment: { set(env: "sandbox"): void };
  Initialize(opts: { token: string; eventCallback?: (e: { name?: string }) => void }): void;
  Checkout: { open(opts: Record<string, unknown>): void };
  PricePreview(opts: { items: { priceId: string; quantity: number }[] }): Promise<{
    data: { details: { lineItems: { formattedTotals: { total: string } }[] } };
  }>;
}
declare global {
  interface Window {
    Paddle?: PaddleJs;
    adsbygoogle?: unknown[];
  }
}

let config: Promise<BillingConfig> | null = null;
/** What's on here: Plus on sale, ads, and the perks (asked once per page load). */
export const billingConfig = () =>
  (config ??= request<BillingConfig>("/api/billing/config").then((c) => (inApp ? { ...c, payments: false, ads: null } : c)));
export const myPlus = () => request<MyPlus>("/api/me/plus");
export const manageLink = () => request<PlusManage>("/api/me/plus/manage", { method: "POST" });

const scripts = new Map<string, Promise<void>>();
/** Add an external script once (never inline: the page's security policy allows only listed hosts). */
export function loadScript(src: string, attrs: Record<string, string> = {}): Promise<void> {
  let p = scripts.get(src);
  if (!p) {
    p = new Promise<void>((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.async = true;
      for (const [k, v] of Object.entries(attrs)) s.setAttribute(k, v);
      s.onload = () => resolve();
      s.onerror = () => {
        scripts.delete(src);
        reject(new Error("could not load"));
      };
      document.head.appendChild(s);
    });
    scripts.set(src, p);
  }
  return p;
}

let ready: Promise<PaddleJs> | null = null;
function paddle(cfg: BillingConfig, onDone: () => void): Promise<PaddleJs> {
  ready ??= loadScript("https://cdn.paddle.com/paddle/v2/paddle.js").then(() => {
    const p = window.Paddle;
    if (!p) throw new Error("Paddle.js missing");
    if (cfg.environment === "sandbox") p.Environment.set("sandbox");
    p.Initialize({ token: cfg.client_token, eventCallback: (e) => e.name === "checkout.completed" && onDone() });
    return p;
  });
  return ready;
}

/** Plus's price in the buyer's own currency, as Paddle shows it ("$1.99", "₹99"...). */
export async function plusPrice(cfg: BillingConfig): Promise<string | null> {
  try {
    // At most 5 s: a blocked script or a slow network shows the plain wording instead.
    const late = new Promise<null>((done) => setTimeout(() => done(null), 5000));
    const ask = (async () => {
      const p = await paddle(cfg, () => undefined);
      const r = await p.PricePreview({ items: [{ priceId: cfg.plus_price, quantity: 1 }] });
      return r.data.details.lineItems[0]?.formattedTotals.total ?? null;
    })();
    return await Promise.race([ask, late]);
  } catch {
    return null;
  }
}

/** Paddle's own checkout, over this page. Plus turns on when Paddle's signed webhook reaches the server. */
export async function buyPlus(cfg: BillingConfig, dark: boolean, onDone: () => void): Promise<void> {
  const [p, mine] = await Promise.all([paddle(cfg, onDone), request<PlusCheckout>("/api/billing/checkout", { method: "POST" })]);
  p.Checkout.open({
    items: [{ priceId: mine.price, quantity: 1 }],
    ...(mine.email ? { customer: { email: mine.email } } : {}),
    customData: mine.custom_data,
    settings: { displayMode: "overlay", theme: dark ? "dark" : "light", successUrl: `${location.origin}/plus?thanks=1` },
  });
}

/** Ads for this person here? Only if the site has ads; the server decides for accounts (Plus has none). */
export const adsFor = (cfg: BillingConfig, user: Account | null) => !!cfg.ads && (user ? user.ads : true);
