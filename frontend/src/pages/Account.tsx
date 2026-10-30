import { useEffect, useId, useState, type FormEvent } from "react";
import { AccountPerks } from "../components/nav";
import {
  Alert,
  AuthMessage,
  EmailCard,
  EmailLinkForm,
  ForgotEmail,
  GoogleButton,
  GoogleCard,
  OrLine,
  OtpField,
  PasswordField,
  ResetPassword,
  SessionCard,
  SignInWithLink,
  VerifyEmail,
  YourPassword,
  errText,
  needsCode,
  useConfirmed,
  useGoogleOutcome,
} from "../components/auth";
import { Authenticator } from "../components/security";
import { Btn, Card, CopyButton, Loading } from "../components/ui";
import { InviteWaiting } from "./Clubs";
import { fetchGames } from "../lib/api";
import {
  buy,
  changePassword,
  deleteAccount,
  leaderboard,
  logIn,
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

export type AccountView = "home" | "forgot" | "reset" | "verify" | "link";
type Tab = "in" | "up" | "forgot";

export function Account({ go, view = "home" }: { go: (path: string) => void; view?: AccountView }) {
  const { user, loaded, available } = useAccount();
  const [code, setCode] = useState<string | null>(null); // a fresh recovery code, shown once
  const [signedOut, setSignedOut] = useState(false);
  const outcome = useGoogleOutcome();

  useEffect(() => {
    if (view === "home" || view === "forgot") document.title = user ? `${user.username} · Snazzlebop` : "Your account · Snazzlebop";
  }, [user, view]);
  useEffect(() => {
    if (user) setSignedOut(false);
  }, [user]);

  if (!loaded) return <Loading page />;
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
  if (view === "reset") return <ResetPassword go={go} />;
  if (view === "verify") return <VerifyEmail go={go} />;
  if (view === "link") return <SignInWithLink go={go} />;
  if (code) return <RecoveryCode code={code} done={() => setCode(null)} />;
  if (user) return <Profile go={go} onSignedOut={() => setSignedOut(true)} notice={outcome} />;
  if (signedOut)
    return (
      <AuthMessage
        go={(p) => (setSignedOut(false), go(p))}
        icon="👋"
        title="You're signed out"
        text="See you next show! Your coins, stats and power-ups are safe for when you sign back in."
        action={["Sign in again", "/account"]}
      />
    );
  return <SignIn key={view} onCode={setCode} start={view === "forgot" ? "forgot" : "in"} notice={outcome} />;
}

/** Sign in, create an account, or get back in after forgetting the password. */
type Notice = { ok: boolean; text: string } | null;

function SignIn({ onCode, start, notice }: { onCode: (code: string) => void; start: Tab; notice: Notice }) {
  const { mail, google } = useAccount();
  const [tab, setTab] = useState<Tab>(start);
  const [byCode, setByCode] = useState(!mail); // forgot: the recovery-code form instead of the email one
  const [byLink, setByLink] = useState(false); // sign in: a link by email instead of the password
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [adult, setAdult] = useState(false);
  const [otp, setOtp] = useState<string | null>(null); // null until the server asks for a code
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  const pick = (t: Tab) => {
    setTab(t);
    setError(null);
    setOtp(null);
    setPassword("");
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const code = otp?.trim() || undefined;
      if (tab === "in") await logIn(username.trim(), password, code);
      else if (tab === "up") onCode(await signUp(username.trim(), password, email.trim() || undefined));
      else onCode(await recover(username.trim(), recoveryCode.trim(), password, code));
      sfx.ding();
    } catch (err) {
      if (needsCode(err) && otp === null) setOtp("");
      else setError(errText(err));
    } finally {
      setBusy(false);
    }
  };

  const tabs: Record<Tab, string> = { in: "Sign in", up: "Sign up", forgot: "Forgot password" };
  const lead: Record<Tab, string> = {
    in: "Welcome back! Your coins and power-ups are waiting.",
    up: "Takes ten seconds. Every game still works without an account.",
    forgot: mail
      ? "We'll email you a reset link. It only goes to an email you've confirmed on the account."
      : "Get back in with the recovery code you saved at sign-up.",
  };
  const ready =
    !!username.trim() && !!password && otp?.trim() !== "" && (tab !== "forgot" || recoveryCode.trim().length >= 10) && (tab !== "up" || (password.length >= 8 && adult));

  return (
    <div className="stack enter acct auth">
      <Card tone="stage" className="center auth-hero">
        <p className="sign">Your account</p>
        <h2 className="space-top acct-title">Win coins. Climb the season. Buy power-ups.</h2>
      </Card>
      <Card className="auth-card">
        <div
          className="auth-tabs"
          role="tablist"
          aria-label="Account"
          onKeyDown={(e) => {
            const order: Tab[] = ["in", "up", "forgot"];
            const i = order.indexOf(tab);
            const next = e.key === "ArrowRight" ? order[(i + 1) % 3] : e.key === "ArrowLeft" ? order[(i + 2) % 3] : null;
            if (!next) return;
            e.preventDefault();
            pick(next);
            document.getElementById(`${id}-tab-${next}`)?.focus();
          }}
        >
          {(["in", "up", "forgot"] as Tab[]).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              id={`${id}-tab-${t}`}
              aria-selected={tab === t}
              aria-controls={`${id}-panel`}
              tabIndex={tab === t ? 0 : -1}
              className={`auth-tab ${tab === t ? "on" : ""}`}
              onClick={() => pick(t)}
            >
              {tabs[t]}
            </button>
          ))}
        </div>
        <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-tab-${tab}`} className="space-top">
          {notice && (
            <div className="auth-notice">
              <Alert text={notice.text} calm={notice.ok} />
            </div>
          )}
          <p className="auth-lead">{tab === "in" && byLink ? "No password needed: we'll email you a link that signs you in." : lead[tab]}</p>
          {tab === "up" && <AccountPerks compact />}
          {tab === "forgot" && mail && !byCode ? (
            <div className="space-top">
              <ForgotEmail onRecoveryCode={() => setByCode(true)} />
            </div>
          ) : tab === "in" && mail && byLink ? (
            <div className="space-top">
              <EmailLinkForm onPassword={() => setByLink(false)} />
            </div>
          ) : (
            <>
            {google && tab !== "forgot" && (
              <div className="space-top">
                <GoogleButton label={tab === "up" ? "Sign up with Google" : "Continue with Google"} />
                <p className="muted acct-hint center">
                  A new account with Google means you're 18 or older and agree to the{" "}
                  <a href="/terms" target="_blank" rel="noopener">
                    Terms
                  </a>
                  .
                </p>
                <OrLine />
              </div>
            )}
            <form className={`stack-sm ${google && tab !== "forgot" ? "" : "space-top"}`} onSubmit={(e) => void submit(e)}>
              <div>
                <label className="field" htmlFor={`${id}-user`}>
                  {tab === "in" && mail ? "Username or email" : "Username"}
                </label>
                <input
                  id={`${id}-user`}
                  type="text"
                  value={username}
                  maxLength={tab === "in" ? 254 : 20}
                  autoComplete="username"
                  autoCapitalize="off"
                  spellCheck={false}
                  aria-describedby={tab === "up" ? `${id}-user-hint` : undefined}
                  onChange={(e) => setUsername(e.target.value)}
                />
                {tab === "up" && (
                  <p id={`${id}-user-hint`} className="muted acct-hint">
                    3-20 letters, numbers, dots, dashes or underscores. It shows on the season leaderboard.
                  </p>
                )}
              </div>
              {tab === "up" && mail && (
                <div>
                  <label className="field" htmlFor={`${id}-email`}>
                    Email <span className="muted">(optional)</span>
                  </label>
                  <input
                    id={`${id}-email`}
                    type="email"
                    inputMode="email"
                    value={email}
                    maxLength={254}
                    autoComplete="email"
                    aria-describedby={`${id}-email-hint`}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                  <p id={`${id}-email-hint`} className="muted acct-hint">
                    For reset links and a heads-up about new sign‑ins. Never shown to anyone, never used for ads.
                  </p>
                </div>
              )}
              {tab === "forgot" && (
                <div>
                  <label className="field" htmlFor={`${id}-code`}>
                    Recovery code
                  </label>
                  <input
                    id={`${id}-code`}
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
              <PasswordField
                id={`${id}-pass`}
                label={tab === "in" ? "Password" : "New password"}
                value={password}
                set={setPassword}
                autoComplete={tab === "in" ? "current-password" : "new-password"}
                meter={tab !== "in"}
                hint={tab !== "in" ? "At least 8 characters. A short sentence is easy to remember and hard to guess." : undefined}
              />
              {tab === "in" && (
                <div className="auth-alt">
                  <button type="button" className="link-button" onClick={() => pick("forgot")}>
                    Forgot your password?
                  </button>
                  {mail && (
                    <button type="button" className="link-button" onClick={() => setByLink(true)}>
                      Email me a sign-in link
                    </button>
                  )}
                </div>
              )}
              {tab === "up" && (
                <label className="check">
                  <input type="checkbox" checked={adult} onChange={(e) => setAdult(e.target.checked)} />
                  <span>
                    I'm 18 or older and agree to the{" "}
                    <a href="/terms" target="_blank" rel="noopener">
                      Terms
                    </a>
                  </span>
                </label>
              )}
              {otp !== null && tab !== "up" && <OtpField id={`${id}-otp`} value={otp} set={setOtp} />}
              <Alert text={error} />
              <Btn type="submit" variant="go" size="big" block disabled={busy || !ready}>
                {busy ? "One moment…" : tab === "in" ? "Sign in" : tab === "up" ? "Create my account" : "Reset my password"}
              </Btn>
              {tab === "forgot" && mail && (
                <button type="button" className="link-button" onClick={() => setByCode(false)}>
                  Lost the code? Get a link by email instead
                </button>
              )}
              {tab === "in" && (
                <p className="muted center auth-switch">
                  New here?{" "}
                  <button type="button" className="link-button" onClick={() => pick("up")}>
                    Make an account
                  </button>
                </p>
              )}
            </form>
            </>
          )}
        </div>
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
      <p>It resets your password if you forget it, even if you lose access to your email.</p>
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

type AcctTab = "profile" | "shop" | "security";
const ACCT_TABS: [AcctTab, string][] = [
  ["profile", "👤 Profile"],
  ["shop", "🛒 Shop"],
  ["security", "🔒 Security"],
];
// The shop's shelves: by what an item is for (the server's "game" line for each item).
const SHOP_GROUPS: [string, (game: string) => boolean][] = [
  ["Party items: any game", (g) => g.startsWith("Party")],
  ["Emote packs", (g) => g === "Emotes"],
  ["Power-ups for each game", (g) => !g.startsWith("Party") && g !== "Emotes"],
];

function Profile({ go, onSignedOut, notice }: { go: (path: string) => void; onSignedOut: () => void; notice: Notice }) {
  const { user, staff } = useAccount();
  const [stats, setStats] = useState<Stats | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [items, setItems] = useState<ShopItem[]>([]);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<AcctTab>(() => (location.hash === "#shop" ? "shop" : location.hash === "#security" ? "security" : "profile"));

  useEffect(() => {
    myStats().then(setStats, () => undefined);
    leaderboard().then(setBoard, () => undefined);
    shopItems().then((r) => setItems(r.items), () => undefined);
    fetchGames().then((g) => setTitles(Object.fromEntries(g.map((x) => [x.id, x.title]))), () => undefined);
  }, [user?.coins]);

  if (!user) return null;
  const shopCard = (
    <Card aria-labelledby="shop-h">
      <h3 id="shop-h">Shop</h3>
      <p className="muted">
        Power-ups work one per game in casual rooms (never ranked games or battles), and everyone sees when you use one. Party items work anywhere; emote packs are
        yours for good.
      </p>
      {SHOP_GROUPS.map(([title, test]) => {
        const group = items.filter((it) => test(it.game));
        if (!group.length) return null;
        return (
          <section key={title} className="shop-group" aria-label={title}>
            <h4>{title}</h4>
            <ul className="shop-grid">
              {group.map((it) => {
                const owned = user.powerups[it.id] ?? 0;
                const kept = it.id.startsWith("emote_"); // emote packs are bought once and kept
                return (
                  <li key={it.id} className="shop-item">
                    <span className="shop-item-icon" aria-hidden="true">
                      {it.icon}
                    </span>
                    <span className="shop-item-text">
                      <b>{it.name}</b>
                      {title.startsWith("Power-ups") && <span className="muted shop-item-game">{it.game}</span>}
                      <span className="muted shop-item-desc">{it.text}</span>
                    </span>
                    {owned > 0 && <span className="chip teal shop-owned">{kept ? "Yours" : `×${owned}`}</span>}
                    <Btn
                      variant="gold"
                      size="small"
                      disabled={user.coins < it.price || (kept && owned > 0)}
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
          </section>
        );
      })}
    </Card>
  );
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
        <div className="row center space-top">
          <Btn variant="gold" onClick={() => go("/")}>
            Play a game
          </Btn>
          <Btn variant="ghost" onClick={() => go("/quests")}>
            Quests and level
          </Btn>
          <Btn variant="ghost" onClick={() => go("/clubs")}>
            Your clubs
          </Btn>
          <Btn variant="ghost" onClick={() => go("/places")}>
            Your places
          </Btn>
          <Btn variant="ghost" onClick={() => go("/ratings")}>
            Your ratings
          </Btn>
          <Btn variant="ghost" onClick={() => go("/plus")}>
            {user.plus ? "Your Plus" : "Get Plus"}
          </Btn>
          <Btn variant="ghost" onClick={() => go("/battles")}>
            Your battles
          </Btn>
          {staff && (
            <Btn variant="ghost" onClick={() => go("/staff")}>
              Staff console
            </Btn>
          )}
        </div>
      </Card>
      {notice && <Alert text={notice.text} calm={notice.ok} />}
      <InviteWaiting go={go} />

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <div className="auth-tabs acct-tabs" role="group" aria-label="Your account">
        {ACCT_TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`auth-tab ${tab === id ? "on" : ""}`}
            aria-pressed={tab === id}
            onClick={() => {
              setTab(id);
              history.replaceState(null, "", id === "profile" ? location.pathname : `#${id}`);
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "shop" && shopCard}

      {tab === "profile" && (
        <>
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
            <h3 id="coins-h">Coins</h3>
            <p className="muted">Every game you finish pays coins: 50 for 1st down to 5 for taking part, up to 600 a day. See where every coin came from and went.</p>
            <Btn className="space-top" variant="ghost" onClick={() => go("/coins")}>
              Coin history
            </Btn>
          </Card>

        </>
      )}

      {tab === "security" && (
        <>
          <EmailCard />
          <GoogleCard />
          <Authenticator />
          <SessionCard onSignedOut={onSignedOut} />
          <Settings />
        </>
      )}
    </div>
  );
}

function Settings() {
  const { user } = useAccount();
  const hasPassword = user?.has_password ?? true;
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [del, setDel] = useState("");
  const [delCode, setDelCode] = useState<string | null>(null); // asked for when the authenticator is on
  const [confirming, setConfirming] = useState(false);
  const delReady = useConfirmed(del);
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
          }, hasPassword ? "Password changed. Other devices have been signed out." : "Password set. You can sign in with it or with Google.");
        }}
      >
        {hasPassword ? (
          <div>
            <label className="field" htmlFor="pw-now">
              Current password
            </label>
            <input id="pw-now" type="password" value={current} maxLength={128} autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
          </div>
        ) : (
          <p className="muted">You sign in with Google. Set a password to sign in with your username too.</p>
        )}
        <PasswordField
          id="pw-new"
          label="New password"
          value={next}
          set={setNext}
          autoComplete="new-password"
          meter
          hint="At least 8 characters. A short sentence is easy to remember and hard to guess."
        />
        <Btn type="submit" disabled={(hasPassword && !current) || next.length < 8}>
          {hasPassword ? "Change password" : "Set a password"}
        </Btn>
      </form>
      {note && (
        <p className={`alert ${note.ok ? "calm" : ""} space-top`} role={note.ok ? "status" : "alert"}>
          {note.text}
        </p>
      )}
      <div className="row space-top acct-actions">
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
            void (async () => {
              try {
                await deleteAccount(del, delCode?.trim() || undefined);
                setNote({ ok: true, text: "Your account and everything in it is gone." });
              } catch (err) {
                if (needsCode(err) && delCode === null) setDelCode("");
                else setNote({ ok: false, text: errText(err) });
              }
            })();
          }}
        >
          <p>
            <b>This deletes your coins, power-ups, stats and season points for good.</b>
            {hasPassword ? " Type your password to confirm." : ""}
          </p>
          <YourPassword id="pw-del" value={del} set={setDel} />
          {delCode !== null && <OtpField id="del-otp" value={delCode} set={setDelCode} />}
          <div className="row">
            <Btn type="submit" variant="danger" disabled={!delReady || delCode?.trim() === ""}>
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
