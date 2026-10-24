import { useCallback, useEffect, useState } from "react";
import { Alert, errText } from "../components/auth";
import { Btn, Card } from "../components/ui";
import { useAccount } from "../lib/account";
import { blocked, EXPORT_URL, unblock, type BlockList } from "../lib/safety";

type Go = (path: string) => void;

/** Your safety and your data: the people you've blocked, how reporting works, and a copy of your data. */
export function Safety({ go }: { go: Go }) {
  const { user, loaded } = useAccount();
  const [list, setList] = useState<BlockList["people"] | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const load = useCallback(() => blocked().then((r) => setList(r.people), () => setList([])), []);

  useEffect(() => {
    document.title = "Safety and data · Snazzlebop";
    if (user) void load();
  }, [user, load]);

  if (!loaded) return <p className="muted center">Loading…</p>;
  return (
    <div className="stack enter prose-page">
      <Card tone="stage" className="center">
        <p className="sign">Safety and data</p>
        <h1 className="space-top prose-title">You're in control</h1>
      </Card>

      <Card aria-labelledby="sf-how">
        <h2 id="sf-how">If someone makes it not fun</h2>
        <ul className="prose-list">
          <li><b>In a room:</b> use <i>Report a problem</i> in the lobby. The host can also remove anyone from the room.</li>
          <li><b>In a club:</b> tap <i>More</i> next to their name on the club page to report or block them. The club's moderators look at reports.</li>
          <li><b>Blocking is silent:</b> they aren't told. You stop seeing each other's chat in rooms, they can't invite you, add you, see when you're around, or join rooms you host.</li>
        </ul>
      </Card>

      {user ? (
        <>
          <Card aria-labelledby="sf-blocked">
            <h2 id="sf-blocked">People you've blocked</h2>
            {list === null ? (
              <p className="muted">Loading…</p>
            ) : list.length ? (
              <ul className="club-rooms">
                {list.map((p) => (
                  <li key={p.username}>
                    <span className="club-room-text">
                      <b>{p.username}</b>
                      <span className="muted">Since {new Date(p.since).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</span>
                    </span>
                    <Btn
                      size="small"
                      variant="ghost"
                      onClick={() =>
                        void unblock(p.username).then(
                          () => (setNote({ ok: true, text: `Unblocked ${p.username}.` }), load()),
                          (e) => setNote({ ok: false, text: errText(e) }),
                        )
                      }
                    >
                      Unblock<span className="sr-only"> {p.username}</span>
                    </Btn>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">Nobody. Good!</p>
            )}
            {note && (
              <div className="space-top">
                <Alert text={note.text} calm={note.ok} />
              </div>
            )}
          </Card>

          <Card aria-labelledby="sf-data">
            <h2 id="sf-data">Your data</h2>
            <p>Download a copy of everything we keep about your account: games, coins, clubs, friends, notifications and settings.</p>
            <a className="btn gold space-top" href={EXPORT_URL} download="snazzlebop-my-data.json">
              Download my data
            </a>
          </Card>
        </>
      ) : (
        <Card className="center">
          <p>Sign in to see the people you've blocked and download your data.</p>
          <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
            Sign in
          </Btn>
        </Card>
      )}

      <p className="center">
        <a
          href="/privacy"
          onClick={(e) => {
            e.preventDefault();
            go("/privacy");
          }}
        >
          Read the privacy notice
        </a>
      </p>
    </div>
  );
}
