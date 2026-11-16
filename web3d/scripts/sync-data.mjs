// Snapshots real engine output (results/, data/synthetic/, web/media/) into
// public/data/ so the site renders without the Python server. Read-only on the
// engine side: nothing outside web3d/ is written.
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const out = path.resolve(here, '..', 'public', 'data');

const exists = (p) => fs.access(p).then(() => true, () => false);
// Python writes inf as `Infinity`, which JSON.parse rejects.
const readJSON = async (p) =>
  JSON.parse((await fs.readFile(p, 'utf8')).replace(/-?\bInfinity\b/g, 'null').replace(/\bNaN\b/g, 'null'));
const tryJSON = async (p) => ((await exists(p)) ? readJSON(p) : null);
async function copyFirst(candidates, dest) {
  for (const src of candidates) {
    if (await exists(src)) {
      await fs.mkdir(path.dirname(dest), { recursive: true });
      await fs.copyFile(src, dest);
      return true;
    }
  }
  return false;
}

await fs.mkdir(out, { recursive: true });
const R = path.join(root, 'results');
const data = { generated: new Date().toISOString(), results: {}, manifests: {}, assets: { samples: {} } };

for (const row of (await tryJSON(path.join(R, 'results.json'))) || []) data.results[row.name] = row;

for (const name of ['ui', 'natural', 'document', 'dense']) {
  const m = await tryJSON(path.join(R, name, 'manifest.json'));
  if (m) {
    data.manifests[name] = {
      width: m.source.width,
      height: m.source.height,
      patch: m.patch_size,
      baseline: m.baseline_tokens,
      optimized: m.optimized_tokens,
      reduction_pct: m.reduction_pct,
      ms: m.timing_ms,
      schema: m.schema,
      regions: m.frames[0].regions.map((r) => [r.x, r.y, r.w, r.h, r.variance]),
    };
  }
  const ok = await copyFirst(
    [path.join(root, 'data', 'synthetic', `${name}.png`), path.join(R, name, 'claude_original.png')],
    path.join(out, 'samples', `${name}.png`),
  );
  if (ok) data.assets.samples[name] = `data/samples/${name}.png`;
}

const v = await tryJSON(path.join(R, 'screen_rec', 'manifest.json'));
if (v) {
  data.video = {
    width: v.source.width,
    height: v.source.height,
    baseline: v.baseline_tokens,
    optimized: v.optimized_tokens,
    reduction_pct: v.reduction_pct,
    scenes: v.scenes,
    overlays: (v.static_overlays || []).length,
    frames: v.frames.map((f) => ({ role: f.role, tokens: f.tokens, scene: f.scene, phash: f.phash })),
  };
}

data.race = await tryJSON(path.join(R, 'ds_race', 'race.json'));
data.complexity = await tryJSON(path.join(R, 'complexity', 'complexity.json'));
data.agent = await tryJSON(path.join(R, 'agent', 'agent.json'));

if (await copyFirst([path.join(R, 'agent', 'agent_filmstrip.png')], path.join(out, 'agent_filmstrip.png')))
  data.assets.filmstrip = 'data/agent_filmstrip.png';
if (await copyFirst([path.join(root, 'web', 'media', 'explainer.mp4')], path.join(out, 'explainer.mp4')))
  data.assets.explainer = 'data/explainer.mp4';
if (await copyFirst([path.join(root, 'web', 'media', 'poster.jpg')], path.join(out, 'poster.jpg')))
  data.assets.poster = 'data/poster.jpg';

await fs.writeFile(path.join(out, 'site-data.json'), JSON.stringify(data));
const kb = ((await fs.stat(path.join(out, 'site-data.json'))).size / 1024).toFixed(0);
console.log(`sync-data: site-data.json ${kb} kB · samples: ${Object.keys(data.assets.samples).join(', ') || 'none'}`);
