import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { sfx } from "../lib/sfx";
import type { BoxesView } from "../types";

interface Props {
  view: BoxesView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen */
  tv?: boolean;
}

const RAISES = [10, 50, 100];

export function Boxes({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const label = (i: number) => `Box ${view.labels[i]}`;
  const sold = view.boxes[view.current];
  useOnChange(view.phase, (_, phase) => {
    if (phase === "sold" && sold) {
      if (sold.winner === null) {
        sfx.ding();
        show.stinger("NO SALE");
      } else if (sold.value < 0) {
        sfx.buzz();
        show.stinger(`${sold.emoji} BOOM!`, !tv && sold.winner === you ? "bad" : "good");
      } else {
        sfx.fanfare();
        show.stinger(`${sold.emoji} SOLD!`);
      }
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("AUCTION CLOSED!");
      show.celebrate();
    }
  });
  const high = view.high ?? null;
  const coins = view.coins[you] ?? 0;
  const floor = high ? high.amount + 10 : 10;
  const sign =
    view.phase === "final"
      ? "Auction closed"
      : view.phase === "peek"
        ? "Sneak a peek"
        : `${label(view.current)} · ${view.phase === "auction" ? "Bidding open" : "Sold"}`;
  return (
    <div className="seg-boxes stack">
      {show.node}
      <ShowHead sign={sign} title="Mystery Box Auction" remaining={view.remaining} receivedAt={receivedAt}>
        <span className="chip plum">2 bombs · 1 dud · 3 prizes</span>
      </ShowHead>

      {!tv && view.you.peek && view.phase !== "final" && (
        <Card tone="soft" className="center">
          <p className="sign">Only you know</p>
          <p className="lead space-top">
            {label(view.you.peek.box)}: <span aria-hidden="true">{view.you.peek.emoji}</span> {view.you.peek.name}{" "}
            <b>({view.you.peek.value >= 0 ? "+" : ""}
            {view.you.peek.value})</b>
          </p>
          {view.you.extra && (
            <p>
              Power peek: {label(view.you.extra.box)} holds <span aria-hidden="true">{view.you.extra.emoji}</span> {view.you.extra.name} (
              {view.you.extra.value >= 0 ? "+" : ""}
              {view.you.extra.value})
            </p>
          )}
        </Card>
      )}

      <ul className="box-row" aria-label="The boxes">
        {view.labels.map((l, i) => {
          const s = view.boxes[i];
          const now = i === view.current && view.phase !== "final";
          return (
            <li key={l} className={`box ${now ? "now" : ""} ${s ? (s.value < 0 ? "bomb" : "open") : ""}`}>
              <span className="box-label">{l}</span>
              {s ? (
                <>
                  <span className="box-emoji" role="img" aria-label={s.name}>
                    {s.emoji}
                  </span>
                  <span className="box-value">
                    {s.value >= 0 ? "+" : ""}
                    {s.value}
                  </span>
                  <span className="muted">{s.winner ? `${nameOf(view.players, s.winner)} · ${s.price}` : "unsold"}</span>
                </>
              ) : (
                <span className="box-emoji" role="img" aria-label="sealed">
                  📦
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {view.phase === "auction" && (
        <Card tone="stage" className="center">
          <p className="sign">{label(view.current)}</p>
          <p className="lead space-top" aria-live="polite">
            {high ? (
              <>
                Top bid <b>{high.amount}</b> by <b>{nameOf(view.players, high.player)}</b>
                {high.player === you ? " (you)" : ""}
              </>
            ) : (
              "No bids yet"
            )}
          </p>
          {!tv && (
            <div className="row center space-top" role="group" aria-label="Bid">
              {RAISES.map((r) => {
                const amount = high ? high.amount + r : r;
                return (
                  <Btn
                    key={r}
                    variant={r === 10 ? "accent" : "ghost"}
                    disabled={amount > coins || high?.player === you || amount < floor}
                    onClick={() => {
                      sfx.pop();
                      send({ t: "act", a: "bid", amount });
                    }}
                  >
                    Bid {amount}
                  </Btn>
                );
              })}
            </div>
          )}
          {!tv && <p className="space-top">You have {coins} coins.</p>}
        </Card>
      )}

      {!tv && view.phase === "auction" && view.claims && !view.claims[you] && (
        <Card tone="soft">
          <p className="muted">Make one claim about this box (everyone hears it, true or not):</p>
          <div className="row" role="group" aria-label="Make a claim">
            {view.claims_list.map((c, i) => (
              <Btn key={c} size="small" variant="ghost" onClick={() => send({ t: "act", a: "say", line: i })}>
                {c}
              </Btn>
            ))}
          </div>
        </Card>
      )}

      {(view.phase === "auction" || view.phase === "sold") && view.claims && Object.keys(view.claims).length > 0 && (
        <Card>
          <h3>Claims</h3>
          <ul className="evidence">
            {Object.entries(view.claims).map(([pid, c]) => (
              <li key={pid}>
                <b>{nameOf(view.players, pid)}</b>: “{c}”
              </li>
            ))}
          </ul>
        </Card>
      )}

      {view.phase === "sold" && sold && (
        <Card tone="stage" className="center">
          <p className="sign">{label(sold.box)} held</p>
          <p className="lead space-top">
            <span aria-hidden="true">{sold.emoji}</span> {sold.name} ({sold.value >= 0 ? "+" : ""}
            {sold.value})
          </p>
          <p>
            {sold.winner
              ? `${nameOf(view.players, sold.winner)} paid ${sold.price}: ${sold.value - sold.price >= 0 ? "+" : ""}${sold.value - sold.price}`
              : "Nobody bid."}
          </p>
          {sold.peekers.length > 0 && <p className="muted">Peeked by {sold.peekers.map((p) => nameOf(view.players, p)).join(", ")}</p>}
        </Card>
      )}

      <Card>
        <h3>Purses</h3>
        <ul className="evidence">
          {view.players.map((p) => (
            <li key={p.id}>
              <b>{p.name}</b>
              {p.id === you ? " (you)" : ""}: {view.coins[p.id]} coins
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
