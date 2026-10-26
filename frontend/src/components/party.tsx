import { useEffect, useRef, useState } from "react";
import { refreshAccount, useAccount } from "../lib/account";
import { sfx } from "../lib/sfx";
import type { RoomState } from "../types";
import { useShow } from "./fx";
import { Card } from "./ui";

type Send = (msg: Record<string, unknown>) => void;

// The same items as the server (backend app/party.py).
export const PARTY: [string, string, string][] = [
  ["party_confetti", "🎉", "Confetti cannon"],
  ["party_airhorn", "📯", "Air horn"],
  ["party_drumroll", "🥁", "Drum roll"],
  ["party_ovation", "👏", "Standing ovation"],
  ["party_spotlight", "🔦", "Spotlight"],
  ["party_replay", "🎬", "Slow-mo replay"],
];
// Emote packs (backend app/party.py EMOTES): kept for good, they add to your live reactions.
export const EMOTE_PACKS: Record<string, [string, string][]> = {
  emote_spooky: [["👻", "Ghost"], ["🎃", "Pumpkin"], ["🦇", "Bat"], ["🕸️", "Web"]],
  emote_animals: [["🐸", "Frog"], ["🦄", "Unicorn"], ["🐙", "Octopus"], ["🦖", "Dinosaur"]],
  emote_snacks: [["🍕", "Pizza"], ["🌮", "Taco"], ["🍩", "Doughnut"], ["🍿", "Popcorn"]],
  emote_royal: [["👑", "Crown"], ["💎", "Diamond"], ["🏆", "Trophy"], ["🥇", "Gold medal"]],
  emote_weather: [["🌈", "Rainbow"], ["⚡", "Lightning"], ["🌪️", "Tornado"], ["❄️", "Snowflake"]],
};
const REPLAY_MS = 6000;
type Moment = NonNullable<RoomState["party"]["effects"][number]["moment"]>;
const COOLDOWN_MS = 20000; // the server's wait between one player's items

/** Your party items, for any moment in the room. Shown only when you have some. */
export function PartyBar({ state, send }: { state: RoomState; send: Send }) {
  const { user } = useAccount();
  const [cooling, setCooling] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const owned = PARTY.filter(([id]) => (user?.powerups[id] ?? 0) > 0);
  if (!user || state.role !== "player" || !owned.length) return null;
  return (
    <Card tone="soft" className="party-bar" aria-labelledby="party-h">
      <h3 id="party-h">
        <span aria-hidden="true">🎊 </span>Party items
      </h3>
      <div className="party-buttons" role="group" aria-labelledby="party-h">
        {owned.map(([id, icon, name]) => (
          <button
            key={id}
            type="button"
            className="react-btn party-btn"
            disabled={cooling}
            aria-label={`${name} (${user.powerups[id]} left)`}
            onClick={() => {
              send({ t: "party", item: id });
              setCooling(true);
              timer.current = window.setTimeout(() => setCooling(false), COOLDOWN_MS);
              window.setTimeout(() => void refreshAccount(), 700);
            }}
          >
            <span aria-hidden="true">{icon}</span>
            <span className="party-count" aria-hidden="true">
              {user.powerups[id]}
            </span>
          </button>
        ))}
      </div>
    </Card>
  );
}

/** Every screen (TV too) plays each party item once, as it arrives. Decorative: aria-hidden. */
export function PartyOverlay({ state }: { state: RoomState }) {
  const fx = useShow();
  const [replay, setReplay] = useState<{ id: number; by: string; moment: Moment } | null>(null);
  useEffect(() => {
    if (!replay) return;
    const t = window.setTimeout(() => setReplay(null), REPLAY_MS);
    return () => window.clearTimeout(t);
  }, [replay]);
  const effects = state.party.effects;
  const seen = useRef<number>(Math.max(0, ...effects.map((e) => e.id)));
  useEffect(() => {
    const fresh = effects.filter((e) => e.id > seen.current);
    if (!fresh.length) return;
    seen.current = Math.max(...fresh.map((e) => e.id));
    const e = fresh[fresh.length - 1]!; // a burst plays only the latest
    if (e.item === "party_confetti") {
      fx.celebrate();
      fx.stinger(`🎉 ${e.by}!`);
      sfx.fanfare();
    } else if (e.item === "party_airhorn") {
      fx.stinger("📯 HONK!");
      sfx.airhorn();
    } else if (e.item === "party_drumroll") {
      fx.stinger("🥁 Drum roll…");
      sfx.drumroll();
    } else if (e.item === "party_ovation") {
      fx.stinger(`👏 Ovation for ${e.by}`);
      sfx.applause();
    } else if (e.item === "party_spotlight") {
      fx.stinger(`🔦 ${e.by}`);
      sfx.ding();
    } else if (e.item === "party_replay" && e.moment) {
      setReplay({ id: e.id, by: e.by, moment: e.moment });
      sfx.drumroll();
    }
  }, [effects, fx]);
  return (
    <>
      {fx.node}
      {replay && (
        <div key={replay.id} className="slowmo" aria-hidden="true">
          <div className="slowmo-frame">
            <p className="slowmo-tag">🎬 Instant replay · {replay.by}</p>
            <p className="slowmo-icon">{replay.moment.icon}</p>
            <p className="slowmo-title">{replay.moment.title}</p>
            <p className="slowmo-text">{replay.moment.text}</p>
          </div>
        </div>
      )}
    </>
  );
}
