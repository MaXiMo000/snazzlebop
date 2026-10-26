import type { ReactNode } from "react";
import type { GameCard } from "../types";
import { SEGMENT_ICON } from "./show";

export const playersLabel = (g: GameCard) => (g.min_players === g.max_players ? `${g.min_players}` : `${g.min_players}-${g.max_players}`);
export const fitsRoom = (g: GameCard, online: number) => online >= g.min_players && online <= g.max_players;

/** A compact game tile: icon, name, players and a line of what it is. Opens the game's sheet. */
export function GameTile({ g, dim = false, onOpen }: { g: GameCard; dim?: boolean; onOpen: () => void }) {
  return (
    <article id={`tile-${g.id}`} className={`game-card game-tile seg-${g.id} ${dim ? "dim" : ""}`} aria-labelledby={`seg-${g.id}`}>
      <button type="button" className="game-tile-open" onClick={onOpen} aria-describedby={`seg-${g.id}-blurb`}>
        <span className="game-tile-icon" aria-hidden="true">
          {SEGMENT_ICON[g.id]}
        </span>
        <span className="game-tile-text">
          <span id={`seg-${g.id}`} className="game-tile-title">
            {g.title}
          </span>
          <span className="game-tile-meta">
            <span className="no-break">{playersLabel(g)} players</span>
            {g.featured !== null && (
              <>
                {" · "}
                <span className="no-break">⭐ easy start</span>
              </>
            )}
          </span>
          <span id={`seg-${g.id}-blurb`} className="game-tile-blurb">
            {g.blurb}
          </span>
        </span>
      </button>
    </article>
  );
}

/** A game's sheet: what it is and how to play in steps; `children` is what you can do with it. */
export function GameInfo({ g, children }: { g: GameCard; children?: ReactNode }) {
  return (
    <article className="game-sheet game-card" aria-labelledby="game-sheet-h">
      <header className="game-sheet-band">
        <span className="game-sheet-icon" aria-hidden="true">
          {SEGMENT_ICON[g.id]}
        </span>
        <div>
          <h2 id="game-sheet-h">{g.title}</h2>
          <p className="game-sheet-tags">
            <span className="chip plum">{playersLabel(g)} players</span>
            {g.teams && <span className="chip plum">Teams</span>}
            {g.ranked && <span className="chip plum">Ranked</span>}
          </p>
        </div>
      </header>
      <p className="game-sheet-blurb">{g.blurb}</p>
      {g.how_to.length > 0 && (
        <ol className="how-steps" aria-label="How to play">
          {g.how_to.slice(0, 4).map((line, i) => (
            <li key={i}>
              <span>{line}</span>
            </li>
          ))}
        </ol>
      )}
      {children}
    </article>
  );
}
