import { useEffect, useRef, useState } from "react";
import { Btn, Card, ShowHead, initials, nameOf } from "../components/ui";
import { useOnChange, useReducedMotion, useShow } from "../components/fx";
import { Drawing, ERASER, Sketch, usePress } from "../components/sketch";
import { useCountdown } from "../lib/useRoom";
import { sfx } from "../lib/sfx";
import type { TelephoneView, TpPage } from "../types";

interface Props {
  view: TelephoneView;
  you: string;
  receivedAt: number;
  send: (msg: Record<string, unknown>) => void;
  /** read-only big screen (TV and audience) */
  tv?: boolean;
}

type Send = Props["send"];
const MAX_TEXT = 80;
const STEP_SIGN: Record<string, string> = {
  write: "Write something silly",
  draw: "Draw it!",
  describe: "What is this?",
};

export function Telephone({ view, you, receivedAt, send, tv = false }: Props) {
  const show = useShow();
  const name = (id: string) => nameOf(view.players, id);
  const task = tv ? null : view.task;

  useOnChange(view.phase, (_, phase) => {
    if (phase === "draw" && task) {
      sfx.pop();
      show.stinger("DRAW IT!");
    } else if (phase === "describe" && task) {
      sfx.pop();
      show.stinger("WHAT IS IT?");
    } else if (phase === "album") {
      sfx.fanfare();
      show.stinger("ALBUM TIME!");
    } else if (phase === "final") {
      sfx.fanfare();
      show.stinger("THAT'S THE GAME!");
      show.celebrate();
    }
  });

  const playing = view.phase === "write" || view.phase === "draw" || view.phase === "describe";
  const step = `Step ${view.round} of ${view.rounds}`;
  const sign =
    view.phase === "final"
      ? "Final scores"
      : view.phase === "album"
        ? `Book ${view.album!.book + 1} of ${view.album!.books} · ${name(view.album!.owner)}’s book`
        : `${step} · ${task ? (task.done ? "Done! Waiting for the others" : STEP_SIGN[view.phase]) : STEP_SIGN[view.phase]}`;

  return (
    <div className="seg-telephone stack">
      {show.node}
      <ShowHead sign={sign} title="Draw Telephone" remaining={view.remaining} receivedAt={receivedAt} />
      {playing && task && task.kind === "draw" && <DrawTask view={view} send={send} />}
      {playing && task && task.kind !== "draw" && (
        <TextTask key={`${view.phase}:${view.round}`} view={view} send={send} receivedAt={receivedAt} />
      )}
      {playing && tv && <TvStep view={view} />}
      {playing && <Progress view={view} you={you} tv={tv} />}
      {view.phase === "album" && <Album view={view} you={you} send={send} tv={tv} />}
      {view.phase === "final" && <Final view={view} you={you} send={send} tv={tv} />}
    </div>
  );
}

/** Write the first sentence, or describe the drawing you were handed. */
function TextTask({ view, send, receivedAt }: { view: TelephoneView; send: Send; receivedAt: number }) {
  const task = view.task!;
  const [text, setText] = useState(task.text ?? "");
  const left = useCountdown(view.remaining, receivedAt);
  const clean = text.trim().replace(/\s+/g, " ");
  const sent = task.done && clean === task.text;
  const submit = () => {
    if (clean && clean !== task.text) send({ t: "act", a: "text", text: clean });
  };
  // Out of time: whatever is typed goes in (as Gartic Phone does).
  useEffect(() => {
    if (left !== null && left <= 1 && clean && clean !== task.text) submit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left]);
  const describe = task.kind === "describe";
  return (
    <Card tone={describe ? "plain" : "stage"} className={describe ? "" : "center"}>
      {describe && task.drawing && (
        <>
          <p className="sign">{nameOf(view.players, task.from!)} drew this. What is it?</p>
          <div className="space-top">
            <Drawing id={task.drawing} send={send} label={`${nameOf(view.players, task.from!)}’s drawing`} />
          </div>
        </>
      )}
      {!describe && (
        <>
          <p className="sign">Start your book</p>
          <p className="lead space-top">Write a sentence for the next player to draw.</p>
        </>
      )}
      <form
        className="tp-entry space-top"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label className="sr-only" htmlFor="tp-text">
          {describe ? "Describe the drawing" : "Your sentence"}
        </label>
        <input
          id="tp-text"
          className="tp-input"
          type="text"
          autoComplete="off"
          enterKeyHint="done"
          maxLength={MAX_TEXT}
          placeholder={describe ? "It's a…" : "Type your sentence"}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Btn type="submit" variant="go" disabled={!clean || sent}>
          {sent ? "Sent ✓" : "Done"}
        </Btn>
      </form>
      {!describe && task.idea && !clean && (
        <div className="tp-idea space-top">
          <p>
            Stuck? Try <q>{task.idea}</q>
          </p>
          <Btn variant="ghost" size="small" onClick={() => setText(task.idea!)}>
            💡 Use it
          </Btn>
        </div>
      )}
      <p className="muted space-top" aria-live="polite">
        {sent ? "Sent! You can still change it until everyone is done." : `Up to ${MAX_TEXT} characters.`}
      </p>
    </Card>
  );
}

function DrawTask({ view, send }: { view: TelephoneView; send: Send }) {
  const task = view.task!;
  const press = usePress(); // the first tap after a stroke can lose its click on phones
  const [colour, setColour] = useState(0);
  const [size, setSize] = useState(1);
  useEffect(() => setColour((c) => (c === ERASER ? 0 : c)), [view.round]);
  return (
    <div className="dg-layout tp-draw">
      <div className="dg-stage">
        <Card tone="stage" className="center tp-prompt">
          <p className="sign">Draw this</p>
          <p className="tp-prompt-text">“{task.prompt}”</p>
          <p className="muted">from {nameOf(view.players, task.from!)}</p>
        </Card>
        <Sketch
          ink={view.ink}
          drawing={!task.done}
          send={send}
          label="Your drawing (done)"
          pen={{ colour, size, setColour, setSize }}
        />
      </div>
      <div className="dg-side">
        <Card className="center">
          {task.done ? (
            <>
              <p className="lead">✅ Done! Waiting for the others…</p>
              <Btn variant="ghost" className="space-top" {...press(() => send({ t: "act", a: "done", done: false }))}>
                ✏️ Keep drawing
              </Btn>
            </>
          ) : (
            <>
              <p className="muted">No letters or numbers!</p>
              <Btn variant="go" size="big" className="space-top" {...press(() => send({ t: "act", a: "done" }))}>
                I’m done ✓
              </Btn>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

const TV_STEP: Record<string, [string, string]> = {
  write: ["✍️", "Everyone is writing a silly sentence…"],
  draw: ["🎨", "Everyone is drawing what they were handed…"],
  describe: ["🤔", "Everyone is guessing what a drawing shows…"],
};

function TvStep({ view }: { view: TelephoneView }) {
  const [icon, text] = TV_STEP[view.phase] ?? ["📞", ""];
  return (
    <Card tone="stage" className="center tp-tv-step">
      <p className="tp-tv-icon" aria-hidden="true">
        {icon}
      </p>
      <p className="tp-tv-text">{text}</p>
      <p className="muted">The album comes after step {view.rounds}: every book, page by page.</p>
    </Card>
  );
}

/** Who has finished this step. */
function Progress({ view, you, tv }: { view: TelephoneView; you: string; tv: boolean }) {
  const waiting = view.order.filter((p) => !view.done.includes(p));
  return (
    <Card className={tv ? "tp-progress big" : "tp-progress"}>
      <h3>
        {view.done.length} of {view.order.length} done
      </h3>
      <ul className="tp-people">
        {view.order.map((p) => {
          const done = view.done.includes(p);
          return (
            <li key={p} className={done ? "done" : ""}>
              <span aria-hidden="true">{done ? "✅" : view.phase === "draw" ? "✏️" : "💭"}</span>{" "}
              <b>
                {nameOf(view.players, p)}
                {p === you ? " (you)" : ""}
              </b>
              <span className="sr-only">{done ? " done" : " still going"}</span>
            </li>
          );
        })}
      </ul>
      {waiting.length > 0 && waiting.length < view.order.length && (
        <p className="muted space-top">
          Waiting for {waiting.length === 1 ? nameOf(view.players, waiting[0]!) : `${waiting.length} players`}…
        </p>
      )}
    </Card>
  );
}

function Page({
  page,
  players,
  you,
  send,
  tv,
  where,
  replay,
  tone,
  fresh = false,
}: {
  page: TpPage;
  players: TelephoneView["players"];
  you: string;
  send: Send;
  tv: boolean;
  where: { book: number; entry: number };
  replay: boolean;
  tone: number;
  fresh?: boolean;
}) {
  const who = nameOf(players, page.by);
  const mine = page.by === you;
  const what = page.kind === "drawing" ? `${who}’s drawing` : `${who}’s words`;
  return (
    <li className={`tp-page ${page.kind} ${where.entry % 2 ? "right" : "left"} ${fresh ? "fresh" : ""}`}>
      <p className="tp-who">
        <span className={`tp-avatar tone-${tone % 8}`} aria-hidden="true">
          {initials(who)}
        </span>
        <span className="tp-who-text">
          <b>{who}</b> {page.kind === "drawing" ? "drew" : where.entry === 0 ? "wrote" : "thought it was"}
        </span>
      </p>
      {page.kind === "drawing" && page.drawing ? (
        <Drawing id={page.drawing} send={send} label={what} replay={replay} />
      ) : (
        <p className="tp-bubble">{page.text}</p>
      )}
      <div className="tp-like-row">
        {tv || mine ? (
          <span className="tp-likes" aria-label={`${page.likes} likes`}>
            ♥ {page.likes}
          </span>
        ) : (
          <button
            type="button"
            className="tp-like"
            aria-pressed={page.liked}
            aria-label={`Like ${what} (${page.likes} likes)`}
            onClick={() => send({ t: "act", a: "like", ...where })}
          >
            <span aria-hidden="true">{page.liked ? "♥" : "♡"}</span> {page.likes}
          </button>
        )}
      </div>
    </li>
  );
}

function Album({ view, you, send, tv }: { view: TelephoneView; you: string; send: Send; tv: boolean }) {
  const album = view.album!;
  const reduced = useReducedMotion();
  const newest = useRef<HTMLDivElement>(null);
  const n = view.order.length;
  const done = album.entry === n - 1;
  const first = album.pages[0];
  const last = album.pages[album.pages.length - 1];
  useOnChange(album.pages.length, (prev, next) => {
    if (next > prev) sfx.pop();
  });
  useOnChange(done, (was, now) => {
    if (now && !was) sfx.fanfare();
  });
  useEffect(() => {
    if (!tv) newest.current?.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
  }, [album.pages.length, album.book, tv, reduced]);
  return (
    <Card className={`tp-album ${tv ? "big" : ""}`}>
      <div className="tp-cover">
        <span className={`tp-avatar big tone-${view.order.indexOf(album.owner) % 8}`} aria-hidden="true">
          {initials(nameOf(view.players, album.owner))}
        </span>
        <div className="tp-cover-text">
          <h3>{nameOf(view.players, album.owner)}’s book</h3>
          <ol className="tp-dots" aria-label={`Page ${album.entry + 1} of ${n}`}>
            {view.order.map((_, i) => (
              <li key={i} className={i < album.entry ? "seen" : i === album.entry ? "now" : ""} />
            ))}
          </ol>
        </div>
      </div>
      <ol className={`tp-pages tp-thread ${tv ? "big" : ""}`}>
        {album.pages
          .map((pg, i) => ({ pg, i }))
          .slice(tv ? -2 : 0)
          .map(({ pg, i }) => (
            <Page
              key={`${album.book}:${i}`}
              page={pg}
              players={view.players}
              you={you}
              send={send}
              tv={tv}
              where={{ book: album.book, entry: i }}
              replay={i === album.pages.length - 1}
              tone={view.order.indexOf(pg.by)}
              fresh={i === album.pages.length - 1}
            />
          ))}
      </ol>
      {done && first?.kind === "text" && last?.kind === "text" && album.pages.length > 1 && (
        <p className="tp-punch" role="status">
          From <q>{first.text}</q> to <q>{last.text}</q>
        </p>
      )}
      <div ref={newest} />
    </Card>
  );
}

function Final({ view, you, send, tv }: { view: TelephoneView; you: string; send: Send; tv: boolean }) {
  const [book, setBook] = useState(0);
  const books = view.books ?? [];
  const ranked = [...view.players].sort((a, b) => (view.scores[b.id] ?? 0) - (view.scores[a.id] ?? 0));
  const top = ranked[0] ? (view.scores[ranked[0].id] ?? 0) : 0;
  const shown = books[book];
  return (
    <div className={tv ? "tp-final big" : "tp-final"}>
      <Card>
        <h3>Standings</h3>
        <ul className="score-rows">
          {ranked.map((p) => (
            <li key={p.id}>
              <b>
                {top > 0 && (view.scores[p.id] ?? 0) === top ? "👑 " : ""}
                {p.name}
                {p.id === you ? " (you)" : ""}
              </b>
              <span className="score-pts">{view.scores[p.id] ?? 0}</span>
            </li>
          ))}
        </ul>
        <p className="muted space-top">Every like is 100 points. You can still like pages.</p>
      </Card>
      <Card>
        <h3>The books</h3>
        <div className="tp-tabs" role="group" aria-label="Choose a book">
          {books.map((b, i) => (
            <button key={b.owner} type="button" className="tp-tab" aria-pressed={i === book} onClick={() => setBook(i)}>
              {nameOf(view.players, b.owner)}
            </button>
          ))}
        </div>
        {shown && (
          <ol className="tp-pages tp-thread space-top">
            {shown.pages.map((pg, i) => (
              <Page
                key={`${book}:${i}`}
                page={pg}
                players={view.players}
                you={you}
                send={send}
                tv={tv}
                where={{ book, entry: i }}
                replay={false}
                tone={view.order.indexOf(pg.by)}
              />
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
