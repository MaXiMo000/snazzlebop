import { useEffect, useState } from "react";
import { Avatar } from "../components/avatar";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { MafiaRole, MafiaView } from "../types";

interface Props {
  view: MafiaView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const ROLE: Record<MafiaRole, { name: string; icon: string; job: string }> = {
  mafia: { name: "Mafia", icon: "🎩", job: "Each night, pick someone to remove. By day, blend in." },
  detective: { name: "Detective", icon: "🕵️", job: "Each night, check one player: Mafia or not?" },
  doctor: { name: "Doctor", icon: "🩺", job: "Each night, protect one player (yourself too, never twice running)." },
  villager: { name: "Villager", icon: "🏘️", job: "No night job. Watch, listen, and vote the Mafia out." },
};
const NIGHT_ASK: Record<MafiaRole, string> = {
  mafia: "Who goes tonight?",
  detective: "Who do you want to check?",
  doctor: "Who do you protect tonight?",
  villager: "Who do you suspect?",
};

export function Mafia({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const me = tv ? null : view.you;
  const name = (pid: string) => nameOf(view.players, pid);
  const night = view.phase === "night" || view.phase === "roles";
  // Your role stays face down after the first screen, in case someone can see your phone.
  const [peek, setPeek] = useState(false);
  useEffect(() => setPeek(false), [view.phase]);

  useOnChange(view.phase, (_, phase) => {
    if (phase === "night") {
      sfx.tick();
      show.stinger(`NIGHT ${view.round}`);
    } else if (phase === "dawn") {
      if (view.news?.killed) sfx.buzz();
      else sfx.ding();
    } else if (phase === "verdict" && view.news?.out) {
      if (view.news.role === "mafia") {
        sfx.fanfare();
        show.stinger("MAFIA CAUGHT!");
      } else {
        sfx.buzz();
        show.stinger("INNOCENT!", "bad");
      }
    } else if (phase === "final") {
      const mine = me ? (me.role === "mafia") === (view.winner === "mafia") : true;
      sfx.fanfare();
      show.stinger(view.winner === "town" ? "TOWN WINS!" : "MAFIA WIN!", mine ? "good" : "bad");
      if (mine) show.celebrate();
    }
  });

  const sign =
    view.phase === "roles"
      ? "Your secret role"
      : view.phase === "night"
        ? `Night ${view.round} · the town sleeps`
        : view.phase === "dawn"
          ? `Morning ${view.round}`
          : view.phase === "day"
            ? `Day ${view.round} · talk, then vote`
            : view.phase === "verdict"
              ? "The verdict"
              : "Game over";
  const acting = !!me?.alive;
  const tally = new Map<string, string[]>();
  for (const [voter, target] of Object.entries(view.votes)) if (target) tally.set(target, [...(tally.get(target) ?? []), voter]);
  const skips = Object.values(view.votes).filter((t) => t === null).length;
  const roleOf = (pid: string): MafiaRole | null =>
    view.roles?.[pid] ?? view.dead.find((d) => d.id === pid)?.role ?? (pid === you && me ? me.role : null);

  return (
    <div className={`seg-mafia stack mf ${night ? "is-night" : "is-day"}`}>
      {show.node}
      <ShowHead sign={sign} title="Mafia Night" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">
          {view.alive.length} still in · {view.counts.mafia ?? 0} Mafia dealt
        </span>
      </ShowHead>

      <div className="mf-sky" aria-hidden="true">
        <span className="mf-orb" />
        <span className="mf-stars" />
        <span className="mf-town" />
      </div>

      {me && view.phase !== "final" && (
        <Card className={`mf-role-card ${me.alive ? "" : "ghost"}`}>
          {!me.alive && <p className="sign">👻 You’re a ghost: watch quietly, no hints!</p>}
          {view.phase === "roles" || peek ? (
            <div className={`mf-role r-${me.role}`}>
              <span className="mf-role-icon" aria-hidden="true">
                {ROLE[me.role].icon}
              </span>
              <div>
                <p className="mf-role-name">
                  You are {me.role === "mafia" ? "" : me.role === "villager" ? "a " : "the "}
                  {ROLE[me.role].name}
                </p>
                <p className="mf-role-job">{ROLE[me.role].job}</p>
                {me.mates.length > 0 && (
                  <p className="mf-role-job">
                    Your partner: <b>{me.mates.map(name).join(" & ")}</b>. You have a private chat.
                  </p>
                )}
                {me.findings && Object.keys(me.findings).length > 0 && (
                  <ul className="mf-findings">
                    {Object.entries(me.findings).map(([pid, bad]) => (
                      <li key={pid} className={bad ? "bad" : "ok"}>
                        <b>{name(pid)}</b>: {bad ? "MAFIA" : "not Mafia"}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : null}
          {view.phase !== "roles" && (
            <Btn variant="ghost" size="small" aria-pressed={peek} onClick={() => setPeek(!peek)}>
              {peek ? "Hide my role" : "🤫 Peek at my role"}
            </Btn>
          )}
        </Card>
      )}

      {view.phase === "roles" && (
        <Card tone="stage" className="center">
          <p className="lead">{tv ? "Everyone is reading their secret role…" : "Memorise it. Night falls in a moment."}</p>
        </Card>
      )}

      {view.phase === "night" && (
        <Card tone="stage" className="center">
          <p className="sign">Shhh…</p>
          <p className="lead space-top" aria-live="polite">
            {view.acted.length} of {view.alive.length} have made their move
          </p>
        </Card>
      )}

      {view.phase === "night" && acting && me && (
        <Card tone="soft">
          <h3>{NIGHT_ASK[me.role]}</h3>
          {me.role === "villager" && (
            <p className="muted">It changes nothing: everyone taps someone, so nobody can tell who has a job.</p>
          )}
          <div className="mf-grid" role="group" aria-label="Pick a player">
            {view.alive
              .filter((p) => p !== you || me.role === "doctor")
              .filter((p) => !(me.role === "mafia" && me.mates.includes(p)))
              .map((p) => {
                const blocked = me.role === "doctor" && me.last_protected === p;
                const mateWants = Object.entries(me.mate_picks ?? {}).filter(([, t]) => t === p);
                return (
                  <button
                    key={p}
                    type="button"
                    className="mf-pick"
                    aria-pressed={me.pick === p}
                    disabled={blocked}
                    onClick={() => {
                      sfx.pop();
                      send({ t: "act", a: "night", target: p });
                    }}
                  >
                    <Avatar pid={p} name={name(p)} />
                    <span className="mf-pick-name">{p === you ? "Yourself" : name(p)}</span>
                    {blocked && <span className="mf-pick-note">protected last night</span>}
                    {mateWants.length > 0 && <span className="mf-pick-note">{name(mateWants[0]![0])}’s pick</span>}
                  </button>
                );
              })}
          </div>
          {me.pick && <p className="muted space-top">Locked in. You can change it until everyone has moved.</p>}
        </Card>
      )}

      {view.phase === "dawn" && view.news && (
        <Card tone="stage" className="center mf-news">
          {view.news.killed ? (
            <>
              <p className="mf-big" aria-hidden="true">
                💀
              </p>
              <p className="lead">
                <b>{name(view.news.killed)}</b> didn’t make it through the night.
              </p>
              <p className={`mf-stamp ${view.news.role === "mafia" ? "bad" : "ok"}`}>They were {ROLE[view.news.role!].name}</p>
            </>
          ) : view.news.saved ? (
            <>
              <p className="mf-big" aria-hidden="true">
                🩺
              </p>
              <p className="lead">Someone was attacked… but the Doctor got there first. Nobody was lost!</p>
            </>
          ) : (
            <>
              <p className="mf-big" aria-hidden="true">
                🌤️
              </p>
              <p className="lead">A quiet night. Nobody was hurt.</p>
            </>
          )}
        </Card>
      )}

      {view.phase === "day" && (
        <Card tone="soft">
          <h3>Who is Mafia?</h3>
          <p className="muted" aria-live="polite">
            {Object.keys(view.votes).length} of {view.alive.length} voted
            {skips > 0 ? ` · ${skips} skipped` : ""}. Most votes goes; a tie saves everyone.
          </p>
          <div className="mf-grid space-top" role="group" aria-label="Vote someone out">
            {view.alive.map((p) => {
              const voters = tally.get(p) ?? [];
              return (
                <button
                  key={p}
                  type="button"
                  className="mf-pick vote"
                  aria-pressed={me?.vote === p}
                  disabled={!acting || p === you}
                  onClick={() => {
                    sfx.pop();
                    send({ t: "act", a: "vote", target: p });
                  }}
                >
                  <Avatar pid={p} name={name(p)} />
                  <span className="mf-pick-name">{p === you && !tv ? "You" : name(p)}</span>
                  <span className="mf-votes" aria-label={`${voters.length} votes`}>
                    {voters.length > 0 ? `${voters.length} 🗳️` : " "}
                  </span>
                  {voters.length > 0 && <span className="mf-pick-note">{voters.map(name).join(", ")}</span>}
                </button>
              );
            })}
          </div>
          {acting && (
            <p className="center space-top">
              <Btn variant="ghost" aria-pressed={me?.voted && me.vote === null} onClick={() => send({ t: "act", a: "vote", target: null })}>
                Skip: vote nobody out
              </Btn>
            </p>
          )}
        </Card>
      )}

      {view.phase === "verdict" && view.news && (
        <Card tone="stage" className="center mf-news">
          {view.news.out ? (
            <>
              <p className="mf-big" aria-hidden="true">
                ⚖️
              </p>
              <p className="lead">
                The town voted out <b>{name(view.news.out)}</b>.
              </p>
              <p className={`mf-stamp ${view.news.role === "mafia" ? "bad" : "ok"}`}>
                {view.news.role === "mafia" ? "MAFIA!" : `Innocent: the ${ROLE[view.news.role!].name}`}
              </p>
            </>
          ) : (
            <>
              <p className="mf-big" aria-hidden="true">
                🤷
              </p>
              <p className="lead">No agreement. Nobody was voted out.</p>
            </>
          )}
        </Card>
      )}

      {view.phase === "final" && (
        <Card tone="stage" className="center mf-news">
          <p className="mf-big" aria-hidden="true">
            {view.winner === "town" ? "🏘️" : "🎩"}
          </p>
          <h3 className="mf-winner">{view.winner === "town" ? "The town wins!" : "The Mafia win!"}</h3>
          <p className="lead">
            Mafia: <b>{view.players.filter((p) => view.roles?.[p.id] === "mafia").map((p) => p.name).join(" & ")}</b>
          </p>
        </Card>
      )}

      <Card>
        <h3>{view.phase === "final" ? "Who was who" : "The town"}</h3>
        <ul className="mf-town-list">
          {view.players.map((p) => {
            const dead = view.dead.find((d) => d.id === p.id);
            const role = roleOf(p.id);
            return (
              <li key={p.id} className={dead ? "out" : ""}>
                <Avatar pid={p.id} name={p.name} />
                <span className="mf-who">
                  <b>{p.name}</b>
                  {p.id === you && !tv ? " (you)" : ""}
                  {dead && <span className="muted"> · {dead.how === "night" ? "lost in the night" : "voted out"}</span>}
                </span>
                {role && (p.id !== you || peek || dead || view.roles) ? (
                  <span className={`mf-tag r-${role}`}>
                    <span aria-hidden="true">{ROLE[role].icon}</span> {ROLE[role].name}
                  </span>
                ) : null}
                {view.scores && <span className="score-pts">{view.scores[p.id] ?? 0}</span>}
              </li>
            );
          })}
        </ul>
      </Card>

      {view.log && (
        <Card>
          <h3>How it went</h3>
          <ol className="mf-log">
            {view.log.map((e, i) => (
              <li key={i}>
                {e.kind === "night" ? (
                  <>
                    <b>Night {e.round}:</b>{" "}
                    {e.killed ? `${name(e.killed)} was lost` : e.saved ? "the Doctor saved the target" : "nobody was hurt"}
                    {e.checked ? `; the Detective checked ${name(e.checked)}` : ""}
                  </>
                ) : (
                  <>
                    <b>Day {e.round}:</b> {e.out ? `${name(e.out)} was voted out` : "nobody was voted out"}
                  </>
                )}
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}
