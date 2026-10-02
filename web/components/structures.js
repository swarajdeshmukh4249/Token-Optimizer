// Pipeline strip + the five data structures as glowing cards.

const PIPELINE = [
  { n: "01", title: "Decode", text: "Image, or video sampled at N fps", icon: "icon-file-input" },
  { n: "02", title: "Allocate", text: "Quadtree + summed-area table (+ max-heap budget)", icon: "icon-grid-2x2" },
  { n: "03", title: "De-duplicate", text: "pHash index, union-find scenes, overlay trie", icon: "icon-copy-minus" },
  { n: "04", title: "Manifest", text: "Model-agnostic list of regions, 1 token each", icon: "icon-file-json" },
  { n: "05", title: "Adapt", text: "Provider format, e.g. Claude overview + crops", icon: "icon-plug" },
];

function PipelineStrip() {
  return (
    <ol className="grid grid-cols-1 md:grid-cols-5 gap-3 mb-6">
      {PIPELINE.map((s, i) => (
        <li key={s.n} className="card p-4 relative">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs text-[var(--lime)]">{s.n}</span>
            <span className={`${s.icon} text-[var(--muted)]`}></span>
          </div>
          <div className="mt-3 font-semibold">{s.title}</div>
          <div className="mt-1 text-sm text-[var(--muted)] leading-snug">{s.text}</div>
          {i < PIPELINE.length - 1 && (
            <span className="hidden md:block absolute -right-[11px] top-1/2 -translate-y-1/2 z-10 icon-chevron-right text-[var(--muted)]"></span>
          )}
        </li>
      ))}
    </ol>
  );
}

function StructuresGrid() {
  try {
    return (
      <div data-name="structures" data-file="components/structures.js">
        <PipelineStrip />
        <ul className="grid grid-cols-1 grid-rows-none gap-4 md:grid-cols-12 md:grid-rows-3 lg:gap-4 xl:max-h-[34rem] xl:grid-rows-2">
          <GridItem area="md:[grid-area:1/1/2/7] xl:[grid-area:1/1/2/5]" icon="icon-grid-2x2" tag="tree · O(nodes)"
            title="Adaptive quadtree"
            description="Splits the patch grid only where pixels vary. A summed-area table gives each region's variance in O(1). One leaf = one token." />
          <GridItem area="md:[grid-area:1/7/2/13] xl:[grid-area:2/1/3/5]" icon="icon-list-ordered" tag="heap · O(log n)"
            title="Max-heap budget"
            description="Under a hard token budget, always refine the region losing the most detail next: best-first allocation keyed on squared error." />
          <GridItem area="md:[grid-area:2/1/3/7] xl:[grid-area:1/5/3/8]" icon="icon-hash" tag="hashing · pigeonhole" highlight
            title="Perceptual hash table"
            description="A 64-bit DCT hash per frame, split into bands, each band in a chained hash table. Every near-duplicate within Hamming distance d is found without a full scan, even when the video cuts back to an old scene." />
          <GridItem area="md:[grid-area:2/7/3/13] xl:[grid-area:1/8/2/13]" icon="icon-git-merge" tag="disjoint sets · α(n)"
            title="Union-find scenes"
            description="Merges similar consecutive frames and duplicates into scenes. Only each scene's first frame is fully encoded; the rest send changed regions." />
          <GridItem area="md:[grid-area:3/1/4/13] xl:[grid-area:2/8/3/13]" icon="icon-network" tag="trie · prefix counts"
            title="Overlay trie"
            description="Counts (block position + block hash) keys across frames. Logos and toolbars that recur are sent once, then referenced." />
        </ul>
      </div>
    );
  } catch (error) {
    console.error("StructuresGrid component error:", error);
    return null;
  }
}

function GridItem({ area, icon, tag, title, description, highlight }) {
  return (
    <li className={`min-h-[14rem] list-none ${area}`}>
      <div className="relative h-full rounded-2xl border border-[var(--border)] p-2 md:rounded-3xl md:p-3">
        <GlowingEffect blur={0} borderWidth={2} spread={80} glow={true} disabled={false} proximity={64} inactiveZone={0.01} />
        <div className="border-0.75 border-[var(--border)] relative flex h-full flex-col justify-between gap-6 overflow-hidden rounded-xl bg-[var(--panel)] p-6">
          <div className="flex items-center justify-between">
            <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center border",
              highlight ? "border-[var(--lime)] text-[var(--lime)]" : "border-[var(--border)] text-[var(--text)]")}>
              <span className={`${icon} text-lg`}></span>
            </div>
            <span className="font-mono text-[11px] text-[var(--muted)]">{tag}</span>
          </div>
          <div className="space-y-2">
            <h3 className="text-xl md:text-2xl font-semibold tracking-tight">{title}</h3>
            <p className="text-sm md:text-[15px] leading-relaxed text-[var(--muted)]">{description}</p>
          </div>
        </div>
      </div>
    </li>
  );
}
