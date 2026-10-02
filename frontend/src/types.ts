export interface PlayerInfo {
  id: string;
  name: string;
  connected: boolean;
  host: boolean;
  total: number;
}

export interface GameCard {
  id: "frenemy" | "alibi" | "price" | "telepathy" | "mural" | "blackjack" | "crossword";
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

export interface TelepathyResult {
  category: { title: string; options: string[] };
  picks: Record<string, number>;
  points: Record<string, number>;
  taxed: number[];
}
export interface TelepathyView extends GameBase {
  game: "telepathy";
  players: { id: string; name: string }[];
  category: { title: string; options: string[] };
  locked: string[];
  you_locked: boolean;
  your_pick: number | null;
  result?: TelepathyResult;
  final?: { history: TelepathyResult[]; mind_meld: { players: [string, string]; matches: number } | null };
}

export interface MuralTile {
  emoji: string;
  name: string;
  color: string;
  kind: string;
}
export interface MuralView extends GameBase {
  game: "mural";
  players: { id: string; name: string }[];
  mural: MuralTile[];
  /** target is the painting's index: only for innocent players, never the Mole or a TV */
  you: { is_mole: boolean; target: number | null };
  hinted: string[];
  your_hint: number | null;
  /** one map per revealed hint round: player id -> tile index */
  hints: Record<string, number>[];
  votes_in: number;
  you_voted: string | null;
  caught: string | null;
  result?: {
    mole: string;
    target: number;
    caught: boolean;
    guess: number | null;
    stole: boolean;
    tally: Record<string, number>;
    votes: Record<string, string>;
  };
}

export interface BlackjackHand {
  cards: string[];
  bet: number;
  value: number;
  /** an ace is still counting as 11 */
  soft: boolean;
}
export interface BlackjackView extends GameBase {
  game: "blackjack";
  players: { id: string; name: string }[];
  chips: Record<string, number>;
  bets: Record<string, number>;
  bet_sizes: number[];
  hands: Record<string, BlackjackHand[]>;
  dealer: { cards: string[]; hidden: boolean; value: number };
  shoe_left: number;
  reshuffled: boolean;
  turn: { player: string; hand: number } | null;
  you: { actions: ("hit" | "stand" | "double" | "split")[]; bet: number | null };
  result?: {
    dealer: string[];
    dealer_value: number;
    dealer_blackjack: boolean;
    net: Record<string, number>;
    outcomes: Record<string, ("bust" | "blackjack" | "lose" | "push" | "win")[]>;
  };
  history?: { hand: number; net: Record<string, number>; dealer_value: number }[];
}

export interface CrosswordClue {
  id: number;
  num: number;
  dir: "across" | "down";
  row: number;
  col: number;
  len: number;
  clue: string;
  solved_by: string | null;
  answer?: string;
}
export interface CrosswordView extends GameBase {
  game: "crossword";
  players: { id: string; name: string }[];
  width: number;
  height: number;
  cells: { row: number; col: number; num: number | null; letter: string | null }[];
  clues: CrosswordClue[];
  hint_level: number;
  locked_for: number;
}

export interface JackpotView {
  game: "jackpot";
  phase: "wager" | "final";
  round: number;
  rounds: number;
  remaining: number | null;
  players: { id: string; name: string }[];
  item: { name: string; blurb: string; emoji: string };
  tag: number;
  stakes: Record<string, number>;
  cap: number;
  locked: string[];
  you: { amount: number; call: "higher" | "lower" } | null;
  result: {
    price: number;
    answer: "higher" | "lower";
    wagers: Record<string, { amount: number; call: "higher" | "lower" }>;
    deltas: Record<string, number>;
  } | null;
}

export type GameView =
  | FrenemyView
  | AlibiView
  | PriceView
  | TelepathyView
  | MuralView
  | BlackjackView
  | CrosswordView
  | JackpotView;

export interface Highlight {
  icon: string;
  title: string;
  text: string;
  /** the game it happened in (show reel only) */
  game?: string;
}

export interface ShowState {
  playlist: { id: GameCard["id"]; title: string }[];
  jackpot: boolean;
  started: number;
  /** next segment to start: a game id, "jackpot", or null when the show is over */
  next: GameCard["id"] | "jackpot" | null;
  finished: boolean;
  games: { game: string; title: string; scores: Record<string, number> }[];
  reel: Highlight[];
  awards: Highlight[];
}

export interface Reaction {
  id: number;
  e: string;
  by: string;
}

export interface Crowd {
  members: { id: string; name: string; points: number; connected: boolean }[];
  /** the running game's contestants (who the crowd can back) */
  contestants: { id: string; name: string }[];
  /** how many of the crowd back each player this game (never who) */
  picks: Record<string, number>;
  open: boolean;
  you_picked: string | null;
}

export type Role = "player" | "tv" | "audience";

export interface RoomState {
  t: "state";
  you: string;
  role: Role;
  room: {
    code: string;
    phase: "lobby" | "game" | "results" | "finale";
    host: string;
    title: string;
    locked: boolean;
    theme: string;
  };
  themes: Record<string, string>;
  show: ShowState | null;
  highlights: Highlight[];
  quip: string;
  reactions: Reaction[];
  crowd: Crowd;
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
