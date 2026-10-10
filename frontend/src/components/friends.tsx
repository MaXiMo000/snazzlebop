import { useCallback, useEffect, useState } from "react";
import { ApiError, joinRoom, request } from "../lib/api";
import { Btn, Card } from "./ui";

type FriendList = { friends: { username: string; room: string | null }[]; sent: string[]; asked: string[] };
const post = (path: string, username: string) =>
  request<{ ok: boolean }>(path, { method: "POST", body: JSON.stringify({ username }) });

/**
 * Home page, signed in: your friends, and a Join button next to anyone hosting right now. Someone's room
 * shows only once you've both added each other.
 */
export function Friends({ name, go }: { name: string; go: (path: string) => void }) {
  const [list, setList] = useState<FriendList | null>(null);
  const [who, setWho] = useState("");
  const [note, setNote] = useState<{ bad: boolean; text: string } | null>(null);
  const load = useCallback(
    () =>
      request<FriendList>("/api/friends")
        .then(setList)
        .catch(() => undefined),
    [],
  );
  // Fresh every 15 seconds while this tab is the one being looked at.
  useEffect(() => {
    void load();
    const t = window.setInterval(() => document.visibilityState === "visible" && void load(), 15000);
    return () => window.clearInterval(t);
  }, [load]);

  const act = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      setNote({ bad: false, text: done });
      await load();
    } catch (e) {
      setNote({ bad: true, text: e instanceof ApiError ? e.message : "Something went wrong" });
    }
  };
  const join = async (code: string) => {
    try {
      await joinRoom(code, name.trim());
    } catch {
      /* name taken, or no name typed: the room page asks for one */
    }
    go(`/r/${code}`);
  };
  if (!list) return null;
  const live = list.friends.filter((f) => f.room);
  return (
    <Card aria-labelledby="friends-h" className="friends">
      <h2 id="friends-h">Friends</h2>
      {live.length > 0 && (
        <ul className="friend-live">
          {live.map((f) => (
            <li key={f.username}>
              <span className="friend-live-text">
                <span className="friend-dot" aria-hidden="true" />
                <b>{f.username}</b> is hosting
              </span>
              <Btn variant="go" size="small" onClick={() => void join(f.room!)}>
                Join<span className="sr-only"> {f.username}’s room</span>
              </Btn>
            </li>
          ))}
        </ul>
      )}
      {list.asked.length > 0 && (
        <ul className="friend-rows">
          {list.asked.map((u) => (
            <li key={u}>
              <span>
                <b>{u}</b> added you
              </span>
              <Btn size="small" onClick={() => void act(() => post("/api/friends", u), `You and ${u} are friends.`)}>
                Add back
              </Btn>
            </li>
          ))}
        </ul>
      )}
      {list.friends.length + list.sent.length > 0 ? (
        <ul className="friend-chips">
          {list.friends.map((f) => (
            <li key={f.username}>
              {f.username}
              <button
                type="button"
                className="friend-x"
                aria-label={`Remove ${f.username}`}
                onClick={() => void act(() => post("/api/friends/remove", f.username), `Removed ${f.username}.`)}
              >
                ✕
              </button>
            </li>
          ))}
          {list.sent.map((u) => (
            <li key={u} className="pending">
              {u} <span className="muted">(hasn’t added you yet)</span>
              <button
                type="button"
                className="friend-x"
                aria-label={`Remove ${u}`}
                onClick={() => void act(() => post("/api/friends/remove", u), `Removed ${u}.`)}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      ) : (
        list.asked.length === 0 && (
          <p className="muted">Add friends by username. When they host a room, you can join with one tap.</p>
        )
      )}
      <form
        className="friend-add"
        onSubmit={(e) => {
          e.preventDefault();
          const u = who.trim();
          if (!u) return;
          void act(() => post("/api/friends", u), `Added ${u}. You'll see their rooms once they add you too.`).then(
            () => setWho(""),
          );
        }}
      >
        <label className="sr-only" htmlFor="friend-name">
          A friend’s username
        </label>
        <input
          id="friend-name"
          type="text"
          value={who}
          maxLength={20}
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="Username"
          onChange={(e) => setWho(e.target.value)}
        />
        <Btn type="submit" disabled={!who.trim()}>
          Add
        </Btn>
      </form>
      {note && (
        <p className={note.bad ? "alert" : "muted"} role="status">
          {note.text}
        </p>
      )}
    </Card>
  );
}

type InstallEvent = Event & { prompt: () => Promise<void> };

/** "Install app": shown when the browser offers it (Android, desktop); on iPhones a one-line how-to. */
export function InstallApp() {
  const [offer, setOffer] = useState<InstallEvent | null>(null);
  const [standalone] = useState(
    () =>
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as { standalone?: boolean }).standalone === true,
  );
  const [ios] = useState(() => /iPhone|iPad/i.test(navigator.userAgent));
  useEffect(() => {
    const on = (e: Event) => {
      e.preventDefault();
      setOffer(e as InstallEvent);
    };
    const done = () => setOffer(null);
    window.addEventListener("beforeinstallprompt", on);
    window.addEventListener("appinstalled", done);
    return () => {
      window.removeEventListener("beforeinstallprompt", on);
      window.removeEventListener("appinstalled", done);
    };
  }, []);
  if (offer)
    return (
      <p className="install center">
        <Btn variant="ghost" onClick={() => void offer.prompt().then(() => setOffer(null))}>
          📲 Install the app
        </Btn>
      </p>
    );
  if (ios && !standalone)
    return <p className="install muted center">On an iPhone: tap Share, then “Add to Home Screen” to install.</p>;
  return null;
}
