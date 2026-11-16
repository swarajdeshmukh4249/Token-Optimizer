// Pipeline: the camera flies through the stages as stacked glass planes.
// image -> uniform patches -> quadtree -> max-heap budget -> manifest. All real data.
import * as THREE from 'three';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { clamp, fmt, lerp, reduced, rng, smooth } from './util.js';

const TW = 1600, TH = 1000, GAP = 9, PW = 16, PH = 10;

function layer(draw) {
  const cv = document.createElement('canvas');
  cv.width = TW; cv.height = TH;
  draw(cv.getContext('2d'));
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

export function initTunnel({ data, image, mobile }) {
  const section = document.querySelector('#pipeline');
  const canvas = document.querySelector('#pipe-canvas');
  const title = document.querySelector('#pipe-title');
  const stageEl = document.querySelector('#pipe-stage');
  const countEl = document.querySelector('#pipe-count');
  const countNum = countEl.querySelector('b');
  const halo = document.querySelector('.pipe-halo');
  const m = data.manifests.ui, s = TW / m.width, regions = m.regions;

  const ghost = (c, a) => { c.globalAlpha = a; c.drawImage(image, 0, 0, TW, TH); c.globalAlpha = 1; };
  const byVar = regions.map((r, i) => [r[4], i]).sort((a, b) => b[0] - a[0]);
  const rank = new Float32Array(regions.length);
  byVar.forEach(([, i], k) => { rank[i] = k / regions.length; });

  const stages = [
    { n: '01', t: 'Image', d: `${m.width} × ${m.height} px screenshot, as the model would normally receive it.`,
      tex: layer((c) => { c.drawImage(image, 0, 0, TW, TH); }), opacity: 1 },
    { n: '02', t: 'Uniform patches', d: `Every ${m.patch} px patch costs one token: ${fmt(m.baseline)} tokens, blank or not.`,
      tex: layer((c) => {
        ghost(c, 0.2); c.strokeStyle = 'rgba(255,255,255,0.4)'; c.lineWidth = 1; c.beginPath();
        for (let x = 0; x <= m.width; x += m.patch) { c.moveTo(x * s, 0); c.lineTo(x * s, TH); }
        for (let y = 0; y <= m.height; y += m.patch) { c.moveTo(0, y * s); c.lineTo(TW, y * s); }
        c.stroke();
      }), opacity: 0.95 },
    { n: '03', t: 'Quadtree', d: `Flat regions merge. ${fmt(regions.length)} cells remain; blue cells keep full detail.`,
      tex: layer((c) => {
        ghost(c, 0.16); c.lineWidth = 1.5;
        for (const [x, y, w, h] of regions) {
          if (w <= m.patch && h <= m.patch) { c.fillStyle = 'rgba(50,80,255,0.95)'; c.fillRect(x * s + 1, y * s + 1, w * s - 2, h * s - 2); }
          else { c.strokeStyle = 'rgba(255,255,255,0.75)'; c.strokeRect(x * s, y * s, w * s, h * s); }
        }
      }), opacity: 1 },
    { n: '04', t: 'Max-heap budget', d: 'Cells ranked by variance. The heap spends tokens on the brightest ones first.',
      tex: layer((c) => {
        ghost(c, 0.08);
        regions.forEach(([x, y, w, h], i) => {
          const a = Math.pow(1 - rank[i], 2.2);
          c.fillStyle = `rgba(255,255,255,${0.05 + 0.9 * a})`;
          c.fillRect(x * s + 1, y * s + 1, w * s - 2, h * s - 2);
        });
      }), opacity: 0.95 },
    { n: '05', t: 'Manifest', d: `${m.schema} · every region with its position and token cost, ready for the model adapter.`,
      tex: layer((c) => {
        c.fillStyle = 'rgba(10,12,24,0.82)'; c.fillRect(0, 0, TW, TH);
        c.font = '500 26px "IBM Plex Mono", monospace'; c.textBaseline = 'top';
        const head = [`"schema": "${m.schema}",`, `"patch_size": ${m.patch},`, `"baseline_tokens": ${m.baseline},`, `"optimized_tokens": ${m.optimized},`, `"reduction_pct": ${m.reduction_pct},`, '"regions": ['];
        head.forEach((l, i) => { c.fillStyle = i === 3 ? '#7f9cff' : 'rgba(255,255,255,0.92)'; c.fillText(l, 70, 60 + i * 40); });
        c.font = '400 21px "IBM Plex Mono", monospace';
        const rows = 20, cols = 2;
        for (let k = 0; k < rows * cols && k < regions.length; k++) {
          const [x, y, w, h, v] = regions[k * 9 % regions.length];
          c.fillStyle = 'rgba(255,255,255,0.55)';
          c.fillText(`{"x":${x},"y":${y},"w":${w},"h":${h},"tokens":1,"variance":${v}},`, 100 + (k % cols) * 740, 310 + Math.floor(k / cols) * 32);
        }
      }), opacity: 1 },
  ];

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, mobile ? 1.5 : 2));
  renderer.setClearColor(0x000000, 1);
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x000000, 0.018);
  const camera = new THREE.PerspectiveCamera(40, 2, 0.05, 200);

  const geo = new THREE.PlaneGeometry(PW, PH);
  const planes = stages.map((st, i) => {
    const mat = new THREE.MeshBasicMaterial({ map: st.tex, transparent: true, depthWrite: false, opacity: 0, fog: false });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.z = -i * GAP;
    mesh.renderOrder = stages.length - i;
    scene.add(mesh);
    // thin frame so each plane reads as a sheet of glass
    const frame = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 }));
    frame.position.copy(mesh.position);
    scene.add(frame);
    return { mesh, mat, frame, base: st.opacity };
  });

  // Dust streaks around the corridor for a sense of speed.
  const rand = rng(4000), N = mobile ? 500 : 1100, pos = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) {
    let x, y;
    do { x = (rand() - 0.5) * 70; y = (rand() - 0.5) * 44; } while (Math.abs(x) < PW * 0.6 && Math.abs(y) < PH * 0.62);
    pos.set([x, y, 22 - rand() * (stages.length * GAP + 40)], i * 3);
  }
  const dustGeo = new THREE.BufferGeometry();
  dustGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({ color: 0x8fa6ff, size: 0.09, transparent: true, opacity: 0.8, sizeAttenuation: true }));
  scene.add(dust);

  const Z0 = 15.6, Z_END = -(stages.length - 1) * GAP + 10.5; // stop where the manifest is readable
  let p = 0, mx = 0, my = 0, cmx = 0, cmy = 0, stageIdx = -1, visible = false, paused = false, raf = 0;

  addEventListener('pointermove', (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // Fit the 16:10 planes on narrow screens.
    camera.fov = camera.aspect < 1.25 ? 2 * THREE.MathUtils.radToDeg(Math.atan((PW * 0.56) / camera.aspect / Z0)) : 40;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(canvas);
  resize();

  function setStage(i) {
    if (i === stageIdx) return;
    stageIdx = i;
    const st = stages[i];
    stageEl.querySelector('.ps-n').textContent = st.n;
    stageEl.querySelector('.ps-t').textContent = st.t;
    stageEl.querySelector('.ps-d').textContent = st.d;
  }

  function render() {
    // 0..0.1 title, 0.1..0.95 flight, last 5% fade out
    const fly = smooth(0.08, 0.96, p);
    const camZ = lerp(Z0, Z_END, fly);
    cmx += (mx - cmx) * 0.06; cmy += (my - cmy) * 0.06;
    camera.position.set(cmx * 1.4, -cmy * 0.9, camZ);
    camera.lookAt(cmx * 0.3, -cmy * 0.2, camZ - 12);

    let ahead = 0;
    planes.forEach((pl, i) => {
      const d = camZ - pl.mesh.position.z; // distance still to travel to this plane
      // Only the plane ahead is bright; the ones behind it stay as faint glass.
      let o = d <= 0 ? 0 : smooth(0.4, 4.2, d) * (1 - 0.93 * smooth(GAP * 0.95, GAP * 1.7, d));
      if (i === 0) o *= 0.22 + 0.78 * smooth(0.05, 0.13, p); // keep the title readable
      pl.mat.opacity = o * pl.base;
      pl.frame.material.opacity = o * 0.35;
      pl.mesh.visible = pl.frame.visible = o > 0.003;
      if (d > 2.2 && camZ - planes[ahead].mesh.position.z <= 2.2) ahead = i;
    });
    setStage(ahead);

    // Token counter: uniform count until the quadtree plane is reached, then the optimised count.
    const toQuad = camZ - planes[2].mesh.position.z;
    const k = 1 - smooth(GAP * 0.25, GAP * 0.95, toQuad);
    countNum.textContent = fmt(lerp(m.baseline, m.optimized, k));

    const hud = smooth(0.1, 0.16, p) * (1 - smooth(0.95, 0.99, p));
    title.style.opacity = String(1 - smooth(0.03, 0.1, p));
    title.style.transform = `translateY(${-p * 300}px) scale(${1 + p * 0.6})`;
    stageEl.style.opacity = countEl.style.opacity = String(hud);
    halo.style.opacity = String(0.2 + 0.5 * fly);
    halo.style.transform = `scale(${0.8 + fly * 0.5}) rotate(${fly * 120}deg)`;
    canvas.style.opacity = String(1 - smooth(0.965, 1, p));
    dust.material.opacity = 0.25 + 0.6 * smooth(0.05, 0.2, p);
    renderer.render(scene, camera);
  }

  function loop() {
    raf = 0;
    if (!visible) return;
    render();
    if (!paused && !reduced) raf = requestAnimationFrame(loop);
  }
  const kick = () => { if (!raf && visible) raf = requestAnimationFrame(loop); };

  ScrollTrigger.create({
    trigger: section, start: 'top top', end: 'bottom bottom',
    onUpdate: (self) => { p = self.progress; kick(); },
  });
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; kick(); }, { rootMargin: '100px' }).observe(section);

  return { setPaused(v) { paused = v; kick(); } };
}
