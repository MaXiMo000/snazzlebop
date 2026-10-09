import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { LocalVideoTrack, Participant, Room as LkRoom, Track } from "livekit-client";
import { onCallPass, type CallPass } from "../lib/callPass";
import { initials } from "./ui";

type Send = (msg: Record<string, unknown>) => void;
type Phase = "off" | "joining" | "live" | "error";

// One call per page. The LiveKit room lives here (not in React state); screens re-render on `version`.
let room: LkRoom | null = null;
let snap = {
  available: false,
  phase: "off" as Phase,
  error: "",
  expanded: false,
  version: 0,
  tv: false,
  audioBlocked: false,
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
        await r.localParticipant.setMicrophoneEnabled(true);
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
export function CallHost({ available, send, auto }: { available: boolean; send: Send; auto?: boolean }) {
  useEffect(() => {
    set({ available });
  }, [available]);
  useEffect(() => onCallPass((p) => void connect(p)), []);
  // The TV joins on its own (watch only, no sound).
  useEffect(() => {
    if (auto && available && snap.phase === "off") {
      set({ phase: "joining" });
      send({ t: "call" });
    }
  }, [auto, available, send]);
  useEffect(() => {
    joinWith = () => {
      set({ phase: "joining", error: "" });
      send({ t: "call" });
    };
  }, [send]);
  useEffect(() => () => leave(), []);
  return null;
}
let joinWith: () => void = () => undefined;

/** Top-bar button: join the call, or (when in it) show or hide the big view. */
export function CallButton() {
  const s = useCall();
  if (!s.available || s.tv) return null;
  const live = s.phase === "live";
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
    <li className={`call-tile ${p.isSpeaking ? "speaking" : ""} ${big ? "big" : ""}`}>
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
        <span className="call-initials" aria-hidden="true">
          {initials(p.name || "?")}
        </span>
      )}
      {!local && !tv && <audio ref={audio} autoPlay />}
      <span className="call-name">
        {p.isMicrophoneEnabled ? "" : "🔇 "}
        {name}
      </span>
      <span className="sr-only">
        {p.isSpeaking ? ", speaking" : ""}
        {p.isMicrophoneEnabled ? "" : ", muted"}
        {camOn ? ", camera on" : ""}
      </span>
    </li>
  );
}

async function toggleMic() {
  if (!room) return;
  try {
    await room.localParticipant.setMicrophoneEnabled(!room.localParticipant.isMicrophoneEnabled);
  } catch {
    set({ error: "Your microphone is blocked: allow it in the browser settings." });
  }
  bump();
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

/** In the room: the faces strip, controls, and the big view. The TV gets a larger strip, no controls. */
export function CallStrip({ tv = false }: { tv?: boolean }) {
  const s = useCall();
  useEffect(() => {
    if (!s.expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && set({ expanded: false });
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [s.expanded]);
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
      <button
        type="button"
        className="call-ctl"
        aria-pressed={!me.isMicrophoneEnabled}
        onClick={() => void toggleMic()}
      >
        <span aria-hidden="true">{me.isMicrophoneEnabled ? "🎙️" : "🔇"}</span>
        <span className="sr-only">{me.isMicrophoneEnabled ? "Mute" : "Unmute"}</span>
      </button>
      <button type="button" className="call-ctl" aria-pressed={me.isCameraEnabled} onClick={() => void toggleCam()}>
        <span aria-hidden="true">{me.isCameraEnabled ? "📷" : "📷"}</span>
        <span className="sr-only">{me.isCameraEnabled ? "Turn camera off" : "Turn camera on"}</span>
        {!me.isCameraEnabled && <span className="call-slash" aria-hidden="true" />}
      </button>
      {mobile && me.isCameraEnabled && (
        <button type="button" className="call-ctl" onClick={() => void flipCam()}>
          <span aria-hidden="true">🔄</span>
          <span className="sr-only">Switch camera</span>
        </button>
      )}
      <button
        type="button"
        className="call-ctl"
        aria-pressed={s.expanded}
        onClick={() => set({ expanded: !s.expanded })}
      >
        <span aria-hidden="true">{s.expanded ? "🗗" : "⛶"}</span>
        <span className="sr-only">{s.expanded ? "Smaller view" : "Big view"}</span>
      </button>
      <button type="button" className="call-ctl leave" onClick={leave}>
        <span aria-hidden="true">📵</span>
        <span className="sr-only">Leave the call</span>
      </button>
    </div>
  );
  return (
    <>
      <section className={`call-strip ${tv ? "tv" : ""}`} aria-label={`Call: ${everyone.length} in the call`}>
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
