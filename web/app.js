class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-semibold mb-4">Something went wrong</h1>
            <p className="text-[var(--muted)] mb-4 font-mono text-sm">{String(this.state.error)}</p>
            <button onClick={() => window.location.reload()} className="btn btn-primary">Reload page</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function SectionTitle({ id, kicker, title, children }) {
  return (
    <div id={id} className="scroll-mt-24 mb-10 space-y-3">
      <div className="kicker">{kicker}</div>
      <h2 className="text-3xl md:text-4xl font-semibold tracking-tight">{title}</h2>
      {children && <p className="text-lg text-[var(--muted)] max-w-3xl">{children}</p>}
    </div>
  );
}

function Hero({ stats }) {
  return (
    <section className="grid lg:grid-cols-12 gap-10 items-center pt-16 pb-12">
      <div className="lg:col-span-6 space-y-6">
        <div className="kicker">Pre-tokenization layer · images &amp; video</div>
        <h1 className="text-5xl md:text-6xl font-semibold leading-[1.02] tracking-tight">
          Pay for <span className="text-[var(--lime)]">detail</span>,<br />not for blank space.
        </h1>
        <p className="text-lg text-[var(--muted)] leading-relaxed max-w-xl">
          Vision models charge the same tokens for an empty wall as for a page of text. TokenOpt inspects an image or
          video first and decides how many tokens each region actually deserves, using a quadtree, a max-heap,
          perceptual hashing, union-find and a trie.
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <a href="#/explainer" className="btn btn-primary px-5 py-3"><span className="icon-circle-play"></span>Watch how it works</a>
          <a href="#playground" className="btn btn-ghost px-5 py-3"><span className="icon-sliders-horizontal"></span>Open the playground</a>
        </div>
      </div>
      <div className="lg:col-span-6">
        <div className="card p-3 relative">
          <div className="flex items-center justify-between px-1 pb-3">
            <span className="label">quadtree allocation · ui screenshot</span>
            <span className="flex gap-3 font-mono text-[11px]">
              <span className="text-[var(--orange)]">■ detail</span>
              <span className="text-[var(--cyan)]">■ merged</span>
            </span>
          </div>
          <img src="/media/hero.png" alt="Quadtree allocation over a UI screenshot" className="w-full rounded-lg border border-[var(--border)]"
               onError={(e) => { e.target.style.display = "none"; }} />
          <div className="absolute -bottom-5 left-6 right-6 grid grid-cols-3 gap-2">
            {[["uniform", stats.uiBase], ["optimized", stats.uiOpt], ["saved", stats.uiRed]].map(([k, v], i) => (
              <div key={k} className={cn("rounded-lg border px-3 py-2", i === 2 ? "bg-[var(--lime)] text-black border-[var(--lime)]" : "bg-[var(--panel-2)] border-[var(--border)]")}>
                <div className={cn("font-mono text-[10px] uppercase tracking-wider", i === 2 ? "text-black/70" : "text-[var(--muted)]")}>{k}</div>
                <div className="font-mono text-lg font-semibold">{v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function StatStrip({ stats }) {
  const items = [
    [stats.uiRed, "fewer tokens on a UI screenshot"],
    [stats.vidRed, "fewer tokens on a screen recording"],
    [stats.gain, "fidelity gain vs. uniform at equal cost"],
    ["5", "data structures, written by hand"],
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 border border-[var(--border)] rounded-2xl overflow-hidden mt-12 mb-24 bg-[var(--panel)]">
      {items.map(([v, k], i) => (
        <div key={k} className={cn("p-6", i > 0 && "md:border-l border-[var(--border)]", i % 2 === 1 && "border-l md:border-l", i > 1 && "border-t md:border-t-0")}>
          <div className="font-mono text-3xl font-semibold text-[var(--lime)]">{v}</div>
          <div className="text-sm text-[var(--muted)] mt-1">{k}</div>
        </div>
      ))}
    </div>
  );
}

function useStats() {
  const [rows, setRows] = React.useState([]);
  React.useEffect(() => { apiRequest("/api/results").then(setRows).catch(() => {}); }, []);
  const by = Object.fromEntries(rows.map((r) => [r.name, r]));
  const pct = (r) => (r ? `−${Math.round(100 * r.reduction)}%` : "–");
  return {
    uiBase: by.ui ? fmtInt(by.ui.baseline) : "–",
    uiOpt: by.ui ? fmtInt(by.ui.optimized) : "–",
    uiRed: pct(by.ui),
    vidRed: pct(by.screen_rec),
    gain: by.ui ? `+${(by.ui.psnr - by.ui.uniform_psnr).toFixed(1)} dB` : "–",
  };
}

function Home() {
  const stats = useStats();
  return (
    <div className="max-w-7xl mx-auto px-6">
      <Hero stats={stats} />
      <StatStrip stats={stats} />

      <SectionTitle id="structures" kicker="Pipeline" title="Five data structures, one token budget">
        Each structure removes a different kind of redundancy before tokenization: spatial (quadtree, heap), temporal
        (hash table, union-find) and recurring overlays (trie).
      </SectionTitle>
      <StructuresGrid />

      <div className="mt-28">
        <SectionTitle id="playground" kicker="Live demo" title="Playground">
          Everything below runs the real Python engine. Change a parameter and the allocation is recomputed.
        </SectionTitle>
        <Playground />
      </div>

      <div className="mt-28">
        <SectionTitle id="results" kicker="Evaluation" title="Benchmark results">
          From the last <code>python main.py demo</code> run, compared against a uniform patch grid.
        </SectionTitle>
        <ResultsSection />
      </div>
    </div>
  );
}

function App() {
  const [hash, setHash] = React.useState(window.location.hash);
  React.useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const route = hash.startsWith("#/explainer") ? "explainer" : "home";

  // Section anchors (#playground, ...) may be clicked from the explainer page: scroll once Home has rendered.
  React.useEffect(() => {
    if (route === "explainer" || hash === "#/" || hash === "") {
      window.scrollTo(0, 0);
      return;
    }
    const el = document.getElementById(hash.slice(1));
    if (el) requestAnimationFrame(() => el.scrollIntoView({ behavior: "smooth" }));
  }, [hash, route]);

  try {
    return (
      <div className="min-h-screen" data-name="app" data-file="app.js">
        <Header route={route} />
        <main>{route === "explainer" ? <ExplainerPage /> : <Home />}</main>
        <Footer />
      </div>
    );
  } catch (error) {
    console.error("App component error:", error);
    return null;
  }
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
);
