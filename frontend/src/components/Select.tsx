import { createPortal } from "react-dom";
import {
  Children,
  isValidElement,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

interface Item {
  value: string;
  label: ReactNode;
  text: string;
}

function text(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<{ children?: ReactNode }>(node))
    return text(node.props.children);
  return "";
}

function items(children: ReactNode): Item[] {
  const out: Item[] = [];
  Children.forEach(children, (child) => {
    if (Array.isArray(child)) {
      out.push(...items(child));
      return;
    }
    if (!isValidElement(child)) return;
    const el = child as ReactElement<{
      value?: string | number;
      children?: ReactNode;
    }>;
    const value = String(el.props.value ?? text(el.props.children));
    out.push({
      value,
      label: el.props.children,
      text: text(el.props.children),
    });
  });
  return out;
}

/**
 * A themed drop-down that behaves like a native <select> to its callers: same `id`, `value`,
 * `onChange(e)` with `e.target.value`, and <option> children. The list is our own (not the phone's
 * system picker), works with the keyboard (arrows, Home/End, letters, Enter, Escape) and screen readers.
 */
export function Select({
  id,
  value,
  onChange,
  children,
  disabled = false,
  "aria-describedby": describedBy,
}: {
  id: string;
  value: string | number;
  onChange: (e: { target: { value: string } }) => void;
  children: ReactNode;
  disabled?: boolean;
  "aria-describedby"?: string;
}) {
  const list = items(children);
  const current = list.findIndex((i) => i.value === String(value));
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(Math.max(0, current));
  const [pos, setPos] = useState<{
    left: number;
    width: number;
    top?: number;
    bottom?: number;
    max: number;
  } | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  const typed = useRef({ text: "", at: 0 });

  const choose = (i: number) => {
    const item = list[i];
    if (item) onChange({ target: { value: item.value } });
    setOpen(false);
    button.current?.focus();
  };

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!wrap.current?.contains(t) && !listRef.current?.contains(t))
        setOpen(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);

  // The list floats above the page (so no card can clip it), under the button, or above it when
  // there isn't room below (a list near the bottom of a phone screen). It follows scrolling.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const b = button.current;
      if (!b) return;
      const r = b.getBoundingClientRect();
      const below = window.innerHeight - r.bottom - 12;
      const above = r.top - 12;
      const want = Math.min(320, list.length * 50 + 16);
      const up = below < want && above > below;
      setPos(
        up
          ? {
              left: r.left,
              width: r.width,
              bottom: window.innerHeight - r.top + 8,
              max: Math.min(320, above),
            }
          : {
              left: r.left,
              width: r.width,
              top: r.bottom + 8,
              max: Math.min(320, Math.max(below, 140)),
            },
      );
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, list.length]);

  // Position through the CSSOM (allowed by our CSP), not a style= attribute.
  useLayoutEffect(() => {
    const el = listRef.current;
    if (!el || !pos) return;
    el.style.left = `${pos.left}px`;
    el.style.width = `${pos.width}px`;
    el.style.top = pos.top === undefined ? "auto" : `${pos.top}px`;
    el.style.bottom = pos.bottom === undefined ? "auto" : `${pos.bottom}px`;
    el.style.maxHeight = `${pos.max}px`;
  }, [pos]);

  useEffect(() => {
    if (open && pos) listRef.current?.focus({ preventScroll: true });
  }, [open, pos === null]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-i="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const openAt = (i: number) => {
    setActive(i < 0 ? 0 : i);
    setOpen(true);
  };

  const onKey = (e: React.KeyboardEvent) => {
    const last = list.length - 1;
    const move = (i: number) => {
      e.preventDefault();
      if (!open) openAt(i);
      else setActive(Math.max(0, Math.min(last, i)));
    };
    switch (e.key) {
      case "ArrowDown":
        return move(open ? active + 1 : current);
      case "ArrowUp":
        return move(open ? active - 1 : current);
      case "Home":
        return move(0);
      case "End":
        return move(last);
      case "Enter":
      case " ":
        e.preventDefault();
        if (open) choose(active);
        else openAt(current);
        return;
      case "Escape":
        if (open) {
          e.preventDefault();
          setOpen(false);
          button.current?.focus();
        }
        return;
      case "Tab":
        setOpen(false);
        return;
      default:
        if (e.key.length === 1 && /\S/.test(e.key)) {
          const now = Date.now();
          typed.current = {
            text:
              (now - typed.current.at < 700 ? typed.current.text : "") +
              e.key.toLowerCase(),
            at: now,
          };
          const hit = list.findIndex((i) =>
            i.text.toLowerCase().startsWith(typed.current.text),
          );
          if (hit >= 0) move(hit);
        }
    }
  };

  return (
    <div className={`select ${open ? "open" : ""}`} ref={wrap}>
      <button
        id={id}
        ref={button}
        type="button"
        className="select-button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-describedby={describedBy}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openAt(current))}
        onKeyDown={onKey}
      >
        <span className="select-value">{list[current]?.label ?? ""}</span>
        <span className="select-caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open &&
        pos &&
        createPortal(
          <ul
            id={listId}
            ref={listRef}
            className="select-list"
            role="listbox"
            tabIndex={-1}
            aria-labelledby={id}
            aria-activedescendant={`${listId}-${active}`}
            onKeyDown={onKey}
          >
            {list.map((item, i) => (
              <li
                key={item.value}
                id={`${listId}-${i}`}
                data-i={i}
                role="option"
                aria-selected={i === current}
                className={`${i === active ? "active" : ""} ${i === current ? "chosen" : ""}`}
                onPointerEnter={() => setActive(i)}
                onClick={() => choose(i)}
              >
                <span>{item.label}</span>
                {i === current && (
                  <span className="select-tick" aria-hidden="true">
                    ✓
                  </span>
                )}
              </li>
            ))}
          </ul>,
          document.body,
        )}
    </div>
  );
}
