import { Btn, Card, ShowHead, money, nameOf } from "./ui";
import { sfx } from "../lib/sfx";
import type { MarketState, RoomState } from "../types";

type Send = (msg: Record<string, unknown>) => void;

const MAX_TRADE = 10;
const MAX_HOLDING = 20;

function Move({ pct }: { pct: number | undefined }) {
  if (pct === undefined) return null;
  const up = pct > 0;
  const label = `${up ? "+" : ""}${Math.round(pct * 100)}%`;
  return <span className={`chip ${up ? "teal" : pct < 0 ? "cherry" : ""}`}>{up ? "▲" : pct < 0 ? "▼" : "•"} {label}</span>;
}

/** The trading floor, shown between show games when the host turned the exchange on. */
export function MarketFloor({ state, receivedAt, send, tv = false }: { state: RoomState; receivedAt: number; send: Send; tv?: boolean }) {
  const m = state.market!;
  const isHost = state.room.host === state.you;
  const me = m.you;
  const players = state.players.map((p) => ({ id: p.id, name: p.name }));
  return (
    <div className="seg-market stack enter">
      <ShowHead sign={`Up next: ${m.next}`} title="Friend Stock Exchange" remaining={m.closes_in} receivedAt={receivedAt}>
        <span className="chip plum">Buy your friends before they win · prices move with every game</span>
      </ShowHead>
      {me?.tip && !tv && (
        <Card tone="soft" className="center">
          <p className="sign">🤫 Insider tip</p>
          <p className="lead space-top">{me.tip}</p>
          <p className="muted">Only you got this one.</p>
        </Card>
      )}
      {me && !tv && (
        <Card tone="stage" className="center">
          <p className="sign">Your portfolio</p>
          <p className="lead space-top">
            Cash <b>{money(me.cash)}</b> · net worth <b>{money(me.worth)}</b>
          </p>
          <p className="muted">
            Every $10 of profit is a show point at the finale (losses count too). Selling what you don’t own opens a short. Each game’s winner pays
            ${m.dividend} a share.
          </p>
        </Card>
      )}
      <Card>
        <h3>The board</h3>
        <ul className="ticker">
          {players.map((p) => {
            const price = m.prices[p.id] ?? 100;
            const held = me?.holdings[p.id] ?? 0;
            const canBuy = (n: number) => !!me && me.cash >= price * n && held + n <= MAX_HOLDING && n <= MAX_TRADE;
            return (
              <li key={p.id}>
                <span className="ticker-name">
                  <b>{p.name}</b>
                  {p.id === state.you ? " (you)" : ""}
                </span>
                <span className="ticker-price">{money(price)}</span>
                <Move pct={m.moves[p.id]} />
                {me && !tv && (
                  <span className="ticker-trade">
                    <span className="muted">{held < 0 ? `${-held} short` : `${held} held`}</span>
                    <Btn size="small" variant="go" aria-label={`Buy 1 share of ${p.name}`} disabled={!canBuy(1)} onClick={() => trade(send, p.id, 1)}>
                      +1
                    </Btn>
                    <Btn size="small" variant="go" aria-label={`Buy 5 shares of ${p.name}`} disabled={!canBuy(5)} onClick={() => trade(send, p.id, 5)}>
                      +5
                    </Btn>
                    <Btn
                      size="small"
                      variant="danger"
                      aria-label={held > 0 ? `Sell 1 share of ${p.name}` : `Short 1 share of ${p.name}`}
                      disabled={held - 1 < -MAX_HOLDING || (p.id === state.you && held < 1)}
                      onClick={() => trade(send, p.id, -1)}
                    >
                      −1
                    </Btn>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
        <p className="muted space-top" aria-live="polite">
          {m.trades} {m.trades === 1 ? "trade" : "trades"} so far. Holdings stay secret until the finale.
        </p>
      </Card>
      {isHost && !tv && (
        <Card tone="soft">
          <div className="row between">
            <p className="muted">You’re the host. The bell rings on its own when the clock runs out.</p>
            <Btn variant="gold" onClick={() => send({ t: "skip" })}>
              🔔 Ring the bell now
            </Btn>
          </div>
        </Card>
      )}
    </div>
  );
}

function trade(send: Send, target: string, qty: number) {
  sfx.pop();
  send({ t: "trade", target, qty });
}

/** After a game: how the prices moved, and your dividend. */
export function MarketMoves({ m, players, you }: { m: MarketState; players: { id: string; name: string }[]; you: string }) {
  if (!Object.keys(m.moves).length) return null;
  const paid = m.dividends[you];
  return (
    <Card tone="soft" aria-label="Stock prices after this game">
      <h3>📈 The market reacts</h3>
      {paid !== undefined && (
        <p className="lead">
          {paid >= 0 ? `💰 Dividend: +${money(paid)}` : `💸 Your short paid ${money(-paid)} in dividends`}
        </p>
      )}
      <ul className="evidence">
        {[...players]
          .sort((a, b) => (m.moves[b.id] ?? 0) - (m.moves[a.id] ?? 0))
          .map((p) => (
            <li key={p.id}>
              <b>{p.name}</b> now {money(m.prices[p.id] ?? 100)} <Move pct={m.moves[p.id]} />
            </li>
          ))}
      </ul>
    </Card>
  );
}

/** Finale: everyone's books and net worth, finally public. */
export function MarketFinale({ m, players, you }: { m: MarketState; players: { id: string; name: string }[]; you: string }) {
  const traders = [...players, ...Object.entries(m.crowd).map(([id, name]) => ({ id, name: `${name} (audience)` }))];
  const ranked = traders.filter((p) => p.id in m.worth).sort((a, b) => (m.worth[b.id] ?? 0) - (m.worth[a.id] ?? 0));
  return (
    <Card aria-labelledby="market-final-h">
      <h3 id="market-final-h">📈 Friend Stock Exchange: closing bell</h3>
      <ol className="evidence">
        {ranked.map((p) => {
          const book = Object.entries(m.books[p.id] ?? {});
          const bonus = m.bonus[p.id] ?? 0;
          return (
            <li key={p.id}>
              <b>{p.name}</b>
              {p.id === you ? " (you)" : ""}: worth {money(m.worth[p.id] ?? 0)} ({bonus >= 0 ? "+" : ""}
              {bonus} points)
              {book.length > 0 && (
                <span className="muted">
                  {" "}
                  · held {book.map(([t, q]) => `${q < 0 ? `short ${-q}` : q} × ${nameOf(players, t)}`).join(", ")}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
