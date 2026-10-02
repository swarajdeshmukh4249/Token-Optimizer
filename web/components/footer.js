function Footer() {
  try {
    const team = ["Swaraj Deshmukh", "Tanmay Tamkhane", "Tanishka Tanawade", "Tanishq Kadoo"];
    return (
      <footer className="border-t border-[var(--border)] mt-28 bg-[rgba(19,21,26,0.6)]" data-name="footer" data-file="components/footer.js">
        <div className="max-w-7xl mx-auto px-6 py-12 grid grid-cols-1 md:grid-cols-3 gap-10">
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Logo size={28} />
              <span className="font-semibold tracking-tight">TokenOpt</span>
            </div>
            <p className="text-sm text-[var(--muted)] leading-relaxed max-w-xs">
              Adaptive Multimodal Token Optimizer: a pre-tokenization layer that decides how many tokens each region of an image or video deserves.
            </p>
          </div>
          <div className="space-y-3">
            <div className="label">Team</div>
            <ul className="space-y-1.5 text-sm">
              {team.map((n) => <li key={n}>{n}</li>)}
            </ul>
          </div>
          <div className="space-y-3">
            <div className="label">Under the hood</div>
            <ul className="space-y-1.5 text-sm text-[var(--muted)]">
              <li>Hand-written quadtree, max-heap, hash table, union-find, trie</li>
              <li>Python · NumPy · OpenCV engine</li>
              <li>React · Tailwind interface</li>
            </ul>
          </div>
        </div>
      </footer>
    );
  } catch (error) {
    console.error("Footer component error:", error);
    return null;
  }
}
