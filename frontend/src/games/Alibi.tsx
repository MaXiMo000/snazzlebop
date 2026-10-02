import { useState } from "react";
import { Btn, Panel, Timer, nameOf } from "../components/ui";
import type { AlibiView } from "../types";

interface Props {
  view: AlibiView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
}

type Tab = "card" | "board" | "vote";

export function Alibi({ view, you, receivedAt, send }: Props) {
  // A tab picked during one phase doesn't carry over: when voting opens, show the vote.
  const [picked, setPicked] = useState<{ phase: string; tab: Tab } | null>(null);
  const tab = picked?.phase === view.phase ? picked.tab : null;
  const me = view.you;
  const tabs: [Tab, string][] = [
    ["card", "My card"],
    ["board", `Board (${view.claims.length})`],
    ["vote", "Vote"],
  ];
  const activeTab: Tab = tab ?? (view.phase === "vote" ? "vote" : "card");

  return (
    <div className="theme-alibi">
      <Panel themed className="halftone">
        <div className="row between">
          <div>
            <span className="tag yellow">
              {view.phase === "briefing" && "Briefing"}
              {view.phase === "interrogate" && `Interrogation ${view.round}/${view.rounds}`}
              {view.phase === "vote" && "Final vote"}
              {view.phase === "final" && "Case closed"}
            </span>
            <h2>Murder at the manor</h2>
            <p>
              {view.victim} was found in the <b>{view.scene}</b> around <b>{view.murder_label}</b>. One of you did it.
            </p>
          </div>
          <Timer remaining={view.remaining} receivedAt={receivedAt} />
        </div>
      </Panel>

      {view.phase === "briefing" && <Briefing view={view} />}

      {view.phase !== "final" && view.phase !== "briefing" && (
        <div className="tabs" role="tablist">
          {tabs.map(([id, label]) => (
            <button key={id} role="tab" className="tab" aria-selected={activeTab === id} onClick={() => setPicked({ phase: view.phase, tab: id })}>
              {label}
            </button>
          ))}
        </div>
      )}

      {view.phase === "briefing" && <Card view={view} send={send} interactive={false} />}
      {(view.phase === "interrogate" || view.phase === "vote") && activeTab === "card" && (
        <Card view={view} send={send} interactive={view.phase === "interrogate"} />
      )}
      {(view.phase === "interrogate" || view.phase === "vote") && activeTab === "board" && (
        <Board view={view} you={you} send={send} readOnly={view.phase === "vote"} />
      )}
      {view.phase === "vote" && activeTab === "vote" && <Vote view={view} you={you} send={send} />}
      {view.phase === "interrogate" && activeTab === "vote" && (
        <Panel>
          <p>Voting opens after the last interrogation round. Keep digging!</p>
        </Panel>
      )}
      {view.phase === "final" && view.result && <Result view={view} you={you} />}
      {me.is_killer && view.phase !== "final" && (
        <Panel className="tilt-r">
          <span className="tag pink">Secret</span>
          <p>
            You're the <b>killer</b>. The lies on your card are marked 🤥. Stay calm and stay consistent.
          </p>
        </Panel>
      )}
    </div>
  );
}

function Briefing({ view }: { view: AlibiView }) {
  return (
    <Panel>
      <h3>Read your card!</h3>
      <p>
        Everyone's alibi for <b>{view.murder_label}</b> goes on the board when the interrogation starts. Study your timeline: you must stay consistent with it.
      </p>
      {view.you.is_killer ? (
        <p>
          <span className="tag pink">You are the killer</span> Your card has lies. Learn them.
        </p>
      ) : (
        <p>
          <span className="tag lime">You are innocent</span> Your card is the truth. Someone else's isn't.
        </p>
      )}
    </Panel>
  );
}

function Card({ view, send, interactive }: { view: AlibiView; send: Props["send"]; interactive: boolean }) {
  const lies = new Set(view.you.fake_slots ?? []);
  return (
    <Panel>
      <h3>Your alibi</h3>
      <ol className="timeline">
        {view.you.card.map((e) => (
          <li key={e.slot} className={`slot ${e.slot === view.murder_slot ? "murder" : ""} ${lies.has(e.slot) ? "lie" : ""}`}>
            <span className="time">{e.label}</span>
            <span>
              <b>{e.location}</b>{" "}
              {e.with.length > 0 ? <>with {e.with.map((id) => nameOf(view.players, id)).join(", ")}</> : <span className="muted">alone</span>}
              {e.slot === view.murder_slot && <span className="tag pink" style={{ marginLeft: 8 }}>murder</span>}
              {lies.has(e.slot) && <span style={{ marginLeft: 8 }} title="This part of your story is a lie">🤥 lie</span>}
            </span>
            {interactive && (
              <Btn size="small" color={e.shared ? "ghost" : "cyan"} disabled={e.shared}
                aria-label={e.shared ? `${e.label} already shared` : `Share your ${e.label} alibi`}
                onClick={() => send({ t: "act", a: "reveal", slot: e.slot })}
              >
                {e.shared ? "Shared" : "Share"}
              </Btn>
            )}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function Board({ view, you, send, readOnly = false }: { view: AlibiView; you: string; send: Props["send"]; readOnly?: boolean }) {
  const [target, setTarget] = useState<string>("");
  const [slot, setSlot] = useState<number>(0);
  const others = view.players.filter((p) => p.id !== you);
  const known = new Set(view.claims.map((c) => `${c.speaker}:${c.slot}`));
  const alreadyOnBoard = target !== "" && known.has(`${target}:${slot}`);

  return (
    <div className="stack">
      {!readOnly && (
        <Panel>
          <h3>Grill someone</h3>
          <p className="muted">Force a player to put one alibi slot on the board. Questions left this round: {view.you.asks_left}</p>
          <div className="row">
            <label className="field" htmlFor="ask-target" style={{ margin: 0 }}>
              Who
            </label>
            <select id="ask-target" value={target} onChange={(e) => setTarget(e.target.value)} className="btn ghost small">
              <option value="">Pick a suspect…</option>
              {others.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <label className="field" htmlFor="ask-slot" style={{ margin: 0 }}>
              When
            </label>
            <select id="ask-slot" value={slot} onChange={(e) => setSlot(Number(e.target.value))} className="btn ghost small">
              {view.slots.map((s, i) => (
                <option key={s} value={i}>
                  {s}
                </option>
              ))}
            </select>
            <Btn color="pink" size="small" disabled={!target || alreadyOnBoard || view.you.asks_left <= 0} onClick={() => send({ t: "act", a: "ask", target, slot })}>
              {alreadyOnBoard ? "Already on board" : "Where were you?"}
            </Btn>
          </div>
        </Panel>
      )}

      {view.flags.length > 0 && (
        <Panel className="tilt-l">
          <h3>🚨 Contradictions</h3>
          <ul className="evidence">
            {view.flags.map((f, i) => (
              <li key={i} className="flag">
                {f.text}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {view.clues.length > 0 && (
        <Panel>
          <h3>Clues</h3>
          <ul className="evidence">
            {view.clues.map((c, i) => (
              <li key={i} className="clue">
                📹 {c.location} camera at {c.label}:{" "}
                {c.occupants.length ? c.occupants.map((id) => nameOf(view.players, id)).join(", ") : "nobody in frame"}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel>
        <h3>The board</h3>
        {view.claims.length === 0 ? (
          <p className="muted">Nothing shared yet.</p>
        ) : (
          <div className="table-scroll" role="region" aria-label="The board" tabIndex={0}>
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Who</th>
                <th>Says they were</th>
              </tr>
            </thead>
            <tbody>
              {view.claims.map((c) => (
                <tr key={`${c.speaker}:${c.slot}`}>
                  <td>{c.label}</td>
                  <td>{nameOf(view.players, c.speaker)}</td>
                  <td>
                    {c.location}
                    {c.with.length ? ` with ${c.with.map((id) => nameOf(view.players, id)).join(", ")}` : " alone"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Panel>

      {view.log.length > 0 && (
        <Panel>
          <h3>Case log</h3>
          <ul className="evidence">
            {[...view.log].reverse().map((l, i) => (
              <li key={i}>{l.text}</li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function Vote({ view, you, send }: { view: AlibiView; you: string; send: Props["send"] }) {
  return (
    <Panel>
      <h3>Who did it?</h3>
      <p>
        Most votes wins. If the killer isn't the <b>single</b> top pick, they walk. {view.votes_in}/{view.players.length} votes in.
      </p>
      <div className="vote-grid">
        {view.players
          .filter((p) => p.id !== you)
          .map((p) => (
            <Btn key={p.id} color="pink" aria-pressed={view.you_voted === p.id} onClick={() => send({ t: "act", a: "vote", target: p.id })}>
              {p.name}
              {view.you_voted === p.id ? " ✓" : ""}
            </Btn>
          ))}
      </div>
    </Panel>
  );
}

function Result({ view, you }: { view: AlibiView; you: string }) {
  const r = view.result!;
  const killerName = nameOf(view.players, r.killer);
  const iWon = r.caught ? r.killer !== you : r.killer === you;
  return (
    <div className="stack">
      <Panel themed className="halftone">
        <h2>{r.caught ? "Caught!" : "They got away!"}</h2>
        <p>
          The killer was <b>{killerName}</b>. {r.caught ? "The room got it right." : "The room was fooled."} {iWon ? "🎉 You win this one." : "Better luck next time."}
        </p>
      </Panel>
      <Panel>
        <h3>The truth</h3>
        <div className="table-scroll" role="region" aria-label="The truth" tabIndex={0}>
        <table className="table">
          <thead>
            <tr>
              <th>Who</th>
              {view.slots.map((s) => (
                <th key={s}>{s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.players.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.name}
                  {p.id === r.killer ? " 🔪" : ""}
                </td>
                {(r.truth[p.id] ?? []).map((loc, i) => (
                  <td key={i} className={p.id === r.killer && r.fake_slots.includes(i) ? "lie" : ""}>
                    {loc}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        <p className="muted">Red cells are slots where the killer's card told a different story.</p>
      </Panel>
      <Panel>
        <h3>Votes</h3>
        <ul className="evidence">
          {Object.entries(r.votes).map(([voter, target]) => (
            <li key={voter}>
              {nameOf(view.players, voter)} → {nameOf(view.players, target)}
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
