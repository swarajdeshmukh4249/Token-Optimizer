// Playground: drives the live engine through its HTTP API (/api/*).
import { fmt } from './util.js';

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  let json;
  try { json = await res.json(); } catch { throw new Error('offline'); }
  if (!res.ok) throw new Error(json.error || `Request failed (${res.status})`);
  return json;
}
const db = (x) => (x == null ? 'lossless' : `${Number(x).toFixed(1)} dB`);
const readFile = (file) => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => no(r.error); r.readAsDataURL(file); });

export function initPlayground() {
  const root = document.querySelector('#pg');
  const state = { source: null, kind: 'image', patch: 16, thr: 40, budget: 0, fps: 2, view: 'overlay', result: null, busy: false };

  root.innerHTML = `
    <div class="pg-panel">
      <div class="pg-group"><div class="pg-h">Examples</div><div class="pg-samples" id="pg-samples"></div></div>
      <div class="pg-group"><label class="pg-drop" id="pg-drop"><input type="file" accept="image/*,video/*">Drop an image or video here, or click to choose</label></div>
      <div class="pg-group"><div class="pg-h">Patch size (px)</div><div class="pg-seg" id="pg-patch">${[8, 16, 32].map((v) => `<button data-v="${v}" class="${v === 16 ? 'on' : ''}">${v}</button>`).join('')}</div></div>
      <div class="pg-group pg-range"><div class="pg-h" style="margin:0">Variance threshold</div><output id="pg-thr-o">40</output><input id="pg-thr" type="range" min="0" max="200" step="5" value="40"></div>
      <div class="pg-group pg-range" data-for="image"><div class="pg-h" style="margin:0">Token budget</div><output id="pg-bud-o">off</output><input id="pg-bud" type="range" min="0" max="100" step="5" value="0"></div>
      <div class="pg-group" data-for="video" hidden><div class="pg-h">Frames analysed / second</div><div class="pg-seg" id="pg-fps">${[1, 2, 4].map((v) => `<button data-v="${v}" class="${v === 2 ? 'on' : ''}">${v}</button>`).join('')}</div></div>
      <button class="pill pill-dark pg-run" id="pg-run"><span>Run the optimizer</span><span class="dot"></span></button>
    </div>
    <div class="pg-panel pg-out">
      <div class="pg-tabs" id="pg-tabs"></div>
      <div class="pg-view" id="pg-view"><div class="pg-msg">Checking for the engine…</div></div>
      <div class="pg-stats" id="pg-stats"></div>
    </div>`;

  const $ = (s) => root.querySelector(s);
  const view = $('#pg-view'), stats = $('#pg-stats'), tabs = $('#pg-tabs'), run = $('#pg-run');
  const msg = (html) => { view.innerHTML = `<div class="pg-msg">${html}</div>`; };
  const offline = () => msg('The engine is offline right now.<br>Once it is back, press Run.');

  function setKind(kind) {
    state.kind = kind;
    root.querySelectorAll('[data-for]').forEach((el) => { el.hidden = el.dataset.for !== kind; });
  }

  function renderImage(r) {
    const views = [['original', 'Original'], ['overlay', 'Quadtree'], ['adaptive', 'What the model sees'], ['uniform', 'Uniform at same cost']];
    tabs.innerHTML = views.map(([k, l]) => `<button data-v="${k}" class="${k === state.view ? 'on' : ''}">${l}</button>`).join('');
    view.innerHTML = `<img alt="${state.view} view" src="${r.images[state.view]}">`;
    const cells = [
      ['Uniform tokens', fmt(r.baseline)], ['Optimised tokens', fmt(r.tokens), 'hi'], ['Reduction', `−${r.reduction.toFixed(1)}%`, 'hi'], ['Engine time', `${r.ms} ms`],
      ['Fidelity (PSNR)', db(r.psnr)], ['Uniform at same cost', db(r.uniform_psnr)], ['SSIM', r.ssim.toFixed(3)],
      ['Claude tokens (estimate)', `${fmt(r.claude.full)} → ${fmt(r.claude.optimized)}`],
    ];
    stats.innerHTML = cells.map(([k, v, c]) => `<div class="pg-stat ${c || ''}"><b>${v}</b><span>${k}</span></div>`).join('');
  }

  function renderVideo(r) {
    tabs.innerHTML = `<div class="pg-roles" style="flex:1" title="one bar per frame">${r.frames.map((f) => `<i class="${f.role}" title="frame ${f.i}: ${f.role}, ${f.tokens} tokens"></i>`).join('')}</div>`;
    view.innerHTML = `<div class="pg-frames">${r.keyframes.map((k) => `<figure><img alt="key frame of scene ${k.scene + 1}" src="${k.seen}"><figcaption>scene ${k.scene + 1} · ${k.frames_in_scene} frames · ${fmt(k.tokens)} tokens</figcaption></figure>`).join('')}</div>`;
    const cells = [
      ['Uniform tokens', fmt(r.baseline)], ['Optimised tokens', fmt(r.tokens), 'hi'], ['Reduction', `−${r.reduction.toFixed(1)}%`, 'hi'], ['Engine time', `${r.ms} ms`],
      ['Scenes', r.scenes], ['Key / delta / duplicate', `${r.roles.key} / ${r.roles.delta} / ${r.roles.duplicate}`], ['Mean PSNR', db(r.mean_psnr)], ['Static overlays', fmt(r.overlays)],
    ];
    stats.innerHTML = cells.map(([k, v, c]) => `<div class="pg-stat ${c || ''}"><b>${v}</b><span>${k}</span></div>`).join('');
  }

  async function go() {
    if (!state.source || state.busy) return;
    state.busy = true; run.disabled = true; run.firstElementChild.textContent = 'Running…';
    try {
      const base = { ...state.source, patch: state.patch, var_threshold: state.thr };
      if (state.kind === 'video') { state.result = await api('/api/video', { ...base, fps: state.fps }); renderVideo(state.result); }
      else { state.result = await api('/api/image', { ...base, budget_ratio: state.budget ? state.budget / 100 : null, curve: false }); renderImage(state.result); }
    } catch (e) {
      if (e.message === 'offline') offline(); else msg(e.message);
    } finally {
      state.busy = false; run.disabled = false; run.firstElementChild.textContent = 'Run the optimizer';
    }
  }

  function pick(source, kind) {
    state.source = source; setKind(kind);
    root.querySelectorAll('.pg-sample').forEach((b) => b.classList.toggle('on', b.dataset.name === source.sample));
    go();
  }

  async function loadSamples() {
    try {
      const samples = await api('/api/samples');
      $('#pg-samples').innerHTML = samples.map((s) => `<button class="pg-sample" data-name="${s.name}" data-kind="${s.kind}" title="${s.label}">${s.thumb ? `<img alt="" src="${s.thumb}">` : ''}<span>${s.kind === 'video' ? 'video' : s.name}</span></button>`).join('');
      msg('Try an example, or drop in your own file.');
      return true;
    } catch {
      $('#pg-samples').innerHTML = '';
      offline();
      return false;
    }
  }

  root.addEventListener('click', async (e) => {
    const sample = e.target.closest('.pg-sample');
    if (sample) return pick({ sample: sample.dataset.name }, sample.dataset.kind);
    const seg = e.target.closest('.pg-seg button');
    if (seg) {
      seg.parentElement.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b === seg));
      if (seg.parentElement.id === 'pg-patch') state.patch = Number(seg.dataset.v); else state.fps = Number(seg.dataset.v);
      return go();
    }
    const tab = e.target.closest('.pg-tabs button');
    if (tab && state.result?.images) { state.view = tab.dataset.v; return renderImage(state.result); }
    if (e.target.closest('#pg-run')) {
      if (!$('#pg-samples').children.length && !(await loadSamples())) return;
      if (!state.source) return pick({ sample: 'ui' }, 'image');
      go();
    }
  });
  $('#pg-thr').addEventListener('input', (e) => { state.thr = Number(e.target.value); $('#pg-thr-o').textContent = e.target.value; });
  $('#pg-thr').addEventListener('change', go);
  $('#pg-bud').addEventListener('input', (e) => { state.budget = Number(e.target.value); $('#pg-bud-o').textContent = state.budget ? `${state.budget}% of uniform` : 'off'; });
  $('#pg-bud').addEventListener('change', go);

  async function upload(file) {
    if (!file) return;
    msg(`Uploading ${file.name}…`);
    try {
      const up = await api('/api/upload', { name: file.name, type: file.type, data: await readFile(file) });
      pick({ id: up.id }, up.kind);
    } catch (e) { if (e.message === 'offline') offline(); else msg(e.message); }
  }
  const drop = $('#pg-drop');
  drop.querySelector('input').addEventListener('change', (e) => upload(e.target.files[0]));
  ['dragenter', 'dragover'].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', (e) => upload(e.dataTransfer.files[0]));

  loadSamples();
}
