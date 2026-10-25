// Why a payout was held back (backend app/fairplay.py NOTES), as players are told.
export const HELD_BACK: Record<string, string> = {
  limit: "today's limit is reached",
  repeat: "you've played this group a lot today",
  device: "these accounts share a device",
  quick: "the game ended too quickly",
  solo: "no other signed-in player",
  new: "new accounts win prizes after 3 days, with a confirmed email",
  left: "left before the end",
};

export const heldBack = (note: string | null | undefined) => (note ? (HELD_BACK[note] ?? note) : "");
