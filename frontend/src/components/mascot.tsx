/** Bop, the show's host: a retro TV with a face, antennae and a microphone. Drawn here as SVG (no
 * image download); it blinks and bobs, and holds still for reduced motion. `mood` changes the face. */
export function Mascot({ size = 160, mood = "happy", className = "" }: { size?: number; mood?: "happy" | "wow" | "sleepy"; className?: string }) {
  return (
    <svg
      className={`mascot ${className}`}
      width={size}
      height={size}
      viewBox="0 0 200 200"
      role="img"
      aria-label="Bop, the Snazzlebop host"
    >
      <g className="mascot-body">
        {/* antennae */}
        <path className="mascot-ink" d="M84 46 66 14" stroke="#2b1b33" strokeWidth="6" strokeLinecap="round" />
        <path className="mascot-ink" d="M116 46 138 10" stroke="#2b1b33" strokeWidth="6" strokeLinecap="round" />
        <circle className="mascot-bulb" cx="66" cy="14" r="9" fill="#f2b705" stroke="#2b1b33" strokeWidth="5" />
        <circle className="mascot-bulb b2" cx="138" cy="10" r="9" fill="#ff6b2c" stroke="#2b1b33" strokeWidth="5" />
        {/* legs */}
        <path className="mascot-ink" d="M76 168v18M124 168v18" stroke="#2b1b33" strokeWidth="8" strokeLinecap="round" />
        {/* cabinet */}
        <rect x="22" y="44" width="156" height="128" rx="30" fill="#ff6b2c" stroke="#2b1b33" strokeWidth="6" />
        <rect x="30" y="52" width="140" height="22" rx="11" fill="#fff" opacity=".22" />
        {/* screen */}
        <rect x="40" y="62" width="104" height="92" rx="22" fill="#2b1239" stroke="#2b1b33" strokeWidth="6" />
        <rect x="50" y="70" width="40" height="12" rx="6" fill="#fff" opacity=".14" />
        {/* dials */}
        <circle cx="160" cy="88" r="8" fill="#ffe7a1" stroke="#2b1b33" strokeWidth="4" />
        <circle cx="160" cy="114" r="8" fill="#0b7476" stroke="#2b1b33" strokeWidth="4" />
        <path d="M152 136h16M152 146h16" stroke="#2b1b33" strokeWidth="4" strokeLinecap="round" />
        {/* face */}
        <g className="mascot-eyes">
          {mood === "sleepy" ? (
            <>
              <path d="M66 104q8 6 16 0M102 104q8 6 16 0" stroke="#ffe7a1" strokeWidth="5" fill="none" strokeLinecap="round" />
            </>
          ) : (
            <>
              <ellipse cx="74" cy="102" rx="9" ry={mood === "wow" ? 12 : 11} fill="#ffe7a1" />
              <ellipse cx="110" cy="102" rx="9" ry={mood === "wow" ? 12 : 11} fill="#ffe7a1" />
              <circle cx="76" cy="99" r="3.5" fill="#2b1239" />
              <circle cx="112" cy="99" r="3.5" fill="#2b1239" />
            </>
          )}
        </g>
        {mood === "wow" ? (
          <ellipse cx="92" cy="132" rx="9" ry="11" fill="#c8203a" stroke="#ffe7a1" strokeWidth="3" />
        ) : (
          <path d="M74 126q18 18 36 0" stroke="#ffe7a1" strokeWidth="5" fill="none" strokeLinecap="round" />
        )}
        <circle cx="62" cy="122" r="5" fill="#ff6b2c" opacity=".55" />
        <circle cx="122" cy="122" r="5" fill="#ff6b2c" opacity=".55" />
        {/* the arm and the microphone */}
        <g className="mascot-mic">
          <path className="mascot-ink" d="M22 120q-16 6-12 30" stroke="#2b1b33" strokeWidth="7" fill="none" strokeLinecap="round" />
          <rect x="2" y="146" width="16" height="26" rx="6" fill="#2b1b33" />
          <circle cx="10" cy="146" r="11" fill="#cdb6d6" stroke="#2b1b33" strokeWidth="5" />
        </g>
      </g>
    </svg>
  );
}
