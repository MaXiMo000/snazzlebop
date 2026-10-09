/** A pass for the room's voice/video call, sent by the server when asked ({"t": "call"}). */
export interface CallPass {
  t: "call";
  url: string;
  token: string;
  /** a TV pass: watch only */
  tv: boolean;
}

const listeners = new Set<(p: CallPass) => void>();
export function onCallPass(fn: (p: CallPass) => void): () => void {
  listeners.add(fn);
  return () => void listeners.delete(fn);
}
export function emitCallPass(p: CallPass) {
  for (const fn of listeners) fn(p);
}
