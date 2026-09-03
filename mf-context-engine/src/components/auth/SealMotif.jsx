import React from "react";

/**
 * SealMotif - The etched regulatory concentric seal graphic.
 * Represents an official AMC compliance stamp / wax-sealed circular.
 * 
 * Props:
 * - animState: "idle" | "settle" | "success"
 * - className: additional classes
 */
export default function SealMotif({ animState = "settle", className = "" }) {
  // Generate radial tick marks for the outer calibration ring
  const ticks = React.useMemo(() => {
    const list = [];
    const center = 350;
    const rOuter = 310;
    const rInnerMajor = 295;
    const rInnerMinor = 302;
    for (let i = 0; i < 72; i++) {
      const angle = (i * 5 * Math.PI) / 180;
      const isMajor = i % 6 === 0;
      const rInner = isMajor ? rInnerMajor : rInnerMinor;
      const x1 = center + rOuter * Math.cos(angle);
      const y1 = center + rOuter * Math.sin(angle);
      const x2 = center + rInner * Math.cos(angle);
      const y2 = center + rInner * Math.sin(angle);
      list.push({ id: i, x1, y1, x2, y2, isMajor });
    }
    return list;
  }, []);

  return (
    <div
      className={`seal-motif-container seal-motif--${animState} ${className}`}
      aria-hidden="true"
    >
      <svg
        className="seal-motif-svg"
        viewBox="0 0 700 700"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <radialGradient
            id="sealGlow"
            cx="50%"
            cy="50%"
            r="50%"
            fx="50%"
            fy="50%"
          >
            <stop offset="0%" stopColor="#B08D57" stopOpacity="0.08" />
            <stop offset="60%" stopColor="#B08D57" stopOpacity="0.03" />
            <stop offset="100%" stopColor="#B08D57" stopOpacity="0" />
          </radialGradient>
          <filter id="sealEtch" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="1" stdDeviation="1" floodColor="#000" floodOpacity="0.5" />
          </filter>
        </defs>

        <g filter="url(#sealEtch)">
          {/* Faint ambient backing */}
          <circle cx="350" cy="350" r="330" fill="url(#sealGlow)" />

          {/* Outermost hairline circle */}
          <circle cx="350" cy="350" r="325" stroke="var(--seal)" strokeWidth="1" strokeOpacity="0.18" />
          
          {/* Secondary framing ring */}
          <circle cx="350" cy="350" r="310" stroke="var(--seal)" strokeWidth="1.5" strokeOpacity="0.28" />

          {/* Calibration ticks */}
          {ticks.map((t) => (
            <line
              key={t.id}
              x1={t.x1}
              y1={t.y1}
              x2={t.x2}
              y2={t.y2}
              stroke="var(--seal)"
              strokeWidth={t.isMajor ? 1.5 : 0.75}
              strokeOpacity={t.isMajor ? 0.35 : 0.2}
            />
          ))}

          {/* Intermediate ring with dash pattern */}
          <circle
            cx="350"
            cy="350"
            r="285"
            stroke="var(--seal)"
            strokeWidth="1"
            strokeDasharray="4 6"
            strokeOpacity="0.25"
          />

          {/* Outer text path guide ring */}
          <circle cx="350" cy="350" r="260" stroke="var(--seal)" strokeWidth="1.2" strokeOpacity="0.22" />

          {/* Primary inner body ring */}
          <circle cx="350" cy="350" r="210" stroke="var(--seal)" strokeWidth="2" strokeOpacity="0.32" />
          <circle cx="350" cy="350" r="202" stroke="var(--seal)" strokeWidth="0.8" strokeOpacity="0.18" />

          {/* Geometric eight-point star / seal compass */}
          <g stroke="var(--seal)" strokeWidth="1" strokeOpacity="0.28">
            <polygon points="350,155 372,210 427,210 383,243 400,296 350,265 300,296 317,243 273,210 328,210" />
            <polygon
              points="350,155 372,210 427,210 383,243 400,296 350,265 300,296 317,243 273,210 328,210"
              transform="rotate(45 350 350)"
              strokeOpacity="0.2"
            />
          </g>

          {/* Central medallion rings */}
          <circle
            cx="350"
            cy="350"
            r="115"
            stroke="var(--seal)"
            strokeWidth="1.5"
            strokeDasharray="2 3"
            strokeOpacity="0.3"
          />
          <circle cx="350" cy="350" r="100" stroke="var(--seal)" strokeWidth="1.8" strokeOpacity="0.35" />
          <circle cx="350" cy="350" r="88" stroke="var(--seal)" strokeWidth="0.75" strokeOpacity="0.2" />

          {/* Central emblem: AMC diamond lattice */}
          <path
            d="M350,290 L392,350 L350,410 L308,350 Z"
            stroke="var(--seal)"
            strokeWidth="1.8"
            strokeOpacity="0.45"
            fill="none"
          />
          <path
            d="M350,312 L376,350 L350,388 L324,350 Z"
            stroke="var(--seal)"
            strokeWidth="1"
            strokeOpacity="0.35"
            fill="none"
          />
          {/* Diamond center bead */}
          <circle cx="350" cy="350" r="4" fill="var(--seal)" fillOpacity="0.5" />
          
          {/* Cardinal alignment dots */}
          <circle cx="350" cy="235" r="2.5" fill="var(--seal)" fillOpacity="0.4" />
          <circle cx="350" cy="465" r="2.5" fill="var(--seal)" fillOpacity="0.4" />
          <circle cx="235" cy="350" r="2.5" fill="var(--seal)" fillOpacity="0.4" />
          <circle cx="465" cy="350" r="2.5" fill="var(--seal)" fillOpacity="0.4" />
        </g>
      </svg>
    </div>
  );
}
