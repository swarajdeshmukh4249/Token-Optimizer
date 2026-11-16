// Reel panel: the UI screenshot with its real quadtree cells lighting up around the
// cursor. It starts as a small blue card beside the intro copy and grows into
// the full-width panel as you scroll.
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { reduced } from './util.js';

export function initReel({ image, manifest, mobile }) {
  const reel = document.querySelector('#reel');
  const canvas = document.querySelector('#reel-canvas');
  const ghost = document.querySelector('#reel-ghost');
  const slot = document.querySelector('#reel-slot');
  const tint = reel.querySelector('.reel-tint');
  const ctx = canvas.getContext('2d');
  const regions = manifest.regions;
  const alpha = new Float32Array(regions.length);
  const patch = manifest.patch;

  let W = 0, H = 0, sx = 1, ox = 0, oy = 0;
  function resize() {
    const dpr = Math.min(devicePixelRatio, 1.5);
    W = Math.round(slot.clientWidth * dpr); H = Math.round(slot.clientHeight * dpr);
    canvas.width = W; canvas.height = H;
    // cover-fit the image
    sx = Math.max(W / manifest.width, H / manifest.height);
    ox = (W - manifest.width * sx) / 2; oy = (H - manifest.height * sx) / 2;
  }
  new ResizeObserver(resize).observe(slot);
  resize();

  const ptr = { x: 0.5, y: 0.5, hover: false };
  reel.addEventListener('pointermove', (e) => {
    const r = reel.getBoundingClientRect();
    ptr.x = (e.clientX - r.left) / r.width; ptr.y = (e.clientY - r.top) / r.height; ptr.hover = true;
  });
  reel.addEventListener('pointerleave', () => { ptr.hover = false; });

  let visible = false, raf = 0, t = 0;
  function draw() {
    raf = 0;
    if (!visible) return;
    t += 1 / 60;
    // Autopilot when nobody is hovering.
    const px = ptr.hover ? ptr.x : 0.5 + 0.36 * Math.sin(t * 0.55);
    const py = ptr.hover ? ptr.y : 0.5 + 0.3 * Math.sin(t * 0.83 + 1.2);
    const cx = (px * W - ox) / sx, cy = (py * H - oy) / sx;
    const R = manifest.width * 0.2, R2 = R * R;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(image, ox, oy, manifest.width * sx, manifest.height * sx);
    ctx.fillStyle = 'rgba(6,7,11,0.6)';
    ctx.fillRect(0, 0, W, H);
    ctx.setTransform(sx, 0, 0, sx, ox, oy);
    ctx.lineWidth = 1 / sx;
    for (let i = 0; i < regions.length; i++) {
      const [x, y, w, h] = regions[i];
      const dx = x + w / 2 - cx, dy = y + h / 2 - cy;
      const target = dx * dx + dy * dy < R2 ? 1 : 0;
      alpha[i] += (target - alpha[i]) * (target ? 0.16 : 0.035);
      const a = alpha[i];
      if (a < 0.02) continue;
      if (w <= patch && h <= patch) {
        ctx.fillStyle = `rgba(40,70,255,${0.78 * a})`;   // single patch: detail kept
        ctx.fillRect(x + 0.5, y + 0.5, w - 1, h - 1);
      } else {
        ctx.fillStyle = `rgba(255,255,255,${0.07 * a})`; // merged: one token for the whole cell
        ctx.fillRect(x, y, w, h);
        ctx.strokeStyle = `rgba(255,255,255,${0.85 * a})`;
        ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
      }
    }
    if (!reduced) raf = requestAnimationFrame(draw);
  }
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible && !raf) raf = requestAnimationFrame(draw); }, { rootMargin: '200px' }).observe(reel);

  function setupScroll() {
    const ui = [reel.querySelector('.reel-ui'), reel.querySelector('.reel-meta')];
    if (reduced || mobile) return;
    const rem = () => parseFloat(getComputedStyle(document.documentElement).fontSize);
    const geo = () => {
      const g = ghost.getBoundingClientRect(), s = slot.getBoundingClientRect();
      return { scale: g.width / s.width, y: g.top - s.top };
    };
    gsap.set(ui, { opacity: 0 });
    const tl = gsap.timeline({
      defaults: { ease: 'none' },
      scrollTrigger: { trigger: ghost, start: 'top 42%', endTrigger: slot, end: 'top 14%', scrub: 0.5, invalidateOnRefresh: true },
    });
    tl.fromTo(reel, { scale: () => geo().scale, y: () => geo().y }, {
      scale: 1, y: 0, duration: 1, ease: 'power1.inOut',
      onUpdate() { reel.style.borderRadius = `${(1.4 * rem()) / Number(gsap.getProperty(reel, 'scaleX'))}px`; },
    }, 0)
      .to(reel, { rotate: -3, skewX: -5, duration: 0.5, ease: 'sine.inOut' }, 0)
      .to(reel, { rotate: 0, skewX: 0, duration: 0.5, ease: 'sine.inOut' }, 0.5)
      .fromTo(reel, { '--t': 1 }, { '--t': 0, duration: 0.6 }, 0.3)
      .to(ui, { opacity: 1, duration: 0.25 }, 0.75);
    reel.style.borderRadius = `${(1.4 * rem()) / geo().scale}px`;
    ScrollTrigger.addEventListener('refreshInit', () => gsap.set(reel, { clearProps: 'borderRadius' }));
  }

  return { setupScroll };
}
