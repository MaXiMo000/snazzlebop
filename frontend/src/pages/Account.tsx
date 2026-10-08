import { useEffect, useState, type FormEvent } from "react";
import { Btn, Card, CopyButton } from "../components/ui";
import { ApiError, fetchGames } from "../lib/api";
import {
  buy,
  changePassword,
  deleteAccount,
  leaderboard,
  logIn,
  logOut,
  myStats,
  recover,
  shopItems,
  signUp,
  useAccount,
  type Board,
  type ShopItem,
  type Stats,
} from "../lib/account";
import { sfx } from "../lib/sfx";

type Tab = "in" | "up" | "forgot";

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

export function Account({ go }: { go: (path: string) => void }) {
  const { user, loaded, available } = useAccount();
  const [code, setCode] = useState<string | null>(null); // a fresh recovery code, shown once

  useEffect(() => {
    document.title = user ? `${user.username} · Snazzlebop` : "Your account · Snazzlebop";
  }, [user]);

  if (!loaded) return <p className="muted center">Loading…</p>;
  if (!available)
    return (
      <Card className="center">
        <h2>Accounts are resting</h2>
        <p className="space-top">Accounts are unavailable right now. Every game still works without one!</p>
        <Btn className="space-top" onClick={() => go("/")}>
          Back to the show
        </Btn>
      </Card>
    );
  if (code) return <RecoveryCode code={code} done={() => setCode(null)} />;
  return user ? <Profile go={go} /> : <SignIn onCode={setCode} />;
}

/** Sign in, create an account, or reset a password with the recovery code. */
function SignIn({ onCode }: { onCode: (code: string) => void }) {
  const [tab, setTab] = useState<Tab>("in");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (tab === "in") await logIn(username.trim(), password);
      else if (tab === "up") onCode(await signUp(username.trim(), password));
      else onCode(await recover(username.trim(), recoveryCode.trim(), password));
      sfx.ding();
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  };

  const titles: Record<Tab, string> = { in: "Sign in", up: "Create account", forgot: "Reset password" };
  const tabs: Record<Tab, string> = { in: "Sign in", up: "Sign up", forgot: "Forgot?" };
  return (
    <div className="stack enter acct">
      <Card tone="stage" className="center">
        <p className="sign">Your account</p>
        <h2 className="space-top acct-title">Win coins. Climb the season. Buy power-ups.</h2>
        <p className="space-top">Optional: every game works without an account. No email needed.</p>
      </Card>
      <Card>
        <div className="acct-tabs" role="group" aria-label="Account">
          {(["in", "up", "forgot"] as Tab[]).map((t) => (
            <Btn
              key={t}
              size="small"
              variant={tab === t ? "gold" : "ghost"}
              aria-pressed={tab === t}
              onClick={() => {
                setTab(t);
                setError(null);
              }}
            >
              {tabs[t]}
            </Btn>
          ))}
        </div>
        <form className="stack-sm space-top" onSubmit={(e) => void submit(e)}>
          <div>
            <label className="field" htmlFor="acct-user">
              Username
            </label>
            <input
              id="acct-user"
              type="text"
              value={username}
              maxLength={20}
              autoComplete="username"
              autoCapitalize="off"
              spellCheck={false}
              aria-describedby={tab === "up" ? "acct-user-hint" : undefined}
              onChange={(e) => setUsername(e.target.value)}
            />
            {tab === "up" && (
              <p id="acct-user-hint" className="muted acct-hint">
                3-20 letters, numbers, dots, dashes or underscores. It shows on the season leaderboard.
              </p>
            )}
          </div>
          {tab === "forgot" && (
            <div>
              <label className="field" htmlFor="acct-code">
                Recovery code
              </label>
              <input
                id="acct-code"
                type="text"
                className="code-input acct-code-input"
                value={recoveryCode}
                maxLength={30}
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                onChange={(e) => setRecoveryCode(e.target.value)}
                placeholder="XXXXX-XXXXX-XXXXX-XXXXX"
              />
            </div>
          )}
          <div>
            <label className="field" htmlFor="acct-pass">
              {tab === "in" ? "Password" : "New password"}
            </label>
            <input
              id="acct-pass"
              type="password"
              value={password}
              maxLength={128}
              autoComplete={tab === "in" ? "current-password" : "new-password"}
              aria-describedby={tab !== "in" ? "acct-pass-hint" : undefined}
              onChange={(e) => setPassword(e.target.value)}
            />
            {tab !== "in" && (
              <p id="acct-pass-hint" className="muted acct-hint">
                At least 8 characters. A short sentence is easy to remember and hard to guess.
              </p>
            )}
          </div>
          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}
          <Btn type="submit" variant="go" size="big" block disabled={busy || !username.trim() || !password}>
            {titles[tab]}
          </Btn>
        </form>
      </Card>
    </div>
  );
}

/** Shown once after sign-up or a reset: the only way back in if the password is forgotten. */
function RecoveryCode({ code, done }: { code: string; done: () => void }) {
  return (
    <Card tone="stage" className="center acct-recovery">
      <p className="sign">Save this somewhere safe</p>
      <h2 className="space-top">Your recovery code</h2>
      <p className="acct-code" aria-label={`Recovery code ${code.split("").join(" ")}`}>
        {code}
      </p>
      <p>There's no email on your account, so this code is the only way back in if you forget your password.</p>
      <p className="space-top">It's shown once. Each code works once, and you get a new one when you use it.</p>
      <div className="row center space-top">
        <CopyButton text={code} label="Copy code" />
        <Btn variant="go" onClick={done}>
          I've saved it
        </Btn>
      </div>
    </Card>
  );
}

function Profile({ go }: { go: (path: string) => void }) {
  const { user } = useAccount();
  const [stats, setStats] = useState<Stats | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [items, setItems] = useState<ShopItem[]>([]);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    myStats().then(setStats, () => undefined);
    leaderboard().then(setBoard, () => undefined);
    shopItems().then((r) => setItems(r.items), () => undefined);
    fetchGames().then((g) => setTitles(Object.fromEntries(g.map((x) => [x.id, x.title]))), () => undefined);
  }, [user?.coins]);

  if (!user) return null;
  const season = stats?.season;
  const month = season ? new Date(`${season.id}-01T00:00:00Z`).toLocaleDateString(undefined, { month: "long", year: "numeric", timeZone: "UTC" }) : "";
  return (
    <div className="stack enter acct">
      <Card tone="stage" className="center">
        <p className="sign">{user.username}</p>
        <p className="acct-coins" aria-label={`${user.coins} coins`}>
          <span aria-hidden="true">🪙</span> {user.coins}
        </p>
        <p>
          {season && season.played
            ? `${month} season: ${season.points} points${season.rank ? ` · #${season.rank}` : ""} · ${season.wins} ${season.wins === 1 ? "win" : "wins"}`
            : `Finish a game in ${month || "this month's season"} to get on the board.`}
        </p>
        <Btn className="space-top" variant="gold" onClick={() => go("/")}>
          Play a game
        </Btn>
      </Card>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <Card aria-labelledby="shop-h">
        <h3 id="shop-h">Power-up shop</h3>
        <p className="muted">Use one per game, in any game. Played in secret, revealed at the results.</p>
        <ul className="acct-shop">
          {items.map((it) => {
            const owned = user.powerups[it.id] ?? 0;
            return (
              <li key={it.id} className="acct-item">
                <span className="acct-item-icon" aria-hidden="true">
                  {it.icon}
                </span>
                <p className="acct-item-name">
                  <b>{it.name}</b>
                </p>
                <p className="muted acct-item-text">
                  {owned > 0 && <span className="chip teal acct-owned">You have {owned}</span>}
                  {it.text}
                </p>
                <Btn
                  variant="gold"
                  disabled={user.coins < it.price}
                  aria-label={`Buy ${it.name} for ${it.price} coins`}
                  onClick={async () => {
                    setError(null);
                    try {
                      await buy(it.id);
                      sfx.ding();
                    } catch (e) {
                      setError(errText(e));
                    }
                  }}
                >
                  🪙 {it.price}
                </Btn>
              </li>
            );
          })}
        </ul>
      </Card>

      <div className="grid">
        <Card aria-labelledby="board-h">
          <h3 id="board-h">{month ? `${month} leaderboard` : "Season leaderboard"}</h3>
          {board && board.rows.length ? (
            <ol className="score-rows">
              {board.rows.map((r, i) => (
                <li key={r.username} className={r.username === user.username ? "on" : ""}>
                  <b>
                    {i === 0 ? "👑 " : `${i + 1}. `}
                    {r.username}
                  </b>
                  <span className="score-tally">
                    <span>{r.wins} {r.wins === 1 ? "win" : "wins"}</span>
                    <span className="score-pts">{r.points}</span>
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">Nobody's scored this month yet. Be first!</p>
          )}
        </Card>

        <Card aria-labelledby="stats-h">
          <h3 id="stats-h">Your games</h3>
          {stats && stats.totals.played ? (
            <>
              <p className="acct-totals">
                <span>{stats.totals.played} played</span>
                <span>{stats.totals.wins} won</span>
                <span>🪙 {stats.totals.coins} earned</span>
              </p>
              <ul className="score-rows space-top">
                {Object.entries(stats.games)
                  .sort((a, b) => b[1].played - a[1].played)
                  .map(([g, s]) => (
                    <li key={g}>
                      <b>{titles[g] ?? g}</b>
                      <span className="score-tally">
                        <span>
                          {s.wins}/{s.played} won
                        </span>
                        <span className="score-pts">{s.best}</span>
                      </span>
                    </li>
                  ))}
              </ul>
              <p className="muted space-top">The number on the right is your best score in that game.</p>
            </>
          ) : (
            <p className="muted">Your games show up here once you've finished one while signed in.</p>
          )}
        </Card>
      </div>

      <Card aria-labelledby="coins-h">
        <h3 id="coins-h">How coins work</h3>
        <ul className="evidence">
          <li>Finish a game with at least one other player: 1st 50, 2nd 30, 3rd 20, 4th 10, everyone else 5.</li>
          <li>Ties share the better place. Up to 600 coins a day.</li>
          <li>Your season points are the coins you earn this month. The table starts fresh every month.</li>
        </ul>
      </Card>

      <Settings />
    </div>
  );
}

function Settings() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [del, setDel] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const run = async (fn: () => Promise<void>, ok: string) => {
    setNote(null);
    try {
      await fn();
      setNote({ ok: true, text: ok });
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    }
  };
  return (
    <Card aria-labelledby="settings-h">
      <h3 id="settings-h">Account settings</h3>
      <form
        className="stack-sm space-top"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await changePassword(current, next);
            setCurrent("");
            setNext("");
          }, "Password changed. Other devices have been signed out.");
        }}
      >
        <div>
          <label className="field" htmlFor="pw-now">
            Current password
          </label>
          <input id="pw-now" type="password" value={current} maxLength={128} autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
        </div>
        <div>
          <label className="field" htmlFor="pw-new">
            New password
          </label>
          <input id="pw-new" type="password" value={next} maxLength={128} autoComplete="new-password" onChange={(e) => setNext(e.target.value)} />
        </div>
        <Btn type="submit" disabled={!current || !next}>
          Change password
        </Btn>
      </form>
      {note && (
        <p className={`alert ${note.ok ? "calm" : ""} space-top`} role={note.ok ? "status" : "alert"}>
          {note.text}
        </p>
      )}
      <div className="row space-top acct-actions">
        <Btn variant="ghost" onClick={() => void run(logOut, "Signed out.")}>
          Sign out
        </Btn>
        {!confirming && (
          <Btn variant="danger" onClick={() => setConfirming(true)}>
            Delete account
          </Btn>
        )}
      </div>
      {confirming && (
        <form
          className="stack-sm space-top acct-delete"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => deleteAccount(del), "Your account and everything in it is gone.");
          }}
        >
          <p>
            <b>This deletes your coins, power-ups, stats and season points for good.</b> Type your password to confirm.
          </p>
          <div>
            <label className="field" htmlFor="pw-del">
              Password
            </label>
            <input id="pw-del" type="password" value={del} maxLength={128} autoComplete="current-password" onChange={(e) => setDel(e.target.value)} />
          </div>
          <div className="row">
            <Btn type="submit" variant="danger" disabled={!del}>
              Delete forever
            </Btn>
            <Btn variant="ghost" onClick={() => setConfirming(false)}>
              Keep my account
            </Btn>
          </div>
        </form>
      )}
    </Card>
  );
}
