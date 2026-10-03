import { useRef, useState, type KeyboardEvent } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { AlibiView } from "../types";

interface Props {
  view: AlibiView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

type Tab = "card" | "board" | "vote";
const TABS: Tab[] = ["card", "board", "vote"];

export function Alibi({ view, you, receivedAt, send, tv = false }: Props) {
  // A tab picked in one phase doesn't carry over: when voting opens, show the vote.
  const [picked, setPicked] = useState<{ phase: string; tab: Tab } | null>(null);
  const activeTab: Tab = (picked?.phase === view.phase ? picked.tab : null) ?? (view.phase === "vote" ? "vote" : "card");
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ card: null, board: null, vote: null });
  const [shaking, setShaking] = useState(0);
  const show = useShow();

  useOnChange(view.flags.length, (prev, next) => {
    if (next > prev) {
      sfx.buzz();
      show.stinger("CONTRADICTION!", "bad");
      setShaking(Date.now());
    }
  });
  useOnChange(view.clues.length, (prev, next) => {
    if (next > prev) sfx.ding();
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "final" && view.result) {
      const iWon = tv ? view.result.caught : view.result.caught ? view.result.killer !== you : view.result.killer === you;
      show.stinger(view.result.caught ? "CAUGHT!" : "THEY GOT AWAY!", view.result.caught ? "good" : "bad");
      if (iWon) {
        sfx.fanfare();
        show.celebrate();
      } else sfx.buzz();
    }
  });

  const labels: Record<Tab, string> = { card: "My card", board: `Board (${view.claims.length})`, vote: "Vote" };
  const pick = (t: Tab) => {
    setPicked({ phase: view.phase, tab: t });
    tabRefs.current[t]?.focus();
  };
  const onTabKey = (e: KeyboardEvent) => {
    const i = TABS.indexOf(activeTab);
    if (e.key === "ArrowRight") pick(TABS[(i + 1) % TABS.length]!);
    else if (e.key === "ArrowLeft") pick(TABS[(i + TABS.length - 1) % TABS.length]!);
    else return;
    e.preventDefault();
  };

  const sign = {
    briefing: "Briefing",
    interrogate: `Interrogation ${view.round} of ${view.rounds}`,
    vote: "Final vote",
    final: "Case closed",
  }[view.phase as "briefing" | "interrogate" | "vote" | "final"];

  return (
    <div className="seg-alibi stack">
      {show.node}
      <ShowHead sign={sign ?? view.phase} title={view.setting} remaining={view.remaining} receivedAt={receivedAt}>
        <p>
          {view.victim} was found in the <b>{view.scene}</b> around <b>{view.murder_label}</b>. One of you did it.
        </p>
      </ShowHead>

      {view.you.is_killer && view.phase !== "final" && (
        <Card tone="stage">
          <p className="sign">Top secret</p>
          <p className="space-top">
            You’re the <b>killer</b>. The lies on your card are marked 🤥. Stay calm, stay consistent.
          </p>
          {view.you.plant ? (
            <p className="space-top">
              🖼️ Your fake clue against <b>{nameOf(view.players, view.you.plant.target)}</b> (
              {view.slots[view.you.plant.slot]}){" "}
              {view.you.plant.released ? "is on the board. Act surprised." : "drops with the next camera feed."}
            </p>
          ) : view.you.can_plant && view.phase === "interrogate" ? (
            <p className="space-top">🖼️ You can plant one fake camera clue on someone: see the Board tab.</p>
          ) : null}
        </Card>
      )}

      <div key={view.phase} className="stack enter">
        {tv && view.phase !== "final" && <TvCase view={view} fresh={Date.now() - shaking < 1500} />}
        {!tv && view.phase === "briefing" && (
          <>
            <Briefing view={view} />
            <AlibiCard view={view} send={send} interactive={false} />
          </>
        )}

        {!tv && (view.phase === "interrogate" || view.phase === "vote") && (
          <>
            <div className="tabs" role="tablist" aria-label="Case file" onKeyDown={onTabKey}>
              {TABS.map((id) => (
                <button
                  key={id}
                  ref={(el) => {
                    tabRefs.current[id] = el;
                  }}
                  id={`tab-${id}`}
                  role="tab"
                  className="tab"
                  aria-selected={activeTab === id}
                  aria-controls={`panel-${id}`}
                  tabIndex={activeTab === id ? 0 : -1}
                  onClick={() => pick(id)}
                >
                  {labels[id]}
                </button>
              ))}
            </div>
            <div id={`panel-${activeTab}`} role="tabpanel" aria-labelledby={`tab-${activeTab}`}>
              {activeTab === "card" && <AlibiCard view={view} send={send} interactive={view.phase === "interrogate"} />}
              {activeTab === "board" && (
                <Board fresh={Date.now() - shaking < 1500} view={view} you={you} send={send} readOnly={view.phase === "vote"} />
              )}
              {activeTab === "vote" &&
                (view.phase === "vote" ? (
                  <Vote view={view} you={you} send={send} />
                ) : (
                  <Card tone="soft">
                    <p>Voting opens after the last interrogation round. Keep digging!</p>
                  </Card>
                ))}
            </div>
          </>
        )}

        {view.phase === "final" && view.result && <Result view={view} you={you} tv={tv} />}
      </div>
    </div>
  );
}

function TvCase({ view, fresh }: { view: AlibiView; fresh: boolean }) {
  if (view.phase === "briefing") {
    return (
      <Card tone="soft" className="center">
        <h3>Contestants are studying their alibi cards…</h3>
        <p>One of them is lying. Everyone’s story for {view.murder_label} goes on the board next.</p>
      </Card>
    );
  }
  return (
    <>
      {view.phase === "vote" && (
        <Card tone="soft" className="center">
          <h3>The vote is open</h3>
          <p className="lead" aria-live="polite">
            {view.votes_in} of {view.players.length} votes in
          </p>
        </Card>
      )}
      <Board view={view} you="" send={() => undefined} readOnly fresh={fresh} />
    </>
  );
}

function Briefing({ view }: { view: AlibiView }) {
  return (
    <Card tone="soft">
      <h3>Read your card!</h3>
      <p>
        Everyone’s alibi for <b>{view.murder_label}</b> goes on the board when interrogation starts. Learn your timeline: you
        must stay consistent with it.
      </p>
      <p>
        Everyone gets one <b>Objection!</b>: +50 if it exposes a story, −50 if it doesn’t. And watch out: the killer can plant
        one fake camera clue.
      </p>
      {view.you.is_killer ? (
        <p>
          <span className="chip cherry">You are the killer</span> Your card has lies. Learn them.
        </p>
      ) : (
        <p>
          <span className="chip teal">You are innocent</span> Your card is the truth as you remember it. Careful: one
          innocent’s memory is usually a little hazy, and it might be yours.
        </p>
      )}
    </Card>
  );
}

function AlibiCard({ view, send, interactive }: { view: AlibiView; send: Props["send"]; interactive: boolean }) {
  const lies = new Set(view.you.fake_slots ?? []);
  return (
    <Card>
      <h3>Your alibi</h3>
      <ol className="timeline">
        {view.you.card.map((e) => (
          <li key={e.slot} className={`slot ${e.slot === view.murder_slot ? "murder" : ""} ${lies.has(e.slot) ? "lie" : ""}`}>
            <span className="time">{e.label}</span>
            <span>
              <b>{e.location}</b>{" "}
              {e.with.length > 0 ? <>with {e.with.map((id) => nameOf(view.players, id)).join(", ")}</> : <span className="muted">alone</span>}
              <span className="marks">
                {e.slot === view.murder_slot && <span className="chip cherry">murder</span>}
                {lies.has(e.slot) && <span className="chip plum">🤥 lie</span>}
              </span>
            </span>
            {interactive && (
              <Btn
                size="small"
                variant={e.shared ? "ghost" : "accent"}
                disabled={e.shared}
                aria-label={e.shared ? `${e.label} already shared` : `Share your ${e.label} alibi`}
                onClick={() => {
                  sfx.pop();
                  send({ t: "act", a: "reveal", slot: e.slot });
                }}
              >
                {e.shared ? "Shared" : "Share"}
              </Btn>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function Board({
  view,
  you,
  send,
  readOnly,
  fresh,
}: {
  view: AlibiView;
  you: string;
  send: Props["send"];
  readOnly: boolean;
  /** a contradiction just landed: shake the flags (the form keeps its state) */
  fresh: boolean;
}) {
  const [target, setTarget] = useState<string>("");
  const [slot, setSlot] = useState<number>(0);
  const others = view.players.filter((p) => p.id !== you);
  const known = new Set(view.claims.map((c) => `${c.speaker}:${c.slot}`));
  const alreadyOnBoard = target !== "" && known.has(`${target}:${slot}`);

  return (
    <div className="stack">
      {!readOnly && (
        <Card tone="soft">
          <h3>Grill someone</h3>
          <p className="muted">Force a player to put one alibi slot on the board. Questions left this round: {view.you.asks_left}</p>
          <div className="ask-form">
            <div>
              <label className="field" htmlFor="ask-target">
                Who
              </label>
              <select id="ask-target" value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">Pick a suspect…</option>
                {others.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field" htmlFor="ask-slot">
                When
              </label>
              <select id="ask-slot" value={slot} onChange={(e) => setSlot(Number(e.target.value))}>
                {view.slots.map((s, i) => (
                  <option key={s} value={i}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <Btn
              variant="danger"
              disabled={!target || alreadyOnBoard || view.you.asks_left <= 0}
              onClick={() => {
                sfx.pop();
                send({ t: "act", a: "ask", target, slot });
              }}
            >
              {alreadyOnBoard ? "Already on board" : "Where were you?"}
            </Btn>
          </div>
        </Card>
      )}

      {!readOnly && view.you.objection_left && (
        <PickForm
          id="obj"
          title="Objection!"
          hint="Their story for that time goes on the board, and we pull the camera headcount for where they claim to be. +50 if it exposes them, −50 if it doesn’t. Once per game."
          view={view}
          you={you}
          action="Objection!"
          variant="gold"
          onPick={(target, slot) => {
            sfx.buzz();
            send({ t: "act", a: "object", target, slot });
          }}
        />
      )}
      {!readOnly && view.you.can_plant && (
        <PickForm
          id="plant"
          title="Plant evidence (killer only)"
          hint="Fake a camera clue that contradicts someone’s story. It drops with the next real clue, worded just like one. Once per game."
          view={view}
          you={you}
          action="Plant it"
          variant="danger"
          onPick={(target, slot) => {
            sfx.pop();
            send({ t: "act", a: "plant", target, slot });
          }}
        />
      )}

      {view.flags.length > 0 && (
        <Card key={view.flags.length} className={fresh ? "shake" : ""}>
          <h3>🚨 Contradictions</h3>
          <ul className="evidence" aria-live="polite">
            {view.flags.map((f, i) => (
              <li key={i} className="flag">
                {f.text}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {view.clues.length > 0 && (
        <Card>
          <h3>Camera clues</h3>
          <ul className="evidence">
            {view.clues.map((c, i) => (
              <li key={i} className="clue">
                📹 {c.location} at {c.label}:{" "}
                {c.kind === "headcount"
                  ? `blurry feed, ${c.count} ${c.count === 1 ? "person" : "people"} in frame`
                  : c.occupants?.length
                    ? c.occupants.map((id) => nameOf(view.players, id)).join(", ")
                    : "nobody in frame"}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <h3>The board</h3>
        {view.claims.length === 0 ? (
          <p className="muted">Nothing shared yet.</p>
        ) : (
          <div className="table-scroll" role="region" aria-label="The board" tabIndex={0}>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Who</th>
                  <th scope="col">Says they were</th>
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
      </Card>

      {view.log.length > 0 && (
        <Card>
          <h3>Case log</h3>
          <ul className="evidence">
            {[...view.log].reverse().map((l, i) => (
              <li key={i}>{l.text}</li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function PickForm({
  id,
  title,
  hint,
  view,
  you,
  action,
  variant,
  onPick,
}: {
  id: string;
  title: string;
  hint: string;
  view: AlibiView;
  you: string;
  action: string;
  variant: "gold" | "danger";
  onPick: (target: string, slot: number) => void;
}) {
  const [target, setTarget] = useState("");
  const [slot, setSlot] = useState(0);
  return (
    <Card tone="soft" aria-labelledby={`${id}-h`}>
      <h3 id={`${id}-h`}>{title}</h3>
      <p className="muted">{hint}</p>
      <div className="ask-form">
        <div>
          <label className="field" htmlFor={`${id}-target`}>
            Who
          </label>
          <select id={`${id}-target`} value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Pick a player…</option>
            {view.players
              .filter((p) => p.id !== you)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
          </select>
        </div>
        <div>
          <label className="field" htmlFor={`${id}-slot`}>
            When
          </label>
          <select id={`${id}-slot`} value={slot} onChange={(e) => setSlot(Number(e.target.value))}>
            {view.slots.map((s, i) => (
              <option key={s} value={i}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <Btn variant={variant} disabled={!target} onClick={() => onPick(target, slot)}>
          {action}
        </Btn>
      </div>
    </Card>
  );
}

function Vote({ view, you, send }: { view: AlibiView; you: string; send: Props["send"] }) {
  return (
    <Card>
      <h3>Who did it?</h3>
      <p>
        Most votes wins. If the killer isn’t the <b>single</b> top pick, they walk.{" "}
        <span aria-live="polite">
          {view.votes_in}/{view.players.length} votes in.
        </span>
      </p>
      <div className="vote-grid">
        {view.players
          .filter((p) => p.id !== you)
          .map((p) => (
            <Btn
              key={p.id}
              variant="danger"
              aria-pressed={view.you_voted === p.id}
              onClick={() => {
                sfx.pop();
                send({ t: "act", a: "vote", target: p.id });
              }}
            >
              {p.name}
              {view.you_voted === p.id ? " ✓" : ""}
            </Btn>
          ))}
      </div>
    </Card>
  );
}

function Result({ view, you, tv }: { view: AlibiView; you: string; tv: boolean }) {
  const r = view.result!;
  const killerName = nameOf(view.players, r.killer);
  const iWon = r.caught ? r.killer !== you : r.killer === you;
  const personal = tv ? "" : iWon ? "🎉 You win this one." : "Better luck next time.";
  return (
    <>
      <Card tone="stage" className="center">
        <p className="sign">{r.caught ? "Caught!" : "They got away!"}</p>
        <h3 className="prompt space-top">The killer was {killerName}</h3>
        <p>
          {r.caught ? "The room got it right." : "The room was fooled."} {personal}
        </p>
      </Card>
      <Card>
        <h3>The truth</h3>
        <div className="table-scroll" role="region" aria-label="The truth" tabIndex={0}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Who</th>
                {view.slots.map((s) => (
                  <th scope="col" key={s}>
                    {s}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {view.players.map((p) => (
                <tr key={p.id}>
                  <th scope="row">
                    {p.name}
                    {p.id === r.killer ? " 🔪" : ""}
                  </th>
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
        <p className="muted space-top">Highlighted cells: where the killer’s card told a different story.</p>
      </Card>
      <Card tone="soft">
        <h3>How it happened</h3>
        <ol className="evidence">
          {r.recap.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ol>
      </Card>
      {view.objections.length > 0 && (
        <Card>
          <h3>Objections</h3>
          <ul className="evidence">
            {view.objections.map((o) => (
              <li key={o.by}>
                {nameOf(view.players, o.by)} → {nameOf(view.players, o.target)} at {o.label}:{" "}
                <span className={`chip ${o.sustained ? "teal" : "cherry"}`}>{o.sustained ? "sustained +50" : "overruled −50"}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card>
        <h3>Votes</h3>
        {Object.keys(r.votes).length === 0 && <p className="muted">Nobody voted.</p>}
        <ul className="evidence">
          {Object.entries(r.votes).map(([voter, target]) => (
            <li key={voter}>
              {nameOf(view.players, voter)} → {nameOf(view.players, target)}
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
