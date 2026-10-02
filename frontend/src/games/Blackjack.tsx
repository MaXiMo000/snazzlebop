import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useCountUp, useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { BlackjackHand, BlackjackView } from "../types";

interface Props {
  view: BlackjackView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const SUIT: Record<string, { sym: string; name: string; red: boolean }> = {
  S: { sym: "♠", name: "spades", red: false },
  H: { sym: "♥", name: "hearts", red: true },
  D: { sym: "♦", name: "diamonds", red: true },
  C: { sym: "♣", name: "clubs", red: false },
};
const RANK_NAME: Record<string, string> = { A: "Ace", J: "Jack", Q: "Queen", K: "King" };

function PlayingCard({ code }: { code: string }) {
  const rank = code.slice(0, -1);
  const suit = SUIT[code.slice(-1)]!;
  return (
    <span className={`pcard ${suit.red ? "red" : ""}`} role="img" aria-label={`${RANK_NAME[rank] ?? rank} of ${suit.name}`}>
      <span aria-hidden="true">{rank}</span>
      <span aria-hidden="true">{suit.sym}</span>
    </span>
  );
}

function Hand({ hand, label }: { hand: BlackjackHand; label?: string }) {
  return (
    <div className="bj-hand">
      <div className="cards">
        {hand.cards.map((c, i) => (
          <PlayingCard key={`${c}-${i}`} code={c} />
        ))}
      </div>
      <p className="muted">
        {label ? `${label} · ` : ""}
        <b>{hand.value > 21 ? `${hand.value} bust` : hand.soft && hand.value < 21 ? `soft ${hand.value}` : hand.value}</b> · bet{" "}
        {hand.bet}
      </p>
    </div>
  );
}

function Chips({ n }: { n: number }) {
  const shown = useCountUp(n);
  return <span className="chip plum">🪙 {shown}</span>;
}

export function Blackjack({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const myTurn = view.turn?.player === you;
  useOnChange(myTurn, (_, now) => {
    if (now && !tv) sfx.ding();
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "settle" && view.result) {
      const r = view.result;
      const mine = r.net[you];
      if (r.dealer_blackjack) {
        sfx.buzz();
        show.stinger("DEALER BLACKJACK", "bad");
      } else if (!tv && (r.outcomes[you] ?? []).includes("blackjack")) {
        sfx.fanfare();
        show.stinger("BLACKJACK!");
        show.celebrate();
      } else if (r.dealer_value > 21) {
        sfx.fanfare();
        show.stinger("DEALER BUSTS!");
      } else if (!tv && mine !== undefined && mine > 0) {
        sfx.ding();
        show.stinger("WINNER!");
      } else if (!tv && mine !== undefined && mine < 0) {
        sfx.buzz();
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("CASH OUT!");
      show.celebrate();
    }
  });
  const sign =
    view.phase === "final"
      ? "Final stacks"
      : `Hand ${view.round} of ${view.rounds} · ${
          { bet: "Place your bets", play: "Players' turn", settle: "Payout" }[view.phase as "bet" | "play" | "settle"] ?? ""
        }`;
  return (
    <div className="seg-blackjack stack">
      {show.node}
      <ShowHead sign={sign} title="Blackjack Showdown" remaining={view.remaining} receivedAt={receivedAt}>
        {view.reshuffled && view.phase === "bet" && <span className="chip plum">Fresh shoe shuffled</span>}
      </ShowHead>

      {view.phase !== "final" && (
        <Card tone="stage" className="felt">
          <p className="sign">Dealer</p>
          {view.dealer.cards.length === 0 && (
            <p className="lead space-top">Cards come out when everyone’s bet is in. Minimum 50.</p>
          )}
          <div className="cards space-top">
            {view.dealer.cards.map((c, i) => (
              <PlayingCard key={`${c}-${i}`} code={c} />
            ))}
            {view.dealer.hidden && (
              <span className="pcard back" role="img" aria-label="Face-down card">
                <span aria-hidden="true">★</span>
              </span>
            )}
          </div>
          {view.dealer.cards.length > 0 && (
            <p className="space-top">
              {view.dealer.hidden ? "Showing" : "Total"} <b>{view.dealer.value}</b>
              {view.result?.dealer_blackjack ? " · Blackjack!" : view.dealer.value > 21 ? " · Bust!" : ""}
            </p>
          )}
        </Card>
      )}

      {!tv && view.phase === "bet" && <BetPanel view={view} you={you} send={send} />}
      {!tv && view.phase === "play" && myTurn && (
        <Card tone="soft" className="center">
          <h3>Your move{(view.hands[you]?.length ?? 0) > 1 ? ` (hand ${(view.turn?.hand ?? 0) + 1})` : ""}</h3>
          <div className="row center">
            {view.you.actions.map((a) => (
              <Btn
                key={a}
                variant={a === "hit" ? "accent" : a === "stand" ? "go" : "gold"}
                size="big"
                onClick={() => {
                  sfx.pop();
                  send({ t: "act", a });
                }}
              >
                {{ hit: "Hit", stand: "Stand", double: "Double", split: "Split" }[a]}
              </Btn>
            ))}
          </div>
        </Card>
      )}

      {view.phase === "final" ? (
        <Final view={view} you={you} />
      ) : (
        <div className="grid">
          {view.players.map((p) => {
            const hands = view.hands[p.id] ?? [];
            const outcomes = view.result?.outcomes[p.id] ?? [];
            const turn = view.turn?.player === p.id;
            return (
              <Card key={p.id} className={`seat ${turn ? "turn" : ""}`} aria-current={turn ? "true" : undefined}>
                <div className="row between">
                  <h3>
                    {p.name}
                    {p.id === you ? " (you)" : ""}
                  </h3>
                  <Chips n={view.chips[p.id] ?? 0} />
                </div>
                {hands.length === 0 ? (
                  <p className="muted">
                    {view.phase === "bet"
                      ? view.bets[p.id]
                        ? `Bet ${view.bets[p.id]} placed`
                        : (view.chips[p.id] ?? 0) < (view.bet_sizes[0] ?? 50)
                          ? "Out of chips: watching"
                          : "Choosing a bet…"
                      : "Sitting this hand out"}
                  </p>
                ) : (
                  hands.map((h, i) => (
                    <Hand key={i} hand={h} label={hands.length > 1 ? `Hand ${i + 1}` : undefined} />
                  ))
                )}
                {view.result && view.result.net[p.id] !== undefined && (
                  <p>
                    <span className={`chip ${view.result.net[p.id]! > 0 ? "teal" : view.result.net[p.id]! < 0 ? "cherry" : ""}`}>
                      {outcomes.join(" / ")} · {view.result.net[p.id]! > 0 ? "+" : ""}
                      {view.result.net[p.id]}
                    </span>
                  </p>
                )}
                {turn && <p className="muted">Deciding…</p>}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function BetPanel({ view, you, send }: { view: BlackjackView; you: string; send: Props["send"] }) {
  const chips = view.chips[you] ?? 0;
  if (view.you.bet) {
    return (
      <Card tone="soft" className="center">
        <h3>Bet placed: {view.you.bet}</h3>
        <p className="muted">Waiting for the table…</p>
      </Card>
    );
  }
  if (chips < (view.bet_sizes[0] ?? 50)) {
    return (
      <Card tone="soft" className="center">
        <p>You’re out of chips. Cheer the table on!</p>
      </Card>
    );
  }
  return (
    <Card tone="soft" className="center">
      <h3>Place your bet</h3>
      <div className="row center" role="group" aria-label="Bet size">
        {view.bet_sizes.map((b) => (
          <Btn
            key={b}
            variant="gold"
            size="big"
            className="bet-chip"
            disabled={b > chips}
            onClick={() => {
              sfx.pop();
              send({ t: "act", a: "bet", amount: b });
            }}
          >
            {b}
          </Btn>
        ))}
      </div>
    </Card>
  );
}

function Final({ view, you }: { view: BlackjackView; you: string }) {
  const ranked = [...view.players].sort((a, b) => (view.chips[b.id] ?? 0) - (view.chips[a.id] ?? 0));
  const top = ranked[0];
  return (
    <>
      <Card tone="stage" className="center felt">
        <p className="sign">Biggest stack</p>
        {top && (
          <p className="lead space-top">
            <span className="burst">
              <b>{nameOf(view.players, top.id)}</b>
            </span>
            {top.id === you ? " (you!)" : ""} cashed out with {view.chips[top.id]} chips.
          </p>
        )}
      </Card>
      <Card>
        <h3>Cash-out</h3>
        <ol className="evidence">
          {ranked.map((p) => {
            const net = (view.chips[p.id] ?? 0) - 1000;
            return (
              <li key={p.id}>
                <b>{p.name}</b>: {view.chips[p.id]} chips ({net >= 0 ? "+" : ""}
                {net})
              </li>
            );
          })}
        </ol>
      </Card>
    </>
  );
}
