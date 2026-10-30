import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { CallButton } from "./components/call";
import { ChatButton } from "./components/chat";
import { Btn, SoundToggle, ThemeToggle, Loading } from "./components/ui";
import { refreshAccount, useAccount } from "./lib/account";
import { useInbox } from "./lib/notify";
import { Account, type AccountView } from "./pages/Account";
import { ClubHome, Clubs, JoinClub } from "./pages/Clubs";
import { Ratings } from "./pages/Ratings";
import { SiteNav } from "./components/nav";
import { Home } from "./pages/Home";
import { Room } from "./pages/Room";

// Pages most visits never open load on demand, so the first page load stays small.
const ClubReports = lazy(() => import("./pages/ClubReports").then((m) => ({ default: m.ClubReports })));
const InboxPage = lazy(() => import("./pages/Inbox").then((m) => ({ default: m.InboxPage })));
const Privacy = lazy(() => import("./pages/Privacy").then((m) => ({ default: m.Privacy })));
const Terms = lazy(() => import("./pages/Terms").then((m) => ({ default: m.Terms })));
const About = lazy(() => import("./pages/About").then((m) => ({ default: m.About })));
const GamesIndex = lazy(() => import("./pages/Games").then((m) => ({ default: m.GamesIndex })));
const GamePage = lazy(() => import("./pages/Games").then((m) => ({ default: m.GamePage })));
const Safety = lazy(() => import("./pages/Safety").then((m) => ({ default: m.Safety })));
const Places = lazy(() => import("./pages/Places").then((m) => ({ default: m.Places })));
const Coins = lazy(() => import("./pages/Coins").then((m) => ({ default: m.Coins })));
const Battles = lazy(() => import("./pages/Battles").then((m) => ({ default: m.Battles })));
const Plus = lazy(() => import("./pages/Plus").then((m) => ({ default: m.Plus })));
const Quests = lazy(() => import("./pages/Quests").then((m) => ({ default: m.Quests })));
const Staff = lazy(() => import("./pages/Staff").then((m) => ({ default: m.Staff })));
const StaffPlaces = lazy(() => import("./pages/StaffPlaces").then((m) => ({ default: m.StaffPlaces })));

const ROOM_PATH = /^\/r\/([A-Za-z]{3,8})\/?$/;
const ACCOUNT_PATH = /^\/account(?:\/(forgot|reset|verify|link))?\/?$/;
const CLUBS_PATH = /^\/clubs\/?$/;
const CLUB_PATH = /^\/clubs\/([a-z0-9-]{1,48})\/?$/;
const CLUB_REPORTS_PATH = /^\/clubs\/([a-z0-9-]{1,48})\/reports\/?$/;
const PRIVACY_PATH = /^\/privacy\/?$/;
const TERMS_PATH = /^\/terms\/?$/;
const ABOUT_PATH = /^\/about\/?$/;
const GAMES_PATH = /^\/games\/?$/;
const GAME_PATH = /^\/games\/([a-z0-9]{2,24})\/?$/;
const SAFETY_PATH = /^\/safety\/?$/;
const STAFF_PATH = /^\/staff\/?$/;
const STAFF_PLACES_PATH = /^\/staff\/places\/?$/;
const PLACES_PATH = /^\/places\/?$/;
const RATINGS_PATH = /^\/ratings\/?$/;
const COINS_PATH = /^\/coins\/?$/;
const BATTLES_PATH = /^\/battles\/?$/;
const QUESTS_PATH = /^\/quests\/?$/;
const PLUS_PATH = /^\/plus\/?$/;
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

/** The server didn't answer: say so calmly, with a retry (it also retries when the device is back online). */
function OfflineNotice() {
  const { offline } = useAccount();
  const [busy, setBusy] = useState(false);
  if (!offline) return null;
  return (
    <div className="alert calm row between offline-notice" role="status">
      <span>Can’t reach Snazzlebop right now. Check your connection.</span>
      <Btn
        size="small"
        variant="ghost"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          void refreshAccount().finally(() => setBusy(false));
        }}
      >
        Try again
      </Btn>
    </div>
  );
}

/** Top bar: your coins when signed in; signed out, a way to sign in inside rooms (elsewhere the site
 * navigation already has it). Hidden if accounts are down. */
function AccountButton({ go, inRoom }: { go: (p: string) => void; inRoom: boolean }) {
  const { user, loaded, available } = useAccount();
  if (!loaded || !available || (!user && !inRoom)) return null;
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
          <AccountButton go={go} inRoom={!!match} />
          <ThemeToggle />
          <SoundToggle />
        </div>
      </header>
      {!match && <SiteNav path={path} go={go} />}
      <main id="main" className={`app ${match ? "" : "with-nav"}`}>
        {!match && <OfflineNotice />}
        <Suspense fallback={<Loading page />}>
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
        ) : TERMS_PATH.test(path) ? (
          <Terms go={go} />
        ) : ABOUT_PATH.test(path) ? (
          <About go={go} />
        ) : GAMES_PATH.test(path) ? (
          <GamesIndex go={go} />
        ) : GAME_PATH.test(path) ? (
          <GamePage key={path} id={GAME_PATH.exec(path)![1]!} go={go} />
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
        ) : QUESTS_PATH.test(path) ? (
          <Quests go={go} />
        ) : PLUS_PATH.test(path) ? (
          <Plus go={go} />
        ) : clubMatch ? (
          <ClubHome key={clubMatch[1]} slug={clubMatch[1]!} go={go} />
        ) : INBOX_PATH.test(path) ? (
          <InboxPage go={go} />
        ) : joinMatch ? (
          <JoinClub code={joinMatch[1]!} go={go} />
        ) : (
          <Home go={go} />
        )}
        </Suspense>
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
        {link("/about", "About")}
        {link("/games", "All games")}
        {link("/privacy", "Privacy")}
        {link("/terms", "Terms")}
        {link("/safety", "Safety and data")}
        {link("/clubs", "Clubs")}
        {link("/ratings", "Ratings")}
      </nav>
    </footer>
  );
}
