// Explainer page: narrated video + clickable chapters + live transcript.

function fmtTime(s) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function ExplainerPage() {
  const [data, setData] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [t, setT] = React.useState(0);
  const [rate, setRate] = React.useState(1);
  const video = React.useRef(null);

  React.useEffect(() => {
    fetch("/media/chapters.json", { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setData)
      .catch(() => setError("The explainer video has not been rendered yet."));
  }, []);

  const chapters = data ? data.chapters : [];
  const active = chapters.reduce((acc, c, i) => (t >= c.start - 0.05 ? i : acc), 0);
  const cue = chapters.length ? (chapters[active].cues || []).find((c) => t >= c.start - 0.1 && t <= c.end + 0.3) : null;

  function seek(s, play = true) {
    const v = video.current;
    if (!v) return;
    v.currentTime = s + 0.01;
    setT(s);
    if (play) v.play().catch(() => {});
  }

  React.useEffect(() => {
    function onKey(e) {
      if (["INPUT", "TEXTAREA"].includes(document.activeElement.tagName) || !chapters.length) return;
      const v = video.current;
      if (e.key === "ArrowRight" && active < chapters.length - 1) { e.preventDefault(); seek(chapters[active + 1].start); }
      if (e.key === "ArrowLeft") { e.preventDefault(); seek(chapters[Math.max(0, t - chapters[active].start > 2 ? active : active - 1)].start); }
      if (e.key === " " && v && document.activeElement !== v) { e.preventDefault(); v.paused ? v.play() : v.pause(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chapters, active, t]);

  React.useEffect(() => { if (video.current) video.current.playbackRate = rate; }, [rate]);

  return (
    <div className="max-w-7xl mx-auto px-6 pt-12" data-name="explainer" data-file="components/explainer.js">
      <div className="mb-8 space-y-3">
        <div className="kicker">Explainer · narrated walkthrough</div>
        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight">How TokenOpt works</h1>
        <p className="text-lg text-[var(--muted)] max-w-3xl">
          {data ? `${chapters.length} chapters, ${fmtTime(data.duration)}. ` : ""}
          Every visual in the video is computed by the real engine. Jump with the chapters, or follow the live transcript.
        </p>
      </div>

      {error && (
        <div className="card p-6 text-sm text-[var(--muted)]">
          {error} Run <code>.venv/bin/python web/explainer/make_video.py</code>, then refresh this page.
        </div>
      )}

      {data && (
        <div className="grid lg:grid-cols-12 gap-6">
          <div className="lg:col-span-8 space-y-4">
            <div className="card overflow-hidden p-0">
              <video ref={video} src="/media/explainer.mp4" poster="/media/poster.jpg" controls preload="metadata"
                     onTimeUpdate={(e) => setT(e.target.currentTime)} onSeeked={(e) => setT(e.target.currentTime)}
                     className="w-full aspect-video bg-black block" />
            </div>
            <div className="card p-5">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="font-mono text-xs text-[var(--lime)]">{chapters[active].tag}</div>
                  <div className="text-xl font-semibold truncate">{chapters[active].title}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button className="btn btn-ghost px-3" disabled={active === 0} onClick={() => seek(chapters[active - 1].start)} aria-label="Previous chapter">
                    <span className="icon-skip-back"></span>
                  </button>
                  <button className="btn btn-ghost px-3" disabled={active === chapters.length - 1} onClick={() => seek(chapters[active + 1].start)} aria-label="Next chapter">
                    <span className="icon-skip-forward"></span>
                  </button>
                  <div className="seg grid-cols-3 w-40">
                    {[1, 1.25, 1.5].map((r) => (
                      <button key={r} onClick={() => setRate(r)} className={cn("seg-btn text-xs", rate === r && "seg-btn-on")}>{r}×</button>
                    ))}
                  </div>
                </div>
              </div>
              <p className="mt-4 text-lg leading-relaxed min-h-[3.5rem]">
                {cue ? cue.text : <span className="text-[var(--muted)]">Press play, or pick a chapter.</span>}
              </p>
              <div className="mt-3 font-mono text-[11px] text-[var(--muted)]">space: play / pause · ← →: previous / next chapter</div>
            </div>
          </div>

          <aside className="lg:col-span-4">
            <div className="card p-2 lg:sticky lg:top-20">
              <div className="label px-3 pt-2 pb-3">Chapters</div>
              <ol className="space-y-0.5">
                {chapters.map((c, i) => {
                  const on = i === active;
                  const prog = on ? Math.min(1, Math.max(0, (t - c.start) / (c.end - c.start))) : t >= c.end ? 1 : 0;
                  return (
                    <li key={c.tag}>
                      <button onClick={() => seek(c.start)}
                        className={cn("w-full text-left rounded-lg px-3 py-2 relative overflow-hidden transition-colors",
                          on ? "bg-[var(--panel-2)]" : "hover:bg-[var(--panel-2)]")}>
                        <div className="flex items-baseline gap-3">
                          <span className={cn("font-mono text-xs w-6", on ? "text-[var(--lime)]" : "text-[var(--muted)]")}>{c.tag.slice(0, 2)}</span>
                          <span className={cn("flex-1 text-sm", on ? "text-[var(--text)]" : "text-[var(--muted)]")}>
                            {c.tag.includes("·") ? c.tag.split("·")[1].trim() : "Introduction"}
                          </span>
                          <span className="font-mono text-[11px] text-[var(--muted)]">{fmtTime(c.start)}</span>
                        </div>
                        <span className="absolute left-0 bottom-0 h-0.5 bg-[var(--lime)] transition-all" style={{ width: `${prog * 100}%` }}></span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </div>
          </aside>

          <section className="lg:col-span-12 mt-6">
            <div className="label mb-4">Full transcript · click any line to jump there</div>
            <div className="grid md:grid-cols-2 gap-4">
              {chapters.map((c, i) => (
                <div key={c.tag} className={cn("card p-5", i === active && "border-[rgba(212,255,63,0.5)]")}>
                  <div className="flex items-baseline justify-between mb-3">
                    <div>
                      <span className="font-mono text-xs text-[var(--lime)] mr-2">{c.tag.slice(0, 2)}</span>
                      <span className="font-semibold">{c.title}</span>
                    </div>
                    <button onClick={() => seek(c.start)} className="font-mono text-xs text-[var(--muted)] hover:text-[var(--lime)]">▶ {fmtTime(c.start)}</button>
                  </div>
                  <div className="space-y-2">
                    {(c.cues || c.lines.map((text) => ({ text, start: c.start }))).map((q, k) => {
                      const speaking = cue && cue.text === q.text && i === active;
                      return (
                        <p key={k} onClick={() => seek(q.start)}
                           className={cn("text-sm leading-relaxed cursor-pointer rounded px-1 -mx-1 transition-colors",
                             speaking ? "text-black bg-[var(--lime)]" : "text-[var(--muted)] hover:text-[var(--text)]")}>
                          {q.text}
                        </p>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
