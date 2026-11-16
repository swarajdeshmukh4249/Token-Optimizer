// Hero: glossy "quadtree tiles" held together by a soft attractor and pushed
// around by the cursor. Small hand-rolled sphere physics, no engine needed.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { reduced, rng } from './util.js';

// A square tile subdivided like a quadtree: finer cells stand taller ("more detail, more tokens").
function tileGeometry(rand) {
  const parts = [];
  const split = (x, y, s, d) => {
    const go = d === 0 || (d < 3 && rand() < (d === 1 ? 0.5 : 0.28));
    if (go) {
      const q = s / 4;
      for (const [dx, dy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) split(x + dx * q, y + dy * q, s / 2, d + 1);
      return;
    }
    const side = s - 0.07;
    const depth = 0.56 + 0.13 * d;
    const g = new RoundedBoxGeometry(side, side, depth, 3, Math.min(0.1, side * 0.22));
    g.translate(x, y, 0);
    parts.push(g);
  };
  split(0, 0, 2.4, 0);
  const merged = mergeGeometries(parts);
  parts.forEach((g) => g.dispose());
  return merged;
}

export function initHero({ canvas, panel, mobile }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, mobile ? 1.5 : 2));
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 1.0;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 2, 0.1, 120);
  camera.position.set(0, 0, 18.5);

  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.035).texture;
  pmrem.dispose();
  const key = new THREE.DirectionalLight(0xffffff, 2.4);
  key.position.set(-6, 9, 10);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x4466ff, 1.6);
  rim.position.set(8, -4, -6);
  scene.add(rim);

  const mats = [
    new THREE.MeshPhysicalMaterial({ color: 0xd9dade, roughness: 0.32, metalness: 0.0, clearcoat: 1, clearcoatRoughness: 0.18 }),
    new THREE.MeshPhysicalMaterial({ color: 0x0a1cff, roughness: 0.3, metalness: 0.0, clearcoat: 1, clearcoatRoughness: 0.1, envMapIntensity: 0.55 }),
    new THREE.MeshPhysicalMaterial({ color: 0x08080a, roughness: 0.16, metalness: 0.2, clearcoat: 1, clearcoatRoughness: 0.05 }),
    new THREE.MeshPhysicalMaterial({ color: 0x8f93a3, roughness: 0.55, metalness: 0.0, clearcoat: 0.3 }),
    new THREE.MeshPhysicalMaterial({ color: 0x1a30ff, roughness: 0.62, metalness: 0.0, envMapIntensity: 0.5 }),
  ];
  const rand = rng(905);
  const geos = Array.from({ length: 6 }, () => tileGeometry(rand));

  const COUNT = mobile ? 15 : 26;
  const matOrder = [0, 1, 2, 0, 1, 3, 0, 1, 2, 4];
  const bodies = [];
  for (let i = 0; i < COUNT; i++) {
    const mesh = new THREE.Mesh(geos[i % geos.length], mats[matOrder[i % matOrder.length]]);
    const scale = 0.82 + rand() * 0.5;
    mesh.scale.setScalar(scale);
    mesh.quaternion.setFromEuler(new THREE.Euler(rand() * 6.28, rand() * 6.28, rand() * 6.28));
    // Start far outside the frame; the attractor pulls everything in after the loader.
    const a = rand() * Math.PI * 2;
    mesh.position.set(Math.cos(a) * (30 + rand() * 14), Math.sin(a) * (16 + rand() * 10), (rand() - 0.5) * 10);
    scene.add(mesh);
    bodies.push({
      mesh, r: 1.18 * scale, m: scale * scale * scale,
      v: new THREE.Vector3(), w: new THREE.Vector3((rand() - 0.5) * 2, (rand() - 0.5) * 2, (rand() - 0.5) * 2),
      phase: rand() * 100,
    });
  }

  // Pointer: an invisible sphere on the z = 0 plane.
  const pointer = { ndc: new THREE.Vector2(9, 9), pos: new THREE.Vector3(999, 999, 0), target: new THREE.Vector3(999, 999, 0), active: false };
  const ray = new THREE.Raycaster();
  const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
  const onMove = (e) => {
    const rect = panel.getBoundingClientRect();
    const inside = e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;
    pointer.active = inside;
    if (!inside) return;
    pointer.ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -(((e.clientY - rect.top) / rect.height) * 2 - 1));
    ray.setFromCamera(pointer.ndc, camera);
    ray.ray.intersectPlane(plane, pointer.target);
  };
  addEventListener('pointermove', onMove, { passive: true });
  addEventListener('pointerleave', () => { pointer.active = false; });

  const tmp = new THREE.Vector3(), n = new THREE.Vector3(), rel = new THREE.Vector3(), dq = new THREE.Quaternion(), axis = new THREE.Vector3();
  const POINTER_R = 2.6;
  let started = false;

  function step(dt, time) {
    if (pointer.active) pointer.pos.lerp(pointer.target, 0.25);
    else pointer.pos.set(999, 999, 0);
    const pull = started ? 1 : 0;

    for (const b of bodies) {
      const p = b.mesh.position;
      // Soft attractor (ellipsoid: wide in x, shallow in z) + a slow swirl so the pile never settles.
      tmp.set(-p.x * 1.5, -p.y * 2.4, -p.z * 3.2).multiplyScalar(pull);
      tmp.x += Math.sin(time * 0.31 + b.phase) * 0.9 - p.y * 0.22 * pull;
      tmp.y += Math.cos(time * 0.27 + b.phase * 1.3) * 0.9 + p.x * 0.1 * pull;
      tmp.z += Math.sin(time * 0.4 + b.phase * 0.7) * 0.6;
      b.v.addScaledVector(tmp, dt);

      // Cursor sphere.
      n.subVectors(p, pointer.pos);
      const d = n.length(), min = b.r + POINTER_R;
      if (d < min && d > 1e-4) {
        n.multiplyScalar(1 / d);
        b.v.addScaledVector(n, (min - d) * 42 * dt);
        b.w.x += n.y * 3 * dt; b.w.y -= n.x * 3 * dt;
      }
      b.v.multiplyScalar(1 - Math.min(1, 1.9 * dt));
      b.w.multiplyScalar(1 - Math.min(1, 0.55 * dt));
    }

    // Sphere-sphere contacts.
    for (let i = 0; i < bodies.length; i++) {
      const a = bodies[i];
      for (let j = i + 1; j < bodies.length; j++) {
        const b = bodies[j];
        n.subVectors(b.mesh.position, a.mesh.position);
        const d = n.length(), min = a.r + b.r;
        if (d >= min || d < 1e-4) continue;
        n.multiplyScalar(1 / d);
        const overlap = min - d, total = a.m + b.m;
        a.mesh.position.addScaledVector(n, -overlap * (b.m / total) * 0.6);
        b.mesh.position.addScaledVector(n, overlap * (a.m / total) * 0.6);
        rel.subVectors(b.v, a.v);
        const vn = rel.dot(n);
        if (vn < 0) {
          const jimp = (-(1.25) * vn) / (1 / a.m + 1 / b.m);
          a.v.addScaledVector(n, -jimp / a.m);
          b.v.addScaledVector(n, jimp / b.m);
        }
        // Tangential slip turns into spin.
        tmp.crossVectors(n, rel).multiplyScalar(0.012);
        a.w.add(tmp); b.w.sub(tmp);
      }
    }

    for (const b of bodies) {
      b.mesh.position.addScaledVector(b.v, dt);
      const speed = b.w.length();
      if (speed > 1e-5) {
        axis.copy(b.w).multiplyScalar(1 / speed);
        dq.setFromAxisAngle(axis, speed * dt);
        b.mesh.quaternion.premultiply(dq);
      }
    }
  }

  function resize() {
    const w = panel.clientWidth, h = panel.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // Keep the pile framed on tall (phone) panels.
    camera.position.z = camera.aspect < 1.3 ? 18.5 * (1.3 / Math.max(0.5, camera.aspect)) * 0.8 : 18.5;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(panel);
  resize();

  let visible = true, paused = false, last = performance.now(), time = 0, raf = 0;
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) kick(); }).observe(panel);
  function frame(now) {
    raf = 0;
    if (!visible || paused) return;
    const dt = Math.min(0.033, (now - last) / 1000);
    last = now; time += dt;
    step(dt / 2, time); step(dt / 2, time);
    renderer.render(scene, camera);
    raf = requestAnimationFrame(frame);
  }
  function kick() { if (!raf && !paused && visible) { last = performance.now(); raf = requestAnimationFrame(frame); } }
  kick();

  return {
    start() {
      started = true;
      if (reduced) {
        // Settle instantly and show one still frame.
        for (let i = 0; i < 600; i++) step(1 / 60, i / 60);
        renderer.render(scene, camera);
        paused = true;
      }
    },
    setPaused(v) { paused = v || reduced; if (!paused) kick(); },
  };
}
