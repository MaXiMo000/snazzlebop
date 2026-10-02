import { useMemo, useState } from "react";
import { Btn, Panel, Timer, nameOf } from "../components/ui";
import type { FrenemyView } from "../types";

interface Props {
  view: FrenemyView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
}

export function Frenemy({ view, you, receivedAt, send }: Props) {
  return (
    <div className="theme-frenemy">
      <Panel themed className="halftone">
        <div className="row between">
          <div>
            <span className="tag yellow">
              Round {view.round}/{view.rounds}
            </span>
            <h2>Frenemy Radar</h2>
          </div>
          <Timer remaining={view.remaining} receivedAt={receivedAt} />
        </div>
      </Panel>
      {view.phase === "rank" && <Rank key={view.round} view={view} you={you} send={send} />}
      {view.phase === "reveal" && view.result && <Reveal view={view} you={you} />}
      {view.phase === "final" && view.final && <Final view={view} you={you} />}
    </div>
  );
}

function Rank({ view, you, send }: Pick<Props, "view" | "you" | "send">) {
  const [order, setOrder] = useState<string[]>(() => view.players.map((p) => p.id));
  const move = (i: number, d: -1 | 1) =>
    setOrder((o) => {
      const next = [...o];
      const j = i + d;
      if (j < 0 || j >= next.length) return o;
      [next[i], next[j]] = [next[j]!, next[i]!];
      return next;
    });

  if (view.you_submitted) {
    return (
      <Panel>
        <h3>Locked in! 🔒</h3>
        <p>
          Waiting for {view.players.length - view.submitted.length} more…{" "}
          {view.players
            .filter((p) => !view.submitted.includes(p.id))
            .map((p) => p.name)
            .join(", ")}
        </p>
      </Panel>
    );
  }
  return (
    <>
      <div className="bubble" role="heading" aria-level={2}>
        {view.prompt}
      </div>
      <Panel className="halftone" style={{ marginTop: 36 }}>
        <p>
          Rank <b>everyone</b>, including yourself. #1 = most like this.
        </p>
        <ol className="rank-list">
          {order.map((id, i) => (
            <li key={id} className={`rank-item ${id === you ? "me" : ""}`}>
              <span className="num">{i + 1}</span>
              <span className="name">
                {nameOf(view.players, id)}
                {id === you ? " (you)" : ""}
              </span>
              <span className="arrows">
                <button
                  className="arrow"
                  disabled={i === 0}
                  onClick={() => move(i, -1)}
                  aria-label={`Move ${nameOf(view.players, id)} up`}
                >
                  ▲
                </button>
                <button
                  className="arrow"
                  disabled={i === order.length - 1}
                  onClick={() => move(i, 1)}
                  aria-label={`Move ${nameOf(view.players, id)} down`}
                >
                  ▼
                </button>
              </span>
            </li>
          ))}
        </ol>
        <p style={{ marginTop: 16 }}>
          <Btn color="lime" size="big" onClick={() => send({ t: "act", a: "rank", order })}>
            Lock it in!
          </Btn>
        </p>
      </Panel>
    </>
  );
}

function verdict(gap: number): string {
  if (Math.abs(gap) < 0.5) return "Spot on 🎯";
  return gap > 0 ? "Thinks they're higher than the room does 😏" : "The room rates them higher than they do 🥹";
}

function Reveal({ view, you }: { view: FrenemyView; you: string }) {
  const rows = useMemo(
    () =>
      view.players
        .map((p) => ({ p, r: view.result![p.id]! }))
        .sort((a, b) => b.r.blind_pct - a.r.blind_pct),
    [view],
  );
  return (
    <Panel>
      <div className="bubble">{view.prompt}</div>
      <div className="stack" style={{ marginTop: 36 }}>
        {rows.map(({ p, r }) => (
          <div key={p.id} className="reveal-card">
            <div className="row between">
              <b>
                {p.name}
                {p.id === you ? " (you)" : ""}
              </b>
              <span className="tag pink">Blind spot {r.blind_pct}%</span>
            </div>
            {r.played ? (
              <>
                <p className="muted">
                  They ranked themselves #{r.self_rank}. Everyone else said #{r.others_avg}. {verdict(r.gap)}
                </p>
                <div className="meter" role="img" aria-label={`Blind spot ${r.blind_pct} percent`}>
                  <i className={r.blind_pct < 25 ? "good" : ""} style={{ width: `${Math.max(4, r.blind_pct)}%` }} />
                </div>
              </>
            ) : (
              <p className="muted">Didn't rank in time. No score.</p>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Final({ view, you }: { view: FrenemyView; you: string }) {
  const fin = view.final!;
  const mine = fin.per_player[you];
  return (
    <>
      <Panel themed className="halftone">
        <h2>Final reveal</h2>
        {mine && (
          <p>
            Your blind-spot score: <b>{mine.blind_spot}%</b> ({mine.avg_gap > 0.4 ? "a touch of optimism" : mine.avg_gap < -0.4 ? "secretly adored" : "pretty self-aware"})
          </p>
        )}
      </Panel>
      <div className="grid">
        {fin.awards.map((a) => (
          <Panel key={a.award} className="tilt-l">
            <span className="tag purple">Award</span>
            <h3>{a.award}</h3>
            <p>
              <b>{nameOf(view.players, a.player)}</b> ({fin.per_player[a.player]?.blind_spot}% blind spot)
            </p>
          </Panel>
        ))}
      </div>
    </>
  );
}
