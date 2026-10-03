// The jump-scare scream: synthesised on the spot (nothing downloaded), different every time.
// Browsers only let a page make sound after the person has touched it, so the first tap anywhere
// quietly unlocks an audio context for later.

let ctx: AudioContext | null = null;

function unlock() {
  try {
    ctx ??= new AudioContext();
    void ctx.resume();
  } catch {
    /* no audio on this device: the ghost still comes */
  }
}
if (typeof window !== "undefined") {
  for (const ev of ["pointerdown", "keydown", "touchstart"]) window.addEventListener(ev, unlock, { capture: true, passive: true });
}

const rand = (a: number, b: number) => a + Math.random() * (b - a);

function distortion(amount: number): Float32Array<ArrayBuffer> {
  const n = 2048;
  const curve = new Float32Array(new ArrayBuffer(n * 4));
  for (let i = 0; i < n; i++) {
    const x = (i * 2) / n - 1;
    curve[i] = ((3 + amount) * x * 20 * (Math.PI / 180)) / (Math.PI + amount * Math.abs(x));
  }
  return curve;
}

function noise(ac: AudioContext, seconds: number): AudioBufferSourceNode {
  const buf = ac.createBuffer(1, Math.ceil(ac.sampleRate * seconds), ac.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  const src = ac.createBufferSource();
  src.buffer = buf;
  return src;
}

/** A sudden, full-volume shriek: a crash, then detuned screaming voices with a nasty wobble. */
export function scream(): void {
  unlock();
  const ac = ctx;
  if (!ac) return;
  const t = ac.currentTime + 0.01;
  const dur = rand(1.6, 2.6);

  const out = ac.createDynamicsCompressor(); // keeps it as loud as possible without hard clipping
  out.threshold.value = -6;
  out.ratio.value = 6;
  const master = ac.createGain();
  master.gain.value = 1;
  out.connect(master).connect(ac.destination);

  // The hit: a burst of noise and a low boom, all at once.
  const hit = noise(ac, 0.6);
  const hitGain = ac.createGain();
  hitGain.gain.setValueAtTime(1, t);
  hitGain.gain.exponentialRampToValueAtTime(0.001, t + 0.55);
  hit.connect(hitGain).connect(out);
  hit.start(t);
  const boom = ac.createOscillator();
  boom.type = "sine";
  boom.frequency.setValueAtTime(rand(70, 110), t);
  boom.frequency.exponentialRampToValueAtTime(30, t + 0.7);
  const boomGain = ac.createGain();
  boomGain.gain.setValueAtTime(1, t);
  boomGain.gain.exponentialRampToValueAtTime(0.001, t + 0.8);
  boom.connect(boomGain).connect(out);
  boom.start(t);
  boom.stop(t + 0.8);

  // The scream: 3-4 detuned voices, a rise, a wobble, a fall, through a harsh distortion.
  const shaper = ac.createWaveShaper();
  shaper.curve = distortion(rand(60, 260));
  const band = ac.createBiquadFilter();
  band.type = "bandpass";
  band.frequency.value = rand(1400, 2600);
  band.Q.value = 0.8;
  const voiceGain = ac.createGain();
  voiceGain.gain.setValueAtTime(0.0001, t);
  voiceGain.gain.exponentialRampToValueAtTime(0.9, t + 0.04);
  voiceGain.gain.setValueAtTime(0.9, t + dur * 0.75);
  voiceGain.gain.exponentialRampToValueAtTime(0.001, t + dur);
  shaper.connect(band).connect(voiceGain).connect(out);
  const base = rand(520, 1100);
  const wobble = ac.createOscillator();
  wobble.frequency.value = rand(5, 12);
  const wobbleDepth = ac.createGain();
  wobbleDepth.gain.value = rand(30, 110);
  wobble.connect(wobbleDepth);
  const voices = 3 + Math.floor(Math.random() * 2);
  for (let i = 0; i < voices; i++) {
    const o = ac.createOscillator();
    o.type = i % 2 ? "sawtooth" : "square";
    const f = base * (1 + (i - 1) * rand(0.01, 0.04));
    o.frequency.setValueAtTime(f * 0.7, t);
    o.frequency.exponentialRampToValueAtTime(f * rand(1.3, 1.8), t + rand(0.15, 0.35));
    o.frequency.exponentialRampToValueAtTime(f * rand(0.6, 0.9), t + dur);
    wobbleDepth.connect(o.frequency);
    o.connect(shaper);
    o.start(t);
    o.stop(t + dur);
  }
  // A breathy hiss on top makes it sound like a throat, not a synth.
  const hiss = noise(ac, dur);
  const hissFilter = ac.createBiquadFilter();
  hissFilter.type = "highpass";
  hissFilter.frequency.value = 3000;
  const hissGain = ac.createGain();
  hissGain.gain.setValueAtTime(0.5, t);
  hissGain.gain.exponentialRampToValueAtTime(0.001, t + dur);
  hiss.connect(hissFilter).connect(hissGain).connect(out);
  hiss.start(t);
  wobble.start(t);
  wobble.stop(t + dur);
  try {
    navigator.vibrate?.([300, 80, 500]);
  } catch {
    /* no vibration motor */
  }
}
