import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { LocalVideoTrack, Participant, Room as LkRoom, Track } from "livekit-client";
import { onCallPass, type CallPass } from "../lib/callPass";
import { Avatar } from "./avatar";

type Send = (msg: Record<string, unknown>) => void;
type Phase = "off" | "joining" | "live" | "error";

// One call per page. The LiveKit room lives here (not in React state); screens re-render on `version`.
let room: LkRoom | null = null;
let snap = {
  available: false,
  allowed: false,
  phase: "off" as Phase,
  error: "",
  expanded: false,
  version: 0,
  tv: false,
  audioBlocked: false,
  host: false,
  ptt: false, // push-to-talk: the microphone is only open while the talk button (or Space) is held
  talking: false,
};
const subs = new Set<() => void>();
const set = (next: Partial<typeof snap>) => {
  snap = { ...snap, ...next, version: snap.version + 1 };
  for (const fn of subs) fn();
};
const bump = () => set({});
const useCall = () =>
  useSyncExternalStore(
    (fn) => {
      subs.add(fn);
      return () => void subs.delete(fn);
    },
    () => snap,
  );

/** Join with a pass from our server. LiveKit's client is only downloaded now, not for everyone. */
async function connect(pass: CallPass) {
  try {
    const lk = await import("livekit-client");
    const r = new lk.Room({
      adaptiveStream: true, // each tile gets the resolution it's shown at
      dynacast: true, // nobody watching a layer: it isn't sent
      audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      videoCaptureDefaults: { resolution: lk.VideoPresets.h540.resolution, facingMode: "user" },
      publishDefaults: {
        simulcast: true,
        videoSimulcastLayers: [lk.VideoPresets.h180, lk.VideoPresets.h360],
        dtx: true, // silence costs nothing
        red: true, // redundant audio: survives packet loss
      },
    });
    const events = [
      lk.RoomEvent.ParticipantConnected,
      lk.RoomEvent.ParticipantDisconnected,
      lk.RoomEvent.TrackSubscribed,
      lk.RoomEvent.TrackUnsubscribed,
      lk.RoomEvent.TrackMuted,
      lk.RoomEvent.TrackUnmuted,
      lk.RoomEvent.LocalTrackPublished,
      lk.RoomEvent.LocalTrackUnpublished,
      lk.RoomEvent.ActiveSpeakersChanged,
      lk.RoomEvent.ConnectionStateChanged,
    ];
    for (const e of events) r.on(e, bump);
    r.on(lk.RoomEvent.AudioPlaybackStatusChanged, () => set({ audioBlocked: !r.canPlaybackAudio }));
    r.on(lk.RoomEvent.Disconnected, () => {
      if (room === r) {
        room = null;
        set({ phase: "off", expanded: false });
      }
    });
    room = r;
    if (import.meta.env.DEV) Object.assign(window, { __call: r }); // dev tools: inspect the live call
    await r.connect(pass.url, pass.token);
    set({ phase: "live", tv: pass.tv, audioBlocked: !pass.tv && !r.canPlaybackAudio });
    if (!pass.tv) {
      try {
        await r.localParticipant.setMicrophoneEnabled(!snap.ptt);
      } catch {
        set({ error: "Your microphone is blocked: allow it in the browser to talk (you can still listen)." });
      }
    }
  } catch {
    room?.disconnect();
    room = null;
    set({ phase: "error", error: "Couldn't join the call. Check your connection and try again." });
  }
}

function leave() {
  room?.disconnect();
  room = null;
  set({ phase: "off", expanded: false, error: "" });
}

/** Mounted by the room page: knows whether calls exist, asks for passes, joins. */
export function CallHost({
  available,
  allowed,
  hush = 0,
  host = false,
  send,
  auto,
}: {
  available: boolean;
  allowed: boolean;
  hush?: number;
  host?: boolean;
  send: Send;
  auto?: boolean;
}) {
  useEffect(() => {
    set({ available, allowed, host });
  }, [available, allowed, host]);
  // The host muted everyone: each screen closes its own microphone (unmute again when you like).
  const heard = useRef(hush);
  useEffect(() => {
    if (hush === heard.current) return;
    heard.current = hush;
    if (!room || snap.tv || !room.localParticipant.isMicrophoneEnabled) return;
    void room.localParticipant.setMicrophoneEnabled(false).then(bump);
    set({ error: "The host muted everyone. Unmute when you want to talk." });
  }, [hush]);
  useEffect(() => onCallPass((p) => void connect(p)), []);
  // The TV joins on its own (watch only, no sound).
  useEffect(() => {
    if (auto && available && allowed && snap.phase === "off") {
      set({ phase: "joining" });
      send({ t: "call" });
    }
  }, [auto, available, allowed, send]);
  useEffect(() => {
    joinWith = () => {
      set({ phase: "joining", error: "" });
      send({ t: "call" });
    };
    hushAll = () => send({ t: "hush" });
  }, [send]);
  useEffect(() => () => leave(), []);
  return null;
}
let joinWith: () => void = () => undefined;
let hushAll: () => void = () => undefined;

/** Top-bar button: join the call, or (when in it) show or hide the big view. */
export function CallButton({ go }: { go: (path: string) => void }) {
  const s = useCall();
  if (!s.available || s.tv) return null;
  const live = s.phase === "live";
  // Calls are for signed-in accounts: a guest's button leads to sign-in (their seat is kept).
  if (!s.allowed)
    return (
      <a
        className="btn ghost call-button"
        href="/account"
        aria-label="Sign in to join the voice and video call"
        onClick={(e) => {
          e.preventDefault();
          go("/account");
        }}
      >
        <span aria-hidden="true">🔒</span>
        <span className="btn-label">Call</span>
      </a>
    );
  return (
    <button
      type="button"
      className={`btn ghost call-button ${live ? "live" : ""}`}
      aria-label={
        live ? "Call: show everyone" : s.phase === "joining" ? "Joining the call" : "Join the voice and video call"
      }
      disabled={s.phase === "joining"}
      onClick={() => (live ? set({ expanded: !s.expanded }) : joinWith())}
    >
      <span aria-hidden="true">📞</span>
      <span className="btn-label">{live ? "Live" : "Call"}</span>
      {live && <span className="call-dot" aria-hidden="true" />}
    </button>
  );
}

function people(): { p: Participant; local: boolean }[] {
  if (!room) return [];
  return [
    { p: room.localParticipant as Participant, local: true },
    ...[...room.remoteParticipants.values()].map((p) => ({ p: p as Participant, local: false })),
  ].filter(({ p }) => !p.identity.startsWith("tv:")); // TV screens watch; they aren't people in the call
}

// Line icons, drawn on a 24px grid.
const MIC = "M9 6a3 3 0 0 1 6 0v5a3 3 0 0 1-6 0ZM6 11a6 6 0 0 0 12 0M12 17v4";
const CAM = "M5 7h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2ZM15 11l6-3v8l-6-3";
const SLASH = "M4 4l16 16";
const ICONS = {
  mic: [MIC],
  micOff: [MIC, SLASH],
  cam: [CAM],
  camOff: [CAM, SLASH],
  flip: ["M4 12a8 8 0 0 1 14-5M20 4v4h-4M20 12a8 8 0 0 1-14 5M4 20v-4h4"],
  grow: ["M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"],
  shrink: ["M9 4v5H4M20 9h-5V4M15 20v-5h5M4 15h5v5"],
  hush: ["M4 10v4h3l5 4V6l-5 4ZM16 9l5 6M21 9l-5 6"],
  leave: ["M4 15c4.5-4.7 11.5-4.7 16 0l-2 2.5-3.5-1.5v-3a9 9 0 0 0-5 0v3L6 17.5Z"],
  talk: ["M9.5 12a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0M7 7a7 7 0 0 0 0 10M17 7a7 7 0 0 1 0 10"],
} as const;

function Icon({ name }: { name: keyof typeof ICONS }) {
  return (
    <svg className="call-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {ICONS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

function Tile({ p, local, tv, big }: { p: Participant; local: boolean; tv: boolean; big: boolean }) {
  const video = useRef<HTMLVideoElement>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const s = useCall();
  const cam = p.getTrackPublication("camera" as Track.Source)?.track;
  const mic = p.getTrackPublication("microphone" as Track.Source)?.track;
  const camOn = !!cam && p.isCameraEnabled;
  useEffect(() => {
    const el = video.current;
    if (!cam || !el) return;
    cam.attach(el);
    return () => void cam.detach(el);
  }, [cam, s.version]);
  useEffect(() => {
    const el = audio.current;
    if (local || tv || !mic || !el) return; // never play yourself back, and the TV stays silent
    mic.attach(el);
    return () => void mic.detach(el);
  }, [mic, local, tv]);
  const name = local ? "You" : p.name || "Guest";
  return (
    <li className={`call-tile ${p.isSpeaking ? "speaking" : ""} ${big ? "big" : ""} ${camOn ? "video" : ""}`}>
      <span className="call-face">
        {camOn ? (
          <video
            ref={video}
            className={`call-video ${local ? "mirror" : ""}`}
            autoPlay
            playsInline
            muted
            aria-hidden="true"
          />
        ) : (
          <Avatar pid={p.identity} name={p.name || "?"} className="call-avatar" />
        )}
        {!p.isMicrophoneEnabled && (
          <span className="call-muted" aria-hidden="true">
            <Icon name="micOff" />
          </span>
        )}
      </span>
      {!local && !tv && <audio ref={audio} autoPlay />}
      <span className="call-name">{name}</span>
      <span className="sr-only">
        {p.isSpeaking ? ", speaking" : ""}
        {p.isMicrophoneEnabled ? "" : ", muted"}
        {camOn ? ", camera on" : ""}
      </span>
    </li>
  );
}

async function setMic(on: boolean) {
  if (!room) return;
  try {
    await room.localParticipant.setMicrophoneEnabled(on);
  } catch {
    set({ error: "Your microphone is blocked: allow it in the browser settings." });
  }
  bump();
}
const toggleMic = () => {
  set({ error: "" });
  return setMic(!room?.localParticipant.isMicrophoneEnabled);
};
function togglePtt() {
  const ptt = !snap.ptt;
  set({ ptt, talking: false, error: "" });
  void setMic(!ptt);
}
function talk(on: boolean) {
  if (!snap.ptt || snap.talking === on) return;
  set({ talking: on });
  void setMic(on);
}
async function toggleCam() {
  if (!room) return;
  try {
    await room.localParticipant.setCameraEnabled(!room.localParticipant.isCameraEnabled);
  } catch {
    set({ error: "Your camera is blocked or in use: allow it in the browser settings." });
  }
  bump();
}
let facing: "user" | "environment" = "user";
async function flipCam() {
  const track = room?.localParticipant.getTrackPublication("camera" as Track.Source)?.track as
    LocalVideoTrack | undefined;
  if (!track) return;
  facing = facing === "user" ? "environment" : "user";
  await track.restartTrack({ facingMode: facing }).catch(() => undefined);
  bump();
}

function Ctl({
  icon,
  label,
  onClick,
  pressed,
  className = "",
}: {
  icon: keyof typeof ICONS;
  label: string;
  onClick: () => void;
  pressed?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={`call-ctl ${className}`}
      aria-pressed={pressed}
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      <Icon name={icon} />
    </button>
  );
}

/** In the room: the voice bar (faces, controls) and the big view. The TV gets larger faces, no controls. */
export function CallStrip({ tv = false }: { tv?: boolean }) {
  const s = useCall();
  useEffect(() => {
    if (!s.expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && set({ expanded: false });
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [s.expanded]);
  // Push-to-talk on a keyboard: hold Space (not while typing or on a control).
  const pttOn = s.ptt && s.phase === "live" && !tv;
  useEffect(() => {
    if (!pttOn) return;
    const busy = (e: KeyboardEvent) =>
      e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(e.target.tagName);
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || busy(e)) return;
      e.preventDefault();
      talk(true);
    };
    const up = (e: KeyboardEvent) => e.code === "Space" && talk(false);
    const blur = () => talk(false);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
      talk(false);
    };
  }, [pttOn]);
  const [mobile] = useState(() => typeof navigator !== "undefined" && /Android|iPhone|iPad/i.test(navigator.userAgent));
  if (s.phase === "error" && !tv)
    return (
      <p className="alert calm call-error" role="status">
        {s.error}{" "}
        <button type="button" className="btn small ghost" onClick={() => set({ phase: "off", error: "" })}>
          OK
        </button>
      </p>
    );
  if (s.phase !== "live" || !room) return null;
  const everyone = people();
  const me = room.localParticipant;
  const controls = !tv && (
    <div className="call-controls" role="group" aria-label="Call controls">
      {s.ptt ? (
        <button
          type="button"
          className={`call-talk ${s.talking ? "on" : ""}`}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            talk(true);
          }}
          onPointerUp={() => talk(false)}
          onPointerCancel={() => talk(false)}
          onKeyDown={(e) => (e.key === " " || e.key === "Enter") && !e.repeat && talk(true)}
          onKeyUp={() => talk(false)}
          onContextMenu={(e) => e.preventDefault()}
        >
          <Icon name="mic" />
          <span>{s.talking ? "Talking…" : "Hold to talk"}</span>
        </button>
      ) : (
        <Ctl
          icon={me.isMicrophoneEnabled ? "mic" : "micOff"}
          label={me.isMicrophoneEnabled ? "Mute" : "Unmute"}
          pressed={!me.isMicrophoneEnabled}
          className="warn"
          onClick={() => void toggleMic()}
        />
      )}
      <Ctl
        icon={me.isCameraEnabled ? "cam" : "camOff"}
        label={me.isCameraEnabled ? "Turn camera off" : "Turn camera on"}
        pressed={me.isCameraEnabled}
        onClick={() => void toggleCam()}
      />
      {mobile && me.isCameraEnabled && <Ctl icon="flip" label="Switch camera" onClick={() => void flipCam()} />}
      <Ctl icon="talk" label="Push to talk" pressed={s.ptt} onClick={togglePtt} />
      <Ctl
        icon={s.expanded ? "shrink" : "grow"}
        label={s.expanded ? "Smaller view" : "Big view"}
        pressed={s.expanded}
        onClick={() => set({ expanded: !s.expanded })}
      />
      {s.host && <Ctl icon="hush" label="Mute everyone" onClick={hushAll} />}
      <Ctl icon="leave" label="Leave the call" className="leave" onClick={leave} />
    </div>
  );
  return (
    <>
      <section className={`call-strip ${tv ? "tv" : ""}`} aria-label={`Call: ${everyone.length} in the call`}>
        {!tv && (
          <p className="call-status">
            <span className="call-live-dot" aria-hidden="true" />
            Voice connected · {everyone.length}
          </p>
        )}
        <ul className="call-tiles">
          {everyone.map(({ p, local }) => (
            <Tile key={p.identity} p={p} local={local} tv={tv} big={false} />
          ))}
        </ul>
        {controls}
        {s.audioBlocked && !tv && (
          <button type="button" className="btn small gold" onClick={() => void room?.startAudio().then(bump)}>
            🔊 Tap to hear the call
          </button>
        )}
        {s.error && !tv && <p className="call-note muted">{s.error}</p>}
      </section>
      {s.expanded && !tv && (
        <div className="call-big" role="dialog" aria-label="Everyone in the call">
          <ul className="call-grid">
            {everyone.map(({ p, local }) => (
              <Tile key={p.identity} p={p} local={local} tv={false} big />
            ))}
          </ul>
          {controls}
        </div>
      )}
    </>
  );
}
