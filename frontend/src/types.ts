export interface PlayerInfo {
  id: string;
  name: string;
  connected: boolean;
  host: boolean;
  total: number;
}

export interface GameCard {
  id: "frenemy" | "alibi" | "price" | "telepathy" | "mural" | "blackjack" | "crossword" | "codewords" | "boxes" | "lonely" | "roulette" | "codes" | "wits" | "chicken" | "split" | "dice" | "truthdare" | "wordrace" | "lastcard" | "ludo" | "chess" | "drawguess" | "telephone" | "tycoon";
  title: string;
  blurb: string;
  min_players: number;
  max_players: number;
  /** host-chosen settings: name -> allowed values (first is the default) */
  options: Record<string, string[]>;
  /** plain-language rules */
  how_to: string[];
  /** false for team games, which are played on their own rather than in a show */
  show: boolean;
  /** the classics everyone knows (board, card and party games): their own lobby section */
  classic: boolean;
  /** the host can switch on Teams: two teams, the combined score wins */
  teams: boolean;
}

export interface ChatMessage {
  id: number;
  by: string;
  name: string;
  text: string;
  /** a team-channel message (only your team ever receives these) */
  team: boolean;
}
export interface ChatState {
  messages: ChatMessage[];
  /** your team channel's name, or null when there's no team chat */
  team: string | null;
  /** the game says you must stay silent (a Codewords Spymaster mid-game) */
  muted: boolean;
  can_send: boolean;
}

export interface TeamsState {
  /** team 0 (Tangerine) and team 1 (Teal) */
  members: string[][];
  /** your team, or null (TV, audience) */
  you: number | null;
  /** results: each team's combined score and the winner (null on a draw) */
  news: { scores: number[]; winner: number | null } | null;
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
  | CodewordsView
  | BoxesView
  | LonelyView
  | RouletteView
  | CodesView
  | WitsView
  | ChickenView
  | SplitView
  | DiceView
  | TruthDareView
  | WordRaceView
  | DrawGuessView
  | TelephoneView
  | TycoonView
  | LastCardView
  | LudoView
  | ChessView
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
  /** the Friend Stock Exchange runs across this show */
  market: boolean;
  /** the host can rerun this lineup from the finale */
  can_rematch: boolean;
}

export type CardId = "double" | "shield" | "steal" | "peek";
export interface CardsState {
  catalog: Record<string, { name: string; icon: string; text: string }>;
  /** cards played in the current game (never whose or which) */
  in_play: number;
  /** results only: what was played and what it did */
  news: { pid: string; card: CardId; game: number; target?: string; effect: number }[];
  /** results: coins each signed-in finisher earned (place and coins paid) */
  coins: Record<string, { place: number; coins: number }>;
  you: {
    card: CardId | null;
    played: CardId | null;
    peek: string | null;
    /** signed in: can use power-ups bought with coins (one per game) */
    signed_in: boolean;
    /** the power-up used this game */
    boost: CardId | null;
  } | null;
}

export interface RivalsState {
  pairs: string[][];
  news: { players: string[]; winner: string | null }[];
  bonus: number;
}

export interface SeasonState {
  number: number;
  table: Record<string, { wins: number; points: number }>;
}

export interface MarketState {
  open: boolean;
  closes_in: number | null;
  /** the game the trading window is for */
  next: string;
  prices: Record<string, number>;
  history: Record<string, number>[];
  /** price changes after the last game (0.3 = +30%) */
  moves: Record<string, number>;
  /** cash paid (or owed, for shorts) from the last game's winner */
  dividends: Record<string, number>;
  dividend: number;
  trades: number;
  you: { cash: number; holdings: Record<string, number>; worth: number; tip: string } | null;
  /** finale: audience traders' names */
  crowd: Record<string, string>;
  /** finale only: everyone's numbers */
  worth: Record<string, number>;
  books: Record<string, Record<string, number>>;
  bonus: Record<string, number>;
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
  mvp: { open: boolean; you_voted: string | null; votes: Record<string, number>; bonus: number };
}

export type Role = "player" | "tv" | "audience";

export interface RoomState {
  t: "state";
  you: string;
  role: Role;
  room: {
    code: string;
    phase: "lobby" | "intro" | "game" | "results" | "finale" | "market";
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
  chat: ChatState;
  crowd: Crowd;
  market: MarketState | null;
  cards: CardsState | null;
  /** a team game: the two teams (also on the intro screen before it starts) */
  teams: TeamsState | null;
  rivals: RivalsState;
  season: SeasonState | null;
  /** the "how to play" screen before a game */
  intro: {
    game: string;
    title: string;
    blurb: string;
    how_to: string[];
    options: Record<string, string>;
    closes_in: number;
    ready: string[];
    needed: number;
  } | null;
  /** a results screen everyone can skip together */
  ready: { open: boolean; stage: string; votes: string[]; needed: number };
  /** the running game's rules */
  how_to: string[];
  /** the prank: how many jump scares the server has queued for this viewer */
  scare: number;
  /** lobby: the last show's final standings */
  last_standings: { id: string; name: string; total: number }[];
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
  palifico?: boolean;
  /** dice showing the bid face, and ones counted as wild (actual = exact + wild) */
  exact: number;
  wild: number;
}
export interface DiceView extends GameBase {
  game: "dice";
  players: { id: string; name: string }[];
  counts: Record<string, number>;
  total: number;
  start_dice: number;
  /** ones aren't wild and the face is fixed this round */
  palifico: boolean;
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
export interface SplitResult {
  pairs: SplitPairResult[];
  bye: string | null;
  golden?: { pot: number; choices: Record<string, "split" | "steal">; gain: Record<string, number> };
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
  /** the last round: everyone in one pot */
  golden: boolean;
  golden_pot: number | null;
  result?: SplitResult;
  history?: SplitResult[];
}

export interface ChickenRound {
  bomb: number;
  bomb_value: number;
  cashed: Record<string, { t: number; value: number }>;
  boomed: string[];
  nerve: string | null;
  insured: string[];
  /** insurance paid out to blown-up insured players */
  payouts: Record<string, number>;
  /** target -> who shortened their fuse */
  saboteurs: Record<string, string[]>;
  fuses: Record<string, number>;
  /** per player: payouts minus what they spent on tricks this round */
  extras: Record<string, number>;
}
export interface ChickenView extends GameBase {
  game: "chicken";
  players: { id: string; name: string }[];
  base: number;
  growth: number;
  /** seconds since the run started, as of this frame (null outside the run) */
  started_ago: number | null;
  cashed: Record<string, { t: number; value: number }>;
  insured: string[];
  costs: { insure: number; fuse: number };
  you: { fused: boolean; fuse_used: boolean };
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
  /** the all-in question: points each player put on their one slot */
  wagers: Record<string, number>;
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
  /** the last question: one slot, your own points at stake */
  all_in: boolean;
  you: { answer: number | null; bets: number[] | null; wager: number | null; max_wager: number };
  result?: WitsResult;
  history?: (WitsResult & { q: string })[];
}

export interface CodesGuess {
  code: number[];
  hits: number;
  near: number;
  /** that answer came from the owner's decoy (shown once you've guessed again) */
  decoy?: boolean;
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
  hint_counts: Record<string, number>;
  /** owners whose decoy has already fooled someone */
  decoy_sprung: string[];
  hint_cost: number;
  max_hints: number;
  you: {
    code: number[];
    decoy: boolean;
    guesses: Record<string, CodesGuess[]>;
    hints: Record<string, { pos: number; symbol: number }[]>;
    cooldown: number;
  };
  /** every code, once it's over */
  codes?: Record<string, number[]>;
}

export interface RouletteBet {
  kind: "red" | "black" | "odd" | "even" | "low" | "high" | "dozen" | "number";
  value: number | null;
  amount: number;
}
export interface RouletteResult {
  number: number;
  color: "red" | "black" | "green";
  nonce: string;
  commit: string;
  house: string;
  house_net: number;
  bets: Record<string, RouletteBet[]>;
  net: Record<string, number>;
  accuse: Record<string, string>;
  spotted: string[];
  rigged: boolean;
  /** the committed number (differs from `number` only when rigged) */
  fair_number: number;
  audits: string[];
  caught: boolean;
  /** chips moved by audits: rewards, false alarms, the House's penalty */
  audit: Record<string, number>;
}
export interface RouletteView extends GameBase {
  game: "roulette";
  players: { id: string; name: string }[];
  chips: Record<string, number>;
  stakes: number[];
  max_bets: number;
  commit: string;
  locked_count: number;
  spins: number[];
  audit_cost: number;
  you: {
    is_house: boolean;
    /** the House, and they haven't rigged a spin yet this game */
    can_rig: boolean;
    audit: boolean;
    locked: boolean;
    bets: RouletteBet[];
    accuse: string | null;
  };
  result?: RouletteResult;
  history?: RouletteResult[];
}

export interface LonelyRound {
  picks: Record<string, number>;
  winner: string | null;
  pot: number;
}
export interface LonelyView extends GameBase {
  game: "lonely";
  players: { id: string; name: string }[];
  top: number;
  pot: number;
  rollover: number;
  locked: string[];
  you: { pick: number | null };
  wins: Record<string, number>;
  result?: LonelyRound;
  history?: LonelyRound[];
}

export interface BoxContent {
  emoji: string;
  name: string;
  value: number;
}
export interface BoxSold extends BoxContent {
  box: number;
  winner: string | null;
  price: number;
  peekers: string[];
}
export interface BoxesView extends GameBase {
  game: "boxes";
  players: { id: string; name: string }[];
  labels: string[];
  current: number;
  coins: Record<string, number>;
  boxes: (BoxSold | null)[];
  claims_list: string[];
  you: { peek: (BoxContent & { box: number }) | null; extra: (BoxContent & { box: number }) | null };
  high?: { player: string; amount: number } | null;
  bids?: { player: string; amount: number }[];
  claims?: Record<string, string>;
}

export type CwColor = "red" | "blue" | "neutral" | "assassin";
export type CwTeam = "red" | "blue";
export interface CwCard {
  word: string;
  revealed: boolean;
  /** known to Spymasters, and to everyone once revealed (or at the end) */
  color: CwColor | null;
  /** guessers on the team at play who are considering this word */
  marks: string[];
}
export type CwLog =
  | { type: "clue"; team: CwTeam; word: string; count: number }
  | { type: "guess"; team: CwTeam; by: string; card: number; word: string; color: CwColor }
  | { type: "pass"; team: CwTeam; by: string }
  | { type: "timeout"; team: CwTeam };
export interface CodewordsView extends GameBase {
  game: "codewords";
  players: { id: string; name: string }[];
  teams: Record<string, CwTeam>;
  spymasters: Record<CwTeam, string | null>;
  turn: CwTeam;
  board: CwCard[];
  left: Record<CwTeam, number>;
  starting: CwTeam | null;
  clue: { team: CwTeam; word: string; count: number } | null;
  guesses_left: number | null;
  guessed_this_turn: number;
  log: CwLog[];
  pace: string;
  you: { team: CwTeam | null; spymaster: boolean };
  valid_teams: boolean;
  winner?: CwTeam;
  how?: "words" | "assassin";
}

export type TdKind = "truth" | "dare";
export interface TdStats {
  truth: number;
  dare: number;
  chicken: number;
  likes: number;
  streak: number;
  points: number;
}
export interface TdResult {
  player: string;
  kind: TdKind;
  prompt: string;
  chicken: boolean;
  yes: number;
  no: number;
  passed: boolean;
  points: number;
  bonus: number;
}
export interface TruthDareView extends GameBase {
  game: "truthdare";
  phase: "spin" | "choose" | "perform" | "vote" | "result" | "final";
  players: { id: string; name: string }[];
  heat: "mild" | "cheeky";
  /** whose turn it is (null once the game is over) */
  target: string | null;
  choice: TdKind | null;
  prompt: string;
  /** how many have voted (never who, or which way, until the result) */
  voted: number;
  voters: number;
  you_voted: boolean | null;
  rerolls: Record<string, number>;
  chickens: Record<string, number>;
  stats: Record<string, TdStats>;
  result: TdResult | null;
  up_next: string | null;
  history?: TdResult[];
}

/** One guess: the letters (null when it isn't yours and the word isn't revealed yet) and its colours:
 * one of g (green), y (yellow), x (grey) per letter. */
export interface WrRow {
  word: string | null;
  marks: string;
}
export interface WrRound {
  answer: string;
  solved: string[];
  tries: Record<string, number>;
  points: Record<string, number>;
}
export interface WordRaceView extends GameBase {
  game: "wordrace";
  phase: "play" | "reveal" | "final";
  players: { id: string; name: string }[];
  hard: boolean;
  tries: number;
  boards: Record<string, WrRow[]>;
  /** who has solved this word, in order */
  solved: string[];
  /** points this round: yours while playing, everyone's at the reveal */
  gained: Record<string, number>;
  you: { playing: boolean; done: boolean; solved: boolean };
  answer: string | null;
  wins: Record<string, number>;
  history?: WrRound[];
}

/** One pen operation on the shared 800 x 600 canvas (see backend games/ink.py). */
export type InkOp =
  | { op: "line"; c: number; w: number; p: number[] }
  | { op: "more"; p: number[] }
  | { op: "undo" }
  | { op: "clear" };
export interface DgFeed {
  by: string;
  /** a wrong guess (right guesses are never shown) */
  text?: string;
  ok?: boolean;
  /** one letter off: only ever set on your own guesses */
  close?: boolean;
}
export interface DgTurn {
  drawer: string;
  word: string;
  guessed: string[];
  points: Record<string, number>;
}
export interface DrawGuessView extends GameBase {
  game: "drawguess";
  phase: "choose" | "draw" | "reveal" | "final";
  players: { id: string; name: string }[];
  order: string[];
  drawer: string | null;
  seconds: number;
  /** the word: for the artist, for you once you've got it, and for everyone at the reveal */
  word: string | null;
  /** one entry per character: "" hidden, a letter (a hint), or a space/dash as-is */
  pattern: string[];
  /** the three words to pick from: the artist only */
  choices: string[] | null;
  guessed: string[];
  gained: Record<string, number>;
  feed: DgFeed[];
  /** the canvas's id and length (the strokes themselves arrive as "ink" messages) */
  ink: { id: string; count: number } | null;
  you: { drawer: boolean; guessed: boolean; playing: boolean };
  scores: Record<string, number>;
  history?: DgTurn[];
}

export interface TpPage {
  by: string;
  kind: "text" | "drawing";
  text: string | null;
  /** a finished drawing's id (fetch it with an "inksync" message) */
  drawing: string | null;
  likes: number;
  liked: boolean;
}
export interface TelephoneView extends GameBase {
  game: "telephone";
  phase: "write" | "draw" | "describe" | "album" | "final";
  players: { id: string; name: string }[];
  order: string[];
  seconds: number;
  /** who has finished this step */
  done: string[];
  /** your job this step (players only) */
  task: {
    kind: "write" | "draw" | "describe";
    done: boolean;
    /** what you sent (you can change it until the step ends) */
    text: string | null;
    idea?: string;
    /** whose page you're working from */
    from?: string;
    prompt?: string;
    drawing?: string;
  } | null;
  /** your canvas while you draw */
  ink: { id: string; count: number } | null;
  you: { playing: boolean };
  scores: Record<string, number>;
  album?: { book: number; books: number; owner: string; entry: number; pages: TpPage[] };
  books?: { owner: string; pages: TpPage[] }[];
}

export interface TySpace {
  kind: "street" | "station" | "utility" | "go" | "fund" | "tax" | "chance" | "jail" | "parking" | "gotojail";
  name: string;
  group?: string;
  price?: number;
  house?: number;
  /** base, 1-4 houses, hotel */
  rents?: number[];
  tax?: number;
}
export interface TySide {
  cash: number;
  squares: number[];
  cards: number;
}
export type TyLog = { type: string; player?: string; to?: string | null; amount?: number; square?: number; why?: string; dice?: number[]; text?: string; deck?: string; how?: string; level?: number };
export interface TycoonView extends GameBase {
  game: "tycoon";
  phase: "roll" | "buy" | "auction" | "manage" | "debt" | "final";
  players: { id: string; name: string }[];
  board: TySpace[];
  order: string[];
  current: string | null;
  dice: number[] | null;
  doubles: number;
  cash: Record<string, number>;
  worth: Record<string, number>;
  pos: Record<string, number>;
  /** in jail: failed tries so far */
  jail: Record<string, number>;
  /** Get Out of Jail Free cards held */
  cards: Record<string, number>;
  out: string[];
  /** square (as a string key) -> owner */
  owner: Record<string, string>;
  /** square -> 1-4 houses, 5 = hotel */
  houses: Record<string, number>;
  mortgaged: number[];
  offer: number | null;
  auction: { square: number; bid: number; bidder: string | null } | null;
  debt: { pid: string; amount: number; to: string | null; why: string } | null;
  raisable: Record<string, number>;
  trades: ({ id: number; from: string; to: string; give: TySide; get: TySide })[];
  bank: { houses: number; hotels: number };
  call_it: string[];
  /** seconds until the party clock runs out (null: no limit) */
  ends_in: number | null;
  log: TyLog[];
  you: { playing: boolean; out: boolean };
  scores: Record<string, number>;
}

export type LcColor = "red" | "yellow" | "green" | "blue";
export interface LcCard {
  id: number;
  color: LcColor | "wild";
  /** "0"-"9", "skip", "reverse", "draw2", "wild", "wild4" */
  value: string;
}
export type LcLog =
  | { type: "start"; card: number; base: LcColor; value: string }
  | { type: "play"; player: string; card: number; base: LcColor | "wild"; value: string; color: LcColor }
  | { type: "draw"; player: string; n: number; reason: string }
  | { type: "skipped"; player: string }
  | { type: "reverse"; direction: number }
  | { type: "pass"; player: string }
  | { type: "challenge"; player: string; against: string; won: boolean }
  | { type: "last"; player: string }
  | { type: "caught"; player: string; by: string }
  | { type: "timeout"; player: string }
  | { type: "reshuffle" }
  | { type: "win"; player: string; points: number };
export interface LastCardView extends GameBase {
  game: "lastcard";
  phase: "play" | "hand_over" | "final";
  players: { id: string; name: string }[];
  /** seating order: play goes round this list (backwards when direction is -1) */
  order: string[];
  turn: string | null;
  direction: number;
  top: LcCard;
  /** the colour to match (a Wild's chosen colour) */
  color: LcColor;
  /** a draw waiting for the current player; "was" = the colour a Wild Draw Four replaced */
  pending: { kind: "draw2" | "wild4"; n: number; by: string; was?: LcColor } | null;
  stacking: boolean;
  counts: Record<string, number>;
  deck: number;
  protected: string[];
  /** on one card without calling LAST CARD: catch them! */
  vulnerable: string[];
  log: LcLog[];
  you: { hand: (LcCard & { playable: boolean })[]; drawn: number | null; can_last: boolean } | null;
  winner: string | null;
  scores: Record<string, number>;
  hands?: Record<string, LcCard[]>;
  history?: { winner: string; points: number; left: Record<string, number> }[];
}

export type LudoColor = "red" | "green" | "yellow" | "blue";
type LudoTurn = { n: number; color: LudoColor; player: string };
export type LudoLog =
  | (LudoTurn & { type: "roll"; value: number })
  | (LudoTurn & { type: "move"; token: number; from: number; to: number })
  | (LudoTurn & { type: "capture"; victims: { color: LudoColor; token: number }[] })
  | (LudoTurn & { type: "home"; token: number })
  | (LudoTurn & { type: "again" | "bust" | "stuck" | "timeout" })
  | { n: number; type: "place"; color: LudoColor; place: number; points: number }
  | { n: number; type: "partner"; color: LudoColor };
export interface LudoView extends GameBase {
  game: "ludo";
  phase: "play" | "final";
  players: { id: string; name: string }[];
  /** token positions: -1 yard, 0-50 round the track from the colour's start, 51-55 home column, 56 home */
  teams: { color: LudoColor; members: string[]; tokens: number[]; points: number }[];
  turn_color: LudoColor | null;
  turn: string | null;
  /** the roll waiting for a move (null: roll first) */
  rolled: number | null;
  sixes: number;
  movable: number[];
  log: LudoLog[];
  /** your colour (null for the TV and the audience) */
  you: LudoColor | null;
  winner: LudoColor | null;
  /** colours in the order they got every token home (at the end, the last one too) */
  places: LudoColor[];
  /** 2 v 2: opposite colours are partners and win together */
  partners: boolean;
  scores: Record<string, number>;
}

export type ChessSide = "w" | "b";
export interface ChessView extends GameBase {
  game: "chess";
  phase: "play" | "final";
  players: { id: string; name: string }[];
  /** 64 squares, a1 = 0 ... h8 = 63: "" or colour + piece ("wK", "bP") */
  board: string[];
  fen: string;
  turn: ChessSide;
  /** who plays each side (more than one: a team taking turns) */
  sides: Record<ChessSide, string[]>;
  /** whose go it is to make the side's move */
  mover: string | null;
  /** the square of a king in check */
  check: string | null;
  /** the last move ("e2e4") */
  last: string | null;
  history: { san: string; side: ChessSide; by: string; uci: string }[];
  /** pieces each side has taken */
  captured: Record<ChessSide, string[]>;
  /** seconds left on each side's clock */
  clocks: Record<ChessSide, number>;
  increment: number;
  /** the side offering a draw */
  draw_offer: ChessSide | null;
  result: { winner: ChessSide | null; reason: string } | null;
  you: {
    side: ChessSide;
    /** it's your go to make the move */
    mover: boolean;
    /** legal moves now (your side's turn): "e2e4", "e7e8q" */
    legal: string[];
    /** teammates' suggestions: only your side sees these */
    suggestions: { by: string; move: string; san: string }[];
  } | null;
  scores: Record<string, number>;
}
