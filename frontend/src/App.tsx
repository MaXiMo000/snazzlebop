import { useCallback, useEffect, useState } from "react";
import { CallButton } from "./components/call";
import { ChatButton } from "./components/chat";
import { SoundToggle, ThemeToggle } from "./components/ui";
import { useAccount } from "./lib/account";
import { useInbox } from "./lib/notify";
import { Account, type AccountView } from "./pages/Account";
import { ClubHome, Clubs, JoinClub } from "./pages/Clubs";
import { ClubReports } from "./pages/ClubReports";
import { InboxPage } from "./pages/Inbox";
import { Privacy } from "./pages/Privacy";
import { Safety } from "./pages/Safety";
import { Places } from "./pages/Places";
import { Ratings } from "./pages/Ratings";
import { Coins } from "./pages/Coins";
import { Battles } from "./pages/Battles";
import { Staff } from "./pages/Staff";
import { StaffPlaces } from "./pages/StaffPlaces";
import { Home } from "./pages/Home";
import { Room } from "./pages/Room";

const ROOM_PATH = /^\/r\/([A-Za-z]{3,8})\/?$/;
const ACCOUNT_PATH = /^\/account(?:\/(forgot|reset|verify|link))?\/?$/;
const CLUBS_PATH = /^\/clubs\/?$/;
const CLUB_PATH = /^\/clubs\/([a-z0-9-]{1,48})\/?$/;
const CLUB_REPORTS_PATH = /^\/clubs\/([a-z0-9-]{1,48})\/reports\/?$/;
const PRIVACY_PATH = /^\/privacy\/?$/;
const SAFETY_PATH = /^\/safety\/?$/;
const STAFF_PATH = /^\/staff\/?$/;
const STAFF_PLACES_PATH = /^\/staff\/places\/?$/;
const PLACES_PATH = /^\/places\/?$/;
const RATINGS_PATH = /^\/ratings\/?$/;
const COINS_PATH = /^\/coins\/?$/;
const BATTLES_PATH = /^\/battles\/?$/;
const JOIN_PATH = /^\/join\/([A-Za-z0-9-]{4,32})\/?$/;
const INBOX_PATH = /^\/inbox\/?$/;

function usePath(): [string, (p: string) => void] {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const go = useCallback((next: string) => {
    window.history.pushState({}, "", next);
    setPath(next);
    window.scrollTo(0, 0);
  }, []);
  return [path, go];
}

/** Top bar: the inbox, with how many are unread. Its poll runs everywhere (it's what makes you "online"
 * to friends), but the bell itself stays out of rooms, where the bar is full of game controls. */
function InboxButton({ go, inRoom }: { go: (p: string) => void; inRoom: boolean }) {
  const { user, available } = useAccount();
  const inbox = useInbox(!!user && available);
  if (!inbox || inRoom) return null;
  const unread = inbox.unread;
  return (
    <a
      className="btn small ghost inbox-btn"
      href="/inbox"
      onClick={(e) => {
        e.preventDefault();
        go("/inbox");
      }}
      aria-label={unread ? `Inbox, ${unread} unread` : "Inbox"}
    >
      <span aria-hidden="true">🔔</span> <span className="btn-label">Inbox</span>
      {unread > 0 && (
        <span className="chat-badge" aria-hidden="true">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </a>
  );
}

/** Top bar: your coins when signed in, otherwise a way to sign in. Hidden if accounts are down. */
function AccountButton({ go }: { go: (p: string) => void }) {
  const { user, loaded, available } = useAccount();
  if (!loaded || !available) return null;
  return (
    <a
      className={`btn small acct-btn ${user ? "gold" : "ghost"}`}
      href="/account"
      onClick={(e) => {
        e.preventDefault();
        go("/account");
      }}
      aria-label={user ? `Your account: ${user.username}, ${user.coins} coins` : "Sign in"}
    >
      {user ? (
        <>
          <span aria-hidden="true">🪙</span> {user.coins}
        </>
      ) : (
        <>
          <span className="acct-icon" aria-hidden="true">
            👤
          </span>
          <span className="account-label">Sign in</span>
        </>
      )}
    </a>
  );
}

export function App() {
  const [path, go] = usePath();
  const match = ROOM_PATH.exec(path);
  const accountMatch = ACCOUNT_PATH.exec(path);
  const clubMatch = CLUB_PATH.exec(path);
  const reportsMatch = CLUB_REPORTS_PATH.exec(path);
  const joinMatch = JOIN_PATH.exec(path);
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <a
          className="logo"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            go("/");
          }}
        >
          <span className="badge" aria-hidden="true">
            ★
          </span>
          <span className="logo-word">
            Snazzlebop<span className="bang">!</span>
          </span>
        </a>
        <div className="row topbar-tools">
          <CallButton go={go} />
          <ChatButton />
          <InboxButton go={go} inRoom={!!match} />
          <AccountButton go={go} />
          <ThemeToggle />
          <SoundToggle />
        </div>
      </header>
      <main id="main" className="app">
        {match ? (
          <Room key={match[1]} code={match[1]!.toUpperCase()} go={go} tv={new URLSearchParams(window.location.search).get("tv") === "1"} />
        ) : accountMatch ? (
          <Account go={go} view={(accountMatch[1] as AccountView | undefined) ?? "home"} />
        ) : CLUBS_PATH.test(path) ? (
          <Clubs go={go} />
        ) : reportsMatch ? (
          <ClubReports key={reportsMatch[1]} slug={reportsMatch[1]!} go={go} />
        ) : PRIVACY_PATH.test(path) ? (
          <Privacy go={go} />
        ) : SAFETY_PATH.test(path) ? (
          <Safety go={go} />
        ) : STAFF_PATH.test(path) ? (
          <Staff go={go} />
        ) : STAFF_PLACES_PATH.test(path) ? (
          <StaffPlaces go={go} />
        ) : PLACES_PATH.test(path) ? (
          <Places go={go} />
        ) : RATINGS_PATH.test(path) ? (
          <Ratings go={go} />
        ) : COINS_PATH.test(path) ? (
          <Coins go={go} />
        ) : BATTLES_PATH.test(path) ? (
          <Battles go={go} />
        ) : clubMatch ? (
          <ClubHome key={clubMatch[1]} slug={clubMatch[1]!} go={go} />
        ) : INBOX_PATH.test(path) ? (
          <InboxPage go={go} />
        ) : joinMatch ? (
          <JoinClub code={joinMatch[1]!} go={go} />
        ) : (
          <Home go={go} />
        )}
      </main>
      {!match && <SiteFooter go={go} />}
    </>
  );
}

/** Every page but a room: the links people look for at the bottom of a site. */
function SiteFooter({ go }: { go: (p: string) => void }) {
  const link = (to: string, label: string) => (
    <a
      href={to}
      onClick={(e) => {
        e.preventDefault();
        go(to);
      }}
    >
      {label}
    </a>
  );
  return (
    <footer className="site-footer">
      <nav aria-label="About this site">
        {link("/privacy", "Privacy")}
        {link("/safety", "Safety and data")}
        {link("/clubs", "Clubs")}
        {link("/ratings", "Ratings")}
      </nav>
    </footer>
  );
}
