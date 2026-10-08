import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { TdKind, TruthDareView } from "../types";

interface Props {
  view: TruthDareView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const KIND: Record<TdKind, { label: string; icon: string; pays: number }> = {
  truth: { label: "Truth", icon: "💬", pays: 100 },
  dare: { label: "Dare", icon: "🔥", pays: 200 },
};

export function TruthDare({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const target = view.target;
  const mine = !tv && target === you;
  const who = target ? nameOf(view.players, target) : "";

  useOnChange(view.phase, (_, phase) => {
    if (phase === "spin") sfx.spin();
    else if (phase === "choose") sfx.ding();
    else if (phase === "perform" && view.choice) {
      sfx.pop();
      show.stinger(view.choice === "dare" ? "🔥 DARE!" : "💬 TRUTH!");
    } else if (phase === "result" && view.result) {
      const r = view.result;
      if (r.chicken) {
        sfx.buzz();
        show.stinger("🐔 BAWK BAWK!", "bad");
      } else if (r.passed) {
        sfx.fanfare();
        show.stinger(r.bonus ? `🔥 DAREDEVIL +${r.points + r.bonus}` : `+${r.points}!`);
        if (r.bonus || (!tv && r.player === you)) show.celebrate();
      } else {
        sfx.buzz();
        show.stinger("👎 WEAK!", "bad");
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });

  const sign =
    view.phase === "final"
      ? "Final scores"
      : `Turn ${view.round} of ${view.rounds} · ${
          view.phase === "spin"
            ? "Spin the bottle"
            : view.phase === "choose"
              ? "Truth or dare?"
              : view.phase === "perform"
                ? view.choice === "dare"
                  ? "Do the dare"
                  : "Tell the truth"
                : view.phase === "vote"
                  ? "The room decides"
                  : "The verdict"
        }`;

  return (
    <div className={`seg-truthdare stack ${view.choice ? `tod-${view.choice}` : ""} ${tv ? "tv-cols" : ""}`}>
      {show.node}
      <ShowHead sign={sign} title="Truth or Dare" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">{view.heat === "cheeky" ? "😈 Cheeky" : "😇 Mild"} · dares pay double</span>
      </ShowHead>

      {view.phase !== "final" && (
        <Card tone="stage" className="center tv-main">
          <Bottle view={view} you={you} />
          <p className="lead space-top" aria-live="polite">
            {view.phase === "spin" ? (
              "Round and round it goes…"
            ) : mine ? (
              view.phase === "choose" ? (
                "🎯 It’s you! Truth or dare?"
              ) : (
                "🎯 Your turn"
              )
            ) : (
              <>
                <b>{who}</b>
                {view.phase === "choose"
                  ? " is choosing…"
                  : view.phase === "perform"
                    ? view.choice === "dare"
                      ? " takes the dare"
                      : " tells the truth"
                    : view.phase === "vote"
                      ? " faces the jury"
                      : ""}
              </>
            )}
          </p>
        </Card>
      )}

      {view.phase === "choose" &&
        (mine ? (
          <div className="tod-pick" role="group" aria-label="Truth or dare">
            {(["truth", "dare"] as TdKind[]).map((k) => (
              <button
                key={k}
                type="button"
                className={`tod-door ${k}`}
                onClick={() => {
                  sfx.pop();
                  send({ t: "act", a: "choose", choice: k });
                }}
              >
                <span className="tod-door-icon" aria-hidden="true">
                  {KIND[k].icon}
                </span>
                <span className="tod-door-label">{KIND[k].label}</span>
                <span className="tod-door-pays">pays {KIND[k].pays}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="center muted">Truth pays 100. Dare pays 200. No pressure, {who}.</p>
        ))}

      {(view.phase === "perform" || view.phase === "vote" || view.phase === "result") && view.choice && view.prompt && (
        <PromptCard key={view.prompt} kind={view.choice} prompt={view.prompt} who={who} />
      )}

      {view.phase === "perform" && mine && (
        <Card tone="soft" className="center">
          <Btn
            variant="go"
            size="big"
            block
            onClick={() => {
              sfx.pop();
              send({ t: "act", a: "done" });
            }}
          >
            Done! Judge me ▶
          </Btn>
          <div className="row center space-top">
            <Btn variant="ghost" disabled={(view.rerolls[you] ?? 0) <= 0} onClick={() => send({ t: "act", a: "reroll" })}>
              🔄 New card{(view.rerolls[you] ?? 0) > 0 ? " (1 left)" : " (used)"}
            </Btn>
            <Btn
              variant="danger"
              disabled={(view.chickens[you] ?? 0) <= 0}
              onClick={() => {
                if (window.confirm("Chicken out? You get no points for this turn.")) send({ t: "act", a: "chicken" });
              }}
            >
              🐔 Chicken out{(view.chickens[you] ?? 0) > 0 ? "" : " (used)"}
            </Btn>
          </div>
        </Card>
      )}
      {view.phase === "perform" && !mine && (
        <p className="center lead">
          Watch {who} {view.choice === "dare" ? "do the dare" : "answer"}. Voting opens when they tap Done.
        </p>
      )}

      {view.phase === "vote" && (
        <Card tone="soft" className="center">
          {!tv && !mine ? (
            view.you_voted === null ? (
              <>
                <h3>Did {who} nail it?</h3>
                <div className="tod-votes" role="group" aria-label={`Judge ${who}`}>
                  <Btn
                    variant="go"
                    size="big"
                    onClick={() => {
                      sfx.pop();
                      send({ t: "act", a: "vote", like: true });
                    }}
                  >
                    <span aria-hidden="true">👍</span>
                    <span>Nailed it</span>
                  </Btn>
                  <Btn
                    variant="danger"
                    size="big"
                    onClick={() => {
                      sfx.pop();
                      send({ t: "act", a: "vote", like: false });
                    }}
                  >
                    <span aria-hidden="true">👎</span>
                    <span>Weak</span>
                  </Btn>
                </div>
              </>
            ) : (
              <p className="lead">You said {view.you_voted ? "👍 nailed it" : "👎 weak"}. Waiting for the others…</p>
            )
          ) : (
            <p className="lead">{mine ? "The room is judging you…" : `The room is judging ${who}…`}</p>
          )}
          <p className="muted space-top" aria-live="polite">
            {view.voted} of {view.voters} voted
          </p>
        </Card>
      )}

      {view.phase === "result" && view.result && <Verdict view={view} you={you} tv={tv} />}

      {/* TV: the room scoreboard beside the game already shows the points until the final */}
      {(!tv || view.phase === "final") && <Standings view={view} you={you} />}
      {view.phase === "final" && view.history && <History view={view} latest={tv ? 4 : undefined} />}
    </div>
  );
}

/** Everyone seated round the bottle; it spins and points at whoever's up. */
function Bottle({ view, you }: { view: TruthDareView; you: string }) {
  const at = view.target ? view.players.findIndex((p) => p.id === view.target) : 0;
  return (
    <div className="tod-ring" data-n={view.players.length} data-at={at} aria-hidden="true">
      <ol className="tod-seats">
        {view.players.map((p) => (
          <li key={p.id} className={`tod-seat ${p.id === view.target && view.phase !== "spin" ? "on" : ""} ${p.id === you ? "you" : ""}`}>
            <span>{p.name}</span>
          </li>
        ))}
      </ol>
      {/* keyed by turn: every turn restarts the spin from the top */}
      <svg key={view.round} className={`tod-bottle ${view.phase === "spin" ? "spinning" : ""}`} viewBox="0 0 40 120" focusable="false">
        <rect x="16" y="4" width="8" height="10" rx="2" className="tod-cork" />
        <path d="M15 14h10v20c0 6 9 12 9 22v54a6 6 0 0 1-6 6H12a6 6 0 0 1-6-6V56c0-10 9-16 9-22z" className="tod-glass" />
        <rect x="9" y="66" width="22" height="26" rx="3" className="tod-label" />
      </svg>
    </div>
  );
}

function PromptCard({ kind, prompt, who }: { kind: TdKind; prompt: string; who: string }) {
  return (
    <div className={`tod-card ${kind}`}>
      <p className="sign">
        <span aria-hidden="true">{KIND[kind].icon} </span>
        {KIND[kind].label} for {who}
      </p>
      <p className="tod-prompt">{prompt}</p>
    </div>
  );
}

function Verdict({ view, you, tv }: { view: TruthDareView; you: string; tv: boolean }) {
  const r = view.result!;
  const who = nameOf(view.players, r.player);
  const me = !tv && r.player === you;
  return (
    <Card tone="stage" className="center">
      <p className="sign">{r.chicken ? "Chickened out" : r.passed ? "The room approves" : "The room is not impressed"}</p>
      <p className="tod-verdict space-top" aria-hidden="true">
        {r.chicken ? "🐔" : r.passed ? "🎉" : "🙈"}
      </p>
      <p className="lead">
        {r.chicken ? (
          <>
            <b>{who}</b>
            {me ? " (you)" : ""} chickened out. No points this turn.
          </>
        ) : (
          <>
            <b>{who}</b>
            {me ? " (you)" : ""} got {r.yes} 👍 and {r.no} 👎.
          </>
        )}
      </p>
      {!r.chicken && (
        <p className="space-top">
          <span className="price-tag">{r.passed ? `+${r.points + r.bonus}` : "0"}</span>
        </p>
      )}
      {r.bonus > 0 && <p className="chip space-top">🔥 Daredevil streak! +{r.bonus} bonus</p>}
      {view.up_next && <p className="muted space-top">Up next: the bottle spins again…</p>}
    </Card>
  );
}

function Standings({ view, you }: { view: TruthDareView; you: string }) {
  const final = view.phase === "final";
  const rows = [...view.players].sort((a, b) => view.stats[b.id]!.points - view.stats[a.id]!.points);
  const top = rows[0] ? view.stats[rows[0].id]!.points : 0;
  return (
    <Card>
      <h3>{final ? "Who did what" : "Bravery board"}</h3>
      <ul className="score-rows">
        {rows.map((p) => {
          const s = view.stats[p.id]!;
          return (
            <li key={p.id} className={p.id === view.target && !final ? "on" : ""}>
              <b>
                {final && top > 0 && s.points === top ? "👑 " : ""}
                {p.name}
                {p.id === you ? " (you)" : ""}
              </b>
              <span className="score-tally" aria-hidden="true">
                {s.truth > 0 && <span>💬 {s.truth}</span>}
                {s.dare > 0 && <span>🔥 {s.dare}</span>}
                {s.chicken > 0 && <span>🐔 {s.chicken}</span>}
                {!final && s.streak >= 2 && <span>⚡{s.streak}</span>}
                <span className="score-pts">{s.points}</span>
              </span>
              <span className="sr-only">
                {s.points} points: {s.truth} truths, {s.dare} dares{s.chicken ? `, chickened out ${s.chicken}` : ""}
                {!final && s.streak >= 2 ? `, ${s.streak} dares in a row` : ""}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/** Every turn, in order. The TV shows only the latest few, so the list never runs off the screen. */
function History({ view, latest }: { view: TruthDareView; latest?: number }) {
  const all = view.history!;
  const shown = latest ? all.slice(-latest) : all;
  const hidden = all.length - shown.length;
  return (
    <Card className="tv-main">
      <h3>{hidden ? "The latest turns" : "Every turn"}</h3>
      {hidden > 0 && <p className="muted">…and {hidden} earlier {hidden === 1 ? "turn" : "turns"} before these.</p>}
      <ol className="evidence" start={hidden + 1}>
        {shown.map((h, i) => (
          <li key={i}>
            <b>{nameOf(view.players, h.player)}</b> · {KIND[h.kind].icon} {h.prompt}{" "}
            <span className="muted">
              {h.chicken ? "🐔 chickened" : h.passed ? `+${h.points + h.bonus}` : "👎 weak"}
            </span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
