// Quadtree glyph: one square split recursively toward a corner.
function Logo({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="1" y="1" width="30" height="30" rx="7" fill="#13151a" stroke="#282c34" />
      <path d="M16 4v24M4 16h24" stroke="#67e8f9" strokeWidth="1.4" />
      <path d="M22 16v12M16 22h12" stroke="#67e8f9" strokeWidth="1.2" />
      <rect x="22.6" y="22.6" width="4.8" height="4.8" rx="1" fill="#d4ff3f" />
      <rect x="16.6" y="22.6" width="4.8" height="4.8" rx="1" fill="#ff6b35" />
    </svg>
  );
}

const NAV = [
  { href: "#/", label: "Overview", route: "home" },
  { href: "#/explainer", label: "Explainer", route: "explainer", icon: "icon-circle-play" },
  { href: "#structures", label: "Pipeline", route: "home" },
  { href: "#playground", label: "Playground", route: "home" },
  { href: "#results", label: "Results", route: "home" },
];

function Header({ route }) {
  try {
    return (
      <header className="sticky top-0 z-50 border-b border-[var(--border)] bg-[rgba(10,11,13,0.8)] backdrop-blur-md" data-name="header" data-file="components/header.js">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <a href="#/" className="flex items-center gap-3">
            <Logo />
            <span className="text-lg font-semibold tracking-tight">TokenOpt</span>
            <span className="hidden sm:inline font-mono text-[10px] text-[var(--muted)] border border-[var(--border)] rounded px-1.5 py-0.5">v0.1</span>
          </a>
          <nav className="hidden md:flex items-center gap-1">
            {NAV.map((n) => {
              const active = n.route === "explainer" ? route === "explainer" : n.href === "#/" && route === "home";
              return (
                <a key={n.label} href={n.href}
                   className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors",
                     active ? "text-[var(--text)] bg-[var(--panel-2)]" : "text-[var(--muted)] hover:text-[var(--text)]",
                     n.route === "explainer" && "text-[var(--lime)] hover:text-[var(--lime)]")}>
                  {n.icon && <span className={n.icon}></span>}{n.label}
                </a>
              );
            })}
          </nav>
          <a href="#/explainer" className="btn btn-primary text-sm py-1.5">
            <span className="icon-play"></span>Watch how it works
          </a>
        </div>
      </header>
    );
  } catch (error) {
    console.error("Header component error:", error);
    return null;
  }
}
