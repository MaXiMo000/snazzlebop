import { useEffect, useRef, useState } from "react";
import { useAccount } from "../lib/account";
import { adsFor, billingConfig, loadScript, type BillingConfig } from "../lib/billing";

/** One display ad (Google AdSense), only between games: the lobby and the results. Never for Plus
 * members, never in an account's (or a guest device's) first days, and nothing at all unless the site
 * has ads set up. */
export function AdSlot({ go }: { go: (path: string) => void }) {
  const { user, loaded } = useAccount();
  const [cfg, setCfg] = useState<BillingConfig | null>(null);
  const pushed = useRef(false);
  useEffect(() => void billingConfig().then(setCfg, () => undefined), []);
  const show = !!cfg && loaded && adsFor(cfg, user);
  useEffect(() => {
    if (!show || !cfg?.ads || pushed.current) return;
    pushed.current = true;
    const src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(cfg.ads.client)}`;
    void loadScript(src, { crossorigin: "anonymous" })
      .then(() => (window.adsbygoogle = window.adsbygoogle ?? []).push({}))
      .catch(() => undefined); // an ad blocker: fine, the slot stays empty
  }, [show, cfg]);
  if (!show || !cfg?.ads) return null;
  return (
    <aside className="ad-slot" aria-label="Advertisement">
      <p className="ad-label muted">Advertisement</p>
      <ins
        className="adsbygoogle ad-unit"
        data-ad-client={cfg.ads.client}
        data-ad-slot={cfg.ads.slot}
        data-ad-format="auto"
        data-full-width-responsive="true"
      />
      {cfg.payments && (
        <a
          className="ad-remove"
          href="/plus"
          onClick={(e) => {
            e.preventDefault();
            go("/plus");
          }}
        >
          No ads with Plus
        </a>
      )}
    </aside>
  );
}
