import { useEffect, useState } from "react";
import { buy, useAccount } from "../lib/account";
import { request } from "../lib/api";
import { inApp } from "../lib/app";
import { sfx } from "../lib/sfx";
import { Alert, errText } from "./auth";
import { AvatarView, stored } from "./avatar";
import { WIN_ICON, WinFx } from "./cosmetics";
import { Btn, Card, Loading } from "./ui";

type Option = { id: string; name: string; level: number; plus: boolean; price: number; unlocked: boolean };
type Kind = "frame" | "char" | "win";
type Picks = Record<Kind, string>;
type MyLook = Picks & {
  level: number;
  plus: boolean;
  slots: number;
  slot_level: number;
  frames: Option[];
  chars: Option[];
  wins: Option[];
};

const TABS: [Kind, string, "frames" | "chars" | "wins"][] = [
  ["frame", "Frames", "frames"],
  ["char", "Characters", "chars"],
  ["win", "Victory", "wins"],
];

/** How an option opens, in a few words: what its tile shows when it isn't worn. */
function tag(o: Option, worn: boolean) {
  if (worn) return "Wearing";
  if (o.unlocked) return "Yours";
  if (o.plus) return "⭐ Plus";
  if (o.price) return `🪙 ${o.price}`;
  return `🔒 Level ${o.level}`;
}

/** Your look: animated frames, characters and victory animations. Open ones are worn with a tap; locked
 * ones can be tried on first, then bought with coins, opened by levels or with Plus. The server checks
 * every pick and purchase. */
export function YourLook({ username, go }: { username: string; go?: (path: string) => void }) {
  const { user } = useAccount();
  const [look, setLook] = useState<MyLook | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Kind>("frame");
  const [trying, setTrying] = useState<Partial<Picks>>({});
  const [replay, setReplay] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void request<MyLook>("/api/me/look").then(setLook, (e) => setError(errText(e)));
  }, []);
  const [face, tone] = stored() ?? [undefined, 3];

  const wear = async (next: Picks) => {
    setError(null);
    try {
      setLook(await request<MyLook>("/api/me/look", { method: "POST", body: JSON.stringify(next) }));
    } catch (e) {
      setError(errText(e));
      void request<MyLook>("/api/me/look").then(setLook, () => undefined);
    }
  };
  if (!look)
    return (
      <Card aria-labelledby="look-h">
        <h2 id="look-h">Your look</h2>
        {error ? <Alert text={error} /> : <Loading />}
      </Card>
    );

  const picks: Picks = { frame: look.frame, char: look.char, win: look.win };
  const shown: Picks = { ...picks, ...trying };
  const list = look[TABS.find(([k]) => k === tab)![2]];
  const focus = list.find((o) => o.id === shown[tab]) ?? list[0]!;
  const coins = user?.coins ?? 0;

  const choose = (o: Option) => {
    setTrying({ ...trying, [tab]: o.id });
    if (tab === "win") setReplay((n) => n + 1);
    if (o.unlocked && picks[tab] !== o.id) void wear({ ...picks, [tab]: o.id });
  };
  const purchase = async (o: Option) => {
    setBusy(true);
    setError(null);
    try {
      await buy(`look_${tab}_${o.id}`);
      sfx.ding();
      await wear({ ...picks, [tab]: o.id });
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card aria-labelledby="look-h" className="look">
      <h2 id="look-h">Your look</h2>
      <p className="muted">Animated frames, characters and victory animations, seen by everyone in your rooms.</p>
      <div className="look-stage">
        <span className="look-who">
          <WinFx key={`${shown.win}-${replay}`} kind={shown.win} />
          <AvatarView name={username} face={face} tone={tone} frame={shown.frame} char={shown.char} className="xl" />
        </span>
        <div className="look-info" aria-live="polite">
          <b className="look-title">{focus.name}</b>
          {picks[tab] === focus.id ? (
            <span className="chip teal">Wearing</span>
          ) : focus.unlocked ? (
            <Btn size="small" variant="go" onClick={() => void wear({ ...picks, [tab]: focus.id })}>
              Wear it
            </Btn>
          ) : focus.price ? (
            <>
              <Btn size="small" variant="gold" disabled={busy || coins < focus.price} onClick={() => void purchase(focus)}>
                Buy for 🪙 {focus.price}
              </Btn>
              <span className="muted look-note">
                {coins < focus.price ? `${focus.price - coins} more coins to go` : "Yours to keep, in every room"}
              </span>
            </>
          ) : focus.plus ? (
            <>
              <span className="muted look-note">For Plus members</span>
              {go && !inApp && (
                <Btn size="small" variant="ghost" onClick={() => go("/plus")}>
                  See Plus
                </Btn>
              )}
            </>
          ) : (
            <span className="muted look-note">
              Opens at level {focus.level}. You're <span className="keep">level {look.level}</span>.
            </span>
          )}
          {tab === "win" && focus.id !== "confetti" && (
            <Btn size="small" variant="ghost" onClick={() => setReplay((n) => n + 1)}>
              ▶ Play again
            </Btn>
          )}
          {tab === "win" && focus.id === "confetti" && <span className="muted look-note">Confetti across your screen when you win.</span>}
        </div>
      </div>
      <p className="look-slots">
        <b>Level {look.level}.</b>{" "}
        {look.slots > 1 ? (
          <>
            You can use <span className="keep">{look.slots} power-ups</span> in each casual game.
          </>
        ) : (
          <>
            One power-up per game; a second slot opens at <span className="keep">level {look.slot_level}</span>.
          </>
        )}
      </p>
      <div className="auth-tabs look-tabs" role="group" aria-label="Kind of look">
        {TABS.map(([k, label]) => (
          <button key={k} type="button" className={`auth-tab ${tab === k ? "on" : ""}`} aria-pressed={tab === k} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>
      <div className="look-grid" role="group" aria-label={TABS.find(([k]) => k === tab)![1]}>
        {list.map((o) => {
          const worn = picks[tab] === o.id;
          const t = tag(o, worn);
          return (
            <button
              key={o.id}
              type="button"
              className={`look-option ${o.unlocked ? "" : "locked"}`}
              aria-pressed={shown[tab] === o.id}
              aria-label={`${o.name}: ${t.replace(/^\W+\s/, "")}`}
              onClick={() => choose(o)}
            >
              {tab === "win" ? (
                <span className="look-icon" aria-hidden="true">
                  {WIN_ICON[o.id] ?? "✨"}
                </span>
              ) : (
                <AvatarView
                  name={username}
                  face={face}
                  tone={tone}
                  frame={tab === "frame" ? o.id : undefined}
                  char={tab === "char" ? o.id : undefined}
                  className="lg"
                />
              )}
              <span className="look-name">{o.name}</span>
              <span className={`look-tag ${worn ? "on" : ""}`} aria-hidden="true">
                {t}
              </span>
            </button>
          );
        })}
      </div>
      {error && <Alert text={error} />}
    </Card>
  );
}
