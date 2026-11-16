// "The Structures": one card per hand-written data structure. Every stat is read
// from the engine's JSON output; the canvases are illustrations of the idea.
import gsap from 'gsap';
import { fmt, reduced, rng, splitRoll } from './util.js';

const W = 1292, H = 840;
const INK = '#0a0b0f', BLUE = '#1a2ffb', LAV = '#dfe3f5', CREAM = '#f3f0e9', SLATE = '#2b2e3a';
const mono = (px) => `500 ${px}px "IBM Plex Mono", monospace`;

const art = {
  quadtree(c, { manifest }) {
    c.fillStyle = INK; c.fillRect(0, 0, W, H);
    const s = Math.max(W / manifest.width, H / manifest.height);
    c.setTransform(s, 0, 0, s, (W - manifest.width * s) / 2, (H - manifest.height * s) / 2);
    c.lineWidth = 1 / s;
    for (const [x, y, w, h] of manifest.regions) {
      if (w <= manifest.patch && h <= manifest.patch) { c.fillStyle = BLUE; c.fillRect(x + 1, y + 1, w - 2, h - 2); }
      else { c.strokeStyle = 'rgba(255,255,255,0.34)'; c.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1); }
    }
  },
  sat(c) {
    c.fillStyle = LAV; c.fillRect(0, 0, W, H);
    const r = rng(7), cell = 46, cols = Math.ceil(W / cell), rows = Math.ceil(H / cell);
    for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
      c.fillStyle = `rgba(10,11,15,${0.03 + r() * 0.1})`;
      c.fillRect(i * cell + 2, j * cell + 2, cell - 4, cell - 4);
    }
    const x0 = cell * 9, y0 = cell * 4, x1 = cell * 21, y1 = cell * 13;
    c.fillStyle = 'rgba(26,47,251,0.9)'; c.fillRect(x0, y0, x1 - x0, y1 - y0);
    c.fillStyle = 'rgba(26,47,251,0.16)'; c.fillRect(0, 0, x1, y0); c.fillRect(0, y0, x0, y1 - y0);
    c.font = mono(26); c.textBaseline = 'middle';
    [[x0, y0, 'A'], [x1, y0, 'B'], [x0, y1, 'C'], [x1, y1, 'D']].forEach(([x, y, l]) => {
      c.fillStyle = '#fff'; c.beginPath(); c.arc(x, y, 17, 0, 7); c.fill();
      c.fillStyle = INK; c.textAlign = 'center'; c.fillText(l, x, y + 1);
    });
    c.fillStyle = '#fff'; c.textAlign = 'left'; c.font = mono(30); c.fillText('D − B − C + A', x0 + 34, y0 + 52);
  },
  heap(c) {
    c.fillStyle = BLUE; c.fillRect(0, 0, W, H);
    const levels = 5, pos = [];
    for (let l = 0; l < levels; l++) for (let i = 0; i < 2 ** l; i++) pos.push([W * ((i + 0.5) / 2 ** l), 110 + l * 150, 54 - l * 9.5]);
    c.strokeStyle = 'rgba(255,255,255,0.55)'; c.lineWidth = 3;
    pos.forEach(([x, y], i) => { if (i) { const [px, py] = pos[(i - 1) >> 1]; c.beginPath(); c.moveTo(px, py); c.lineTo(x, y); c.stroke(); } });
    pos.forEach(([x, y, rad], i) => {
      c.fillStyle = i === 0 ? '#fff' : i < 3 ? 'rgba(255,255,255,0.92)' : i < 7 ? 'rgba(255,255,255,0.75)' : 'rgba(255,255,255,0.5)';
      c.beginPath(); c.arc(x, y, rad, 0, 7); c.fill();
    });
    c.fillStyle = BLUE; c.font = mono(24); c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('max σ²', pos[0][0], pos[0][1] + 1);
  },
  hash(c, { video }) {
    c.fillStyle = INK; c.fillRect(0, 0, W, H);
    // A real 64-bit pHash from the screen recording, cut into 4 bands of 16 bits (multi-index hashing).
    const hex = (video?.frames?.[0]?.phash || 'afd4aad4a8d4aad0').padEnd(16, '0');
    const bits = [...hex].flatMap((h) => parseInt(h, 16).toString(2).padStart(4, '0').split('').map(Number));
    const size = 34, gap = 8, x0 = 90, r = rng(11);
    for (let band = 0; band < 4; band++) {
      const y = 120 + band * 168;
      for (let i = 0; i < 16; i++) {
        c.fillStyle = bits[band * 16 + i] ? '#fff' : 'rgba(255,255,255,0.13)';
        c.fillRect(x0 + i * (size + gap), y, size, size);
      }
      const bx = x0 + 16 * (size + gap) + 70;
      c.strokeStyle = 'rgba(255,255,255,0.35)'; c.lineWidth = 2;
      c.beginPath(); c.moveTo(bx - 56, y + size / 2); c.lineTo(bx - 12, y + size / 2); c.stroke();
      const n = 2 + Math.floor(r() * 5);
      for (let k = 0; k < n; k++) { c.fillStyle = k === 0 ? BLUE : 'rgba(91,134,255,0.45)'; c.beginPath(); c.roundRect(bx + k * 62, y - 6, 50, size + 12, 10); c.fill(); }
      c.fillStyle = 'rgba(255,255,255,0.5)'; c.font = mono(20); c.textAlign = 'left'; c.textBaseline = 'alphabetic';
      c.fillText(`band ${band + 1} · 0x${hex.slice(band * 4, band * 4 + 4)}`, x0, y - 16);
    }
  },
  bktree(c) {
    c.fillStyle = CREAM; c.fillRect(0, 0, W, H);
    const r = rng(23), nodes = [{ x: W / 2, y: 130, d: null, p: -1 }];
    const grow = (pi, depth, spread) => {
      if (depth > 3) return;
      const k = depth === 1 ? 4 : 1 + Math.floor(r() * 3), p = nodes[pi];
      for (let i = 0; i < k; i++) {
        const x = p.x + (i - (k - 1) / 2) * spread, y = p.y + 170 + (r() - 0.5) * 30;
        nodes.push({ x, y, d: 1 + Math.floor(r() * 9) + i, p: pi });
        grow(nodes.length - 1, depth + 1, spread / (k + 0.4));
      }
    };
    grow(0, 1, 300);
    c.lineWidth = 2.5; c.font = mono(20); c.textAlign = 'center'; c.textBaseline = 'middle';
    nodes.forEach((n, i) => {
      if (n.p < 0) return;
      const p = nodes[n.p], hot = i % 5 === 1;
      c.strokeStyle = hot ? BLUE : 'rgba(10,11,15,0.28)';
      c.beginPath(); c.moveTo(p.x, p.y); c.lineTo(n.x, n.y); c.stroke();
      c.fillStyle = hot ? BLUE : 'rgba(10,11,15,0.5)';
      c.fillText(String(n.d), (p.x + n.x) / 2 + 16, (p.y + n.y) / 2);
    });
    nodes.forEach((n, i) => { c.fillStyle = i === 0 ? BLUE : INK; c.beginPath(); c.arc(n.x, n.y, i === 0 ? 24 : 12, 0, 7); c.fill(); });
  },
  unionfind(c, { video }) {
    c.fillStyle = SLATE; c.fillRect(0, 0, W, H);
    const scenes = video?.scenes || [[0, 1, 2, 3, 4, 5, 6, 7], [8, 9, 10, 11, 12, 13], [14, 15, 16, 17, 18, 19, 20, 21, 22, 23]];
    const frames = video?.frames || [];
    const cx = scenes.map((_, i) => W * ((i + 0.5) / scenes.length));
    scenes.forEach((group, s) => {
      const R = 60 + group.length * 11, x0 = cx[s], y0 = H / 2 - 30;
      c.strokeStyle = 'rgba(255,255,255,0.14)'; c.lineWidth = 2; c.beginPath(); c.arc(x0, y0, R + 46, 0, 7); c.stroke();
      group.forEach((f, k) => {
        if (k === 0) return;
        const a = (k / (group.length - 1)) * Math.PI * 2 - Math.PI / 2, x = x0 + Math.cos(a) * R, y = y0 + Math.sin(a) * R;
        c.strokeStyle = 'rgba(255,255,255,0.4)'; c.beginPath(); c.moveTo(x0, y0); c.lineTo(x, y); c.stroke();
        c.fillStyle = frames[f]?.role === 'duplicate' ? 'rgba(255,255,255,0.3)' : '#fff';
        c.beginPath(); c.arc(x, y, 13, 0, 7); c.fill();
      });
      c.fillStyle = '#5b86ff'; c.beginPath(); c.arc(x0, y0, 30, 0, 7); c.fill();
      c.fillStyle = 'rgba(255,255,255,0.6)'; c.font = mono(20); c.textAlign = 'center';
      c.fillText(`scene ${s + 1} · ${group.length} frames`, x0, y0 + R + 96);
    });
  },
  trie(c) {
    c.fillStyle = LAV; c.fillRect(0, 0, W, H);
    const r = rng(41), depth = 7, keys = Array.from({ length: 9 }, () => Array.from({ length: depth }, () => (r() < 0.5 ? 0 : 1)));
    const seen = new Set();
    const at = (key, d) => { let x = W / 2, span = W * 0.23; for (let i = 0; i < d; i++) { x += (key[i] ? 1 : -1) * span; span *= 0.56; } return [x, 80 + d * 100]; };
    c.lineCap = 'round'; c.font = mono(18); c.textAlign = 'center'; c.textBaseline = 'middle';
    keys.forEach((key, ki) => {
      for (let d = 0; d < depth; d++) {
        const id = key.slice(0, d + 1).join('');
        const [x0, y0] = at(key, d), [x1, y1] = at(key, d + 1), hot = ki === 0;
        if (!seen.has(id) || hot) {
          c.strokeStyle = hot ? BLUE : 'rgba(10,11,15,0.3)'; c.lineWidth = hot ? 7 : 2.5;
          c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke();
          if (!seen.has(id)) { c.fillStyle = hot ? BLUE : 'rgba(10,11,15,0.45)'; c.fillText(String(key[d]), (x0 + x1) / 2 + (key[d] ? 16 : -16), (y0 + y1) / 2 - 6); }
          seen.add(id);
        }
        c.fillStyle = hot ? BLUE : INK; c.beginPath(); c.arc(x1, y1, hot ? 11 : 7, 0, 7); c.fill();
      }
    });
    c.fillStyle = INK; c.beginPath(); c.arc(W / 2, 80, 16, 0, 7); c.fill();
  },
  video(c, { video }) {
    c.fillStyle = BLUE; c.fillRect(0, 0, W, H);
    const frames = video?.frames || [], n = frames.length || 24, max = Math.max(...frames.map((f) => f.tokens), 1);
    const bw = (W - 180) / n;
    frames.forEach((f, i) => {
      const h = f.role === 'duplicate' ? 6 : Math.max(10, (f.tokens / max) * 470), x = 90 + i * bw;
      c.fillStyle = f.role === 'key' ? '#fff' : f.role === 'delta' ? 'rgba(255,255,255,0.6)' : 'rgba(255,255,255,0.28)';
      c.beginPath(); c.roundRect(x + 5, 640 - h, bw - 10, h, 8); c.fill();
    });
    c.fillStyle = 'rgba(255,255,255,0.7)'; c.font = mono(20); c.textAlign = 'left';
    c.fillText('tokens sent per frame · key / delta / duplicate', 90, 700);
  },
};

export function initCards({ data }) {
  const root = document.querySelector('#cards');
  const cx = data.complexity || {}, fits = cx.fits || {}, race = data.race, video = data.video, ui = data.manifests.ui;
  const last = (a) => (a && a.length ? a[a.length - 1] : null);
  const big = race ? last(race.scaling) : null;
  const sat = last(cx.sat), heap = last(cx.heap), uf = last(cx.union_find), ht = last(cx.hash_table), trie = last(cx.trie);
  const r2 = (k) => (fits[k]?.r2 ? ` • R² ${fits[k].r2.toFixed(4)}` : '');
  const us = '<span class="u">µs</span>';
  const model = (k, fb) => (fits[k]?.model || fb).replace('alpha', 'α').toUpperCase();

  const cards = [
    { art: 'quadtree', shade: true, title: 'Quadtree', tags: `Spatial • ${model('quadtree', 'O(nodes)')}${r2('quadtree')}`,
      stat: `${fmt(ui.regions.length)} regions`, sub: `from ${fmt(ui.baseline)} uniform patches · ui screenshot`,
      desc: 'Splits the image only where pixel variance is high. Flat areas collapse into one large cell and one token.' },
    { art: 'sat', ink: true, title: 'Summed-Area Table', tags: `Variance in ${model('sat_query', 'O(1)')}${sat ? ` • ${sat.sat_us.toFixed(1)} ${us} flat` : ''}`,
      stat: sat ? `${fmt(sat.naive_us / sat.sat_us)}× faster` : '–', sub: sat ? `than summing pixels · ${fmt(sat.area)} px region` : '',
      desc: 'Two prefix-sum tables answer the variance of any rectangle with four lookups, so the quadtree never rescans pixels.' },
    { art: 'heap', title: 'Max-Heap', tags: `Budget • ${model('heap', 'O(log n)')}`,
      stat: heap ? `${heap.us_per_op.toFixed(2)} µs` : '–', sub: heap ? `per push / pop at n = ${fmt(heap.n)}` : '',
      desc: 'With a fixed token budget, the heap always splits the highest-variance cell next, so detail is bought in order of value.' },
    { art: 'hash', shade: true, title: 'pHash + Multi-Index Hash', tags: `Temporal • ${model('hash_table', 'O(1) average')}${big ? ` • ${big.mih.query_us.toFixed(1)} ${us} query` : ''}`,
      stat: big ? `${fmt(big.linear.query_us / big.mih.query_us)}× faster` : '–', sub: big ? `than a linear scan at n = ${fmt(big.n)} · radius ${race.radius}` : '',
      desc: 'Each frame gets a 64-bit perceptual hash. Four 16-bit bands index it, so near-duplicate frames are found without scanning.' },
    { art: 'bktree', ink: true, title: 'BK-Tree', tags: 'Metric tree • Hamming distance',
      stat: big ? `${(big.linear.comparisons / big.bktree.comparisons).toFixed(1)}× fewer` : '–', sub: big ? `comparisons than linear at n = ${fmt(big.n)}` : '',
      desc: 'The same search as a metric tree. The triangle inequality prunes whole branches; it loses to multi-index hashing as the radius grows.' },
    { art: 'unionfind', title: 'Union-Find', tags: `Scenes • ${model('union_find', 'O(α(n))')}${uf ? ` • ${uf.us_per_op.toFixed(2)} ${us}/op` : ''}`,
      stat: video ? `${video.scenes.length} scenes` : '–', sub: video ? `from ${video.frames.length} frames · screen recording` : '',
      desc: 'Frames whose hashes are close are unioned into scenes. Each scene sends one key frame; the rest become deltas or duplicates.' },
    { art: 'trie', ink: true, title: 'Bit-Trie', tags: `Overlays • ${model('trie', 'O(key bits)')}${trie ? ` • ${trie.us_per_op.toFixed(0)} ${us}/op` : ''}`,
      stat: video ? `${fmt(video.overlays)} blocks` : '–', sub: 'static overlay blocks recognised · screen recording',
      desc: 'Menu bars and toolbars repeat on every frame. Their block hashes live in a binary trie and are sent once, then referenced.' },
    { art: 'video', title: 'All Seven, Together', tags: 'Screen recording • end to end', tile: true,
      stat: video ? `−${video.reduction_pct.toFixed(1)}%` : '–', sub: video ? `${fmt(video.baseline)} → ${fmt(video.optimized)} tokens` : '',
      desc: 'Spatial, temporal and overlay redundancy removed in one pass over a screen recording.' },
  ];

  const ctxData = { manifest: ui, video };
  cards.forEach((card) => {
    const el = document.createElement('article');
    el.className = `card${card.tile ? ' tile' : ''}${card.ink ? ' ink' : ''}${card.shade ? ' shade' : ''}`;
    el.innerHTML = `
      <div class="card-media"><canvas width="${W}" height="${H}"></canvas>
        <div class="card-stat">${card.stat}<small>${card.sub}</small></div></div>
      <div class="card-tags">${card.tags}</div>
      <h3 class="card-title"><span class="roll">${card.title}</span></h3>
      <p class="card-desc">${card.desc}</p>`;
    root.appendChild(el);
    splitRoll(el.querySelector('.roll'));
    const c = el.querySelector('canvas').getContext('2d');
    art[card.art](c, ctxData);
    if (!reduced) {
      const media = el.querySelector('.card-media');
      gsap.from(media, { clipPath: 'inset(100% 0% 0% 0% round 1.4rem)', y: 60, duration: 1.4, ease: 'expo.out', scrollTrigger: { trigger: el, start: 'top 92%', once: true }, clearProps: 'clipPath' });
      gsap.from([el.querySelector('.card-tags'), el.querySelector('.card-title'), el.querySelector('.card-desc')], { opacity: 0, y: 20, duration: 1, ease: 'expo.out', stagger: 0.07, scrollTrigger: { trigger: el, start: 'top 80%', once: true } });
    }
  });
}
