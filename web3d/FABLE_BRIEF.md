# Brief: cinematic site for the Adaptive Multimodal Token Optimizer

Review is on 2026-11-17. Build an ORIGINAL site in the *style* of lusion.co: playful,
tactile real-time 3D that reacts to the cursor (soft physics, objects that push and settle),
big confident type, clean light/dark contrast, smooth scroll-driven scenes. Do NOT copy
Lusion's layout, copy, code, models, textures or branding; take the feel, invent the
content around our project (image -> quadtree cells -> tokens). Another session is
editing the Python engine at the same time, so:

**Only create or edit files inside `web3d/`.** Do not touch `tokenopt/`, `main.py`, `tests/`,
`results/` or `web/`. Read them freely.

## Stack
Vite + Three.js + GSAP (ScrollTrigger) + Lenis. Pin exact versions. Dev server proxies
`/api` and `/results` to the existing Python server:

    .venv/bin/python web/server.py      # http://localhost:8420

## Data available (real engine output, never invent numbers)
- `GET /api/samples`, `GET /api/results` -> benchmark per sample (document, ui, natural, dense, screen_rec)
- `POST /api/image`, `POST /api/video`, `POST /api/upload` -> live optimisation (see `web/server.py`, `web/app.js` for request/response shapes)
- `GET /results/<path>` -> static files, including:
  - `results/results.json`, `results/*/manifest.json` (quadtree regions per sample)
  - `results/ds_race/race.json` -- linear vs BK-tree vs multi-index hashing (MIH 224x faster at n=50k)
  - `results/complexity/complexity.json` -- measured vs theoretical complexity per structure
  - `results/agent/agent.json` -- 20-turn computer-use agent: 93.8% fewer screenshot tokens, 91.9% fewer context tokens

## Priority order (build the highest-value pieces first)
1. **Hero (GLSL + physics):** a sample image built from its *real* quadtree cells (from its
   manifest) as soft 3D tiles; the cursor pushes them apart and they settle back, big cells
   heavy and calm, small detailed cells light and jittery; live token counter
   (baseline -> optimised).
2. **Glass-layers camera move** (one, scroll-driven): image -> quadtree -> heap budget -> manifest
   as stacked translucent planes the camera flies through.
3. One section per data structure (quadtree, summed-area table, max-heap, pHash + multi-index
   hash table, BK-tree, union-find, bit-trie), each with its real number from the JSON above.
4. Agent section: filmstrip + cumulative-context chart from `agent.json`.
5. Playground: restyle the existing upload/analyse flow from `web/app.js` against the same API.
6. Liquid transitions between samples; reduced-motion fallback; works at phone width.

Claude token counts in the data are estimates (`w*h/750`); label them as estimates.
