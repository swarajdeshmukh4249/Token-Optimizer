# Adaptive Multimodal Token Optimizer

DS-II (CS2308) course project, Group 6, Div K / D3. A pre-tokenization layer that decides
**how many tokens each region of an image or video deserves** before it reaches a
multimodal LLM. It's built entirely from hand-implemented data structures.

## Run it

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python main.py demo              # synthetic test set + full evaluation -> results/REPORT.md
.venv/bin/python main.py image photo.png   # one image
.venv/bin/python main.py video clip.mp4    # one video (sampled at --fps, default 2)
.venv/bin/python -m pytest -q              # 19 tests
```

Put real screenshots, photos or clips in `data/real/` and `demo` evaluates them as well.

### Web UI

```bash
.venv/bin/python web/server.py            # http://localhost:8420  (pass a port to change it)
```

It's a dark React + Tailwind site with two pages: **Overview** (hero, pipeline, the five data structures, a live
**playground** that runs the real engine, and benchmark results) and **Explainer** (`#/explainer`), a narrated 5½-minute
video with clickable chapters and a live, clickable transcript. Use it to present the project.

The explainer video is generated from the engine itself (every visual is real output) and narrated with the macOS
`say` voice:

```bash
.venv/bin/python web/explainer/make_video.py   # ~5 min; writes web/media/explainer.mp4 + chapters.json
```

In the playground you choose a sample or drop your own image or video, then tune the patch size, variance threshold
and max-heap token budget. You see the quadtree overlay, an equal-cost compare slider against uniform, the
rate-distortion curve, and the Claude adapter estimate. For video you get a per-frame key/delta/duplicate timeline and
the scene key frames. `?sample=screen_rec` (or `document`, `ui`, `natural`, `dense`) opens a sample directly.
The server uses only the standard library, keeps uploads in memory, and listens on 127.0.0.1 only.

## Where each data structure lives

| Synopsis component | Implementation | Role |
|---|---|---|
| Variance-based adaptive quadtree | `tokenopt/ds/quadtree.py` | Splits the patch grid only where content varies. One leaf = one token |
| Summed-area table | `tokenopt/ds/summed_area.py` | O(1) mean/variance of any rectangle, so the tree costs O(nodes) |
| Max-heap budget allocation | `tokenopt/ds/max_heap.py` + `build_budgeted` | Best-first refinement: a hard token budget goes to the region with the largest error |
| Perceptual hash + hash table (chaining) | `tokenopt/phash.py`, `tokenopt/ds/hash_table.py` | DCT pHash. Multi-index hashing guarantees every near-duplicate within distance *d* is found |
| Union-Find scene segmentation | `tokenopt/ds/union_find.py` | Groups frames into scenes. Also merges detail patches into crops for the adapter |
| Trie for recurring overlays | `tokenopt/ds/trie.py` | Counts (block position ‖ block hash) keys across frames. Logos and toolbars are sent once |
| Optimized Token Manifest | `tokenopt/manifest.py` | Model-agnostic JSON (`otm/0.1`) |
| Model adapter | `tokenopt/adapters/claude.py` | Manifest → Claude Messages API image blocks (overview + detail crops) |

```
input ─► decode ─► quadtree (SAT + heap) ─► manifest ─► adapter ─► model
 video:  pHash ─► multi-index hash (dups) ─► union-find (scenes) ─► trie (overlays)
         ─► per frame: key (full tree) | delta (changed leaves only) | duplicate (0 tokens)
```

## Current results (synthetic set, patch 16px)

| input | baseline → optimized tokens | reduction | PSNR of what the model sees |
|---|---|---:|---:|
| document | 5312 → 2722 | 48.8% | 70.6 dB |
| UI screenshot | 4000 → 905 | 77.4% | 42.8 dB |
| natural scene | 3072 → 458 | 85.1% | 42.3 dB |
| dense texture | 2304 → 2304 | 0% (expected) | lossless |
| screen recording, 24 frames | 54720 → 1107 | 98.0% | 48.1 dB mean |

At equal token cost, adaptive allocation beats uniform downscaling by 5 to 30+ dB on
structured content (`results/rd_curves.png`). On pure texture it ties, which is expected.
See `results/REPORT.md` for SSIM, timings, the Claude adapter estimates and the
limitations.

## Toward the paper: open items

1. **Answer-quality evaluation**: a fixed question set (OCR, counting, UI element lookup)
   answered by a real vision model on original vs optimized inputs, plus exact token
   counts via `count_tokens_with_claude()`.
2. **A better split criterion**: variance treats smooth gradients and noise as "detail".
   Measure the energy actually lost by resampling a region to one patch instead.
3. **Real datasets**: DocVQA/ChartQA-style documents, RICO-style UI screenshots, real
   screen recordings and camera footage.
4. **Break-even analysis**: preprocessing time vs tokens saved across repeated calls and
   agent turns, and when the approach does *not* pay off (a single small image sent once).
5. **Cross-call cache**: persist the signature store so repeated attachments cost zero.
