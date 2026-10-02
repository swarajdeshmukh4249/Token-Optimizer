// Interactive playground: pick/upload a file, tune parameters, see live results.

const PATCH_SIZES = [8, 14, 16, 32];

function Stat({ icon, label, value, sub, accent }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 label"><span className={`${icon} text-sm`}></span>{label}</div>
      <div className={cn("mt-2 text-2xl font-semibold tracking-tight font-mono", accent && "text-[var(--lime)]")}>{value}</div>
      {sub && <div className="text-xs text-[var(--muted)] mt-1">{sub}</div>}
    </div>
  );
}

function SampleCard({ s, active, onClick }) {
  return (
    <button onClick={onClick}
      className={cn("group text-left rounded-xl border overflow-hidden transition-all bg-[var(--bg)]",
        active ? "border-[var(--lime)] ring-1 ring-[var(--lime)]" : "border-[var(--border)] hover:border-[var(--muted)]")}>
      <div className="aspect-[4/3] overflow-hidden relative">
        {s.thumb && <img src={s.thumb} alt={s.label} className="w-full h-full object-cover opacity-90 group-hover:opacity-100 group-hover:scale-105 transition" />}
        <span className="absolute top-1.5 right-1.5 rounded bg-black/75 text-white font-mono text-[10px] px-1.5 py-0.5 flex items-center gap-1">
          <span className={s.kind === "video" ? "icon-film" : "icon-image"}></span>{s.kind}
        </span>
      </div>
      <div className={cn("px-2 py-1.5 text-xs truncate", active ? "text-[var(--lime)]" : "")}>{s.label}</div>
    </button>
  );
}

function Dropzone({ onFile, busy }) {
  const [over, setOver] = React.useState(false);
  const input = React.useRef(null);
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]); }}
      onClick={() => input.current && input.current.click()}
      className={cn("rounded-xl border border-dashed p-5 text-center cursor-pointer transition-colors",
        over ? "border-[var(--lime)] bg-[rgba(212,255,63,0.05)]" : "border-[var(--border)] hover:bg-[var(--panel-2)]")}>
      <div className={cn("text-2xl text-[var(--muted)]", busy ? "icon-loader-circle animate-spin inline-block" : "icon-upload")}></div>
      <div className="mt-1 text-sm font-medium">Drop an image or video</div>
      <div className="text-xs text-[var(--muted)]">PNG, JPG, MP4, MOV… up to 60 MB</div>
      <input ref={input} type="file" accept="image/*,video/*" className="hidden"
             onChange={(e) => e.target.files[0] && onFile(e.target.files[0])} />
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange, format, hint }) {
  return (
    <div>
      <div className="flex justify-between items-baseline">
        <span className="text-sm">{label}</span>
        <span className="text-sm font-mono text-[var(--lime)]">{format ? format(value) : value}</span>
      </div>
      <input type="range" className="w-full mt-2" min={min} max={max} step={step} value={value}
             onChange={(e) => onChange(+e.target.value)} />
      {hint && <p className="text-xs text-[var(--muted)] mt-1">{hint}</p>}
    </div>
  );
}

function ImageResults({ r }) {
  const [view, setView] = React.useState("overlay");
  const tabs = [
    ["overlay", "Quadtree", "icon-grid-2x2"],
    ["compare", "Compare at equal cost", "icon-columns-2"],
    ["adaptive", "What the model sees", "icon-eye"],
    ["original", "Original", "icon-image"],
  ];
  const caption = {
    overlay: `${fmtInt(r.tokens)} leaves. Orange = single-patch detail, cyan = merged region (1 token each).`,
    compare: `Left: uniform grid shrunk to ${fmtInt(r.uniform_tokens)} tokens (${fmtDb(r.uniform_psnr)}). Right: adaptive at ${fmtInt(r.tokens)} tokens (${fmtDb(r.psnr)}). Drag to compare.`,
    adaptive: "Each leaf resampled to a single patch and stretched back: exactly what the token budget can carry.",
    original: `${r.width}×${r.height}px, ${r.grid[0]}×${r.grid[1]} patch grid at ${r.patch}px.`,
  }[view];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat icon="icon-layers" label="Baseline" value={fmtInt(r.baseline)} sub="uniform patch tokens" />
        <Stat icon="icon-sparkles" label="Optimized" value={fmtInt(r.tokens)} sub={r.budget ? `budget ${fmtInt(r.budget)}` : "threshold mode"} />
        <Stat icon="icon-trending-down" label="Saved" value={`${r.reduction.toFixed(1)}%`} sub={`${fmtInt(r.baseline - r.tokens)} tokens`} accent />
        <Stat icon="icon-gauge" label="Fidelity" value={fmtDb(r.psnr)} sub={`SSIM ${r.ssim.toFixed(3)} · ${r.ms} ms`} />
      </div>

      <div className="card overflow-hidden">
        <div className="flex flex-wrap gap-1 p-2 border-b border-[var(--border)]">
          {tabs.map(([k, label, icon]) => (
            <button key={k} onClick={() => setView(k)}
              className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors",
                view === k ? "bg-[var(--lime)] text-black" : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--panel-2)]")}>
              <span className={icon}></span>{label}
            </button>
          ))}
        </div>
        <div className="bg-black p-3">
          {view === "compare"
            ? <CompareSlider left={r.images.uniform} right={r.images.adaptive} leftLabel="Uniform" rightLabel="Adaptive" />
            : <img src={r.images[view]} alt={view} className="w-full h-auto block rounded" />}
        </div>
        <p className="px-4 py-3 text-sm text-[var(--muted)] border-t border-[var(--border)]">{caption}</p>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <div className="card p-4 space-y-3">
          <div className="label">Token count</div>
          <TokenMeter baseline={r.baseline} tokens={r.tokens} />
          <div className="text-xs text-[var(--muted)] pt-1">
            Uniform at the same cost scores {fmtDb(r.uniform_psnr)} / SSIM {r.uniform_ssim.toFixed(3)}.
          </div>
        </div>
        <div className="card p-4">
          <div className="label mb-2">Leaf sizes (patches per token)</div>
          <LeafHistogram sizes={r.leaf_sizes} />
        </div>
        <div className="card p-4">
          <div className="label mb-1">PSNR vs token budget</div>
          <div className="flex gap-3 text-[11px] font-mono text-[var(--muted)] mb-1">
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[var(--lime)] inline-block"></span>adaptive</span>
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#5b6170] inline-block"></span>uniform</span>
          </div>
          <RDChart curve={r.curve} />
        </div>
      </div>

      <div className="card p-4 flex flex-col md:flex-row md:items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg border border-[var(--border)] flex items-center justify-center"><span className="icon-send text-lg"></span></div>
          <div>
            <div className="font-semibold">Claude adapter <span className="font-mono text-xs font-normal text-[var(--muted)]">pixel-area estimate</span></div>
            <div className="text-sm text-[var(--muted)]">
              {r.claude.fallback
                ? "Detail is spread across the image, so the adapter sends the original: no gain here."
                : `Overview thumbnail + ${r.claude.crops} full-resolution detail crop${r.claude.crops === 1 ? "" : "s"}.`}
            </div>
          </div>
        </div>
        <div className="md:ml-auto flex gap-6 text-sm">
          <div><div className="label">Full image</div><div className="font-mono text-lg">{fmtInt(r.claude.full)}</div></div>
          <div><div className="label">Payload</div><div className="font-mono text-lg">{fmtInt(r.claude.optimized)}</div></div>
          <div><div className="label">Saved</div><div className="font-mono text-lg text-[var(--lime)]">{(100 * (1 - r.claude.optimized / r.claude.full)).toFixed(1)}%</div></div>
        </div>
      </div>
    </div>
  );
}

function VideoResults({ r }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat icon="icon-layers" label="Baseline" value={fmtInt(r.baseline)} sub={`${r.frames.length} frames × ${fmtInt(r.per_frame_baseline)}`} />
        <Stat icon="icon-sparkles" label="Optimized" value={fmtInt(r.tokens)} sub={`${r.roles.key} key · ${r.roles.delta} delta · ${r.roles.duplicate} dup`} />
        <Stat icon="icon-trending-down" label="Saved" value={`${r.reduction.toFixed(1)}%`} sub={`${fmtInt(r.baseline - r.tokens)} tokens`} accent />
        <Stat icon="icon-gauge" label="Fidelity" value={fmtDb(r.mean_psnr)} sub={`min ${fmtDb(r.min_psnr)} · ${(r.ms / 1000).toFixed(1)} s`} />
      </div>
      <div className="card p-5">
        <div className="flex items-center justify-between mb-6">
          <div className="label">Tokens charged per sampled frame</div>
          <div className="font-mono text-xs text-[var(--muted)]">{r.scenes} scenes (union-find) · {r.overlays} static blocks (trie)</div>
        </div>
        <FrameTimeline frames={r.frames} perFrame={r.per_frame_baseline} />
      </div>
      <div className="card p-5">
        <div className="label mb-3">First frame of each scene: original vs what the model receives</div>
        <div className="grid sm:grid-cols-2 gap-4">
          {r.keyframes.map((k) => (
            <div key={k.index} className="rounded-xl border border-[var(--border)] overflow-hidden">
              <div className="grid grid-cols-2">
                <img src={k.original} alt="original" className="w-full h-auto" />
                <img src={k.seen} alt="model view" className="w-full h-auto" />
              </div>
              <div className="px-3 py-2 font-mono text-xs text-[var(--muted)] flex justify-between">
                <span>scene {k.scene + 1} · frame {k.index} · t={k.t}s</span>
                <span>{k.tokens} tok · {k.frames_in_scene} frames</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card h-full min-h-[24rem] flex flex-col items-center justify-center text-center p-10">
      <div className="icon-scan text-4xl text-[var(--muted)]"></div>
      <h3 className="mt-4 text-lg font-semibold">Pick a sample or drop a file</h3>
      <p className="mt-1 text-sm text-[var(--muted)] max-w-sm">The optimizer runs locally and shows how many tokens each region actually needs.</p>
    </div>
  );
}

function Playground() {
  const [samples, setSamples] = React.useState([]);
  const [source, setSource] = React.useState(null); // {sample} or {id}, plus name/kind
  const [patch, setPatch] = React.useState(16);
  const [thr, setThr] = React.useState(40);
  const [useBudget, setUseBudget] = React.useState(false);
  const [budget, setBudget] = React.useState(30);
  const [fps, setFps] = React.useState(2);
  const [result, setResult] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const reqId = React.useRef(0);

  React.useEffect(() => {
    apiRequest("/api/samples")
      .then((s) => {
        setSamples(s);
        const wanted = new URLSearchParams(window.location.search).get("sample") || "ui";
        const first = s.find((x) => x.name === wanted) || s[0];
        if (first) setSource({ sample: first.name, name: first.label, kind: first.kind });
      })
      .catch((e) => setError(e.message));
  }, []);

  React.useEffect(() => {
    if (!source) return;
    const id = ++reqId.current;
    const timer = setTimeout(async () => {
      setLoading(true);
      setError(null);
      const ref = source.sample ? { sample: source.sample } : { id: source.id };
      try {
        const data = source.kind === "video"
          ? await apiRequest("/api/video", { ...ref, patch, var_threshold: thr, fps })
          : await apiRequest("/api/image", { ...ref, patch, var_threshold: thr, budget_ratio: useBudget ? budget / 100 : null });
        if (id === reqId.current) setResult({ kind: source.kind, data });
      } catch (e) {
        if (id === reqId.current) setError(e.message);
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [source, patch, thr, useBudget, budget, fps]);

  async function handleFile(file) {
    setUploading(true);
    setError(null);
    try {
      const data = await readFileAsDataURL(file);
      const info = await apiRequest("/api/upload", { name: file.name, type: file.type, data });
      setSource({ id: info.id, name: info.name, kind: info.kind });
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  const isVideo = source && source.kind === "video";
  const shown = result && source && result.kind === source.kind ? result : null;

  return (
    <div className="grid lg:grid-cols-12 gap-6" data-name="playground" data-file="components/playground.js">
      <aside className="lg:col-span-4 space-y-5">
        <div className="card p-5 space-y-4">
          <div className="label">Input</div>
          <div className="grid grid-cols-3 gap-2">
            {samples.map((s) => (
              <SampleCard key={s.name} s={s} active={source && source.sample === s.name}
                          onClick={() => setSource({ sample: s.name, name: s.label, kind: s.kind })} />
            ))}
          </div>
          <Dropzone onFile={handleFile} busy={uploading} />
          {source && !source.sample && (
            <div className="text-xs text-[var(--muted)] flex items-center gap-1.5">
              <span className={isVideo ? "icon-film" : "icon-image"}></span>Using upload: <span className="text-[var(--lime)]">{source.name}</span>
            </div>
          )}
        </div>

        <div className="card p-5 space-y-5">
          <div className="label">Parameters</div>
          <div>
            <div className="text-sm mb-2">Encoder patch size</div>
            <div className="seg grid-cols-4">
              {PATCH_SIZES.map((p) => (
                <button key={p} onClick={() => setPatch(p)} className={cn("seg-btn", patch === p && "seg-btn-on")}>{p}px</button>
              ))}
            </div>
          </div>
          <Slider label="Variance threshold τ" value={thr} min={0} max={300} step={5} onChange={setThr}
                  hint="Split a region while its pixel variance is above τ. Higher = fewer tokens, less detail." />
          {!isVideo && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm">Hard token budget <span className="font-mono text-xs text-[var(--muted)]">max-heap</span></span>
                <button onClick={() => setUseBudget(!useBudget)} aria-pressed={useBudget} aria-label="Toggle token budget"
                  className={cn("w-10 h-6 rounded-full relative transition-colors", useBudget ? "bg-[var(--lime)]" : "bg-[var(--border)]")}>
                  <span className={cn("absolute top-0.5 w-5 h-5 rounded-full transition-all", useBudget ? "left-[18px] bg-black" : "left-0.5 bg-[var(--muted)]")}></span>
                </button>
              </div>
              {useBudget && (
                <Slider label="Budget" value={budget} min={2} max={100} step={1} onChange={setBudget}
                        format={(v) => `${v}% of baseline`} hint="Best-first refinement stops when the budget is spent." />
              )}
            </div>
          )}
          {isVideo && (
            <div>
              <div className="text-sm mb-2">Sampling rate</div>
              <div className="seg grid-cols-4">
                {[1, 2, 4, 8].map((f) => (
                  <button key={f} onClick={() => setFps(f)} className={cn("seg-btn", fps === f && "seg-btn-on")}>{f} fps</button>
                ))}
              </div>
            </div>
          )}
        </div>
      </aside>

      <section className="lg:col-span-8 relative">
        {error && (
          <div className="mb-4 rounded-xl border border-[rgba(255,107,53,0.4)] bg-[rgba(255,107,53,0.1)] text-[var(--orange)] px-4 py-3 text-sm flex items-start gap-2">
            <span className="icon-triangle-alert mt-0.5"></span><span>{error}</span>
          </div>
        )}
        {loading && (
          <div className="absolute right-0 -top-9 flex items-center gap-2 font-mono text-xs text-[var(--muted)]">
            <span className="icon-loader-circle animate-spin inline-block"></span>optimizing{isVideo ? " video, a few seconds" : ""}…
          </div>
        )}
        <div className={cn("transition-opacity", loading && shown ? "opacity-60" : "")}>
          {!shown ? <EmptyState /> : shown.kind === "video" ? <VideoResults r={shown.data} /> : <ImageResults r={shown.data} />}
        </div>
      </section>
    </div>
  );
}
