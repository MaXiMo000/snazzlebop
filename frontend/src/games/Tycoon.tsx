import { useEffect, useMemo, useState } from "react";
import { Btn, Card, ShowHead, nameOf } from "../components/ui";
import { useOnChange, useShow } from "../components/fx";
import { Select } from "../components/Select";
import { useCountdown } from "../lib/useRoom";
import { sfx } from "../lib/sfx";
import type { TyLog, TySide, TySpace, TycoonView } from "../types";

interface Props {
  view: TycoonView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen (TV and audience) */
  tv?: boolean;
}

type Send = Props["send"];
const GROUP_NAME: Record<string, string> = {
  brown: "Brown",
  sky: "Sky blue",
  pink: "Pink",
  orange: "Orange",
  red: "Red",
  yellow: "Yellow",
  green: "Green",
  navy: "Navy",
};
const LEVEL = ["no houses", "1 house", "2 houses", "3 houses", "4 houses", "a hotel"];
const money = (n: number) => `$${n.toLocaleString("en-US")}`;

/** Read-only helpers over the view. */
function useTycoon(view: TycoonView, you: string) {
  return useMemo(() => {
    const owner = (sq: number) => view.owner[String(sq)] ?? null;
    const houses = (sq: number) => view.houses[String(sq)] ?? 0;
    const mortgaged = new Set(view.mortgaged);
    const groups: Record<string, number[]> = {};
    view.board.forEach((sp, sq) => {
      if (sp.kind === "street" && sp.group) (groups[sp.group] ??= []).push(sq);
    });
    const seat = (pid: string) => view.order.indexOf(pid);
    const name = (pid: string | null | undefined) => (pid ? nameOf(view.players, pid) : "the bank");
    const mine = view.board.map((_, sq) => sq).filter((sq) => owner(sq) === you);
    return { owner, houses, mortgaged, groups, seat, name, mine };
  }, [view, you]);
}

export function Tycoon({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const t = useTycoon(view, you);
  const playing = !tv && view.you.playing && !view.you.out;
  const myTurn = playing && view.current === you;
  const debtor = view.debt?.pid ?? null;

  useOnChange(view.log.length ? JSON.stringify(view.log[view.log.length - 1]) : "", (_, last) => {
    if (!last) return;
    const e = JSON.parse(last) as TyLog;
    if (e.type === "roll") sfx.rattle();
    else if (e.type === "buy" || e.type === "won") sfx.ding();
    else if (e.type === "jail") {
      sfx.buzz();
      show.stinger(`${t.name(e.player).toUpperCase()} TO JAIL!`, "bad");
    } else if (e.type === "bankrupt") {
      sfx.buzz();
      show.stinger(`${t.name(e.player).toUpperCase()} IS BANKRUPT!`, "bad");
    } else if (e.type === "pay" && e.player === you && (e.amount ?? 0) >= 200) sfx.buzz();
  });
  useOnChange(view.phase, (_, phase) => {
    if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    } else if (phase === "roll" && view.current === you && playing) sfx.pop();
  });

  const sign =
    view.phase === "final"
      ? "Final scores"
      : view.phase === "debt"
        ? `Turn ${view.round} · ${debtor === you && playing ? "Raise the money!" : `${t.name(debtor)} owes money`}`
        : view.phase === "auction"
          ? `Turn ${view.round} · Auction!`
          : `Turn ${view.round} · ${myTurn ? "Your turn" : `${t.name(view.current)}’s turn`}`;

  return (
    <div className="seg-tycoon stack">
      {show.node}
      <ShowHead sign={sign} title="Property Tycoon" remaining={view.remaining} receivedAt={receivedAt}>
        <PartyClock view={view} receivedAt={receivedAt} />
      </ShowHead>
      {view.phase === "final" ? (
        <Final view={view} you={you} />
      ) : (
        <div className={`ty-layout ${tv ? "big" : ""}`}>
          <div className="ty-board-col">
            <Board view={view} you={you} />
          </div>
          <div className="ty-side">
            <Action view={view} you={you} send={send} playing={playing} />
            <Players view={view} you={you} />
            {playing && <MyStreets view={view} you={you} send={send} />}
            {playing && <Trades view={view} you={you} send={send} />}
            <Log view={view} you={you} />
            {playing && <CallIt view={view} you={you} send={send} />}
          </div>
        </div>
      )}
    </div>
  );
}

function PartyClock({ view, receivedAt }: { view: TycoonView; receivedAt: number }) {
  const left = useCountdown(view.ends_in, receivedAt);
  if (view.ends_in === null || left === null || view.phase === "final") return null;
  const mins = Math.ceil(left / 60);
  return <span className="chip plum ty-clock">{left > 0 ? `⏱ ${mins} min left` : "⏱ Time's up: last turn!"}</span>;
}

// -- the board ----------------------------------------------------------------------------------------
function side(sq: number): string {
  if (sq % 10 === 0) return "corner";
  return sq < 10 ? "b" : sq < 20 ? "l" : sq < 30 ? "t" : "r";
}

const CORNER_ICON: Record<number, string> = { 0: "GO", 10: "🔒", 20: "🅿️", 30: "👮" };
// Board labels: short enough that no word is split across lines, even on a laptop-sized board.
const SHORT: Record<string, string> = {
  "Community Fund": "Fund",
  "Starlight Boulevard": "Starlight Blvd",
  "Marigold Avenue": "Marigold Ave",
  "Sunflower Street": "Sunflower St",
};
const KIND_ICON: Record<string, string> = { station: "🚂", utility: "💡", chance: "❓", fund: "💰", tax: "🧾" };

function Board({ view, you }: { view: TycoonView; you: string }) {
  const t = useTycoon(view, you);
  const last = [...view.log].reverse().find((e) => e.type === "card" || e.type === "roll");
  return (
    <div className="ty-frame">
      <div className="ty-board" aria-hidden="true">
        {view.board.map((sp, sq) => {
          const who = t.owner(sq);
          const level = t.houses(sq);
          const here = view.order.filter((p) => !view.out.includes(p) && view.pos[p] === sq);
          return (
            <div
              key={sq}
              className={`ty-sq ty-at-${sq} ty-side-${side(sq)} ${sp.group ? `ty-g-${sp.group}` : ""} ${
                t.mortgaged.has(sq) ? "mortgaged" : ""
              } ${who ? `owned ty-own-${t.seat(who)}` : ""} ${sq === view.offer || sq === view.auction?.square ? "lit" : ""}`}
            >
              {sp.kind === "street" && (
                <span className="ty-band">
                  {level === 5 ? (
                    <i className="ty-hotel" />
                  ) : (
                    Array.from({ length: level }, (_, i) => <i key={i} className="ty-house" />)
                  )}
                </span>
              )}
              {sq % 10 === 0 ? (
                <span className="ty-corner">{CORNER_ICON[sq]}</span>
              ) : (
                <>
                  {KIND_ICON[sp.kind] && <span className="ty-icon">{KIND_ICON[sp.kind]}</span>}
                  <span className="ty-name">{SHORT[sp.name] ?? sp.name}</span>
                </>
              )}
              {here.length > 0 && (
                <span className="ty-tokens">
                  {here.map((p) => (
                    <i key={p} className={`ty-token ty-p${t.seat(p)} ${p === view.current ? "now" : ""}`} />
                  ))}
                </span>
              )}
            </div>
          );
        })}
        <div className="ty-center">
          <p className="ty-logo">Property Tycoon</p>
          {view.dice && (
            <div className="ty-dice">
              {view.dice.map((d, i) => (
                <span key={`${view.round}-${view.log.length}-${i}`} className={`ludo-die ty-die f-${d} rolled`}>
                  {Array.from({ length: 9 }, (_, j) => (
                    <i key={j} className={`p${j}`} />
                  ))}
                </span>
              ))}
            </div>
          )}
          {last?.type === "card" && <p className="ty-card-text">“{last.text}”</p>}
        </div>
      </div>
      <p className="sr-only">
        {view.order
          .filter((p) => !view.out.includes(p))
          .map((p) => `${t.name(p)} is on ${view.board[view.pos[p] ?? 0]!.name}`)
          .join(". ")}
        {view.dice ? `. Last roll ${view.dice.join(" and ")}.` : ""}
      </p>
    </div>
  );
}

// -- what to do now -----------------------------------------------------------------------------------
function Action({ view, you, send, playing }: { view: TycoonView; you: string; send: Send; playing: boolean }) {
  const t = useTycoon(view, you);
  const act = (a: string, extra: Record<string, unknown> = {}) => send({ t: "act", a, ...extra });
  const mine = playing && view.current === you;
  const cash = view.cash[you] ?? 0;
  const [sure, setSure] = useState(false);
  useEffect(() => setSure(false), [view.phase, view.round]);

  let body: React.ReactNode;
  if (view.phase === "debt" && view.debt) {
    const d = view.debt;
    if (playing && d.pid === you) {
      const short = Math.max(0, d.amount - cash);
      body = (
        <>
          <p className="lead">
            You owe <b>{money(d.amount)}</b> to {t.name(d.to)}.
          </p>
          <p className="muted space-top">
            {short > 0
              ? `Raise ${money(short)} more: sell buildings or mortgage streets below. You could raise ${money(view.raisable[you] ?? 0)} in all.`
              : "You have enough now."}
          </p>
          <div className="ty-buttons space-top">
            <Btn variant="go" disabled={short > 0} onClick={() => act("pay_debt")}>
              Pay {money(d.amount)}
            </Btn>
            <Btn variant="danger" onClick={() => (sure ? act("bankrupt") : setSure(true))}>
              {sure ? "Tap again: go bankrupt" : "Declare bankruptcy"}
            </Btn>
          </div>
        </>
      );
    } else
      body = (
        <p className="lead">
          {t.name(d.pid)} owes {money(d.amount)} and is raising the money…
        </p>
      );
  } else if (view.phase === "auction" && view.auction) {
    const a = view.auction;
    const sp = view.board[a.square]!;
    body = (
      <>
        <p className="lead">
          <b>{sp.name}</b> is up for auction (worth {money(sp.price ?? 0)}).
        </p>
        <p className="ty-bid space-top" aria-live="polite">
          {a.bidder ? `${t.name(a.bidder)} bids ${money(a.bid)}` : "No bids yet"}
        </p>
        {playing && (
          <Bids high={a.bid} cash={cash} leading={a.bidder === you} onBid={(amount) => act("bid", { amount })} />
        )}
      </>
    );
  } else if (view.phase === "buy" && view.offer !== null) {
    const sp = view.board[view.offer]!;
    body = mine ? (
      <>
        <Deed space={sp} sq={view.offer} view={view} you={you} />
        <div className="ty-buttons space-top">
          <Btn variant="go" disabled={cash < (sp.price ?? 0)} onClick={() => act("buy")}>
            Buy for {money(sp.price ?? 0)}
          </Btn>
          <Btn variant="ghost" onClick={() => act("decline")}>
            Auction it
          </Btn>
        </div>
        {cash < (sp.price ?? 0) && (
          <p className="muted space-top">Not enough cash: mortgage something below, or auction it.</p>
        )}
      </>
    ) : (
      <p className="lead">
        {t.name(view.current)} is deciding whether to buy <b>{sp.name}</b>…
      </p>
    );
  } else if (view.phase === "roll") {
    const jailed = view.current ? view.current in view.jail : false;
    body = mine ? (
      <>
        {jailed && (
          <p className="lead">
            You’re in jail (try {(view.jail[you] ?? 0) + 1} of 3). Pay $50, use a card, or roll for doubles.
          </p>
        )}
        {view.doubles > 0 && !jailed && <p className="lead">Doubles! Roll again.</p>}
        <div className="ty-buttons space-top">
          <Btn variant="go" size="big" onClick={() => act("roll")}>
            🎲 {jailed ? "Roll for doubles" : "Roll"}
          </Btn>
          {jailed && (
            <Btn variant="gold" disabled={cash < 50} onClick={() => act("pay_fine")}>
              Pay $50
            </Btn>
          )}
          {jailed && (view.cards[you] ?? 0) > 0 && (
            <Btn variant="ghost" onClick={() => act("use_card")}>
              Use your card
            </Btn>
          )}
        </div>
      </>
    ) : (
      <p className="lead">{t.name(view.current)} is about to roll…</p>
    );
  } else {
    body = mine ? (
      <>
        <p className="lead">Build, mortgage or trade, then end your turn.</p>
        <div className="ty-buttons space-top">
          <Btn variant="go" size="big" onClick={() => act("end")}>
            End turn ▶
          </Btn>
        </div>
      </>
    ) : (
      <p className="lead">{t.name(view.current)} is taking their turn…</p>
    );
  }
  const urgent = (mine && view.phase !== "auction") || (view.phase === "debt" && view.debt?.pid === you && playing);
  return <Card className={`ty-action ${urgent ? "mine" : ""}`}>{body}</Card>;
}

function Bids({
  high,
  cash,
  leading,
  onBid,
}: {
  high: number;
  cash: number;
  leading: boolean;
  onBid: (n: number) => void;
}) {
  const [custom, setCustom] = useState("");
  const value = Number.parseInt(custom, 10);
  if (leading) return <p className="muted space-top">You’re the highest bidder.</p>;
  return (
    <>
      <div className="ty-buttons space-top">
        {[10, 50, 100].map((step) => (
          <Btn key={step} variant="gold" disabled={high + step > cash} onClick={() => onBid(high + step)}>
            {money(high + step)}
          </Btn>
        ))}
      </div>
      <form
        className="ty-custom space-top"
        onSubmit={(e) => {
          e.preventDefault();
          if (value > high && value <= cash) onBid(value);
          setCustom("");
        }}
      >
        <label className="sr-only" htmlFor="ty-bid">
          Your bid in dollars
        </label>
        <input
          id="ty-bid"
          type="number"
          inputMode="numeric"
          min={high + 1}
          max={cash}
          placeholder={`More than ${money(high)}`}
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
        />
        <Btn type="submit" variant="go" disabled={!(value > high && value <= cash)}>
          Bid
        </Btn>
      </form>
    </>
  );
}

function Deed({ space, sq, view, you }: { space: TySpace; sq: number; view: TycoonView; you: string }) {
  const t = useTycoon(view, you);
  const who = t.owner(sq);
  return (
    <div className={`ty-deed ${space.group ? `ty-g-${space.group}` : ""}`}>
      <p className="ty-deed-name">
        {KIND_ICON[space.kind] ?? ""} {space.name}
      </p>
      {space.kind === "street" && space.rents ? (
        <ul className="ty-rents">
          <li>
            Rent <b>{money(space.rents[0]!)}</b> <span className="muted">(double with the whole set)</span>
          </li>
          {space.rents.slice(1).map((r, i) => (
            <li key={i}>
              {i < 4 ? `With ${LEVEL[i + 1]}` : "With a hotel"} <b>{money(r)}</b>
            </li>
          ))}
          <li className="muted">Houses {money(space.house ?? 0)} each</li>
        </ul>
      ) : space.kind === "station" ? (
        <p className="muted">Rent $25 / $50 / $100 / $200 for 1-4 stations owned.</p>
      ) : (
        <p className="muted">Rent: 4x the dice, or 10x with both utilities.</p>
      )}
      <p className="muted">
        Price {money(space.price ?? 0)} · mortgage {money(Math.floor((space.price ?? 0) / 2))}
        {who ? ` · owned by ${t.name(who)}` : ""}
      </p>
    </div>
  );
}

// -- people -------------------------------------------------------------------------------------------
function Players({ view, you }: { view: TycoonView; you: string }) {
  const t = useTycoon(view, you);
  return (
    <Card>
      <h3>Players</h3>
      <ul className="ty-players">
        {view.order.map((p) => {
          const out = view.out.includes(p);
          const count = Object.values(view.owner).filter((w) => w === p).length;
          return (
            <li key={p} className={`${p === view.current ? "now" : ""} ${out ? "out" : ""}`}>
              <i className={`ty-token ty-p${t.seat(p)}`} aria-hidden="true" />
              <b className="ty-who">
                {t.name(p)}
                {p === you ? " (you)" : ""}
              </b>
              <span className="ty-cash">{out ? "bankrupt" : money(view.cash[p] ?? 0)}</span>
              {!out && (
                <span className="ty-meta muted">
                  {count} {count === 1 ? "property" : "properties"} · worth {money(view.worth[p] ?? 0)}
                  {p in view.jail ? " · 🔒 in jail" : ""}
                  {(view.cards[p] ?? 0) > 0 ? ` · 🎟️ ${view.cards[p]}` : ""}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function MyStreets({ view, you, send }: { view: TycoonView; you: string; send: Send }) {
  const t = useTycoon(view, you);
  if (!t.mine.length) return null;
  const act = (a: string, square: number) => send({ t: "act", a, square });
  const debtor = view.phase === "debt" && view.debt?.pid === you;
  const turn = view.current === you && (view.phase === "roll" || view.phase === "manage" || view.phase === "buy");
  const cash = view.cash[you] ?? 0;
  return (
    <Card>
      <h3>Your properties</h3>
      {!turn && !debtor && <p className="muted">You can build and mortgage on your turn.</p>}
      <ul className="ty-mine">
        {t.mine.map((sq) => {
          const sp = view.board[sq]!;
          const level = t.houses(sq);
          const mort = t.mortgaged.has(sq);
          const group = sp.group ? t.groups[sp.group]! : [];
          const full =
            sp.kind === "street" && group.every((s) => t.owner(s) === you) && !group.some((s) => t.mortgaged.has(s));
          const levels = group.map((s) => t.houses(s));
          // The build button shows whenever building here is your move; it's disabled (with the reason
          // in its label) when you're short of cash or the bank is out of buildings.
          const showBuild = turn && full && level < 5 && level === Math.min(...levels);
          const stock = level === 4 ? view.bank.hotels > 0 : view.bank.houses > 0;
          const canBuild = showBuild && cash >= (sp.house ?? 0) && stock;
          const canSell = (turn || debtor) && level > 0 && level === Math.max(...levels);
          const canMortgage = (turn || debtor) && !mort && !levels.some((l) => l > 0);
          const unmortgage = Math.floor((sp.price ?? 0) / 2) + Math.ceil(Math.floor((sp.price ?? 0) / 2) / 10);
          return (
            <li key={sq} className={`${sp.group ? `ty-g-${sp.group}` : ""} ${mort ? "mortgaged" : ""}`}>
              <span className="ty-swatch" aria-hidden="true" />
              <span className="ty-street">
                <b>{sp.name}</b>
                <span className="muted">
                  {mort
                    ? "mortgaged"
                    : sp.kind === "street"
                      ? level
                        ? LEVEL[level]
                        : full
                          ? "full set!"
                          : sp.group && GROUP_NAME[sp.group]
                      : sp.kind}
                </span>
              </span>
              <span className="ty-row-buttons">
                {showBuild && (
                  <Btn
                    size="small"
                    variant="go"
                    disabled={!canBuild}
                    onClick={() => act("build", sq)}
                    aria-label={`Build on ${sp.name} for ${money(sp.house ?? 0)}${
                      !stock ? " (the bank is out of buildings)" : cash < (sp.house ?? 0) ? " (not enough cash)" : ""
                    }`}
                  >
                    +🏠 {money(sp.house ?? 0)}
                  </Btn>
                )}
                {canSell && (
                  <Btn
                    size="small"
                    variant="ghost"
                    onClick={() => act("sell", sq)}
                    aria-label={`Sell a building on ${sp.name}`}
                  >
                    Sell
                  </Btn>
                )}
                {canMortgage && (
                  <Btn
                    size="small"
                    variant="ghost"
                    onClick={() => act("mortgage", sq)}
                    aria-label={`Mortgage ${sp.name}`}
                  >
                    Mortgage
                  </Btn>
                )}
                {turn && mort && (
                  <Btn
                    size="small"
                    variant="ghost"
                    disabled={cash < unmortgage}
                    onClick={() => act("unmortgage", sq)}
                    aria-label={`Unmortgage ${sp.name} for ${money(unmortgage)}`}
                  >
                    Unmortgage {money(unmortgage)}
                  </Btn>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

// -- trades -------------------------------------------------------------------------------------------
function sideText(view: TycoonView, s: TySide): string {
  const parts = s.squares.map((sq) => view.board[sq]!.name);
  if (s.cash) parts.push(money(s.cash));
  if (s.cards) parts.push(s.cards === 1 ? "a jail card" : `${s.cards} jail cards`);
  return parts.length ? parts.join(", ") : "nothing";
}

function Trades({ view, you, send }: { view: TycoonView; you: string; send: Send }) {
  const t = useTycoon(view, you);
  const others = view.order.filter((p) => p !== you && !view.out.includes(p));
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState(others[0] ?? "");
  const [give, setGive] = useState<number[]>([]);
  const [get, setGet] = useState<number[]>([]);
  const [giveCash, setGiveCash] = useState("");
  const [getCash, setGetCash] = useState("");
  const tradable = (pid: string) =>
    view.board
      .map((_, sq) => sq)
      .filter(
        (sq) =>
          t.owner(sq) === pid &&
          !(view.board[sq]!.group && t.groups[view.board[sq]!.group!]!.some((s) => t.houses(s) > 0)),
      );
  const toggle = (list: number[], set: (v: number[]) => void, sq: number) =>
    set(list.includes(sq) ? list.filter((s) => s !== sq) : [...list, sq]);
  const mine = view.trades.filter((tr) => tr.from === you || tr.to === you);
  const submit = () => {
    send({
      t: "act",
      a: "offer",
      to,
      give: { cash: Number.parseInt(giveCash, 10) || 0, squares: give },
      get: { cash: Number.parseInt(getCash, 10) || 0, squares: get },
    });
    setOpen(false);
    setGive([]);
    setGet([]);
    setGiveCash("");
    setGetCash("");
  };
  if (!others.length) return null;
  return (
    <Card>
      <h3>Trades</h3>
      {mine.length > 0 && (
        <ul className="ty-trades">
          {mine.map((tr) => (
            <li key={tr.id}>
              <p>
                {tr.from === you ? (
                  <>
                    You offered <b>{t.name(tr.to)}</b> {sideText(view, tr.give)} for {sideText(view, tr.get)}.
                  </>
                ) : (
                  <>
                    <b>{t.name(tr.from)}</b> offers {sideText(view, tr.give)} for your {sideText(view, tr.get)}.
                  </>
                )}
              </p>
              <div className="ty-buttons">
                {tr.to === you && (
                  <Btn size="small" variant="go" onClick={() => send({ t: "act", a: "accept", trade: tr.id })}>
                    Accept
                  </Btn>
                )}
                <Btn size="small" variant="ghost" onClick={() => send({ t: "act", a: "reject", trade: tr.id })}>
                  {tr.to === you ? "Decline" : "Withdraw"}
                </Btn>
              </div>
            </li>
          ))}
        </ul>
      )}
      {!open ? (
        <Btn variant="ghost" className="space-top" onClick={() => setOpen(true)}>
          🤝 Propose a trade
        </Btn>
      ) : (
        <form
          className="ty-trade-form space-top"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <label className="field" htmlFor="ty-trade-to">
            Trade with
          </label>
          <Select id="ty-trade-to" value={to} onChange={(e) => (setTo(e.target.value), setGet([]))}>
            {others.map((p) => (
              <option key={p} value={p}>
                {t.name(p)}
              </option>
            ))}
          </Select>
          <fieldset>
            <legend>You give</legend>
            <Picks view={view} squares={tradable(you)} picked={give} toggle={(sq) => toggle(give, setGive, sq)} />
            <label className="ty-cash-field">
              <span>Cash ($)</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                max={view.cash[you]}
                value={giveCash}
                onChange={(e) => setGiveCash(e.target.value)}
              />
            </label>
          </fieldset>
          <fieldset>
            <legend>You get</legend>
            <Picks view={view} squares={tradable(to)} picked={get} toggle={(sq) => toggle(get, setGet, sq)} />
            <label className="ty-cash-field">
              <span>Cash ($)</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                max={view.cash[to]}
                value={getCash}
                onChange={(e) => setGetCash(e.target.value)}
              />
            </label>
          </fieldset>
          <div className="ty-buttons">
            <Btn type="submit" variant="go">
              Send offer
            </Btn>
            <Btn variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Btn>
          </div>
        </form>
      )}
    </Card>
  );
}

function Picks({
  view,
  squares,
  picked,
  toggle,
}: {
  view: TycoonView;
  squares: number[];
  picked: number[];
  toggle: (sq: number) => void;
}) {
  if (!squares.length) return <p className="muted">No properties to trade.</p>;
  return (
    <ul className="ty-picks">
      {squares.map((sq) => {
        const sp = view.board[sq]!;
        return (
          <li key={sq} className={sp.group ? `ty-g-${sp.group}` : ""}>
            <label>
              <input type="checkbox" checked={picked.includes(sq)} onChange={() => toggle(sq)} />
              <span className="ty-swatch" aria-hidden="true" /> {sp.name}
              {view.mortgaged.includes(sq) ? " (mortgaged)" : ""}
            </label>
          </li>
        );
      })}
    </ul>
  );
}

// -- the log ------------------------------------------------------------------------------------------
function describe(e: TyLog, view: TycoonView, name: (p: string | null | undefined) => string): string {
  const who = name(e.player);
  const sq = e.square !== undefined ? view.board[e.square]?.name : "";
  switch (e.type) {
    case "roll":
      return `${who} rolled ${e.dice?.join(" + ")}`;
    case "buy":
      return `${who} bought ${sq} for ${money(e.amount ?? 0)}`;
    case "auction":
      return `${sq} goes to auction`;
    case "won":
      return `${who} won ${sq} at auction for ${money(e.amount ?? 0)}`;
    case "unsold":
      return `Nobody bid for ${sq}`;
    case "pay": {
      const why = e.why?.startsWith("rent")
        ? " rent"
        : e.why?.startsWith("tax")
          ? " tax"
          : e.why === "fine"
            ? " to leave jail"
            : "";
      return `${who} paid ${money(e.amount ?? 0)}${why}${e.to ? ` to ${name(e.to)}` : ""}`;
    }
    case "get":
      return e.why === "go" ? `${who} passed GO: +$200` : `${who} collected ${money(e.amount ?? 0)}`;
    case "card":
      return `${who}: “${e.text}”`;
    case "jail":
      return `${who} went to jail`;
    case "free":
      return `${who} got out of jail${e.how === "paid" ? " (paid $50)" : e.how === "card" ? " (used a card)" : e.how === "doubles" ? " with doubles" : ""}`;
    case "build":
      return `${who} built on ${sq} (${LEVEL[e.level ?? 0]})`;
    case "sell":
      return `${who} sold a building on ${sq}`;
    case "mortgage":
      return `${who} mortgaged ${sq}`;
    case "unmortgage":
      return `${who} unmortgaged ${sq}`;
    case "bankrupt":
      return `${who} went bankrupt${e.to ? ` to ${name(e.to)}` : ""}`;
    case "offer":
      return `${who} offered ${name(e.to)} a trade`;
    case "trade":
      return `${who} and ${name(e.to)} made a deal`;
    default:
      return "";
  }
}

function Log({ view, you }: { view: TycoonView; you: string }) {
  const t = useTycoon(view, you);
  const lines = view.log
    .map((e) => describe(e, view, t.name))
    .filter(Boolean)
    .reverse()
    .slice(0, 8);
  return (
    <Card className="ty-log-card">
      <h3>What happened</h3>
      <ol className="ty-log" aria-live="polite">
        {lines.map((line, i) => (
          <li key={`${view.log.length}-${i}`}>{line}</li>
        ))}
      </ol>
    </Card>
  );
}

function CallIt({ view, you, send }: { view: TycoonView; you: string; send: Send }) {
  const alive = view.order.filter((p) => !view.out.includes(p));
  const voted = view.call_it.includes(you);
  return (
    <Card tone="soft">
      <p className="muted">
        Out of time? When everyone agrees, the game ends now and the richest wins. {view.call_it.length}/{alive.length}{" "}
        want to stop.
      </p>
      <Btn
        variant="ghost"
        className="space-top"
        aria-pressed={voted}
        onClick={() => send({ t: "act", a: "call_it", on: !voted })}
      >
        {voted ? "✋ Keep playing" : "🌙 Call it a night"}
      </Btn>
    </Card>
  );
}

function Final({ view, you }: { view: TycoonView; you: string }) {
  const t = useTycoon(view, you);
  const ranked = [...view.order].sort((a, b) => (view.scores[b] ?? 0) - (view.scores[a] ?? 0));
  return (
    <Card>
      <h3>Standings</h3>
      <ul className="score-rows">
        {ranked.map((p, i) => (
          <li key={p}>
            <b>
              {i === 0 ? "👑 " : ""}
              {t.name(p)}
              {p === you ? " (you)" : ""}
            </b>
            <span className="score-pts">{view.out.includes(p) ? "bankrupt" : money(view.worth[p] ?? 0)}</span>
          </li>
        ))}
      </ul>
      <p className="muted space-top">Net worth: cash plus property and buildings at cost (mortgaged at half).</p>
    </Card>
  );
}
