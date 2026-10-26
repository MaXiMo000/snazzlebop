import { useEffect, useRef, type ReactNode } from "react";

/** A modal sheet: slides up from the bottom on phones, a centred card on wider screens. The browser's
 * own <dialog> keeps focus inside it, closes on Esc and returns focus to what opened it; a tap on the
 * dimmed backdrop closes it too. */
export function Sheet({
  open,
  onClose,
  labelledBy,
  className = "",
  children,
}: {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  className?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className={`sheet ${className}`}
      aria-labelledby={labelledBy}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose(); // the backdrop, not the sheet's own content
      }}
    >
      <div className="sheet-body">
        <button type="button" className="sheet-close" aria-label="Close" onClick={onClose}>
          <span aria-hidden="true">✕</span>
        </button>
        {children}
      </div>
    </dialog>
  );
}

/** A section that folds away: a big, labelled summary row, the content under it when opened. */
export function Fold({ icon, title, hint, children, open = false }: { icon: string; title: string; hint?: string; children: ReactNode; open?: boolean }) {
  return (
    <details className="fold" open={open}>
      <summary>
        <span className="fold-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="fold-text">
          <b>{title}</b>
          {hint && <span className="muted">{hint}</span>}
        </span>
        <span className="fold-arrow" aria-hidden="true" />
      </summary>
      <div className="fold-content">{children}</div>
    </details>
  );
}
