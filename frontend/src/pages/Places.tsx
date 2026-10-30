import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { Alert, errText } from "../components/auth";
import { Btn, Card, Loading } from "../components/ui";
import { useAccount } from "../lib/account";
import { confirmPlace, myPlaces, removePlace, startPlace, type MyPlaces } from "../lib/places";
import { sfx } from "../lib/sfx";

type Go = (path: string) => void;
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

/** /places: prove where you're from (a college or company) with a code to your address there. */
export function Places({ go }: { go: Go }) {
  const { user, loaded } = useAccount();
  const [data, setData] = useState<MyPlaces | null>(null);
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState<{ name: string; to: string } | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const id = useId();
  const load = useCallback(() => myPlaces().then(setData, () => undefined), []);

  useEffect(() => {
    document.title = "Your places · Snazzlebop";
    if (user) void load();
  }, [user, load]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setNote(null);
    try {
      await fn();
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    } finally {
      setBusy(false);
    }
  };
  const send = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const r = await startPlace(email.trim());
      setPending({ name: r.place.name, to: r.sent_to });
      setCode("");
    });
  };
  const confirm = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      setData(await confirmPlace(code.trim()));
      sfx.ding();
      setNote({ ok: true, text: `You're verified at ${pending?.name}.` });
      setPending(null);
      setEmail("");
    });
  };

  if (!loaded) return <Loading page />;
  if (!user)
    return (
      <Card tone="stage" className="center">
        <p className="sign">Your places</p>
        <p className="space-top">Sign in to show which college or company you're from, and join clubs for it.</p>
        <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
          Sign in
        </Btn>
      </Card>
    );

  return (
    <div className="stack enter prose-page">
      <Card tone="stage" className="center">
        <p className="sign">Your places</p>
        <h1 className="space-top prose-title">Show where you're from</h1>
        <p className="space-top">Verify your college or company to get its badge and join clubs that are just for it.</p>
      </Card>

      {note && <Alert text={note.text} calm={note.ok} />}

      <Card aria-labelledby={`${id}-mine`}>
        <h2 id={`${id}-mine`}>Verified</h2>
        {data === null ? (
          <Loading />
        ) : data.places.length ? (
          <ul className="club-rooms">
            {data.places.map((p) => (
              <li key={p.slug}>
                <span className="club-room-text">
                  <b>
                    {p.kind === "college" ? "🎓" : "🏢"} {p.name}
                  </b>
                  <span className="muted">{p.status === "verified" ? `Verified until ${day(p.expires_at)}` : `Alumni since ${day(p.expires_at)}`}</span>
                </span>
                <span className="place-actions">
                  {p.status === "alumni" && <span className="chip">Alumni</span>}
                  <Btn size="small" variant="ghost" disabled={busy} onClick={() => void run(async () => setData(await removePlace(p.slug)))}>
                    Remove<span className="sr-only"> {p.name}</span>
                  </Btn>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="empty-state">
            <span aria-hidden="true">🎓</span>
            <p>
              <b>None yet.</b> Verify a college or work email below for its badge.
            </p>
          </div>
        )}
      </Card>

      <Card aria-labelledby={`${id}-add`}>
        <h2 id={`${id}-add`}>{pending ? `Check your email` : "Verify a place"}</h2>
        {data && !data.mail ? (
          <p className="muted">Verifying needs email, which isn't set up on this site yet.</p>
        ) : pending ? (
          <form className="stack-sm" onSubmit={confirm}>
            <p>
              We sent a 6-digit code to <b className="auth-who">{pending.to}</b> to show you're from {pending.name}. It works for 15 minutes.
            </p>
            <div>
              <label className="field" htmlFor={`${id}-code`}>
                Code
              </label>
              <input
                id={`${id}-code`}
                type="text"
                className="code-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={7}
                value={code}
                autoFocus
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
              />
            </div>
            <div className="row">
              <Btn type="submit" variant="go" disabled={busy || code.replace(/\D/g, "").length !== 6}>
                Verify
              </Btn>
              <Btn variant="ghost" onClick={() => setPending(null)}>
                Use another address
              </Btn>
            </div>
          </form>
        ) : (
          <form className="stack-sm" onSubmit={send}>
            <div>
              <label className="field" htmlFor={`${id}-email`}>
                Your college or work email
              </label>
              <input id={`${id}-email`} type="email" inputMode="email" autoComplete="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@college.edu" />
              <p className="muted acct-hint">We only use it to send the code. We don't keep the address, and nobody else ever sees it.</p>
            </div>
            <Btn type="submit" variant="go" disabled={busy || !email.includes("@")}>
              Send me a code
            </Btn>
          </form>
        )}
        <p className="muted space-top">A verification lasts a year. After that your badge shows as alumni until you verify again.</p>
      </Card>
    </div>
  );
}
