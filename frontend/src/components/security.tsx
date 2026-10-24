import { useEffect, useState } from "react";
import { ApiError } from "../lib/api";
import { mfaDisable, mfaEnable, mfaNewCodes, mfaSetup, mfaStatus, type MfaSetup, type MfaStatus } from "../lib/account";
import { Btn, Card, CopyButton } from "./ui";

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

/** A QR code from the server's rows of "1" (dark) and "0" (light): one path, no injected markup. */
export function QrCode({ rows, label }: { rows: string[]; label: string }) {
  const d = rows.flatMap((row, y) => [...row].flatMap((cell, x) => (cell === "1" ? [`M${x} ${y}h1v1h-1z`] : []))).join("");
  return (
    <svg className="qr" viewBox={`0 0 ${rows.length} ${rows.length}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <path d={d} />
    </svg>
  );
}

/** The key in groups of four, easier to type into an app by hand. */
const grouped = (secret: string) => secret.match(/.{1,4}/g)?.join(" ") ?? secret;

type Step = { kind: "idle" } | { kind: "password" } | { kind: "scan"; setup: MfaSetup } | { kind: "codes"; codes: string[] } | { kind: "off" } | { kind: "renew" };

/** Account page: switch on sign-in with an authenticator app, see backup codes left, switch it off. */
export function Authenticator() {
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [step, setStep] = useState<Step>({ kind: "idle" });
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => mfaStatus().then(setStatus, () => undefined);
  useEffect(() => {
    void load();
  }, []);

  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setPassword("");
      setCode("");
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const cancel = () => {
    setStep({ kind: "idle" });
    setError(null);
    setPassword("");
    setCode("");
  };
  const codeField = (id: string, label: string) => (
    <div>
      <label className="field" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        className="code-input"
        inputMode="text"
        autoComplete="one-time-code"
        maxLength={12}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="123 456"
      />
    </div>
  );
  const passwordField = (id: string) => (
    <div>
      <label className="field" htmlFor={id}>
        Password
      </label>
      <input id={id} type="password" value={password} maxLength={128} autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
    </div>
  );

  if (status === null) return null;
  return (
    <Card aria-labelledby="mfa-h">
      <h3 id="mfa-h">Authenticator app</h3>

      {step.kind === "codes" ? (
        <div className="stack-sm space-top">
          <p>
            <b>Your backup codes.</b> If you lose your phone, each one signs you in once. Save them somewhere safe: they're
            shown only now.
          </p>
          <ol className="mfa-codes" aria-label="Backup codes">
            {step.codes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ol>
          <div className="row">
            <CopyButton text={step.codes.join("\n")} label="Copy all" />
            <Btn variant="go" onClick={cancel}>
              I've saved them
            </Btn>
          </div>
        </div>
      ) : status.enabled ? (
        <div className="stack-sm space-top">
          <p className="mfa-on">
            <span aria-hidden="true">🔐</span> On. Signing in asks for a code from your app. {status.backup_codes_left} backup
            code{status.backup_codes_left === 1 ? "" : "s"} left.
          </p>
          {step.kind === "renew" && (
            <form
              className="stack-sm"
              onSubmit={(e) => {
                e.preventDefault();
                void act(async () => {
                  setStep({ kind: "codes", codes: await mfaNewCodes(code) });
                  void load();
                });
              }}
            >
              {codeField("mfa-renew", "Code from your app")}
              <div className="row">
                <Btn type="submit" disabled={busy || !code.trim()}>
                  Make new backup codes
                </Btn>
                <Btn variant="ghost" onClick={cancel}>
                  Cancel
                </Btn>
              </div>
            </form>
          )}
          {step.kind === "off" && (
            <form
              className="stack-sm"
              onSubmit={(e) => {
                e.preventDefault();
                void act(async () => {
                  await mfaDisable(password, code);
                  setStep({ kind: "idle" });
                  void load();
                });
              }}
            >
              {passwordField("mfa-off-pw")}
              {codeField("mfa-off-code", "Code from your app, or a backup code")}
              <div className="row">
                <Btn type="submit" variant="danger" disabled={busy || !password || !code.trim()}>
                  Turn it off
                </Btn>
                <Btn variant="ghost" onClick={cancel}>
                  Keep it on
                </Btn>
              </div>
            </form>
          )}
          {step.kind === "idle" && (
            <div className="row">
              <Btn variant="ghost" onClick={() => setStep({ kind: "renew" })}>
                New backup codes
              </Btn>
              <Btn variant="ghost" onClick={() => setStep({ kind: "off" })}>
                Turn off
              </Btn>
            </div>
          )}
        </div>
      ) : step.kind === "scan" ? (
        <form
          className="stack-sm space-top"
          onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              setStep({ kind: "codes", codes: await mfaEnable(code) });
              void load();
            });
          }}
        >
          <p>
            <b>1.</b> In Google Authenticator, Authy, 1Password or a similar app, add an account and scan this code.
          </p>
          <QrCode rows={step.setup.qr} label="QR code to scan with your authenticator app" />
          <p className="muted">
            Can't scan? Type this key instead: <span className="mfa-key">{grouped(step.setup.secret)}</span>
          </p>
          <CopyButton text={step.setup.secret} label="Copy key" />
          <p>
            <b>2.</b> Type the 6-digit code the app shows.
          </p>
          {codeField("mfa-first", "Code from your app")}
          <div className="row">
            <Btn type="submit" variant="go" disabled={busy || !code.trim()}>
              Turn it on
            </Btn>
            <Btn variant="ghost" onClick={cancel}>
              Cancel
            </Btn>
          </div>
        </form>
      ) : (
        <div className="stack-sm space-top">
          <p>Add a second step to signing in: a code from an app on your phone. Someone who learns your password still can't get in.</p>
          {step.kind === "password" ? (
            <form
              className="stack-sm"
              onSubmit={(e) => {
                e.preventDefault();
                void act(async () => setStep({ kind: "scan", setup: await mfaSetup(password) }));
              }}
            >
              {passwordField("mfa-pw")}
              <div className="row">
                <Btn type="submit" disabled={busy || !password}>
                  Continue
                </Btn>
                <Btn variant="ghost" onClick={cancel}>
                  Cancel
                </Btn>
              </div>
            </form>
          ) : (
            <Btn onClick={() => setStep({ kind: "password" })}>Set up an authenticator app</Btn>
          )}
        </div>
      )}
      {error && (
        <p className="alert space-top" role="alert">
          {error}
        </p>
      )}
    </Card>
  );
}
