import { useAccount } from "../lib/account";

type Go = (path: string) => void;

// The site's main places. On phones the first five are a tab bar at the bottom; wider screens show all.
const LINKS: { to: string; icon: string; label: string; match: RegExp; wide?: boolean }[] = [
  { to: "/", icon: "🎲", label: "Play", match: /^\/$/ },
  { to: "/clubs", icon: "🏠", label: "Clubs", match: /^\/(clubs|join)\b/ },
  { to: "/quests", icon: "🎯", label: "Quests", match: /^\/quests\b/ },
  { to: "/ratings", icon: "📈", label: "Ranked", match: /^\/ratings\b/ },
  { to: "/battles", icon: "⚔️", label: "Battles", match: /^\/battles\b/, wide: true },
  { to: "/coins", icon: "🪙", label: "Coins", match: /^\/coins\b/, wide: true },
  { to: "/account", icon: "👤", label: "Me", match: /^\/(account|places|inbox|privacy|safety)\b/ },
];

/** One way around the site, the same everywhere except inside a game room. */
export function SiteNav({ path, go }: { path: string; go: Go }) {
  const { user } = useAccount();
  return (
    <nav className="site-nav" aria-label="Site">
      <ul>
        {LINKS.map((l) => {
          const here = l.match.test(path);
          return (
            <li key={l.to} className={l.wide ? "wide-only" : ""}>
              <a
                href={l.to}
                aria-current={here ? "page" : undefined}
                onClick={(e) => {
                  e.preventDefault();
                  go(l.to);
                }}
              >
                <span className="site-nav-icon" aria-hidden="true">
                  {l.icon}
                </span>
                <span className="site-nav-label">{l.to === "/account" && !user ? "Sign in" : l.label}</span>
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

const CORNER: { to: string; icon: string; label: string; text: string }[] = [
  { to: "/clubs", icon: "🏠", label: "Clubs", text: "Your groups and their rooms" },
  { to: "/quests", icon: "🎯", label: "Quests", text: "Today's three, your level" },
  { to: "/ratings", icon: "📈", label: "Ranked", text: "Ratings and leaderboards" },
  { to: "/battles", icon: "⚔️", label: "Battles", text: "Challenges and trophies" },
  { to: "/coins", icon: "🪙", label: "Coins", text: "Balance and history" },
  { to: "/places", icon: "🎓", label: "Places", text: "Your college or company" },
];

/** Home page: every feature one tap away, near the top. Guests see what signing in unlocks. */
export function YourCorner({ go }: { go: Go }) {
  const { user, available } = useAccount();
  if (!available) return null;
  if (!user)
    return (
      <section className="card soft corner-guest" aria-labelledby="corner-h">
        <h2 id="corner-h">More with an account</h2>
        <p className="muted">Clubs, daily quests, ratings, battles and a power-up shop. Games stay free and open to everyone.</p>
        <a
          className="btn gold"
          href="/account"
          onClick={(e) => {
            e.preventDefault();
            go("/account");
          }}
        >
          Sign in or sign up
        </a>
      </section>
    );
  return (
    <section className="corner" aria-labelledby="corner-h">
      <h2 id="corner-h" className="sr-only">
        Your corner
      </h2>
      <ul className="corner-grid">
        {CORNER.map((c) => (
          <li key={c.to}>
            <a
              className="corner-tile"
              href={c.to}
              onClick={(e) => {
                e.preventDefault();
                go(c.to);
              }}
            >
              <span className="corner-icon" aria-hidden="true">
                {c.icon}
              </span>
              <span className="corner-label">{c.label}</span>
              <span className="corner-text">{c.text}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
