import { Btn, Card, nameOf } from "./ui";
import { sfx } from "../lib/sfx";
import type { RoomState } from "../types";

type Send = (msg: Record<string, unknown>) => void;

export const TEAM_NAMES = ["Team Tangerine", "Team Teal"] as const;

function Members({ state, ids }: { state: RoomState; ids: string[] }) {
  return (
    <ul className="team-members">
      {ids.map((id) => (
        <li key={id}>
          {nameOf(state.players, id)}
          {id === state.you ? " (you)" : ""}
        </li>
      ))}
    </ul>
  );
}

/** The intro screen: who's on which team (the host can shuffle them before it starts). */
export function TeamsCard({ state, send, readOnly }: { state: RoomState; send: Send; readOnly: boolean }) {
  const t = state.teams;
  if (!t) return null;
  const isHost = state.room.host === state.you;
  return (
    <Card aria-labelledby="teams-h">
      <h3 id="teams-h">The teams</h3>
      {t.you !== null && !readOnly && (
        <p className="lead">
          You're on <b className={`team-name team-${t.you}`}>{TEAM_NAMES[t.you]}</b>
        </p>
      )}
      <div className="teams-grid space-top">
        {t.members.map((ids, i) => (
          <div key={i} className={`team-box team-${i}`}>
            <p className="team-name">{TEAM_NAMES[i]}</p>
            <Members state={state} ids={ids} />
          </div>
        ))}
      </div>
      <p className="muted space-top">Same rules as always. The team with the bigger combined score wins.</p>
      {isHost && !readOnly && (
        <Btn
          variant="ghost"
          className="space-top"
          onClick={() => {
            sfx.spin();
            send({ t: "shuffle" });
          }}
        >
          🔀 Shuffle the teams
        </Btn>
      )}
    </Card>
  );
}

/** During a team game: your team (players) or both line-ups (TV). */
export function TeamBadge({ state, tv = false }: { state: RoomState; tv?: boolean }) {
  const t = state.teams;
  if (!t || state.room.phase !== "game") return null;
  if (tv || t.you === null) {
    return (
      <p className="team-strip" aria-label="Teams">
        {t.members.map((ids, i) => (
          <span key={i} className={`chip team-chip team-${i}`}>
            {TEAM_NAMES[i]}: {ids.map((id) => nameOf(state.players, id)).join(" & ")}
          </span>
        ))}
      </p>
    );
  }
  const mates = t.members[t.you]!.filter((id) => id !== state.you);
  return (
    <p className="team-strip">
      <span className={`chip team-chip team-${t.you}`}>
        {TEAM_NAMES[t.you]}
        {mates.length ? ` with ${mates.map((id) => nameOf(state.players, id)).join(" & ")}` : ""}
      </span>
    </p>
  );
}

/** Results: the team totals and the winner. */
export function TeamResult({ state }: { state: RoomState }) {
  const t = state.teams;
  const news = t?.news;
  if (!t || !news) return null;
  const head = news.winner === null ? "It's a draw!" : `${TEAM_NAMES[news.winner]} wins!`;
  return (
    <Card tone="stage" className="center team-result" role="status">
      <p className="sign">Team game</p>
      <h3 className="team-head">{head}</h3>
      <div className="teams-grid space-top">
        {t.members.map((ids, i) => (
          <div key={i} className={`team-box team-${i} ${news.winner === i ? "won" : ""}`}>
            <p className="team-name">{TEAM_NAMES[i]}</p>
            <p className="team-score">{news.scores[i]}</p>
            <Members state={state} ids={ids} />
          </div>
        ))}
      </div>
    </Card>
  );
}
