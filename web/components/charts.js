// Small hand-rolled SVG / div charts used by the playground.

function RDChart({ curve }) {
  if (!curve || !curve.length) return null;
  const W = 320, H = 170, L = 34, R = 10, T = 10, B = 26;
  const ys = curve.flatMap((p) => [p.adaptive, p.uniform]);
  const yMin = Math.floor(Math.min(...ys) / 5) * 5;
  const yMax = Math.ceil(Math.max(...ys) / 5) * 5;
  const xMax = Math.max(...curve.map((p) => p.frac));
  const x = (f) => L + (f / xMax) * (W - L - R);
  const y = (v) => T + (1 - (v - yMin) / Math.max(1, yMax - yMin)) * (H - T - B);
  const line = (key) => curve.map((p, i) => `${i ? "L" : "M"}${x(p.frac).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const ticks = [yMin, (yMin + yMax) / 2, yMax];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto font-mono" role="img" aria-label="PSNR vs token budget">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#282c34" />
          <text x={L - 6} y={y(t) + 4} fontSize="10" textAnchor="end" fill="#8b919c">{Math.round(t)}</text>
        </g>
      ))}
      {curve.map((p) => (
        <text key={p.frac} x={x(p.frac)} y={H - 8} fontSize="10" textAnchor="middle" fill="#8b919c">{Math.round(p.frac * 100)}%</text>
      ))}
      <path d={line("uniform")} fill="none" stroke="#5b6170" strokeWidth="2" />
      <path d={line("adaptive")} fill="none" stroke="#d4ff3f" strokeWidth="2.5" />
      {curve.map((p) => <circle key={"u" + p.frac} cx={x(p.frac)} cy={y(p.uniform)} r="3" fill="#5b6170"><title>{`Uniform @ ${Math.round(p.frac * 100)}%: ${p.uniform.toFixed(1)} dB`}</title></circle>)}
      {curve.map((p) => <circle key={"a" + p.frac} cx={x(p.frac)} cy={y(p.adaptive)} r="3.5" fill="#d4ff3f"><title>{`Adaptive @ ${Math.round(p.frac * 100)}%: ${p.adaptive.toFixed(1)} dB`}</title></circle>)}
    </svg>
  );
}

function TokenMeter({ baseline, tokens }) {
  const pct = baseline ? Math.max(0.5, (100 * tokens) / baseline) : 100;
  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="flex justify-between mb-1">
          <span className="text-[var(--muted)]">Uniform grid</span>
          <span className="font-mono">{fmtInt(baseline)}</span>
        </div>
        <div className="h-2.5 rounded-full bg-[#5b6170]"></div>
      </div>
      <div>
        <div className="flex justify-between mb-1">
          <span className="text-[var(--muted)]">Optimized</span>
          <span className="font-mono text-[var(--lime)]">{fmtInt(tokens)}</span>
        </div>
        <div className="h-2.5 rounded-full bg-[var(--bg)] overflow-hidden">
          <div className="h-full rounded-full bg-[var(--lime)] transition-all duration-500" style={{ width: `${pct}%` }}></div>
        </div>
      </div>
    </div>
  );
}

function LeafHistogram({ sizes }) {
  if (!sizes) return null;
  const entries = Object.entries(sizes);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div className="flex items-end gap-2 h-28">
      {entries.map(([k, v]) => (
        <div key={k} className="flex-1 flex flex-col items-center gap-1 h-full justify-end">
          <span className="text-[10px] font-mono text-[var(--muted)]">{v}</span>
          <div className={`w-full rounded-t-md ${k === "1" ? "bg-[var(--orange)]" : "bg-[var(--cyan)]"}`} style={{ height: `${Math.max(2, (90 * v) / max)}%` }}></div>
          <span className="text-[10px] font-mono text-[var(--muted)]">{k}</span>
        </div>
      ))}
    </div>
  );
}

// Before/after wipe: drag the handle to reveal `right` over `left`.
function CompareSlider({ left, right, leftLabel, rightLabel }) {
  const [pos, setPos] = React.useState(50);
  return (
    <div className="relative select-none">
      <img src={left} className="w-full h-auto block" alt={leftLabel} />
      <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `inset(0 0 0 ${pos}%)` }}>
        <img src={right} className="w-full h-auto block" alt={rightLabel} />
      </div>
      <div className="absolute top-0 bottom-0 w-0.5 bg-[var(--lime)]" style={{ left: `${pos}%` }}>
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-[var(--lime)] text-black flex items-center justify-center shadow-lg">
          <span className="icon-move-horizontal text-sm"></span>
        </div>
      </div>
      <span className="absolute top-3 left-3 font-mono text-xs bg-black/75 text-white rounded-md px-2 py-1">{leftLabel}</span>
      <span className="absolute top-3 right-3 font-mono text-xs bg-[var(--lime)] text-black rounded-md px-2 py-1">{rightLabel}</span>
      <input type="range" min="0" max="100" value={pos} onChange={(e) => setPos(+e.target.value)}
             className="absolute inset-0 w-full h-full opacity-0 cursor-ew-resize" aria-label="Compare position" />
    </div>
  );
}

const ROLE_STYLE = {
  key: { bg: "bg-[var(--lime)]", label: "Key frame" },
  delta: { bg: "bg-[var(--cyan)]", label: "Delta (changed regions)" },
  duplicate: { bg: "bg-[var(--dup)]", label: "Duplicate (0 tokens)" },
};

function FrameTimeline({ frames, perFrame }) {
  const logMax = Math.log10(perFrame + 1);
  return (
    <div>
      <div className="relative h-40 flex items-end gap-[2px] border-b border-[var(--border)]">
        <div className="absolute left-0 right-0 top-0 border-t border-dashed border-[var(--muted)]"></div>
        <span className="absolute right-0 -top-5 font-mono text-[10px] text-[var(--muted)]">uniform baseline: {fmtInt(perFrame)} tokens / frame</span>
        {frames.map((f) => {
          const h = f.tokens > 0 ? 6 + (94 * Math.log10(f.tokens + 1)) / logMax : 2;
          return (
            <div key={f.i} className="flex-1 h-full flex items-end group relative">
              <div className={`w-full rounded-t-sm ${ROLE_STYLE[f.role].bg}`} style={{ height: `${Math.min(100, h)}%` }}></div>
              <div className="hidden group-hover:block absolute bottom-full mb-2 left-1/2 -translate-x-1/2 z-10 whitespace-nowrap rounded-lg bg-[var(--panel-2)] border border-[var(--border)] font-mono text-xs px-2 py-1">
                frame {f.i} · t={f.t}s · {f.role} · {f.tokens} tok{f.ref != null ? ` · ref ${f.ref}` : ""}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-4 mt-3 text-xs text-[var(--muted)]">
        {Object.entries(ROLE_STYLE).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1.5"><span className={`w-3 h-3 rounded-sm ${v.bg}`}></span>{v.label}</span>
        ))}
        <span>Bar height is log-scaled.</span>
      </div>
    </div>
  );
}
