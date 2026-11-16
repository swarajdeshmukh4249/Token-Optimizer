# TokenOpt site (web3d)

Scroll-driven site for the Adaptive Multimodal Token Optimizer.

## Run

    .venv/bin/python web/server.py        # from the repo root: live engine API on :8420
    cd web3d && npm install && npm run dev # site on http://localhost:5173

`npm run dev` and `npm run build` first run `npm run sync`, which snapshots the engine's
output (`results/`, `data/synthetic/`, `web/media/`) into `public/data/`. Everything except
the Playground works from that snapshot; the Playground calls `/api/*` on the Python server.
Re-run `npm run sync` after regenerating results.

## Layout

| File | What it does |
| --- | --- |
| `scripts/sync-data.mjs` | Builds `public/data/site-data.json` and copies example images, the agent filmstrip and the explainer video |
| `src/main.js` | Loader, data binding, smooth scroll (Lenis), reveals, header / menu / video modal |
| `src/hero3d.js` | Hero: glossy quadtree tiles with hand-rolled sphere physics and a cursor collider (Three.js) |
| `src/reel.js` | Card that grows into the full-width panel; real quadtree cells light up under the cursor |
| `src/cards.js` | One card per data structure, stats read from `complexity.json`, `race.json` and the manifests |
| `src/tunnel.js` | Pinned camera flight through image, patches, quadtree, heap and manifest planes |
| `src/agent.js` | 20-turn filmstrip and cumulative-context chart from `agent.json` |
| `src/playground.js` | Example / upload controls against the live engine |

## Notes

- Fonts: Figtree and IBM Plex Mono (both open licence, bundled via `@fontsource`).
- Every number on the page is read from engine output; none is typed in. Claude token
  counts are estimates (w x h / 750) and are labelled as such.
- `prefers-reduced-motion` disables smooth scroll, scrubbed transforms and the render loops.
