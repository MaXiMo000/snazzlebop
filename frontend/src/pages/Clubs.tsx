import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Btn, Card, CopyButton } from "../components/ui";
import { ReportForm } from "../components/report";
import { UpForGame } from "../components/upgame";
import { ClubBattles } from "../components/battle";
import { useAccount } from "../lib/account";
import { ApiError, fetchGames } from "../lib/api";
import {
  closeClub,
  club as loadClub,
  clubRoom,
  createClub,
  handOver,
  joinClub,
  leaveClub,
  mayEdit,
  mayInvite,
  mayRemove,
  myClubs,
  newInvite,
  removeMember,
  revokeInvite,
  rolesYouCanGive,
  ROLE_NAMES,
  saveClub,
  setRole,
  STATUS_TEXT,
  type ClubDetail,
  type ClubSummary,
  type NewInvite,
} from "../lib/clubs";
import { allPlaces } from "../lib/places";
import { block, report } from "../lib/safety";
import { sfx } from "../lib/sfx";

type Go = (path: string) => void;
const errText = (e: unknown) =>
  e instanceof ApiError ? e.message : "Something went wrong";
const INVITE_KEY = "snazzlebop:invite"; // an invite opened while signed out, kept for after sign-in

export function pendingInvite(): string | null {
  try {
    return sessionStorage.getItem(INVITE_KEY);
  } catch {
    return null;
  }
}
function keepInvite(code: string | null) {
  try {
    if (code) sessionStorage.setItem(INVITE_KEY, code);
    else sessionStorage.removeItem(INVITE_KEY);
  } catch {
    /* storage unavailable: the link can just be opened again */
  }
}

/** Runs one action at a time with a shared busy flag and error line. */
function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}

function Alert({ text }: { text: string | null }) {
  return text ? (
    <p className="alert" role="alert">
      {text}
    </p>
  ) : null;
}

function SignInFirst({ go, why }: { go: Go; why: string }) {
  return (
    <Card tone="stage" className="center">
      <p className="sign">Clubs</p>
      <p className="space-top">{why}</p>
      <Btn className="space-top" variant="gold" onClick={() => go("/account")}>
        Sign in or sign up
      </Btn>
    </Card>
  );
}

function Resting({ go }: { go: Go }) {
  return (
    <Card className="center">
      <h2>Clubs are resting</h2>
      <p className="space-top">
        Clubs are unavailable right now. Every game still works without one!
      </p>
      <Btn className="space-top" onClick={() => go("/")}>
        Back to the show
      </Btn>
    </Card>
  );
}

// -- /clubs: your clubs, and making a new one -------------------------------------------------------
export function Clubs({ go }: { go: Go }) {
  const { user, loaded, available } = useAccount();
  const [clubs, setClubs] = useState<ClubSummary[] | null>(null);
  const [name, setName] = useState("");
  const [about, setAbout] = useState("");
  const { busy, error, run } = useAction();

  useEffect(() => {
    document.title = "Clubs · Snazzlebop";
    if (user)
      myClubs().then(
        (r) => setClubs(r.clubs),
        () => setClubs([]),
      );
  }, [user]);

  if (!loaded) return <p className="muted center">Loading…</p>;
  if (!available) return <Resting go={go} />;
  if (!user)
    return (
      <SignInFirst
        go={go}
        why="A club is your group's home: your hostel, team or office plays together, with its own rooms and rules. Sign in to start one or join one."
      />
    );

  const create = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const made = await createClub(name.trim(), about.trim());
      sfx.ding();
      go(`/clubs/${made.slug}`);
    });
  };

  return (
    <div className="stack enter clubs">
      <Card tone="stage" className="center">
        <p className="sign">Your clubs</p>
        <p className="space-top">
          Play with the same crowd again and again. Clubs are private: people
          join with an invite link.
        </p>
      </Card>

      <Card aria-labelledby="mine-h">
        <h3 id="mine-h">Clubs you're in</h3>
        {clubs === null ? (
          <p className="muted">Loading…</p>
        ) : clubs.length ? (
          <ul className="club-list">
            {clubs.map((c) => (
              <li key={c.slug}>
                <a
                  className="club-link"
                  href={`/clubs/${c.slug}`}
                  onClick={(e) => {
                    e.preventDefault();
                    go(`/clubs/${c.slug}`);
                  }}
                >
                  <b>{c.name}</b>
                  <span className="muted">
                    {ROLE_NAMES[c.role] ?? c.role} · {c.members}{" "}
                    {c.members === 1 ? "member" : "members"}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            You're not in a club yet. Start one below, or open an invite link
            from a friend.
          </p>
        )}
      </Card>

      <Card aria-labelledby="new-h">
        <h3 id="new-h">Start a club</h3>
        <form className="stack-sm" onSubmit={create}>
          <div>
            <label className="field" htmlFor="club-name">
              Club name
            </label>
            <input
              id="club-name"
              type="text"
              maxLength={40}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Hostel 4 Quiz Crew"
            />
          </div>
          <div>
            <label className="field" htmlFor="club-about">
              What it's about <span className="muted">(optional)</span>
            </label>
            <input
              id="club-about"
              type="text"
              maxLength={200}
              value={about}
              onChange={(e) => setAbout(e.target.value)}
              placeholder="Friday game nights"
            />
          </div>
          <Alert text={error} />
          <Btn
            type="submit"
            variant="go"
            disabled={busy || name.trim().length < 3}
          >
            Start the club
          </Btn>
        </form>
      </Card>
    </div>
  );
}

// -- /join/<code>: an invite link ---------------------------------------------------------------------
export function JoinClub({ code, go }: { code: string; go: Go }) {
  const { user, loaded, available } = useAccount();
  const { error, run } = useAction();

  useEffect(() => {
    document.title = "Join a club · Snazzlebop";
    if (!loaded || !available) return;
    if (!user) {
      keepInvite(code);
      return;
    }
    void run(async () => {
      const joined = await joinClub(code);
      keepInvite(null);
      sfx.ding();
      go(`/clubs/${joined.slug}`);
    });
  }, [code, user, loaded, available, go, run]);

  if (!loaded) return <p className="muted center">Loading…</p>;
  if (!available) return <Resting go={go} />;
  if (!user)
    return (
      <SignInFirst
        go={go}
        why="You've been invited to a club. Sign in (or make an account in a few seconds) and you'll be let in."
      />
    );
  return error ? (
    <Card className="center">
      <h2>That invite didn't work</h2>
      <p className="space-top">{error}</p>
      <Btn className="space-top" onClick={() => go("/clubs")}>
        Your clubs
      </Btn>
    </Card>
  ) : (
    <p className="muted center">Letting you in…</p>
  );
}

/** On the profile: an invite opened while signed out, ready to accept. */
export function InviteWaiting({ go }: { go: Go }) {
  const code = pendingInvite();
  if (!code) return null;
  return (
    <Card tone="stage" className="center" aria-labelledby="invite-h">
      <h3 id="invite-h">You've got a club invite</h3>
      <div className="row center space-top">
        <Btn variant="gold" onClick={() => go(`/join/${code}`)}>
          Join the club
        </Btn>
        <Btn variant="ghost" onClick={() => (keepInvite(null), go("/account"))}>
          Not now
        </Btn>
      </div>
    </Card>
  );
}

// -- /clubs/<slug>: the club's home -------------------------------------------------------------------
export function ClubHome({ slug, go }: { slug: string; go: Go }) {
  const { user, loaded, available } = useAccount();
  const [c, setC] = useState<ClubDetail | null>(null);
  const [missing, setMissing] = useState(false);

  const refresh = useCallback(
    () =>
      loadClub(slug).then(
        (d) => setC(d),
        (e) => {
          if (e instanceof ApiError && e.status === 404) setMissing(true);
        },
      ),
    [slug],
  );

  useEffect(() => {
    if (!user) return;
    void refresh();
    const t = window.setInterval(
      () => document.visibilityState === "visible" && void refresh(),
      20000,
    );
    return () => window.clearInterval(t);
  }, [user, refresh]);

  useEffect(() => {
    document.title = c ? `${c.name} · Snazzlebop` : "Club · Snazzlebop";
  }, [c]);

  if (!loaded) return <p className="muted center">Loading…</p>;
  if (!available) return <Resting go={go} />;
  if (!user) return <SignInFirst go={go} why="Sign in to see this club." />;
  if (missing)
    return (
      <Card className="center">
        <h2>Club not found</h2>
        <p className="space-top">
          It may have closed, or you're not a member. Ask a member for an invite
          link.
        </p>
        <Btn className="space-top" onClick={() => go("/clubs")}>
          Your clubs
        </Btn>
      </Card>
    );
  if (!c) return <p className="muted center">Loading…</p>;

  return (
    <div className="stack enter clubs">
      <Card tone="stage" className="center">
        <p className="sign club-name">{c.name}</p>
        {c.about && <p className="space-top">{c.about}</p>}
        <p className="space-top">
          <span className="chip teal">{ROLE_NAMES[c.role] ?? c.role}</span>{" "}
          <span>
            {c.member_count} {c.member_count === 1 ? "member" : "members"}
          </span>
        </p>
        {c.place && <p className="space-top club-place">🎓 For people verified at {c.place.name}</p>}
      </Card>
      {c.secure_nudge && (
        <p className="alert calm club-nudge" role="status">
          You run this club: turn on your authenticator app so a stolen password can't take it over.{" "}
          <a
            href="/account"
            onClick={(e) => {
              e.preventDefault();
              go("/account");
            }}
          >
            Set it up
          </a>
        </p>
      )}
      {mayInvite(c.role) && (
        <a
          className={`club-mod-link ${c.open_reports ? "waiting" : ""}`}
          href={`/clubs/${c.slug}/reports`}
          onClick={(e) => {
            e.preventDefault();
            go(`/clubs/${c.slug}/reports`);
          }}
        >
          <span aria-hidden="true">🛡️</span>
          <span>
            <b>Reports</b>
            <span className="muted"> · {c.open_reports ? `${c.open_reports} waiting` : "nothing waiting"}</span>
          </span>
        </a>
      )}
      <UpForGame c={c} go={go} name={user.username} update={setC} />
      <PlayNow c={c} go={go} name={user.username} />
      <ClubBattles c={c} me={user.username} go={go} />
      {mayInvite(c.role) && <Invites c={c} refresh={refresh} />}
      <Members c={c} me={user.username} refresh={refresh} />
      {mayEdit(c.role) && <Settings c={c} refresh={refresh} />}
      <Leave c={c} go={go} />
    </div>
  );
}

function PlayNow({ c, go, name }: { c: ClubDetail; go: Go; name: string }) {
  const [seat, setSeat] = useState(name.slice(0, 20));
  const { busy, error, run } = useAction();
  const start = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => go(`/r/${await clubRoom(c.slug, seat.trim())}`));
  };
  return (
    <Card aria-labelledby="play-h">
      <h3 id="play-h">Play now</h3>
      {c.rooms.length ? (
        <ul className="club-rooms">
          {c.rooms.map((r) => (
            <li key={r.code}>
              <span className="club-room-text">
                <b>
                  {r.battle && <span aria-hidden="true">⚔️ </span>}
                  {r.host}'s {r.battle ? "battle" : "room"}
                </b>
                <span className="muted">
                  {r.players} {r.players === 1 ? "player" : "players"} ·{" "}
                  {r.game ?? (r.open ? "in the lobby" : "between games")}
                </span>
              </span>
              <Btn
                size="small"
                variant={r.open ? "go" : "ghost"}
                onClick={() => go(`/r/${r.code}`)}
                aria-label={`Join ${r.host}'s room`}
              >
                {r.open ? "Join" : "Watch"}
              </Btn>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">
          No club rooms open right now. Start one and the club will see it here.
        </p>
      )}
      <form className="club-start space-top" onSubmit={start}>
        <div>
          <label className="field" htmlFor="seat-name">
            Your name in the game
          </label>
          <input
            id="seat-name"
            type="text"
            maxLength={20}
            value={seat}
            onChange={(e) => setSeat(e.target.value)}
          />
        </div>
        <Btn type="submit" variant="gold" disabled={busy || !seat.trim()}>
          Start a club room
        </Btn>
      </form>
      {c.rules.games.length > 0 && (
        <p className="muted space-top">
          This club plays {c.rules.games.length} chosen games.
        </p>
      )}
      <Alert text={error} />
    </Card>
  );
}

function Invites({
  c,
  refresh,
}: {
  c: ClubDetail;
  refresh: () => Promise<void>;
}) {
  const [days, setDays] = useState(7);
  const [uses, setUses] = useState(25);
  const [made, setMade] = useState<NewInvite | null>(null);
  const { busy, error, run } = useAction();
  const link = made ? `${window.location.origin}${made.path}` : "";
  return (
    <Card aria-labelledby="inv-h">
      <h3 id="inv-h">Invite people</h3>
      <p className="muted">
        Anyone with a link can join until it runs out. Share it in your group
        chat.
      </p>
      <div className="club-invite-form space-top">
        <div>
          <label className="field" htmlFor="inv-days">
            Lasts
          </label>
          <select
            id="inv-days"
            className="select-button"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {[1, 7, 30].map((d) => (
              <option key={d} value={d}>
                {d === 1 ? "1 day" : `${d} days`}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="field" htmlFor="inv-uses">
            Uses
          </label>
          <select
            id="inv-uses"
            className="select-button"
            value={uses}
            onChange={(e) => setUses(Number(e.target.value))}
          >
            {[1, 10, 25, 100].map((u) => (
              <option key={u} value={u}>
                {u === 1 ? "1 person" : `${u} people`}
              </option>
            ))}
          </select>
        </div>
        <Btn
          variant="go"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              setMade(await newInvite(c.slug, days, uses));
              sfx.pop();
              await refresh();
            })
          }
        >
          Make a link
        </Btn>
      </div>
      {made && (
        <div className="club-new-link space-top" aria-live="polite">
          <p className="club-url">{link}</p>
          <div className="row">
            <CopyButton text={link} label="Copy link" />
            <span className="muted">Code {made.code}</span>
          </div>
          <p className="muted">The link is shown once: copy it now.</p>
        </div>
      )}
      {c.invites.length > 0 && (
        <>
          <h4 className="space-top">Live links</h4>
          <ul className="club-rooms">
            {c.invites.map((i) => (
              <li key={i.id}>
                <span className="club-room-text">
                  <span>
                    {i.uses_left} {i.uses_left === 1 ? "use" : "uses"} left
                  </span>
                  <span className="muted">
                    until{" "}
                    {new Date(i.expires_at).toLocaleDateString(undefined, {
                      day: "numeric",
                      month: "short",
                    })}
                  </span>
                </span>
                <Btn
                  size="small"
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await revokeInvite(c.slug, i.id);
                      if (made?.id === i.id) setMade(null);
                      await refresh();
                    })
                  }
                >
                  Turn off
                </Btn>
              </li>
            ))}
          </ul>
        </>
      )}
      <Alert text={error} />
    </Card>
  );
}

function Members({
  c,
  me,
  refresh,
}: {
  c: ClubDetail;
  me: string;
  refresh: () => Promise<void>;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [reporting, setReporting] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { busy, error, run } = useAction();
  const act = (fn: () => Promise<unknown>) =>
    void run(async () => {
      await fn();
      setOpen(null);
      await refresh();
    });
  return (
    <Card aria-labelledby="mem-h">
      <h3 id="mem-h">Members</h3>
      <ul className="club-members">
        {c.members.map((m) => {
          const you = m.username === me;
          const give = you
            ? []
            : rolesYouCanGive(c.role, m.role).filter((r) => r !== m.role);
          const remove = !you && mayRemove(c.role, m.role);
          const handover = !you && c.role === "owner";
          const powers = give.length > 0 || remove || handover;
          return (
            <li key={m.username}>
              <div className="club-member">
                <span className="club-room-text">
                  <b className="member-name">
                    <span className={`status-dot ${m.status}`} aria-hidden="true" />
                    {m.username}
                    {you && " (you)"}
                  </b>
                  <span className="muted">
                    {ROLE_NAMES[m.role] ?? m.role}
                    {!you && (
                      <>
                        {" · "}
                        {STATUS_TEXT[m.status]}
                      </>
                    )}
                  </span>
                  {m.places.length > 0 && (
                    <span className="member-places">
                      {m.places.map((p) => (
                        <span key={p} className="chip place-badge">
                          {p}
                        </span>
                      ))}
                    </span>
                  )}
                </span>
                {!you && (
                  <Btn
                    size="small"
                    variant="ghost"
                    aria-expanded={open === m.username}
                    onClick={() => {
                      setOpen(open === m.username ? null : m.username);
                      setReporting(null);
                      setNotice(null);
                    }}
                  >
                    {powers ? "Manage" : "More"}
                    <span className="sr-only"> {m.username}</span>
                  </Btn>
                )}
              </div>
              {open === m.username && (
                <div
                  className="club-manage"
                  role="group"
                  aria-label={`Manage ${m.username}`}
                >
                  {give.map((r) => (
                    <Btn
                      key={r}
                      size="small"
                      disabled={busy}
                      onClick={() => act(() => setRole(c.slug, m.username, r))}
                    >
                      Make {ROLE_NAMES[r]?.toLowerCase()}
                    </Btn>
                  ))}
                  {handover && (
                    <Btn
                      size="small"
                      variant="gold"
                      disabled={busy}
                      onClick={() =>
                        window.confirm(
                          `Hand ${c.name} to ${m.username}? You'll stay on as an admin.`,
                        ) && act(() => handOver(c.slug, m.username))
                      }
                    >
                      Make owner
                    </Btn>
                  )}
                  {remove && (
                    <>
                      <Btn
                        size="small"
                        variant="danger"
                        disabled={busy}
                        onClick={() =>
                          act(() => removeMember(c.slug, m.username, false))
                        }
                      >
                        Remove
                      </Btn>
                      <Btn
                        size="small"
                        variant="danger"
                        disabled={busy}
                        onClick={() =>
                          window.confirm(
                            `Ban ${m.username}? They won't be able to rejoin.`,
                          ) && act(() => removeMember(c.slug, m.username, true))
                        }
                      >
                        Ban
                      </Btn>
                    </>
                  )}
                  <Btn
                    size="small"
                    variant="ghost"
                    aria-expanded={reporting === m.username}
                    onClick={() => setReporting(reporting === m.username ? null : m.username)}
                  >
                    Report
                  </Btn>
                  <Btn
                    size="small"
                    variant="ghost"
                    disabled={busy}
                    onClick={() =>
                      window.confirm(
                        `Block ${m.username}? They won't be told. You'll stop seeing each other's chat, and they can't invite you or join your rooms.`,
                      ) &&
                      void run(async () => {
                        await block(m.username);
                        setOpen(null);
                        setNotice(`Blocked ${m.username}. Undo it any time on the Safety and data page.`);
                        await refresh();
                      })
                    }
                  >
                    Block
                  </Btn>
                </div>
              )}
              {open === m.username && reporting === m.username && (
                <div className="club-report">
                  <ReportForm
                    who={m.username}
                    canBlock
                    send={async (reason, note, alsoBlock) => {
                      await report(m.username, reason, note, c.slug);
                      if (alsoBlock) await block(m.username);
                    }}
                    done={(text) => {
                      setOpen(null);
                      setReporting(null);
                      setNotice(text);
                      void refresh();
                    }}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {notice && (
        <p className="alert calm space-top" role="status">
          {notice}
        </p>
      )}
      <Alert text={error} />
    </Card>
  );
}

function Settings({
  c,
  refresh,
}: {
  c: ClubDetail;
  refresh: () => Promise<void>;
}) {
  const [name, setName] = useState(c.name);
  const [about, setAbout] = useState(c.about);
  const [chat, setChat] = useState(c.rules.chat);
  const [games, setGames] = useState<string[]>(c.rules.games);
  const [place, setPlace] = useState(c.rules.place ?? "");
  const [places, setPlaces] = useState<{ slug: string; name: string }[]>([]);
  const [all, setAll] = useState<{ id: string; title: string }[]>([]);
  const [saved, setSaved] = useState(false);
  const { busy, error, run } = useAction();

  useEffect(() => {
    allPlaces().then((r) => setPlaces(r.places), () => undefined);
    fetchGames().then(
      (g) =>
        setAll(
          g
            .map((x) => ({ id: x.id, title: x.title }))
            .sort((a, b) => a.title.localeCompare(b.title)),
        ),
      () => undefined,
    );
  }, []);

  const toggle = (id: string) =>
    setGames((g) => (g.includes(id) ? g.filter((x) => x !== id) : [...g, id]));
  const save = (e: FormEvent) => {
    e.preventDefault();
    setSaved(false);
    void run(async () => {
      await saveClub(c.slug, {
        name: name.trim(),
        about: about.trim(),
        rules: { chat, games, place: place || null },
      });
      setSaved(true);
      sfx.pop();
      await refresh();
    });
  };
  return (
    <Card aria-labelledby="set-h">
      <h3 id="set-h">Club settings</h3>
      <form className="stack-sm" onSubmit={save}>
        <div>
          <label className="field" htmlFor="set-name">
            Club name
          </label>
          <input
            id="set-name"
            type="text"
            maxLength={40}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label className="field" htmlFor="set-about">
            What it's about
          </label>
          <input
            id="set-about"
            type="text"
            maxLength={200}
            value={about}
            onChange={(e) => setAbout(e.target.value)}
          />
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={chat}
            onChange={(e) => setChat(e.target.checked)}
          />
          <span>Chat in club rooms</span>
        </label>
        <div>
          <label className="field" htmlFor="set-place">
            Who can join
          </label>
          <select id="set-place" className="select-button" value={place} onChange={(e) => setPlace(e.target.value)}>
            <option value="">Anyone with an invite link</option>
            {places.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.name}
              </option>
            ))}
          </select>
          <p className="muted acct-hint">Pick a place and only people verified there can join. Members already in stay either way.</p>
        </div>
        <details className="club-games">
          <summary>
            Games the club plays:{" "}
            {games.length ? `${games.length} picked` : "all"}
          </summary>
          <fieldset className="club-games">
            <legend className="sr-only">Games the club plays</legend>
            <p className="muted">
              None ticked means every game. Club rooms show only the ticked
              ones.
            </p>
            <div className="club-game-grid">
              {all.map((g) => (
                <label key={g.id} className="check">
                  <input
                    type="checkbox"
                    checked={games.includes(g.id)}
                    onChange={() => toggle(g.id)}
                  />
                  <span>{g.title}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </details>
        <p className="muted">Changes apply to rooms opened after you save.</p>
        <Alert text={error} />
        <div className="row">
          <Btn
            type="submit"
            variant="go"
            disabled={busy || name.trim().length < 3}
          >
            Save settings
          </Btn>
          <span aria-live="polite">{saved && !busy ? "Saved" : ""}</span>
        </div>
      </form>
    </Card>
  );
}

function Leave({ c, go }: { c: ClubDetail; go: Go }) {
  const { busy, error, run } = useAction();
  const alone = c.member_count === 1;
  const owner = c.role === "owner";
  const leave = () => {
    const msg =
      owner && alone
        ? `You're the only member: leaving closes ${c.name}. Go ahead?`
        : `Leave ${c.name}?`;
    if (!window.confirm(msg)) return;
    void run(async () => {
      await leaveClub(c.slug);
      go("/clubs");
    });
  };
  const close = () => {
    if (!window.confirm(`Close ${c.name} for everyone? This can't be undone.`))
      return;
    void run(async () => {
      await closeClub(c.slug);
      go("/clubs");
    });
  };
  return (
    <Card aria-labelledby="leave-h">
      <h3 id="leave-h">{owner ? "Leave or close" : "Leave the club"}</h3>
      {owner && !alone && (
        <p className="muted">
          You own this club: hand it to someone (Members, then Manage) before
          you leave.
        </p>
      )}
      <div className="row space-top">
        {(!owner || alone) && (
          <Btn variant="danger" disabled={busy} onClick={leave}>
            Leave the club
          </Btn>
        )}
        {owner && (
          <Btn variant="danger" disabled={busy} onClick={close}>
            Close the club
          </Btn>
        )}
      </div>
      <Alert text={error} />
    </Card>
  );
}
