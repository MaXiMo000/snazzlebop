import { useCallback, useEffect, useState } from "react";
import { Home } from "./pages/Home";
import { Room } from "./pages/Room";

const ROOM_PATH = /^\/r\/([A-Za-z]{3,8})\/?$/;

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

export function App() {
  const [path, go] = usePath();
  const match = ROOM_PATH.exec(path);
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="app">
        <div className="topbar">
          <a
            className="logo"
            href="/"
            onClick={(e) => {
              e.preventDefault();
              go("/");
            }}
          >
            SNAZZLEBOP!
          </a>
        </div>
        <main id="main">{match ? <Room key={match[1]} code={match[1]!.toUpperCase()} go={go} /> : <Home go={go} />}</main>
      </div>
    </>
  );
}
