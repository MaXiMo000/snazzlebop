export interface PlayerInfo {
  id: string;
  name: string;
  connected: boolean;
  host: boolean;
  total: number;
}

export interface GameCard {
  id: "frenemy" | "alibi" | "price";
  title: string;
  blurb: string;
  min_players: number;
  max_players: number;
}

export interface GameBase {
  game: GameCard["id"];
  phase: string;
  round: number;
  rounds: number;
  remaining: number | null;
}

export interface FrenemyRow {
  self_rank: number;
  others_avg: number;
  gap: number;
  blind_pct: number;
  played: number;
}
export interface FrenemyView extends GameBase {
  game: "frenemy";
  prompt: string;
  players: { id: string; name: string }[];
  submitted: string[];
  you_submitted: boolean;
  result?: Record<string, FrenemyRow>;
  final?: {
    per_player: Record<string, { blind_spot: number; avg_gap: number }>;
    awards: { award: string; player: string }[];
  };
  history?: { prompt: string; result: Record<string, FrenemyRow> }[];
}

export interface AlibiClaim {
  speaker: string;
  slot: number;
  label: string;
  location: string;
  with: string[];
}
export interface AlibiView extends GameBase {
  game: "alibi";
  players: { id: string; name: string }[];
  setting: string;
  victim: string;
  scene: string;
  murder_slot: number;
  murder_label: string;
  slots: string[];
  locations: string[];
  you: {
    card: { slot: number; label: string; location: string; with: string[]; shared: boolean }[];
    is_killer: boolean;
    fake_slots: number[] | null;
    asks_left: number;
  };
  claims: AlibiClaim[];
  flags: { kind: string; slot: number; label: string; players: string[]; text: string }[];
  /** "camera" names who was there; "headcount" (blurry feed) only counts them */
  clues: { kind: "camera" | "headcount"; location: string; slot: number; label: string; occupants?: string[]; count?: number }[];
  log: { kind: string; text: string }[];
  votes_in: number;
  you_voted: string | null;
  result?: {
    killer: string;
    caught: boolean;
    tally: Record<string, number>;
    votes: Record<string, string>;
    truth: Record<string, string[]>;
    fake_slots: number[];
    hazy: { player: string; slot: number } | null;
    recap: string[];
  };
}

export interface PriceResult {
  item: string;
  base_price: number;
  modifier: number;
  true_price: number;
  nonce: string;
  commit: string;
  guesses: Record<string, number[]>;
  winner: string | null;
  pot: number;
  rollover: number;
  rigged: boolean;
  /** saboteur -> target, revealed with the result */
  sabotage: Record<string, string>;
  /** Double or Nothing outcomes on the final item */
  double: Record<string, "doubled" | "wiped">;
}
export interface PriceView extends GameBase {
  game: "price";
  item: { name: string; blurb: string; emoji: string };
  commit: string;
  chips: number;
  locked: string[];
  you_locked: boolean;
  rollover: number;
  rigged: boolean;
  final_round: boolean;
  sabotage_left: number;
  your_sabotage: string | null;
  your_double: boolean;
  your_guesses?: number[];
  result?: PriceResult;
  history?: PriceResult[];
}

export type GameView = FrenemyView | AlibiView | PriceView;

export interface RoomState {
  t: "state";
  you: string;
  room: { code: string; phase: "lobby" | "game" | "results"; host: string };
  players: PlayerInfo[];
  games: GameCard[];
  game: GameView | null;
  stage: string | null;
  /** true on a TV-mode (read-only big screen) connection */
  tv: boolean;
}

export interface Session {
  token: string;
  playerId: string;
}
