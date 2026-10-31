import { useId, type ReactNode } from "react";

/* Cosmetics drawn on the device: animated avatar frames, animated characters and victory animations.
 * Everything is inline SVG and CSS (styles/87-cosmetics.css), so nothing is downloaded. The server
 * (backend app/progress.py LOOKS) decides who may wear what; these only draw an id. Every animation is
 * transform or opacity only, and the resting state (what reduced motion shows) is a complete picture. */

// Frames sit on a 140 x 140 canvas around the avatar: the avatar is the circle at (70, 70), radius 50.
const C = 70;
const R = 50;

/** Points around the avatar: [x, y] at `r` from the centre, `n` of them, starting at `from` degrees. */
function around(n: number, r: number, from = -90): [number, number][] {
  return Array.from({ length: n }, (_, i) => {
    const a = ((from + (360 / n) * i) * Math.PI) / 180;
    return [C + r * Math.cos(a), C + r * Math.sin(a)];
  });
}

const star4 = (x: number, y: number, s: number) =>
  `M${x} ${y - s}Q${x + s * 0.18} ${y - s * 0.18} ${x + s} ${y}Q${x + s * 0.18} ${y + s * 0.18} ${x} ${y + s}Q${x - s * 0.18} ${y + s * 0.18} ${x - s} ${y}Q${x - s * 0.18} ${y - s * 0.18} ${x} ${y - s}Z`;
const heart = (x: number, y: number, s: number) =>
  `M${x} ${y + s * 0.9}C${x - s * 1.6} ${y - s * 0.2} ${x - s * 0.7} ${y - s * 1.3} ${x} ${y - s * 0.45}C${x + s * 0.7} ${y - s * 1.3} ${x + s * 1.6} ${y - s * 0.2} ${x} ${y + s * 0.9}Z`;

function Metal({
  id,
  stops,
  sparkle,
}: {
  id: string;
  stops: string[];
  sparkle?: boolean;
}) {
  return (
    <>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          {stops.map((c, i) => (
            <stop key={i} offset={i / (stops.length - 1)} stopColor={c} />
          ))}
        </linearGradient>
      </defs>
      <circle
        cx={C}
        cy={C}
        r={R + 4}
        fill="none"
        stroke={`url(#${id})`}
        strokeWidth="6"
      />
      <circle
        className="d-spin-slow"
        cx={C}
        cy={C}
        r={R + 4}
        fill="none"
        stroke="#fff"
        strokeOpacity="0.85"
        strokeWidth="3"
        strokeLinecap="round"
        pathLength="100"
        strokeDasharray="7 93"
      />
      {sparkle &&
        around(3, R + 6, -60).map(([x, y], i) => (
          <path
            key={i}
            className={`d-twinkle t${i}`}
            d={star4(x, y, 7)}
            fill="#fff7cf"
          />
        ))}
    </>
  );
}

function Flames({ id }: { id: string }) {
  return (
    <>
      <defs>
        <linearGradient id={id} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#ff3d00" />
          <stop offset="0.6" stopColor="#ff9100" />
          <stop offset="1" stopColor="#ffd54f" stopOpacity="0.2" />
        </linearGradient>
      </defs>
      <circle
        cx={C}
        cy={C}
        r={R + 3}
        fill="none"
        stroke="#ff6d00"
        strokeOpacity="0.45"
        strokeWidth="8"
        className="d-pulse"
      />
      {Array.from({ length: 14 }, (_, i) => {
        const big = i % 2 === 0;
        const h = big ? 20 : 13;
        return (
          <g key={i} transform={`rotate(${(360 / 14) * i} ${C} ${C})`}>
            <path
              className={`d-flame f${i % 4}`}
              d={`M${C - 7} ${C - R + 2}Q${C - 6} ${C - R - h * 0.6} ${C} ${C - R - h}Q${C + 6} ${C - R - h * 0.6} ${C + 7} ${C - R + 2}Z`}
              fill={`url(#${id})`}
            />
            {big && (
              <path
                className={`d-flame f${(i + 2) % 4}`}
                d={`M${C - 3.5} ${C - R + 1}Q${C - 3} ${C - R - 8} ${C} ${C - R - 11}Q${C + 3} ${C - R - 8} ${C + 3.5} ${C - R + 1}Z`}
                fill="#fff59d"
              />
            )}
          </g>
        );
      })}
      {around(5, R + 6, 30).map(([x, y], i) => (
        <circle
          key={i}
          className={`d-ember e${i}`}
          cx={x}
          cy={y}
          r="1.8"
          fill="#ffd54f"
        />
      ))}
    </>
  );
}

/** One avatar frame, drawn around the avatar it sits in. */
export function Decor({ id }: { id: string }) {
  const uid = useId().replace(/:/g, "");
  const g = (n: string) => `${uid}${n}`;
  let art: ReactNode = null;
  switch (id) {
    case "bronze":
      art = (
        <Metal
          id={g("m")}
          stops={["#f2b07a", "#8a4b22", "#d98b4f", "#6b3417"]}
        />
      );
      break;
    case "silver":
      art = (
        <Metal
          id={g("m")}
          stops={["#ffffff", "#8d99a8", "#e3e8ee", "#6f7a88"]}
        />
      );
      break;
    case "gold":
      art = (
        <Metal
          id={g("m")}
          stops={["#fff3b0", "#d99b00", "#ffe066", "#a86b00"]}
          sparkle
        />
      );
      break;
    case "neon":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#36f1cd"
            strokeOpacity="0.25"
            strokeWidth="11"
            className="d-pulse"
          />
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#9ffff0"
            strokeWidth="2.5"
            className="d-flicker"
          />
          <circle
            cx={C}
            cy={C}
            r={R + 10}
            fill="none"
            stroke="#ff4fd8"
            strokeOpacity="0.3"
            strokeWidth="6"
            className="d-pulse late"
          />
          <circle
            cx={C}
            cy={C}
            r={R + 10}
            fill="none"
            stroke="#ffb3f1"
            strokeWidth="1.6"
            className="d-flicker late"
          />
        </>
      );
      break;
    case "rainbow": {
      const cols = [
        "#ff3b3b",
        "#ff9f1a",
        "#ffe11a",
        "#2ee66b",
        "#2bb3ff",
        "#9b5bff",
      ];
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 6}
            fill="none"
            stroke="#fff"
            strokeOpacity="0.18"
            strokeWidth="12"
          />
          <g className="d-spin">
            {cols.map((c, i) => (
              <circle
                key={c}
                cx={C}
                cy={C}
                r={R + 6}
                fill="none"
                stroke={c}
                strokeWidth="7"
                pathLength="60"
                strokeDasharray="10 50"
                strokeDashoffset={-10 * i}
              />
            ))}
          </g>
        </>
      );
      break;
    }
    case "starlight":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#fff1dc"
            strokeOpacity="0.7"
            strokeWidth="2"
          />
          <g className="d-spin">
            {around(3, R + 4).map(([x, y], i) => (
              <path key={i} d={star4(x, y, 7)} fill="#fff7d6" />
            ))}
          </g>
          <g className="d-spin-rev">
            {around(4, R + 12, -45).map(([x, y], i) => (
              <path
                key={i}
                className={`d-twinkle t${i}`}
                d={star4(x, y, 4.5)}
                fill="#ffe08a"
              />
            ))}
          </g>
        </>
      );
      break;
    case "plus":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 5}
            fill="none"
            stroke="#ff6b2c"
            strokeOpacity="0.35"
            strokeWidth="10"
            className="d-pulse"
          />
          <circle
            className="d-spin"
            cx={C}
            cy={C}
            r={R + 5}
            fill="none"
            stroke="#ffb27a"
            strokeWidth="3"
            pathLength="48"
            strokeDasharray="4 2"
          />
          {around(4, R + 13, -45).map(([x, y], i) => (
            <path
              key={i}
              className={`d-twinkle t${i}`}
              d={`M${x - 4} ${y}H${x + 4}M${x} ${y - 4}V${y + 4}`}
              stroke="#ffd2a8"
              strokeWidth="2.4"
              strokeLinecap="round"
            />
          ))}
        </>
      );
      break;
    case "comet":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 6}
            fill="none"
            stroke="#8fd3ff"
            strokeOpacity="0.2"
            strokeWidth="2"
          />
          <g className="d-spin-fast">
            <circle
              cx={C}
              cy={C}
              r={R + 6}
              fill="none"
              stroke="#8fd3ff"
              strokeOpacity="0.18"
              strokeWidth="9"
              pathLength="100"
              strokeDasharray="0 66 34 0"
              strokeLinecap="round"
            />
            <circle
              cx={C}
              cy={C}
              r={R + 6}
              fill="none"
              stroke="#c9ecff"
              strokeOpacity="0.55"
              strokeWidth="5"
              pathLength="100"
              strokeDasharray="0 82 18 0"
              strokeLinecap="round"
            />
            <circle cx={C} cy={C - R - 6} r="6" fill="#fff" />
            <circle
              cx={C}
              cy={C - R - 6}
              r="10"
              fill="#8fd3ff"
              fillOpacity="0.35"
            />
          </g>
        </>
      );
      break;
    case "orbit":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 6}
            fill="none"
            stroke="#ffd166"
            strokeOpacity="0.25"
            strokeWidth="1.5"
            strokeDasharray="2 5"
          />
          {[
            ["d-spin-fast", "#ffd166", R + 6],
            ["d-spin-rev", "#ff6b9a", R + 11],
            ["d-spin", "#5ef0ff", R + 2],
          ].map(([cls, col, r], i) => (
            <g key={i} transform={`rotate(${i * 120} ${C} ${C})`}>
              <g className={cls as string}>
                <circle
                  cx={C}
                  cy={C - (r as number)}
                  r="7"
                  fill={col as string}
                  fillOpacity="0.3"
                />
                <circle cx={C} cy={C - (r as number)} r="3.4" fill="#fff" />
              </g>
            </g>
          ))}
        </>
      );
      break;
    case "hearts":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#ff7eb6"
            strokeWidth="3"
          />
          {around(7, R + 8, 0).map(([x, y], i) => (
            <path
              key={i}
              className={`d-rise r${i}`}
              d={heart(x, y, 6 + (i % 3))}
              fill={i % 2 ? "#ff4d8d" : "#ff9cc4"}
            />
          ))}
        </>
      );
      break;
    case "bubbles":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#7fe0ff"
            strokeOpacity="0.6"
            strokeWidth="2.5"
          />
          {around(8, R + 8, 10).map(([x, y], i) => (
            <g key={i} className={`d-rise r${i}`}>
              <circle
                cx={x}
                cy={y}
                r={3 + (i % 3) * 2}
                fill="#bdf2ff"
                fillOpacity="0.2"
                stroke="#e6fbff"
                strokeWidth="1.4"
              />
              <circle cx={x - 1.4} cy={y - 1.6} r="1" fill="#fff" />
            </g>
          ))}
        </>
      );
      break;
    case "catears":
      art = (
        <>
          <g className="d-ear left">
            <path
              d="M30 42L26 4L60 24Z"
              fill="#2f2236"
              stroke="#fff"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            <path d="M34 34L31 14L50 25Z" fill="#ff9ec4" />
          </g>
          <g className="d-ear right">
            <path
              d="M110 42L114 4L80 24Z"
              fill="#2f2236"
              stroke="#fff"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            <path d="M106 34L109 14L90 25Z" fill="#ff9ec4" />
          </g>
        </>
      );
      break;
    case "halo":
      art = (
        <g className="d-bob">
          <ellipse
            cx={C}
            cy="12"
            rx="30"
            ry="8"
            fill="none"
            stroke="#ffe27a"
            strokeOpacity="0.35"
            strokeWidth="9"
          />
          <ellipse
            cx={C}
            cy="12"
            rx="30"
            ry="8"
            fill="none"
            stroke="#fff6c2"
            strokeWidth="3.5"
          />
          <path className="d-twinkle t1" d={star4(104, 8, 5)} fill="#fff6c2" />
          <path className="d-twinkle t2" d={star4(36, 16, 4)} fill="#fff6c2" />
        </g>
      );
      break;
    case "horns":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#ff3355"
            strokeOpacity="0.35"
            strokeWidth="8"
            className="d-pulse"
          />
          <g className="d-wiggle">
            <path
              d="M34 34C22 26 18 12 24 2C30 14 40 18 48 24Z"
              fill="#e8173c"
              stroke="#5a0010"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <path
              d="M106 34C118 26 122 12 116 2C110 14 100 18 92 24Z"
              fill="#e8173c"
              stroke="#5a0010"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <path
              d="M27 9C29 15 34 19 40 22"
              stroke="#ff8a9e"
              strokeWidth="2"
              fill="none"
              strokeLinecap="round"
            />
            <path
              d="M113 9C111 15 106 19 100 22"
              stroke="#ff8a9e"
              strokeWidth="2"
              fill="none"
              strokeLinecap="round"
            />
          </g>
        </>
      );
      break;
    case "sakura":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#ffc1dc"
            strokeWidth="3"
          />
          <g className="d-spin-slow">
            {around(8, R + 6).map(([x, y], i) => (
              <g key={i} transform={`rotate(${i * 45} ${x} ${y})`}>
                {[0, 72, 144, 216, 288].map((a) => (
                  <ellipse
                    key={a}
                    cx={x}
                    cy={y - 3.6}
                    rx="2.6"
                    ry="4"
                    fill={i % 2 ? "#ffb7d5" : "#ffd6e8"}
                    transform={`rotate(${a} ${x} ${y})`}
                  />
                ))}
                <circle cx={x} cy={y} r="1.6" fill="#ff6fa8" />
              </g>
            ))}
          </g>
          {[30, 70, 112].map((x, i) => (
            <ellipse
              key={x}
              className={`d-fall r${i}`}
              cx={x}
              cy="16"
              rx="2.6"
              ry="4"
              fill="#ffc1dc"
            />
          ))}
        </>
      );
      break;
    case "frost":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#bfefff"
            strokeWidth="3"
          />
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#7fd6ff"
            strokeOpacity="0.3"
            strokeWidth="10"
            className="d-pulse"
          />
          <g className="d-spin-slow">
            {around(8, R + 6).map(([x, y], i) => (
              <g
                key={i}
                className={`d-twinkle t${i % 4}`}
                stroke="#ecfbff"
                strokeWidth="1.6"
                strokeLinecap="round"
              >
                <path
                  d={`M${x} ${y - 6}V${y + 6}M${x - 5.2} ${y - 3}L${x + 5.2} ${y + 3}M${x - 5.2} ${y + 3}L${x + 5.2} ${y - 3}`}
                />
              </g>
            ))}
          </g>
        </>
      );
      break;
    case "pixel": {
      const dots = around(24, R + 6);
      art = (
        <>
          <g className="d-glitch a">
            {dots.map(([x, y], i) => (
              <rect
                key={i}
                x={x - 3}
                y={y - 3}
                width="6"
                height="6"
                fill="#ff2e63"
              />
            ))}
          </g>
          <g className="d-glitch b">
            {dots.map(([x, y], i) => (
              <rect
                key={i}
                x={x - 3}
                y={y - 3}
                width="6"
                height="6"
                fill="#08d9d6"
              />
            ))}
          </g>
          <g>
            {dots.map(([x, y], i) => (
              <rect
                key={i}
                className={i % 5 === 0 ? `d-blink t${i % 4}` : ""}
                x={x - 3}
                y={y - 3}
                width="6"
                height="6"
                fill={i % 3 ? "#f8f8f2" : "#ffe66d"}
              />
            ))}
          </g>
        </>
      );
      break;
    }
    case "aurora":
      art = (
        <>
          <circle
            className="d-spin"
            cx={C}
            cy={C}
            r={R + 6}
            fill="none"
            stroke="#3dffb0"
            strokeOpacity="0.55"
            strokeWidth="9"
            pathLength="100"
            strokeDasharray="38 12"
            strokeLinecap="round"
          />
          <circle
            className="d-spin-rev"
            cx={C}
            cy={C}
            r={R + 7}
            fill="none"
            stroke="#5f8bff"
            strokeOpacity="0.5"
            strokeWidth="7"
            pathLength="100"
            strokeDasharray="30 20"
            strokeLinecap="round"
          />
          <circle
            className="d-spin-slow"
            cx={C}
            cy={C}
            r={R + 5}
            fill="none"
            stroke="#d36bff"
            strokeOpacity="0.5"
            strokeWidth="5"
            pathLength="100"
            strokeDasharray="22 28"
            strokeLinecap="round"
          />
          <circle
            cx={C}
            cy={C}
            r={R + 2}
            fill="none"
            stroke="#e8fff6"
            strokeOpacity="0.8"
            strokeWidth="1.5"
          />
        </>
      );
      break;
    case "headphones":
      art = (
        <>
          <path
            d="M22 70C22 30 44 14 70 14C96 14 118 30 118 70"
            fill="none"
            stroke="#2b2b3a"
            strokeWidth="8"
            strokeLinecap="round"
          />
          <path
            d="M26 62C28 34 46 20 70 20C94 20 112 34 114 62"
            fill="none"
            stroke="#ff4f8b"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <g className="d-thump">
            <rect
              x="10"
              y="56"
              width="18"
              height="30"
              rx="8"
              fill="#ff4f8b"
              stroke="#2b2b3a"
              strokeWidth="3"
            />
            <rect
              x="112"
              y="56"
              width="18"
              height="30"
              rx="8"
              fill="#ff4f8b"
              stroke="#2b2b3a"
              strokeWidth="3"
            />
          </g>
          {[0, 1].map((i) => (
            <g
              key={i}
              className={`d-wave w${i}`}
              stroke="#5ef0ff"
              strokeWidth="2.4"
              fill="none"
              strokeLinecap="round"
            >
              <path d="M6 60C1 66 1 76 6 82" />
              <path d="M134 60C139 66 139 76 134 82" />
            </g>
          ))}
        </>
      );
      break;
    case "inferno":
      art = <Flames id={g("f")} />;
      break;
    case "electric":
      art = (
        <>
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#7cc8ff"
            strokeOpacity="0.35"
            strokeWidth="9"
            className="d-pulse"
          />
          <circle
            cx={C}
            cy={C}
            r={R + 4}
            fill="none"
            stroke="#e6f6ff"
            strokeWidth="2"
          />
          <g className="d-spin-slow">
            {[0, 90, 180, 270].map((a, i) => (
              <g key={a} transform={`rotate(${a} ${C} ${C})`}>
                <path
                  className={`d-zap t${i}`}
                  d={`M${C - 16} ${C - R - 2}L${C - 8} ${C - R - 10}L${C - 2} ${C - R - 3}L${C + 6} ${C - R - 13}L${C + 10} ${C - R - 5}L${C + 17} ${C - R - 9}`}
                  fill="none"
                  stroke="#fff"
                  strokeWidth="2.6"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              </g>
            ))}
          </g>
        </>
      );
      break;
    case "galaxy":
      art = (
        <>
          <defs>
            <linearGradient id={g("gx")} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#7b2ff7" />
              <stop offset="0.5" stopColor="#f107a3" />
              <stop offset="1" stopColor="#1fd1f9" />
            </linearGradient>
          </defs>
          <circle
            className="d-spin-slow"
            cx={C}
            cy={C}
            r={R + 6}
            fill="none"
            stroke={`url(#${g("gx")})`}
            strokeWidth="10"
          />
          <g className="d-spin">
            {around(10, R + 6, 7).map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r={i % 3 ? 1.2 : 2} fill="#fff" />
            ))}
          </g>
          <g className="d-spin-rev">
            {around(3, R + 14, 20).map(([x, y], i) => (
              <path
                key={i}
                className={`d-twinkle t${i}`}
                d={star4(x, y, 5)}
                fill="#fff"
              />
            ))}
          </g>
        </>
      );
      break;
    default:
      return null;
  }
  return (
    <svg
      className={`decor decor-${id}`}
      viewBox="0 0 140 140"
      aria-hidden="true"
      focusable="false"
    >
      {art}
    </svg>
  );
}

// Characters fill the avatar's own circle (100 x 100), on the picked colour.
const eyes = (lx: number, rx: number, y: number, r = 4.5, fill = "#1d1226") => (
  <g className="c-blink">
    <circle cx={lx} cy={y} r={r} fill={fill} />
    <circle cx={rx} cy={y} r={r} fill={fill} />
    <circle cx={lx + r * 0.35} cy={y - r * 0.35} r={r * 0.32} fill="#fff" />
    <circle cx={rx + r * 0.35} cy={y - r * 0.35} r={r * 0.32} fill="#fff" />
  </g>
);

const CHARACTERS: Record<string, () => ReactNode> = {
  blob: () => (
    <g className="c-squish">
      <path d="M18 88C10 62 22 30 50 30C78 30 90 62 82 88Z" fill="#4be38a" />
      <path
        d="M30 50C32 42 38 38 44 37"
        stroke="#b9ffd7"
        strokeWidth="4"
        strokeLinecap="round"
        fill="none"
      />
      {eyes(40, 60, 58, 5)}
      <path
        d="M43 70Q50 76 57 70"
        stroke="#1d1226"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />
    </g>
  ),
  robot: () => (
    <g>
      <path d="M50 26V14" stroke="#c9d1db" strokeWidth="3" />
      <circle className="c-light" cx="50" cy="12" r="4.5" fill="#ff4545" />
      <rect x="22" y="26" width="56" height="50" rx="12" fill="#c9d1db" />
      <rect x="15" y="44" width="7" height="16" rx="3" fill="#8d99a8" />
      <rect x="78" y="44" width="7" height="16" rx="3" fill="#8d99a8" />
      <rect x="29" y="34" width="42" height="28" rx="7" fill="#1f2a3a" />
      <g className="c-blink">
        <rect x="35" y="42" width="10" height="9" rx="2.5" fill="#5ef0ff" />
        <rect x="55" y="42" width="10" height="9" rx="2.5" fill="#5ef0ff" />
      </g>
      <path
        d="M38 69H62"
        stroke="#6f7a88"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray="3 4"
      />
      <rect x="30" y="78" width="40" height="22" rx="6" fill="#8d99a8" />
    </g>
  ),
  ghost: () => (
    <g className="c-float">
      <path
        d="M24 92V50C24 32 36 20 50 20C64 20 76 32 76 50V92L67 84L58 92L50 84L42 92L33 84Z"
        fill="#fbf8ff"
      />
      {eyes(41, 59, 50, 5)}
      <ellipse cx="50" cy="64" rx="4" ry="5" fill="#1d1226" />
      <circle cx="34" cy="58" r="3.5" fill="#ffb3c8" />
      <circle cx="66" cy="58" r="3.5" fill="#ffb3c8" />
    </g>
  ),
  cat: () => (
    <g>
      <path className="c-ear-l" d="M24 44L22 14L46 30Z" fill="#ff9f43" />
      <path className="c-ear-r" d="M76 44L78 14L54 30Z" fill="#ff9f43" />
      <path d="M26 38L26 22L40 32Z" fill="#ffd1a3" />
      <path d="M74 38L74 22L60 32Z" fill="#ffd1a3" />
      <ellipse cx="50" cy="56" rx="32" ry="28" fill="#ff9f43" />
      <path
        d="M44 30L46 40M50 29V40M56 30L54 40"
        stroke="#e07b1f"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      {eyes(39, 61, 54, 4.8, "#2c6e2f")}
      <path d="M47 63H53L50 67Z" fill="#ff6f91" />
      <path
        d="M50 67Q46 72 42 70M50 67Q54 72 58 70"
        stroke="#5a3418"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M30 64H16M31 69L18 73M70 64H84M69 69L82 73"
        stroke="#5a3418"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </g>
  ),
  alien: () => (
    <g>
      <g className="c-wobble">
        <path
          d="M38 28L30 10M62 28L70 10"
          stroke="#7be36a"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <circle cx="30" cy="10" r="4.5" fill="#d6ff6b" />
        <circle cx="70" cy="10" r="4.5" fill="#d6ff6b" />
      </g>
      <path
        d="M50 22C74 22 84 40 80 58C76 76 62 90 50 90C38 90 24 76 20 58C16 40 26 22 50 22Z"
        fill="#7be36a"
      />
      <g className="c-blink">
        <path d="M28 52C30 42 40 42 45 50C46 58 36 62 30 58Z" fill="#141018" />
        <path d="M72 52C70 42 60 42 55 50C54 58 64 62 70 58Z" fill="#141018" />
        <circle cx="36" cy="50" r="2" fill="#fff" />
        <circle cx="64" cy="50" r="2" fill="#fff" />
      </g>
      <path
        d="M45 74Q50 77 55 74"
        stroke="#2d6b24"
        strokeWidth="2.4"
        fill="none"
        strokeLinecap="round"
      />
    </g>
  ),
  frog: () => (
    <g>
      <ellipse cx="50" cy="64" rx="36" ry="26" fill="#52c76a" />
      <circle cx="33" cy="38" r="13" fill="#52c76a" />
      <circle cx="67" cy="38" r="13" fill="#52c76a" />
      <circle cx="33" cy="38" r="8.5" fill="#fff" />
      <circle cx="67" cy="38" r="8.5" fill="#fff" />
      {eyes(33, 67, 39, 4.6)}
      <path
        d="M28 64Q50 80 72 64"
        stroke="#1f5a2a"
        strokeWidth="3.2"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="24" cy="58" r="4" fill="#ff9eb5" fillOpacity="0.8" />
      <circle cx="76" cy="58" r="4" fill="#ff9eb5" fillOpacity="0.8" />
    </g>
  ),
  penguin: () => (
    <g className="c-waddle">
      <ellipse cx="50" cy="62" rx="34" ry="38" fill="#22223a" />
      <path
        d="M50 30C64 30 72 42 72 58C72 78 62 92 50 92C38 92 28 78 28 58C28 42 36 30 50 30Z"
        fill="#fbf8ff"
      />
      <path d="M32 40C36 30 44 28 50 34C56 28 64 30 68 40" fill="#22223a" />
      {eyes(41, 59, 48, 4.2)}
      <path d="M43 56L57 56L50 64Z" fill="#ffa62b" />
      <circle cx="35" cy="60" r="3.5" fill="#ffb3c8" />
      <circle cx="65" cy="60" r="3.5" fill="#ffb3c8" />
    </g>
  ),
  dino: () => (
    <g>
      <g className="c-wobble">
        <path
          d="M30 30L34 16L40 28L46 12L52 27L58 12L63 28L70 16L72 32Z"
          fill="#2fa36b"
        />
      </g>
      <path
        d="M50 24C74 24 86 40 86 58C86 78 70 92 50 92C30 92 14 78 14 58C14 40 26 24 50 24Z"
        fill="#46c98a"
      />
      <ellipse cx="50" cy="72" rx="26" ry="14" fill="#a6f0c6" />
      {eyes(36, 64, 50, 5.4)}
      <path
        d="M34 70Q50 82 66 70"
        stroke="#1f5a3c"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />
      <path d="M40 73L43 78L46 74M54 74L57 78L60 73" fill="#fff" />
      <circle cx="44" cy="62" r="1.6" fill="#1f5a3c" />
      <circle cx="56" cy="62" r="1.6" fill="#1f5a3c" />
    </g>
  ),
  tvhost: () => (
    <g>
      <g className="c-wobble">
        <path
          d="M44 22L32 6M56 22L68 6"
          stroke="#2b1a2e"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <circle cx="32" cy="6" r="3.4" fill="#ffd23f" />
        <circle cx="68" cy="6" r="3.4" fill="#ffd23f" />
      </g>
      <rect x="16" y="22" width="68" height="54" rx="12" fill="#ff6b2c" />
      <rect x="22" y="28" width="46" height="42" rx="9" fill="#18222e" />
      <rect
        className="c-scan"
        x="22"
        y="28"
        width="46"
        height="5"
        fill="#5ef0ff"
        fillOpacity="0.25"
      />
      <g className="c-blink">
        <rect x="31" y="40" width="7" height="9" rx="3.5" fill="#5ef0ff" />
        <rect x="52" y="40" width="7" height="9" rx="3.5" fill="#5ef0ff" />
      </g>
      <path
        d="M34 56Q45 64 56 56"
        stroke="#5ef0ff"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="76" cy="38" r="3" fill="#ffd23f" />
      <circle cx="76" cy="48" r="3" fill="#2b1a2e" />
      <path d="M36 86L48 80V92ZM64 86L52 80V92Z" fill="#e8173c" />
      <circle cx="50" cy="86" r="4" fill="#ff4f6d" />
    </g>
  ),
  pumpkin: () => (
    <g>
      <path
        d="M50 26C48 18 52 12 58 10"
        stroke="#3f7d2c"
        strokeWidth="5"
        strokeLinecap="round"
        fill="none"
      />
      <ellipse cx="34" cy="60" rx="20" ry="30" fill="#ff8a1f" />
      <ellipse cx="66" cy="60" rx="20" ry="30" fill="#ff8a1f" />
      <ellipse cx="50" cy="60" rx="20" ry="32" fill="#ffa23a" />
      <g className="c-glow">
        <path d="M30 52L40 42L44 54Z" fill="#ffe14d" />
        <path d="M70 52L60 42L56 54Z" fill="#ffe14d" />
        <path
          d="M30 68L36 74L42 68L50 76L58 68L64 74L70 68Q50 88 30 68Z"
          fill="#ffe14d"
        />
      </g>
    </g>
  ),
  panda: () => (
    <g>
      <circle cx="24" cy="30" r="11" fill="#1f1f2b" />
      <circle cx="76" cy="30" r="11" fill="#1f1f2b" />
      <ellipse cx="50" cy="56" rx="34" ry="31" fill="#fbf8ff" />
      <ellipse
        cx="37"
        cy="52"
        rx="9"
        ry="11"
        fill="#1f1f2b"
        transform="rotate(-20 37 52)"
      />
      <ellipse
        cx="63"
        cy="52"
        rx="9"
        ry="11"
        fill="#1f1f2b"
        transform="rotate(20 63 52)"
      />
      {eyes(38, 62, 52, 3.4, "#fbf8ff")}
      <ellipse cx="50" cy="66" rx="5" ry="3.5" fill="#1f1f2b" />
      <path
        d="M50 69Q46 74 42 72M50 69Q54 74 58 72"
        stroke="#1f1f2b"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
      <path
        className="c-chew"
        d="M70 84L92 62"
        stroke="#6ccf5f"
        strokeWidth="6"
        strokeLinecap="round"
      />
    </g>
  ),
  bee: () => (
    <g>
      <g className="c-wings">
        <ellipse
          cx="22"
          cy="40"
          rx="14"
          ry="10"
          fill="#e6f7ff"
          fillOpacity="0.85"
        />
        <ellipse
          cx="78"
          cy="40"
          rx="14"
          ry="10"
          fill="#e6f7ff"
          fillOpacity="0.85"
        />
      </g>
      <path
        d="M40 26L34 12M60 26L66 12"
        stroke="#1f1f2b"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <circle cx="34" cy="12" r="3" fill="#1f1f2b" />
      <circle cx="66" cy="12" r="3" fill="#1f1f2b" />
      <circle cx="50" cy="58" r="32" fill="#ffd23f" />
      <path d="M20 66H80M24 78H76" stroke="#1f1f2b" strokeWidth="7" />
      {eyes(39, 61, 48, 4.6)}
      <path
        d="M44 56Q50 61 56 56"
        stroke="#1f1f2b"
        strokeWidth="2.6"
        fill="none"
        strokeLinecap="round"
      />
    </g>
  ),
  octo: () => (
    <g>
      <g className="c-tentacles">
        {[22, 36, 50, 64, 78].map((x, i) => (
          <path
            key={x}
            d={`M${x} 66Q${x + (i % 2 ? 6 : -6)} 82 ${x} 96`}
            stroke="#b05cff"
            strokeWidth="9"
            strokeLinecap="round"
            fill="none"
          />
        ))}
      </g>
      <ellipse cx="50" cy="48" rx="32" ry="30" fill="#c27bff" />
      <circle cx="36" cy="30" r="4" fill="#e3c2ff" />
      <circle cx="62" cy="26" r="3" fill="#e3c2ff" />
      {eyes(39, 61, 50, 5)}
      <path
        d="M45 62Q50 66 55 62"
        stroke="#3d1466"
        strokeWidth="2.6"
        fill="none"
        strokeLinecap="round"
      />
    </g>
  ),
  ninja: () => (
    <g>
      <g className="c-flutter">
        <path d="M80 36L98 28L94 40L99 50L80 44Z" fill="#e8173c" />
      </g>
      <circle cx="50" cy="54" r="34" fill="#22223a" />
      <rect x="16" y="32" width="68" height="9" fill="#e8173c" />
      <rect x="22" y="46" width="56" height="18" rx="9" fill="#f5c9a0" />
      <g className="c-blink">
        <path d="M30 55L44 52L44 58Z" fill="#1d1226" />
        <path d="M70 55L56 52L56 58Z" fill="#1d1226" />
      </g>
    </g>
  ),
  wizard: () => (
    <g>
      <ellipse cx="50" cy="44" rx="40" ry="8" fill="#5b2bb5" />
      <path d="M26 44L52 2L76 44Z" fill="#7a3ff2" />
      <path
        className="c-twinkle"
        d="M54 16L56 21L61 22L56 24L54 29L52 24L47 22L52 21Z"
        fill="#ffe14d"
      />
      <circle className="c-twinkle late" cx="40" cy="34" r="2" fill="#ffe14d" />
      <rect x="28" y="44" width="44" height="26" rx="10" fill="#f5c9a0" />
      {eyes(41, 59, 55, 3.8)}
      <path
        d="M26 64C30 92 70 92 74 64C66 72 58 70 50 74C42 70 34 72 26 64Z"
        fill="#fbf8ff"
      />
    </g>
  ),
  vampire: () => (
    <g>
      <path d="M8 100L24 62L50 80L76 62L92 100Z" fill="#b3122e" />
      <ellipse cx="50" cy="52" rx="28" ry="32" fill="#e9e4f2" />
      <path
        d="M22 46C22 26 34 18 50 18C66 18 78 26 78 46C70 36 60 34 50 46C40 34 30 36 22 46Z"
        fill="#1f1f2b"
      />
      <g className="c-brows">
        <path
          d="M33 48L45 52M67 48L55 52"
          stroke="#1f1f2b"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </g>
      {eyes(39, 61, 57, 4, "#c4102f")}
      <path
        d="M40 70Q50 76 60 70"
        stroke="#1f1f2b"
        strokeWidth="2.6"
        fill="none"
        strokeLinecap="round"
      />
      <path d="M43 72L45 79L47 73M53 73L55 79L57 72" fill="#fff" />
    </g>
  ),
  dragon: () => (
    <g>
      <path d="M28 34L18 10L40 26ZM72 34L82 10L60 26Z" fill="#ffd23f" />
      <path
        d="M50 22C74 22 86 40 86 60C86 80 70 94 50 94C30 94 14 80 14 60C14 40 26 22 50 22Z"
        fill="#f2433d"
      />
      <path
        d="M22 50C14 46 8 40 6 30C16 34 22 40 26 46ZM78 50C86 46 92 40 94 30C84 34 78 40 74 46Z"
        fill="#ff7a59"
      />
      <ellipse cx="50" cy="72" rx="22" ry="14" fill="#ff9a7a" />
      {eyes(36, 64, 50, 5, "#2b0f0f")}
      <circle cx="44" cy="70" r="2.4" fill="#7a1612" />
      <circle cx="56" cy="70" r="2.4" fill="#7a1612" />
      <g className="c-smoke">
        <circle cx="42" cy="62" r="4" fill="#d9d4e0" fillOpacity="0.8" />
        <circle cx="58" cy="60" r="3.2" fill="#d9d4e0" fillOpacity="0.8" />
      </g>
    </g>
  ),
};

export const hasCharacter = (id: string | undefined) =>
  !!id && id in CHARACTERS;

/** An animated character, filling the avatar's circle. */
export function Character({ id }: { id: string }) {
  const draw = CHARACTERS[id];
  if (!draw) return null;
  return (
    <svg
      className={`char char-${id}`}
      viewBox="0 0 100 100"
      aria-hidden="true"
      focusable="false"
    >
      {draw()}
    </svg>
  );
}

// Victory animations: particles around a winner, placed and timed by styles/87-cosmetics.css.
const WIN_PARTS: Record<string, number> = {
  fireworks: 12,
  spotlight: 0,
  disco: 8,
  rocket: 6,
  crown: 8,
  supernova: 10,
  hearts: 12,
  balloons: 8,
  snow: 14,
  trophy: 6,
  lightning: 4,
  stardust: 14,
  lasers: 6,
};
export const WIN_ICON: Record<string, string> = {
  confetti: "🎉",
  fireworks: "🎆",
  spotlight: "🔦",
  disco: "🪩",
  rocket: "🚀",
  crown: "👑",
  supernova: "🌟",
  hearts: "💖",
  balloons: "🎈",
  snow: "❄️",
  trophy: "🏆",
  lightning: "⚡",
  stardust: "✨",
  lasers: "🔆",
};

/** A winner's victory animation, centred on their avatar (confetti is the screen-wide default). */
export function WinFx({ kind }: { kind: string }) {
  const n = WIN_PARTS[kind];
  if (n === undefined) return null;
  return (
    <span className={`wfx wfx-${kind}`} aria-hidden="true">
      <b className="wfx-core" />
      {Array.from({ length: n }, (_, i) => (
        <i key={i} />
      ))}
    </span>
  );
}
