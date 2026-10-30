import { useEffect, useRef, useState } from "react";
import { useAccount } from "../lib/account";
import { adsFor, billingConfig, loadScript, type BillingConfig } from "../lib/billing";

/** One display ad (Google AdSense), never during a game: the lobby, the results and the foot of the home
 * page. Never for Plus members or inside the store app, and nothing at all unless the site has ads set
 * up. `lazy`: nothing loads until the spot is scrolled near, so opening the page never pops an ad. */
export function AdSlot({ go, lazy = false }: { go: (path: string) => void; lazy?: boolean }) {
  const { user, loaded } = useAccount();
  const [cfg, setCfg] = useState<BillingConfig | null>(null);
  const [near, setNear] = useState(!lazy);
  const pushed = useRef(false);
  const spot = useRef<HTMLDivElement>(null);
  useEffect(() => void billingConfig().then(setCfg, () => undefined), []);
  useEffect(() => {
    if (near || !spot.current || typeof IntersectionObserver === "undefined") return;
    const watch = new IntersectionObserver((seen) => seen.some((e) => e.isIntersecting) && setNear(true), {
      rootMargin: "300px 0px",
    });
    watch.observe(spot.current);
    return () => watch.disconnect();
  }, [near, cfg]);
  const allowed = !!cfg && loaded && adsFor(cfg, user);
  const show = allowed && near;
  useEffect(() => {
    if (!show || !cfg?.ads || pushed.current) return;
    pushed.current = true;
    const src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(cfg.ads.client)}`;
    void loadScript(src, { crossorigin: "anonymous" })
      .then(() => (window.adsbygoogle = window.adsbygoogle ?? []).push({}))
      .catch(() => undefined); // an ad blocker: fine, the slot stays empty
  }, [show, cfg]);
  if (allowed && !near) return <div ref={spot} className="ad-spot" aria-hidden="true" />;
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
