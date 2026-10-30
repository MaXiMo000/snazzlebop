import { useState } from "react";
import { useAccount } from "../lib/account";
import { ApiError, request } from "../lib/api";
import { STATUS_TEXT } from "../lib/clubs";
import type { Invitees, Ok } from "../lib/contract";
import { Btn, Loading } from "./ui";

/**
 * In the lobby, for a signed-in player: invite friends (who added you back) and, in a club room,
 * clubmates. They get it in their inbox and as a push. Shown only to people seated in the room.
 */
export function InviteFriends({ code }: { code: string }) {
  const { user } = useAccount();
  const [people, setPeople] = useState<Invitees["people"] | null>(null);
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  if (!user) return null;

  const load = async () => {
    setError(null);
    try {
      setPeople((await request<Invitees>(`/api/rooms/${encodeURIComponent(code)}/invitees`)).people);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load your friends");
    }
  };
  const invite = async (username: string) => {
    setError(null);
    try {
      await request<Ok>(`/api/rooms/${encodeURIComponent(code)}/invite`, { method: "POST", body: JSON.stringify({ username }) });
      setSent((s) => new Set(s).add(username));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't send that invite");
    }
  };

  return (
    <div className="invite-friends space-top">
      <Btn
        size="small"
        variant="ghost"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          if (!open) void load();
        }}
      >
        {open ? "Hide friends" : "Invite friends"}
      </Btn>
      {open && (
        <div className="invite-panel">
          {error ? (
            <p className="muted">{error}</p>
          ) : people === null ? (
            <Loading />
          ) : people.length ? (
            <ul className="club-rooms invite-list">
              {people.map((p) => (
                <li key={p.username}>
                  <span className="club-room-text">
                    <b className="member-name">
                      <span className={`status-dot ${p.status}`} aria-hidden="true" />
                      {p.username}
                    </b>
                    <span className="muted">
                      {STATUS_TEXT[p.status]} · {p.why === "club" ? "Clubmate" : "Friend"}
                    </span>
                  </span>
                  <Btn size="small" variant={sent.has(p.username) ? "ghost" : "go"} disabled={sent.has(p.username)} onClick={() => void invite(p.username)}>
                    {sent.has(p.username) ? "Invited" : "Invite"}
                    <span className="sr-only"> {p.username}</span>
                  </Btn>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No one to invite yet. Add friends on the home page (they add you back), or join a club.</p>
          )}
        </div>
      )}
    </div>
  );
}
