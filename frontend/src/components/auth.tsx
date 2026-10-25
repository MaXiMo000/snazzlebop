import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ApiError } from "../lib/api";
import {
  emailSignInLink,
  forgotPassword,
  logOut,
  mySessions,
  removeEmail,
  resendEmail,
  resetPassword,
  setEmail,
  signOutOthers,
  signOutSession,
  useAccount,
  signInWithLink,
  verifyEmail,
} from "../lib/account";
import type { SessionList } from "../lib/contract";
import { sfx } from "../lib/sfx";
import { Btn, Card } from "./ui";

type Go = (path: string) => void;
export const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");
/** The server wants the second step: a code from the authenticator app (or a backup code). */
export const needsCode = (e: unknown) => e instanceof ApiError && e.code === "mfa_required";

export function Alert({ text, calm = false }: { text: string | null; calm?: boolean }) {
  if (!text) return null;
  return (
    <p className={`alert ${calm ? "calm" : ""}`} role={calm ? "status" : "alert"}>
      {text}
    </p>
  );
}

/** The authenticator code box, shown once the server asks for it. */
export function OtpField({ id, value, set }: { id: string; value: string; set: (v: string) => void }) {
  return (
    <div>
      <label className="field" htmlFor={id}>
        Code from your authenticator app (or a backup code)
      </label>
      <input
        id={id}
        type="text"
        className="code-input"
        inputMode="text"
        autoComplete="one-time-code"
        maxLength={12}
        value={value}
        autoFocus
        onChange={(e) => set(e.target.value)}
        placeholder="123 456"
      />
    </div>
  );
}

// -- passwords --------------------------------------------------------------------------------------
const COMMON = ["password", "12345678", "qwerty", "iloveyou", "letmein", "welcome", "snazzlebop", "football"];

/** 0-4: a rough guide for the meter. The server's rules (8+ characters, not a common one) still decide. */
export function strength(pw: string): number {
  if (pw.length < 8 || COMMON.some((c) => pw.toLowerCase().includes(c))) return 0;
  const kinds = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  let score = 1 + (pw.length >= 12 ? 1 : 0) + (pw.length >= 16 ? 1 : 0) + (kinds >= 3 ? 1 : 0);
  if (/^(.)\1+$/.test(pw)) score = 1;
  return Math.min(score, 4);
}
const STRENGTH = ["Too short or too common", "Weak", "OK", "Good", "Strong"];

export function PasswordField({
  id,
  label,
  value,
  set,
  autoComplete,
  meter = false,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  set: (v: string) => void;
  autoComplete: "current-password" | "new-password";
  meter?: boolean;
  hint?: string;
}) {
  const [shown, setShown] = useState(false);
  const [caps, setCaps] = useState(false);
  const score = strength(value);
  const hintId = `${id}-hint`;
  const checkCaps = (e: KeyboardEvent<HTMLInputElement>) => setCaps(e.getModifierState("CapsLock"));
  return (
    <div>
      <label className="field" htmlFor={id}>
        {label}
      </label>
      <div className="pw-wrap">
        <input
          id={id}
          type={shown ? "text" : "password"}
          value={value}
          maxLength={128}
          autoComplete={autoComplete}
          autoCapitalize="off"
          spellCheck={false}
          aria-describedby={hint || meter ? hintId : undefined}
          onChange={(e) => set(e.target.value)}
          onKeyUp={checkCaps}
          onKeyDown={checkCaps}
          onBlur={() => setCaps(false)}
        />
        <button type="button" className="pw-toggle" aria-controls={id} aria-pressed={shown} onClick={() => setShown((s) => !s)}>
          {shown ? "Hide" : "Show"}
          <span className="sr-only"> password</span>
        </button>
      </div>
      {caps && (
        <p className="pw-caps" role="status">
          Caps Lock is on
        </p>
      )}
      {meter && value && (
        <div className={`pw-meter s${score}`} aria-hidden="true">
          {[1, 2, 3, 4].map((i) => (
            <span key={i} className={i <= score ? "on" : ""} />
          ))}
        </div>
      )}
      {(hint || meter) && (
        <p id={hintId} className="muted acct-hint" aria-live="polite">
          {meter && value ? <b className="pw-score">{STRENGTH[score]}. </b> : null}
          {hint}
        </p>
      )}
    </div>
  );
}

// -- forgot password --------------------------------------------------------------------------------
/** Both ways back in: a link by email (when the site sends email), or the recovery code. */
export function ForgotEmail({ onRecoveryCode }: { onRecoveryCode: () => void }) {
  const [login, setLogin] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (wait <= 0) return;
    const t = window.setTimeout(() => setWait((w) => w - 1), 1000);
    return () => window.clearTimeout(t);
  }, [wait]);

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await forgotPassword(login.trim());
      setSent(login.trim());
      setWait(60);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  };

  if (sent)
    return (
      <div className="stack-sm auth-sent" aria-live="polite">
        <p className="auth-big" aria-hidden="true">
          📬
        </p>
        <h3>Check your inbox</h3>
        <p>
          If <b className="auth-who">{sent}</b> has a confirmed email, a reset link is on its way. It works for 30 minutes.
        </p>
        <p className="muted">Nothing there? Check spam, or the account may not have an email: use your recovery code instead.</p>
        <Alert text={error} />
        <div className="row">
          <Btn size="small" variant="ghost" disabled={busy || wait > 0} onClick={() => void send()}>
            {wait > 0 ? `Send again in ${wait}s` : "Send again"}
          </Btn>
          <Btn size="small" variant="ghost" onClick={onRecoveryCode}>
            Use my recovery code
          </Btn>
        </div>
      </div>
    );

  return (
    <form className="stack-sm" onSubmit={(e) => void send(e)}>
      <div>
        <label className="field" htmlFor="forgot-login">
          Username or email
        </label>
        <input
          id="forgot-login"
          type="text"
          value={login}
          maxLength={254}
          autoComplete="username"
          autoCapitalize="off"
          spellCheck={false}
          onChange={(e) => setLogin(e.target.value)}
        />
      </div>
      <Alert text={error} />
      <Btn type="submit" variant="go" size="big" block disabled={busy || !login.trim()}>
        Email me a reset link
      </Btn>
      <button type="button" className="link-button" onClick={onRecoveryCode}>
        No email on your account? Use your recovery code
      </button>
    </form>
  );
}

/** Sign in with a link sent to your confirmed email: no password to type. */
export function EmailLinkForm({ onPassword }: { onPassword: () => void }) {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  useEffect(() => {
    if (wait <= 0) return;
    const t = window.setTimeout(() => setWait((w) => w - 1), 1000);
    return () => window.clearTimeout(t);
  }, [wait]);

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await emailSignInLink(email.trim());
      setSent(email.trim());
      setWait(60);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  };

  if (sent)
    return (
      <div className="stack-sm auth-sent" aria-live="polite">
        <p className="auth-big" aria-hidden="true">
          📬
        </p>
        <h3>Check your inbox</h3>
        <p>
          If <b className="auth-who">{sent}</b> is confirmed on an account, a sign-in link is on its way. It works once, for 15 minutes.
        </p>
        <p className="muted">Open it on the device you want to play on.</p>
        <Alert text={error} />
        <div className="row">
          <Btn size="small" variant="ghost" disabled={busy || wait > 0} onClick={() => void send()}>
            {wait > 0 ? `Send again in ${wait}s` : "Send again"}
          </Btn>
          <Btn size="small" variant="ghost" onClick={onPassword}>
            Use my password
          </Btn>
        </div>
      </div>
    );

  return (
    <form className="stack-sm" onSubmit={(e) => void send(e)}>
      <div>
        <label className="field" htmlFor={`${id}-email`}>
          Your email
        </label>
        <input id={`${id}-email`} type="email" inputMode="email" autoComplete="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <Alert text={error} />
      <Btn type="submit" variant="go" size="big" block disabled={busy || !email.includes("@")}>
        Send me a link
      </Btn>
      <button type="button" className="link-button" onClick={onPassword}>
        Use my password instead
      </button>
    </form>
  );
}

/** The fragment of the current address: where emailed links carry their token (never sent to a server). */
const fragment = () => window.location.hash.replace(/^#/, "");

// -- /account/reset#<token> -------------------------------------------------------------------------
export function ResetPassword({ go }: { go: Go }) {
  const token = useRef(fragment()).current;
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  useEffect(() => {
    document.title = "Reset your password · Snazzlebop";
    if (window.location.hash) window.history.replaceState({}, "", window.location.pathname); // out of history
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await resetPassword(token, password, otp?.trim() || undefined);
      sfx.ding();
      setDone(true);
    } catch (err) {
      if (needsCode(err) && otp === null) setOtp("");
      else setError(errText(err));
    } finally {
      setBusy(false);
    }
  };

  if (!token)
    return (
      <AuthMessage go={go} icon="🔗" title="That link is incomplete" text="Open the reset link from your email again, or ask for a new one." action={["Ask for a new link", "/account/forgot"]} />
    );
  if (done)
    return <AuthMessage go={go} icon="🔑" title="Password changed" text="You're signed in. Every other device has been signed out." action={["Go to your account", "/account"]} />;
  return (
    <div className="stack enter acct auth">
      <Card className="auth-card">
        <p className="auth-big" aria-hidden="true">
          🔑
        </p>
        <h2 className="auth-title">Choose a new password</h2>
        <form className="stack-sm space-top" onSubmit={(e) => void submit(e)}>
          <PasswordField id={`${id}-pw`} label="New password" value={password} set={setPassword} autoComplete="new-password" meter hint="At least 8 characters. A short sentence is easy to remember and hard to guess." />
          {otp !== null && <OtpField id={`${id}-otp`} value={otp} set={setOtp} />}
          <Alert text={error} />
          <Btn type="submit" variant="go" size="big" block disabled={busy || password.length < 8 || otp?.trim() === ""}>
            Save password
          </Btn>
        </form>
      </Card>
    </div>
  );
}

// -- /account/link#<token>: an emailed sign-in link ----------------------------------------------------
export function SignInWithLink({ go }: { go: Go }) {
  const token = useRef(fragment()).current;
  const [otp, setOtp] = useState<string | null>(null);
  const [state, setState] = useState<"working" | "done" | "code" | string>(token ? "working" : "That link is incomplete. Open it from your email again.");
  const ran = useRef(false);
  const id = useId();

  const attempt = async (code?: string) => {
    try {
      await signInWithLink(token, code);
      sfx.ding();
      setState("done");
    } catch (e) {
      if (needsCode(e)) setState("code");
      else setState(errText(e));
    }
  };

  useEffect(() => {
    document.title = "Signing in · Snazzlebop";
    if (window.location.hash) window.history.replaceState({}, "", window.location.pathname);
    if (!token || ran.current) return;
    ran.current = true;
    void attempt();
  }, [token]); // runs once per link; `attempt` reads only the token and the code

  if (state === "working") return <p className="muted center">Signing you in…</p>;
  if (state === "done")
    return <AuthMessage go={go} icon="🎉" title="You're signed in" text="Welcome back! Your coins, clubs and power-ups are waiting." action={["Go to your account", "/account"]} />;
  if (state === "code")
    return (
      <div className="stack enter acct auth">
        <Card className="auth-card">
          <p className="auth-big" aria-hidden="true">
            🔐
          </p>
          <h2 className="auth-title">One more step</h2>
          <form
            className="stack-sm space-top"
            onSubmit={(e) => {
              e.preventDefault();
              void attempt(otp?.trim());
            }}
          >
            <OtpField id={`${id}-otp`} value={otp ?? ""} set={setOtp} />
            <Btn type="submit" variant="go" size="big" block disabled={!otp?.trim()}>
              Sign in
            </Btn>
          </form>
        </Card>
      </div>
    );
  return <AuthMessage go={go} icon="⚠️" title="That link didn't work" text={state} action={["Sign in another way", "/account"]} />;
}

// -- /account/verify#<token> ------------------------------------------------------------------------
export function VerifyEmail({ go }: { go: Go }) {
  const token = useRef(fragment()).current;
  const [state, setState] = useState<"working" | "done" | string>(token ? "working" : "That link is incomplete. Open it from your email again.");
  const ran = useRef(false);

  useEffect(() => {
    document.title = "Confirm your email · Snazzlebop";
    if (window.location.hash) window.history.replaceState({}, "", window.location.pathname);
    if (!token || ran.current) return;
    ran.current = true;
    verifyEmail(token).then(
      () => {
        sfx.ding();
        setState("done");
      },
      (e) => setState(errText(e)),
    );
  }, [token]);

  if (state === "working") return <p className="muted center">Confirming your email…</p>;
  if (state === "done")
    return (
      <AuthMessage
        go={go}
        icon="✅"
        title="Email confirmed"
        text="You can now sign in with it and reset your password by email. We'll also warn you there if anything changes on your account."
        action={["Go to your account", "/account"]}
      />
    );
  return <AuthMessage go={go} icon="⚠️" title="That link didn't work" text={state} action={["Go to your account", "/account"]} />;
}

export function AuthMessage({ go, icon, title, text, action }: { go: Go; icon: string; title: string; text: string; action: [string, string] }) {
  return (
    <div className="stack enter acct auth">
      <Card className="auth-card center">
        <p className="auth-big" aria-hidden="true">
          {icon}
        </p>
        <h2 className="auth-title">{title}</h2>
        <p className="space-top auth-text">{text}</p>
        <div className="row center space-top">
          <Btn variant="go" onClick={() => go(action[1])}>
            {action[0]}
          </Btn>
          <Btn variant="ghost" onClick={() => go("/")}>
            Play a game
          </Btn>
        </div>
      </Card>
    </div>
  );
}

// -- on the profile ---------------------------------------------------------------------------------
export function EmailCard() {
  const { user, mail } = useAccount();
  const [editing, setEditing] = useState(false);
  const [email, setEmailText] = useState("");
  const [password, setPassword] = useState("");
  const [removing, setRemoving] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const id = useId();
  if (!user || (!mail && !user.email)) return null;

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    setNote(null);
    try {
      await fn();
      setNote({ ok: true, text: ok });
      setEditing(false);
      setRemoving(false);
      setPassword("");
      setEmailText("");
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card aria-labelledby={`${id}-h`}>
      <h3 id={`${id}-h`}>Email</h3>
      {user.email ? (
        <div className="email-now">
          <p className="email-address">{user.email}</p>
          <span className={`chip ${user.email_verified ? "teal" : "cherry"}`}>{user.email_verified ? "Confirmed" : "Not confirmed yet"}</span>
        </div>
      ) : (
        <p className="muted">No email on your account. Add one to sign in with it, reset your password by link, and hear about sign-ins from new devices.</p>
      )}
      {user.email && !user.email_verified && (
        <p className="muted space-top">We sent a confirmation link to this address. It works for 2 days.</p>
      )}
      {!editing && !removing && (
        <div className="row space-top">
          {mail && (
            <Btn size="small" variant={user.email ? "ghost" : "go"} onClick={() => setEditing(true)}>
              {user.email ? "Change email" : "Add an email"}
            </Btn>
          )}
          {mail && user.email && !user.email_verified && (
            <Btn size="small" variant="ghost" disabled={busy} onClick={() => void run(resendEmail, "A new confirmation link is on its way.")}>
              Send the link again
            </Btn>
          )}
          {user.email && (
            <Btn size="small" variant="ghost" onClick={() => setRemoving(true)}>
              Remove
            </Btn>
          )}
        </div>
      )}
      {editing && (
        <form
          className="stack-sm space-top"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => setEmail(email.trim(), password), "Check your inbox: we sent a confirmation link.");
          }}
        >
          <div>
            <label className="field" htmlFor={`${id}-email`}>
              {user.email ? "New email" : "Email"}
            </label>
            <input id={`${id}-email`} type="email" inputMode="email" autoComplete="email" maxLength={254} value={email} onChange={(e) => setEmailText(e.target.value)} />
          </div>
          <PasswordField id={`${id}-pw`} label="Your password" value={password} set={setPassword} autoComplete="current-password" />
          <div className="row">
            <Btn type="submit" variant="go" disabled={busy || !email.includes("@") || !password}>
              Send confirmation link
            </Btn>
            <Btn variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Btn>
          </div>
        </form>
      )}
      {removing && (
        <form
          className="stack-sm space-top"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => removeEmail(password), "Email removed. Your recovery code is now the only way to reset your password.");
          }}
        >
          <p>Without an email, only your recovery code can reset a forgotten password.</p>
          <PasswordField id={`${id}-rpw`} label="Your password" value={password} set={setPassword} autoComplete="current-password" />
          <div className="row">
            <Btn type="submit" variant="danger" disabled={busy || !password}>
              Remove email
            </Btn>
            <Btn variant="ghost" onClick={() => setRemoving(false)}>
              Keep it
            </Btn>
          </div>
        </form>
      )}
      {note && (
        <div className="space-top">
          <Alert text={note.text} calm={note.ok} />
        </div>
      )}
    </Card>
  );
}

export function SessionCard({ onSignedOut }: { onSignedOut: () => void }) {
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [devices, setDevices] = useState<SessionList["sessions"] | null>(null);
  const load = useCallback(() => mySessions().then((r) => setDevices(r.sessions), () => undefined), []);
  useEffect(() => void load(), [load]);

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    setNote(null);
    try {
      await fn();
      if (ok) setNote({ ok: true, text: ok });
      await load();
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    } finally {
      setBusy(false);
    }
  };
  const seen = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "a while ago";
  const others = (devices ?? []).filter((d) => !d.current).length;
  return (
    <Card aria-labelledby="session-h">
      <h3 id="session-h">Where you're signed in</h3>
      {devices && devices.length > 0 && (
        <ul className="club-rooms">
          {devices.map((d) => (
            <li key={d.id}>
              <span className="club-room-text">
                <b>{d.device}</b>
                <span className="muted">{d.current ? `Signed in ${seen(d.signed_in)}` : `Last used ${seen(d.last_seen)}`}</span>
              </span>
              {d.current ? (
                <span className="chip teal">You're here</span>
              ) : (
                <Btn size="small" variant="ghost" disabled={busy} onClick={() => void act(() => signOutSession(d.id), `Signed out ${d.device}.`)}>
                  Sign out<span className="sr-only"> {d.device}</span>
                </Btn>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="muted space-top">Lost a phone, or signed in on a friend's laptop? Sign it out here.</p>
      <div className="row space-top">
        <Btn variant="gold" disabled={busy} onClick={() => void act(async () => (await logOut(), onSignedOut()))}>
          Sign out
        </Btn>
        {others > 1 && (
          <Btn variant="ghost" disabled={busy} onClick={() => void act(signOutOthers, "Every other device is signed out.")}>
            Sign out all others
          </Btn>
        )}
      </div>
      {note && (
        <div className="space-top">
          <Alert text={note.text} calm={note.ok} />
        </div>
      )}
    </Card>
  );
}
