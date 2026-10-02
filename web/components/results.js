// Benchmark results from the last `python main.py demo` run.
function ResultsSection() {
  const [rows, setRows] = React.useState(null);
  React.useEffect(() => {
    apiRequest("/api/results").then(setRows).catch(() => setRows([]));
  }, []);

  if (rows === null) return <div className="text-sm text-[var(--muted)]">Loading results…</div>;
  if (!rows.length) {
    return <div className="card p-6 text-sm text-[var(--muted)]">No benchmark yet. Run <code>python main.py demo</code> and refresh.</div>;
  }

  return (
    <div className="space-y-6" data-name="results" data-file="components/results.js">
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left border-b border-[var(--border)]">
            <tr className="label">
              <th className="px-4 py-3 font-semibold">Input</th>
              <th className="px-4 py-3 font-semibold">Size</th>
              <th className="px-4 py-3 font-semibold text-right">Baseline</th>
              <th className="px-4 py-3 font-semibold text-right">Optimized</th>
              <th className="px-4 py-3 font-semibold text-right">Reduction</th>
              <th className="px-4 py-3 font-semibold text-right">PSNR</th>
              <th className="px-4 py-3 font-semibold text-right">Time</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-t border-[var(--border)] hover:bg-[var(--panel-2)]">
                <td className="px-4 py-3 flex items-center gap-2">
                  <span className={cn(r.kind === "video" ? "icon-film" : "icon-image", "text-[var(--muted)]")}></span>{r.name}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--muted)]">{r.size}</td>
                <td className="px-4 py-3 text-right font-mono">{fmtInt(r.baseline)}</td>
                <td className="px-4 py-3 text-right font-mono">{fmtInt(r.optimized)}</td>
                <td className="px-4 py-3 text-right">
                  <span className={cn("inline-block rounded px-2 py-0.5 font-mono text-xs",
                    r.reduction > 0.5 ? "bg-[var(--lime)] text-black" : r.reduction > 0.05 ? "bg-[rgba(103,232,249,0.15)] text-[var(--cyan)]" : "bg-[var(--panel-2)] text-[var(--muted)]")}>
                    {r.reduction > 0.0005 ? "−" : ""}{(100 * r.reduction).toFixed(1)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-right font-mono">{typeof r.psnr === "number" && isFinite(r.psnr) ? `${r.psnr.toFixed(1)} dB` : "lossless"}</td>
                <td className="px-4 py-3 text-right font-mono text-[var(--muted)]">{Math.round(r.ms)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid md:grid-cols-2 gap-6">
        <figure className="card p-3">
          <div className="rounded-lg bg-white p-2"><img src="/results/token_bars.png" alt="Tokens before vs after" className="w-full h-auto" /></div>
          <figcaption className="font-mono text-xs text-[var(--muted)] px-1 pt-3">fig. 1 · tokens before and after, log scale</figcaption>
        </figure>
        <figure className="card p-3">
          <div className="rounded-lg bg-white p-2"><img src="/results/rd_curves.png" alt="Fidelity at equal token cost" className="w-full h-auto" /></div>
          <figcaption className="font-mono text-xs text-[var(--muted)] px-1 pt-3">fig. 2 · PSNR at equal token budgets: adaptive quadtree vs uniform grid</figcaption>
        </figure>
      </div>
      <div className="rounded-xl border border-[rgba(255,107,53,0.4)] bg-[rgba(255,107,53,0.07)] px-4 py-3 text-sm">
        <span className="font-semibold text-[var(--orange)]">Honest limits so far:</span>{" "}
        <span className="text-[var(--muted)]">inputs are synthetic; fidelity is pixel-level (PSNR/SSIM), not answer quality from a real model;
        dense texture gets no reduction by design; the screen recording is a favourable case.</span>
      </div>
    </div>
  );
}
