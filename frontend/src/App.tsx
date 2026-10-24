import { useCallback, useEffect, useState } from "react";
import { CallButton } from "./components/call";
import { ChatButton } from "./components/chat";
import { SoundToggle, ThemeToggle } from "./components/ui";
import { useAccount } from "./lib/account";
import { Account, type AccountView } from "./pages/Account";
import { ClubHome, Clubs, JoinClub } from "./pages/Clubs";
import { Home } from "./pages/Home";
import { Room } from "./pages/Room";

const ROOM_PATH = /^\/r\/([A-Za-z]{3,8})\/?$/;
const ACCOUNT_PATH = /^\/account(?:\/(forgot|reset|verify))?\/?$/;
const CLUBS_PATH = /^\/clubs\/?$/;
const CLUB_PATH = /^\/clubs\/([a-z0-9-]{1,48})\/?$/;
const JOIN_PATH = /^\/join\/([A-Za-z0-9-]{4,32})\/?$/;

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
        ) : clubMatch ? (
          <ClubHome key={clubMatch[1]} slug={clubMatch[1]!} go={go} />
        ) : joinMatch ? (
          <JoinClub code={joinMatch[1]!} go={go} />
        ) : (
          <Home go={go} />
        )}
      </main>
    </>
  );
}
