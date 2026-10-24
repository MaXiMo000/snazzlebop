import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { Alert, errText } from "../components/auth";
import { when } from "../components/casecard";
import { Btn, Card } from "../components/ui";
import { ApiError } from "../lib/api";
import { declineRequest, savePlace, staffPlaces, type StaffPlaces as Data } from "../lib/places";

type Go = (path: string) => void;
type Place = Data["places"][number];
interface Draft {
  slug?: string;
  name: string;
  kind: string;
  domains: string;
}
const blank: Draft = { name: "", kind: "college", domains: "" };

/** /staff/places: the colleges and companies people can verify, and requests for new ones. */
export function StaffPlaces({ go }: { go: Go }) {
  const [data, setData] = useState<Data | null>(null);
  const [gate, setGate] = useState<"loading" | "open" | "mfa" | "closed">("loading");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(
    () =>
      staffPlaces().then(
        (d) => (setData(d), setGate("open")),
        (e) => setGate(e instanceof ApiError && e.code === "needs_mfa" ? "mfa" : "closed"),
      ),
    [],
  );
  useEffect(() => {
    document.title = "Places · Staff · Snazzlebop";
    void load();
  }, [load]);

  const run = async (fn: () => Promise<Data>, ok: string) => {
    setNote(null);
    try {
      setData(await fn());
      setNote({ ok: true, text: ok });
      setDraft(null);
    } catch (e) {
      setNote({ ok: false, text: errText(e) });
    }
  };

  if (gate === "loading") return <p className="muted center">Loading…</p>;
  if (gate !== "open" || !data)
    return (
      <Card className="center">
        <h2>{gate === "mfa" ? "One more step" : "Page not found"}</h2>
        {gate === "mfa" && <p className="space-top">The staff console needs your authenticator app turned on.</p>}
        <Btn className="space-top" onClick={() => go(gate === "mfa" ? "/account" : "/")}>
          {gate === "mfa" ? "Set it up on your account page" : "Back to the show"}
        </Btn>
      </Card>
    );

  const edit = (p: Place) => setDraft({ slug: p.slug, name: p.name, kind: p.kind, domains: p.domains.join(", ") });
  return (
    <div className="stack enter reports-page">
      <Card tone="stage" className="center">
        <p className="sign">Places</p>
        <p className="space-top">
          {data.places.length} {data.places.length === 1 ? "place" : "places"} · {data.requests.length} {data.requests.length === 1 ? "request" : "requests"}
        </p>
        <div className="row center space-top">
          <Btn variant="ghost" onClick={() => go("/staff")}>
            Back to cases
          </Btn>
          {!draft && (
            <Btn variant="gold" onClick={() => setDraft(blank)}>
              Add a place
            </Btn>
          )}
        </div>
      </Card>
      {note && <Alert text={note.text} calm={note.ok} />}

      {draft && <PlaceForm draft={draft} cancel={() => setDraft(null)} save={(d) => run(() => savePlace(d), `Saved ${d.name}.`)} />}

      {data.requests.length > 0 && (
        <Card aria-labelledby="req-h">
          <h3 id="req-h">Asked for</h3>
          <p className="muted">People tried to verify with these domains. Add the place, or decline it.</p>
          <ul className="club-rooms space-top">
            {data.requests.map((r) => (
              <li key={r.domain}>
                <span className="club-room-text">
                  <b>{r.domain}</b>
                  <span className="muted">
                    {r.count} {r.count === 1 ? "try" : "tries"} · last {when(r.last_at)}
                  </span>
                </span>
                <span className="place-actions">
                  <Btn size="small" variant="go" onClick={() => setDraft({ ...blank, domains: r.domain })}>
                    Add
                  </Btn>
                  <Btn size="small" variant="ghost" onClick={() => void run(() => declineRequest(r.domain), `Declined ${r.domain}.`)}>
                    Decline<span className="sr-only"> {r.domain}</span>
                  </Btn>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card aria-labelledby="places-h">
        <h3 id="places-h">Places</h3>
        {data.places.length ? (
          <ul className="club-rooms">
            {data.places.map((p) => (
              <li key={p.slug}>
                <span className="club-room-text">
                  <b>
                    {p.kind === "college" ? "🎓" : "🏢"} {p.name}
                  </b>
                  <span className="muted place-domains">{p.domains.join(", ")}</span>
                  <span className="muted">
                    {p.members} verified
                  </span>
                </span>
                <Btn size="small" variant="ghost" onClick={() => edit(p)}>
                  Change<span className="sr-only"> {p.name}</span>
                </Btn>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No places yet. Add the launch campuses and companies here.</p>
        )}
      </Card>
    </div>
  );
}

function PlaceForm({ draft, cancel, save }: { draft: Draft; cancel: () => void; save: (d: { slug?: string; name: string; kind: string; domains: string[] }) => void }) {
  const [d, setD] = useState(draft);
  const id = useId();
  useEffect(() => setD(draft), [draft]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const domains = d.domains
      .split(/[\s,]+/)
      .map((x) => x.trim())
      .filter(Boolean);
    save({ ...(d.slug ? { slug: d.slug } : {}), name: d.name.trim(), kind: d.kind, domains });
  };
  return (
    <Card aria-labelledby={`${id}-h`}>
      <h3 id={`${id}-h`}>{d.slug ? `Change ${draft.name}` : "Add a place"}</h3>
      <form className="stack-sm space-top" onSubmit={submit}>
        <div>
          <label className="field" htmlFor={`${id}-name`}>
            Name
          </label>
          <input id={`${id}-name`} type="text" maxLength={80} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="IIT Delhi" />
        </div>
        <fieldset className="report-reasons">
          <legend className="field">Kind</legend>
          <div className="auth-tabs place-kinds">
            {["college", "company"].map((k) => (
              <button key={k} type="button" className={`auth-tab ${d.kind === k ? "on" : ""}`} aria-pressed={d.kind === k} onClick={() => setD({ ...d, kind: k })}>
                {k === "college" ? "College" : "Company"}
              </button>
            ))}
          </div>
        </fieldset>
        <div>
          <label className="field" htmlFor={`${id}-domains`}>
            Email domains
          </label>
          <input id={`${id}-domains`} type="text" value={d.domains} onChange={(e) => setD({ ...d, domains: e.target.value })} placeholder="iitd.ac.in, iitd.ernet.in" />
          <p className="muted acct-hint">Comma separated. Subdomains count too (cs.iitd.ac.in). Free providers like gmail.com never do.</p>
        </div>
        <div className="row">
          <Btn type="submit" variant="go" disabled={d.name.trim().length < 2 || !d.domains.trim()}>
            Save
          </Btn>
          <Btn variant="ghost" onClick={cancel}>
            Cancel
          </Btn>
        </div>
      </form>
    </Card>
  );
}
