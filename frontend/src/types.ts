export interface PlayerInfo {
  id: string;
  name: string;
  connected: boolean;
  host: boolean;
  total: number;
}

export interface GameCard {
  id: "frenemy" | "alibi" | "price" | "telepathy" | "mural" | "blackjack" | "crossword" | "codes" | "wits" | "chicken" | "split" | "dice";
  title: string;
  blurb: string;
  min_players: number;
  max_players: number;
  /** host-chosen settings: name -> allowed values (first is the default) */
  options: Record<string, string[]>;
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
  /** where they guessed the room would rank them (0 = no guess) */
  predicted: number;
  /** bonus for that guess: 50 spot on, 25 one off */
  mirror: number;
}
export interface FrenemyView extends GameBase {
  game: "frenemy";
  prompt: string;
  players: { id: string; name: string }[];
  submitted: string[];
  you_submitted: boolean;
  you_predicted: number | null;
  result?: Record<string, FrenemyRow>;
  final?: {
    per_player: Record<string, { blind_spot: number; avg_gap: number }>;
    awards: { award: string; player: string }[];
    pairs: { frenemies?: [string, string]; fans?: [string, string] };
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
    objection_left: boolean;
    /** the killer's own planted clue (null for everyone else) */
    plant: { target: string; slot: number; released: boolean } | null;
    can_plant: boolean;
  };
  objections: { by: string; target: string; slot: number; label: string; sustained: boolean }[];
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
    planted: { target: string; slot: number; location: string; released: boolean } | null;
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
export interface PriceItem {
  name: string;
  blurb: string;
  emoji: string;
}
export interface PriceDuelResult {
  items: (PriceItem & { price: number })[];
  /** index of the pricier item (null when they cost the same: every pick counts) */
  answer: 0 | 1 | null;
  picks: Record<string, number>;
  right: string[];
}
export interface PriceView extends GameBase {
  game: "price";
  /** the final round's three prizes (prices only from the reveal on) */
  showcase?: PriceItem[];
  showcase_prices?: number[];
  duel?: { items: PriceItem[]; locked: string[]; your_pick: number | null };
  last_duel?: PriceDuelResult;
  duels?: PriceDuelResult[];
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
  /** streak bonus included in points */
  bonus: Record<string, number>;
  taxed: number[];
  /** a contrarian round: no tax, only unique picks score */
  contrarian: boolean;
  streaks: Record<string, number>;
}
export interface TelepathyView extends GameBase {
  game: "telepathy";
  players: { id: string; name: string }[];
  category: { title: string; options: string[] };
  locked: string[];
  you_locked: boolean;
  your_pick: number | null;
  contrarian: boolean;
  streaks: Record<string, number>;
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
  /** how many Moles (1, or 2 at 7-8 players), never who */
  moles: number;
  /** target is the painting's index: only for innocent players, never a Mole or a TV */
  you: { is_mole: boolean; target: number | null; can_swap: boolean; swap_with: string | null; guessed: boolean };
  /** your own real hints so far (the public record may show a swap) */
  your_hints: number[];
  /** hint rounds whose reveal had a Switcheroo in it (not who) */
  swapped_rounds: number[];
  hinted: string[];
  your_hint: number | null;
  /** one map per revealed hint round: player id -> tile index */
  hints: Record<string, number>[];
  votes_in: number;
  you_voted: string | null;
  caught: string[];
  result?: {
    moles: string[];
    target: number;
    caught: string[];
    guesses: Record<string, number>;
    stole: string[];
    tally: Record<string, number>;
    votes: Record<string, string>;
    swaps: { round: number; by: string; with: string }[];
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
  mode: "classic" | "tournament";
  /** still in the game (everyone in classic) */
  active: string[];
  out: { player: string; hand: number; why: "busted" | "shortest stack" }[];
  chips: Record<string, number>;
  bets: Record<string, number>;
  side: Record<string, { on: string; amount: number }>;
  bet_sizes: number[];
  /** empty when playing solo */
  side_sizes: number[];
  chaos: { id: string; label: string; text: string } | null;
  chaos_coming: boolean;
  standings?: string[];
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
    side: Record<string, { on: string; amount: number; pay: number }>;
    chaos: string | null;
    eliminated: string[];
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
  /** bought: a letter your side paid for (only you / your team see it) */
  cells: { row: number; col: number; num: number | null; letter: string | null; bought: boolean }[];
  clues: CrosswordClue[];
  hint_level: number;
  locked_for: number;
  mode: "race" | "teams";
  /** player id -> team name (team mode only) */
  teams: Record<string, string>;
  team_totals: Record<string, number>;
  letters_left: number;
  letter_cost: number;
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
  | CodesView
  | WitsView
  | ChickenView
  | SplitView
  | DiceView
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

export interface DiceBid {
  player: string;
  qty: number;
  face: number;
}
export interface DiceChallenge {
  call: "liar" | "spot";
  caller: string;
  bid: DiceBid;
  actual: number;
  loser: string | null;
  gained: string | null;
}
export interface DiceView extends GameBase {
  game: "dice";
  players: { id: string; name: string }[];
  counts: Record<string, number>;
  total: number;
  start_dice: number;
  bid: DiceBid | null;
  turn: string | null;
  you: { dice: number[] };
  out: string[];
  history: DiceChallenge[];
  /** the challenged round, all dice face up */
  last?: DiceChallenge & { dice: Record<string, number[]> };
  standings?: string[];
}

export interface SplitPairResult {
  players: [string, string];
  pot: number;
  choices: Record<string, "split" | "steal">;
  gain: Record<string, number>;
}
export interface SplitView extends GameBase {
  game: "split";
  players: { id: string; name: string }[];
  pairs: { players: [string, string]; pot: number }[];
  bye: string | null;
  locked: string[];
  said: Record<string, string>;
  lines: string[];
  record: Record<string, { split: number; steal: number }>;
  you: { partner: string | null; choice: "split" | "steal" | null };
  result?: { pairs: SplitPairResult[]; bye: string | null };
  history?: { pairs: SplitPairResult[]; bye: string | null }[];
}

export interface ChickenRound {
  bomb: number;
  bomb_value: number;
  cashed: Record<string, { t: number; value: number }>;
  boomed: string[];
  nerve: string | null;
}
export interface ChickenView extends GameBase {
  game: "chicken";
  players: { id: string; name: string }[];
  base: number;
  growth: number;
  /** seconds since the run started, as of this frame (null outside the run) */
  started_ago: number | null;
  cashed: Record<string, { t: number; value: number }>;
  result?: ChickenRound;
  history?: ChickenRound[];
}

export interface WitsSlot {
  slot: number;
  /** null: the "lower than all of them" slot */
  value: number | null;
  by: string[];
  odds: number;
}
export interface WitsResult {
  answer: number;
  slot: number;
  gains: Record<string, number>;
  bets: Record<string, number[]>;
  answers: Record<string, number>;
}
export interface WitsView extends GameBase {
  game: "wits";
  players: { id: string; name: string }[];
  question: { q: string; unit: string };
  answered: string[];
  board: WitsSlot[];
  bet_in: string[];
  chips: number;
  chip_value: number;
  you: { answer: number | null; bets: number[] | null };
  result?: WitsResult;
  history?: (WitsResult & { q: string })[];
}

export interface CodesGuess {
  code: number[];
  hits: number;
  near: number;
}
export interface CodesView extends GameBase {
  game: "codes";
  players: { id: string; name: string }[];
  length: number;
  symbols: number;
  set: string[];
  /** code owner -> who cracked it, in order */
  cracked: Record<string, string[]>;
  guess_counts: Record<string, number>;
  you: { code: number[]; guesses: Record<string, CodesGuess[]>; cooldown: number };
  /** every code, once it's over */
  codes?: Record<string, number[]>;
}
