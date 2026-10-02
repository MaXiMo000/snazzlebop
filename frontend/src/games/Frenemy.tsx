import { useMemo, useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { FrenemyView } from "../types";

interface Props {
  view: FrenemyView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
}

export function Frenemy({ view, you, receivedAt, send }: Props) {
  const show = useShow();
  useOnChange(view.phase, (_, phase) => {
    if (phase === "reveal") {
      sfx.ding();
      show.stinger("THE RESULTS!");
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("AWARDS TIME!");
      show.celebrate();
    }
  });
  const sign =
    view.phase === "final" ? "Final reveal" : `Round ${view.round} of ${view.rounds} · ${view.phase === "rank" ? "Rank 'em" : "Reveal"}`;
  return (
    <div className="seg-frenemy stack">
      {show.node}
      <ShowHead sign={sign} title="Frenemy Radar" remaining={view.remaining} receivedAt={receivedAt} />
      <div key={`${view.phase}-${view.round}`} className="stack enter">
        {view.phase === "rank" && <Rank view={view} you={you} send={send} />}
        {view.phase === "reveal" && view.result && <Reveal view={view} you={you} />}
        {view.phase === "final" && view.final && <Final view={view} you={you} />}
      </div>
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
  const waitingOn = view.players.filter((p) => !view.submitted.includes(p.id));

  if (view.you_submitted) {
    return (
      <Card tone="soft" className="center">
        <h3>Locked in! 🔒</h3>
        <p aria-live="polite">
          Waiting for {waitingOn.length} more: {waitingOn.map((p) => p.name).join(", ")}
        </p>
      </Card>
    );
  }
  return (
    <>
      <Card tone="stage">
        <p className="sign">Tonight’s question</p>
        <h3 className="prompt space-top">{view.prompt}</h3>
      </Card>
      <Card>
        <p>
          Rank <b>everyone</b>, yourself included. <b>#1</b> = most like this.
        </p>
        <ol className="rank-list" aria-label="Your ranking">
          {order.map((id, i) => {
            const name = nameOf(view.players, id);
            return (
              <li key={id} className={`rank-item ${id === you ? "me" : ""}`}>
                <span className="num" aria-hidden="true">
                  {i + 1}
                </span>
                <span className="name">
                  {name}
                  {id === you ? " (you)" : ""}
                </span>
                <span className="arrows">
                  <button className="arrow" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move ${name} up`}>
                    ▲
                  </button>
                  <button className="arrow" disabled={i === order.length - 1} onClick={() => move(i, 1)} aria-label={`Move ${name} down`}>
                    ▼
                  </button>
                </span>
              </li>
            );
          })}
        </ol>
        <div className="space-top">
          <Btn
            variant="accent"
            size="big"
            block
            onClick={() => {
              sfx.pop();
              send({ t: "act", a: "rank", order });
            }}
          >
            Lock it in!
          </Btn>
        </div>
      </Card>
    </>
  );
}

function verdict(gap: number): string {
  if (Math.abs(gap) < 0.5) return "Spot on 🎯";
  return gap > 0 ? "Rates themselves higher than the room does 😏" : "The room rates them higher than they do 🥹";
}

function Gauge({ pct }: { pct: number }) {
  const w = Math.max(4, Math.min(100, pct));
  return (
    <svg className="gauge" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
      <rect className="track" x="0" y="0" width="100" height="10" rx="5" vectorEffect="non-scaling-stroke" />
      <rect className={`fill ${pct < 25 ? "good" : ""}`} x="0" y="0" width={w} height="10" rx="5" />
    </svg>
  );
}

function Reveal({ view, you }: { view: FrenemyView; you: string }) {
  const rows = useMemo(
    () =>
      view.players
        .map((p) => ({ p, r: view.result![p.id]! }))
        .sort((a, b) => b.r.played - a.r.played || b.r.blind_pct - a.r.blind_pct),
    [view],
  );
  return (
    <>
      <Card tone="stage">
        <p className="sign">The room has spoken</p>
        <h3 className="prompt space-top">{view.prompt}</h3>
      </Card>
      <div className="stack-sm">
        {rows.map(({ p, r }, i) => (
          <div key={p.id} className={`verdict ${i === 0 && r.played ? "top" : ""}`}>
            <div className="row between">
              <b>
                {p.name}
                {p.id === you ? " (you)" : ""}
              </b>
              {r.played ? <span className="chip cherry">Blind spot {r.blind_pct}%</span> : null}
            </div>
            {r.played ? (
              <>
                <p className="muted">
                  Ranked themselves #{r.self_rank}. Everyone else said #{r.others_avg}. {verdict(r.gap)}
                </p>
                <Gauge pct={r.blind_pct} />
              </>
            ) : (
              <p className="muted">Didn’t rank in time. No score.</p>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

const CUPS: Record<string, string> = {
  "Delusional Optimist": "🌈",
  "Secretly Loved": "💖",
  "Unknown to Self": "🕵️",
  "Crystal Clear": "🔮",
};

function Final({ view, you }: { view: FrenemyView; you: string }) {
  const fin = view.final!;
  const mine = fin.per_player[you];
  return (
    <>
      <Card tone="stage" className="center">
        <p className="sign">Final reveal</p>
        {mine ? (
          <>
            <p className="space-top">Your blind-spot score</p>
            <p className="burst">
              <span className="price-tag">{mine.blind_spot}%</span>
            </p>
            <p>{mine.avg_gap > 0.4 ? "A touch of optimism." : mine.avg_gap < -0.4 ? "Secretly adored." : "Pretty self-aware."}</p>
          </>
        ) : (
          <p className="space-top">You sat this one out, so no blind-spot score.</p>
        )}
      </Card>
      <div className="grid">
        {fin.awards.map((a) => (
          <Card key={a.award} className="trophy">
            <div className="cup" aria-hidden="true">
              {CUPS[a.award] ?? "🏆"}
            </div>
            <h3>{a.award}</h3>
            <p>
              <b>{nameOf(view.players, a.player)}</b>
              {a.player === you ? " (you!)" : ""} · {fin.per_player[a.player]?.blind_spot}% blind spot
            </p>
          </Card>
        ))}
      </div>
    </>
  );
}
