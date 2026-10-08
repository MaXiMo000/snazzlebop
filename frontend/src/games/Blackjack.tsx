import { useEffect, useRef, useState } from "react";
import { Btn, Card, ShowHead, nameList, nameOf } from "../components/ui";
import { useCountUp, useOnChange, useReducedMotion, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { BlackjackHand, BlackjackView } from "../types";
import { Select } from "../components/Select";

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

const OUTCOME: Record<string, string> = { win: "You win", blackjack: "Blackjack!", push: "Push", lose: "You lose", bust: "Bust" };

/** Your payout this hand, big: the headline of the settle screen. */
function MyResult({ view, you }: { view: BlackjackView; you: string }) {
  const net = view.result!.net[you]!;
  const outcomes = view.result!.outcomes[you] ?? [];
  const head = outcomes.length === 1 ? (OUTCOME[outcomes[0]!] ?? outcomes[0]) : outcomes.map((o) => OUTCOME[o] ?? o).join(" · ");
  // Bring the payout to the top of the screen when it lands (the Ready bar sits at the bottom).
  const top = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    top.current?.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
  }, []);
  return (
    <>
    <div ref={top} className="bj-anchor" aria-hidden="true" />
    <Card tone="stage" className={`center bj-my-result ${net > 0 ? "up" : net < 0 ? "down" : ""}`} role="status">
      <p className="sign">This hand</p>
      <p className="bj-my-head">{head}</p>
      <p className="bj-my-net">
        {net > 0 ? "+" : net < 0 ? "−" : "±"}
        {Math.abs(net)}
      </p>
    </Card>
    </>
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
  useOnChange(view.chaos?.id ?? null, (_, now) => {
    if (now) {
      sfx.buzz();
      show.stinger("CHAOS CARD!", "bad");
    }
  });
  const solo = view.players.length === 1;
  const sign =
    view.phase === "final"
      ? view.mode === "tournament"
        ? "Tournament over"
        : "Final stacks"
      : `Hand ${view.round} of ${view.rounds} · ${
          { bet: "Place your bets", play: "Players' turn", settle: "Payout" }[view.phase as "bet" | "play" | "settle"] ?? ""
        }`;
  return (
    <div className="seg-blackjack stack">
      {show.node}
      <ShowHead sign={sign} title="Blackjack Showdown" remaining={view.remaining} receivedAt={receivedAt}>
        <div className="row">
          {view.mode === "tournament" && <span className="chip cherry">Tournament: shortest stack goes home</span>}
          {solo && <span className="chip plum">Solo: just you and the dealer</span>}
          {view.reshuffled && view.phase === "bet" && <span className="chip plum">Fresh shoe shuffled</span>}
          {view.chaos_coming && !view.chaos && <span className="chip">🃏 A Chaos card is somewhere in the shoe…</span>}
        </div>
      </ShowHead>
      {view.chaos && (
        <Card tone="stage" className="center chaos" role="status">
          <p className="sign">Chaos card</p>
          <h3 className="space-top">{view.chaos.label}</h3>
          <p>{view.chaos.text}</p>
        </Card>
      )}

      {/* the payout headline first: it's what everyone looks for */}
      {!tv && view.phase === "settle" && view.result?.net[you] !== undefined && <MyResult view={view} you={you} />}
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
        // Your hand sits right beside Hit and Stand; on phones this card stays pinned to the screen bottom.
        <Card tone="soft" className="center bj-move">
          <h3>Your move{(view.hands[you]?.length ?? 0) > 1 ? ` (hand ${(view.turn?.hand ?? 0) + 1})` : ""}</h3>
          {view.hands[you]?.[view.turn?.hand ?? 0] && <Hand hand={view.hands[you]![view.turn?.hand ?? 0]!} />}
          <p className="muted bj-dealer-shows">
            Dealer shows <b>{view.dealer.value}</b>
          </p>
          <div className="bj-actions">
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
          {/* your own seat first, so your cards are never far from the buttons */}
          {[...view.players].sort((a, b) => (tv ? 0 : Number(b.id === you) - Number(a.id === you))).map((p) => {
            const hands = view.hands[p.id] ?? [];
            const outcomes = view.result?.outcomes[p.id] ?? [];
            const turn = view.turn?.player === p.id;
            const gone = view.out.find((o) => o.player === p.id);
            const side = view.side[p.id];
            const sidePay = view.result?.side[p.id];
            return (
              <Card key={p.id} className={`seat ${turn ? "turn" : ""} ${gone ? "out" : ""}`} aria-current={turn ? "true" : undefined}>
                <div className="row between">
                  <h3>
                    {p.name}
                    {p.id === you ? " (you)" : ""}
                  </h3>
                  <Chips n={view.chips[p.id] ?? 0} />
                </div>
                {gone && (
                  <p>
                    <span className="chip cherry">
                      Out after hand {gone.hand} ({gone.why})
                    </span>
                  </p>
                )}
                {side && (
                  <p className="muted">
                    Side bet: {side.amount} on {nameOf(view.players, side.on)}
                    {sidePay ? (sidePay.pay > side.amount ? " · paid!" : sidePay.pay === side.amount ? " · refunded" : " · lost") : ""}
                  </p>
                )}
                {gone ? null : hands.length === 0 ? (
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
                    <span className={`chip bj-result ${view.result.net[p.id]! > 0 ? "teal" : view.result.net[p.id]! < 0 ? "cherry" : ""}`}>
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
  const [sideOn, setSideOn] = useState("");
  const [sideAmount, setSideAmount] = useState(view.side_sizes[0] ?? 0);
  if (!view.active.includes(you)) {
    return (
      <Card tone="soft" className="center">
        <p>You’re out of this tournament. Cheer the survivors on!</p>
      </Card>
    );
  }
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
      {view.side_sizes.length > 0 && (
        <div className="ask-form space-top">
          <div>
            <label className="field" htmlFor="side-on">
              Step 1 (optional): back a friend’s hand too
            </label>
            <Select id="side-on" value={sideOn} onChange={(e) => setSideOn(e.target.value)}>
              <option value="">No side bet</option>
              {view.players
                .filter((p) => p.id !== you && view.active.includes(p.id) && (view.chips[p.id] ?? 0) >= (view.bet_sizes[0] ?? 50))
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </Select>
          </div>
          {sideOn && (
            <div role="group" aria-label="Side bet amount" className="row">
              {view.side_sizes.map((n) => (
                <Btn key={n} size="small" variant="ghost" aria-pressed={sideAmount === n} onClick={() => setSideAmount(n)}>
                  Side {n}
                </Btn>
              ))}
            </div>
          )}
        </div>
      )}
      {sideOn && (
        <p className="muted">Pays 1:1 if {nameOf(view.players, sideOn)}’s hand makes money, refunded on a push.</p>
      )}
      {view.side_sizes.length > 0 && <p className="field space-top">Step 2: tap your bet to lock it in</p>}
      <div className="row center" role="group" aria-label="Bet size">
        {view.bet_sizes.map((b) => (
          <Btn
            key={b}
            variant="gold"
            size="big"
            className="bet-chip"
            disabled={b + (sideOn ? sideAmount : 0) > chips}
            onClick={() => {
              sfx.pop();
              send({ t: "act", a: "bet", amount: b, ...(sideOn ? { side_on: sideOn, side_amount: sideAmount } : {}) });
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
  const ranked = (view.standings ?? []).length
    ? view.standings!.map((id) => view.players.find((p) => p.id === id)!).filter(Boolean)
    : [...view.players].sort((a, b) => (view.chips[b.id] ?? 0) - (view.chips[a.id] ?? 0));
  if (view.mode === "tournament") {
    const champ = ranked[0];
    return (
      <>
        <Card tone="stage" className="center felt">
          <p className="sign">Last one standing</p>
          {champ && (
            <p className="lead space-top">
              <span className="burst">
                <b>{champ.name}</b>
              </span>
              {champ.id === you ? " (you!)" : ""} wins the tournament with {view.chips[champ.id]} chips.
            </p>
          )}
        </Card>
        <Card>
          <h3>Standings</h3>
          <ol className="evidence">
            {ranked.map((p) => {
              const gone = view.out.find((o) => o.player === p.id);
              return (
                <li key={p.id}>
                  <b>{p.name}</b>: {gone ? `out after hand ${gone.hand} (${gone.why})` : `survived with ${view.chips[p.id]} chips`}
                </li>
              );
            })}
          </ol>
        </Card>
      </>
    );
  }
  const top = ranked[0];
  const leaders = top ? ranked.filter((p) => view.chips[p.id] === view.chips[top.id]) : []; // ties share the sign
  return (
    <>
      <Card tone="stage" className="center felt">
        <p className="sign">Biggest stack</p>
        {top && (
          <p className="lead space-top">
            <span className="burst">
              <b>{nameList(leaders.map((p) => nameOf(view.players, p.id)))}</b>
            </span>
            {leaders.some((p) => p.id === you) ? " (you!)" : ""} cashed out with {view.chips[top.id]} chips
            {leaders.length > 1 ? " each" : ""}.
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
