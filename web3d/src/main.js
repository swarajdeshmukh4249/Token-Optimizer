import '@fontsource/figtree/400.css';
import '@fontsource/figtree/500.css';
import '@fontsource/figtree/400-italic.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import './styles.css';

import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';

import { asset, fmt, isMobile, loadImage, reduced, splitRoll, splitWords } from './util.js';
import { initHero } from './hero3d.js';
import { initReel } from './reel.js';
import { initCards } from './cards.js';
import { initTunnel } from './tunnel.js';
import { initAgent } from './agent.js';
import { initPlayground } from './playground.js';

gsap.registerPlugin(ScrollTrigger);
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ---------------- loader ---------------- */
const loader = {
  el: $('#loader'), fill: $('.ld-bar i'), bar: $('.ld-bar'), digits: $('#ld-digits'),
  shown: 0, target: 0.08, from: 0, to: 0, strips: [], t0: performance.now(),
  build(n) {
    this.digits.innerHTML = '';
    this.strips = Array.from({ length: n }, () => {
      const col = document.createElement('span'); col.className = 'col';
      const strip = document.createElement('span'); strip.className = 'strip';
      strip.innerHTML = '0123456789'.split('').map((d) => `<b>${d}</b>`).join('');
      col.appendChild(strip); this.digits.appendChild(col);
      return strip;
    });
  },
  set(value) {
    const s = String(Math.round(value)).padStart(this.strips.length, '0');
    this.strips.forEach((strip, i) => { strip.style.transform = `translateY(${-Number(s[i]) * 10}%)`; });
  },
  tick() {
    const minTime = reduced ? 0.4 : 2.6;
    const cap = Math.min(1, (performance.now() - this.t0) / 1000 / minTime);
    const goal = Math.min(this.target, cap);
    this.shown += (goal - this.shown) * 0.09;
    if (goal - this.shown < 0.002) this.shown = goal;
    this.fill.style.transform = `scaleX(${this.shown})`;
    // The counter runs from the uniform-grid token count down to the optimised one.
    this.set(this.from + (this.to - this.from) * this.shown);
    return this.shown >= 1;
  },
};
loader.build(4);

/* ---------------- boot ---------------- */
async function boot() {
  let done = false;
  const spin = () => { if (!done) { loader.tick(); requestAnimationFrame(spin); } };
  spin();

  const data = await fetch(asset('data/site-data.json')).then((r) => r.json());
  const ui = data.manifests.ui;
  loader.build(String(ui.baseline).length);
  loader.from = ui.baseline; loader.to = ui.optimized;
  loader.target = 0.3;

  const [uiImage] = await Promise.all([
    loadImage(asset(data.assets.samples.ui)),
    document.fonts.ready,
  ]);
  loader.target = 0.6;

  bind(data);
  $$('[data-roll]').forEach(splitRoll);

  const mobile = isMobile();
  const hero = initHero({ canvas: $('#hero-canvas'), panel: $('#hero-panel'), mobile });
  loader.target = 0.8;
  const reel = initReel({ image: uiImage, manifest: ui, mobile });
  initCards({ data, image: uiImage });
  const tunnel = initTunnel({ data, image: uiImage, mobile });
  initAgent({ data });
  initPlayground({ data });
  loader.target = 1;

  await new Promise((resolve) => {
    const wait = () => (loader.tick() ? resolve() : requestAnimationFrame(wait));
    done = true; wait();
  });

  // Unlock the document before measuring anything: triggers created while the body is
  // clipped to the loader would all resolve to scroll position 0.
  history.scrollRestoration = 'manual';
  document.body.classList.remove('is-loading');
  window.scrollTo(0, 0);
  const lenis = setupScroll();
  lenis?.stop();
  setupReveals();
  setupChrome({ lenis, hero, tunnel, reel, data });
  reel.setupScroll();
  ScrollTrigger.refresh();
  // The playground and late images change the page height; keep trigger positions honest.
  let refreshTimer = 0, lastH = document.documentElement.scrollHeight;
  new ResizeObserver(() => {
    const h = document.documentElement.scrollHeight;
    if (Math.abs(h - lastH) < 2) return;
    lastH = h; clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => ScrollTrigger.refresh(), 200);
  }).observe($('#main'));
  intro(hero, lenis);
}

/* ---------------- data binding ---------------- */
function bind(data) {
  const r = data.results, a = data.agent?.summary, ui = data.manifests.ui;
  const pct = (x) => `${(100 * x).toFixed(1)}%`;
  const values = {
    'ui.baseline': fmt(ui.baseline),
    'ui.optimized': fmt(ui.optimized),
    'ui.regions': fmt(ui.regions.length),
    'ui.reduction': r.ui ? pct(r.ui.reduction) : '–',
    'agent.turns': a ? a.turns : '–',
    'agent.shotRed': a ? pct(a.screenshot_reduction) : '–',
    'agent.ctxBase': a ? fmt(a.context_tokens_baseline) : '–',
    'agent.ctxOpt': a ? fmt(a.context_tokens_optimized) : '–',
    'agent.ctxRed': a ? pct(a.context_reduction) : '–',
    'agent.minPsnr': a ? `${a.min_psnr.toFixed(1)} dB` : '–',
    generated: new Date(data.generated).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }),
  };
  $$('[data-bind]').forEach((el) => { el.textContent = values[el.dataset.bind] ?? '–'; });
}

/* ---------------- smooth scroll ---------------- */
function setupScroll() {
  if (reduced) return null;
  const lenis = new Lenis({ lerp: 0.085, smoothWheel: true, wheelMultiplier: 0.95 });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((t) => lenis.raf(t * 1000));
  gsap.ticker.lagSmoothing(0);
  return lenis;
}

/* ---------------- reveals ---------------- */
function setupReveals() {
  if (reduced) { $('.cta-big').classList.add('in'); return; }
  $$('[data-lines]').forEach((el) => {
    if (el.closest('#hero')) return; // hero is revealed by the intro timeline
    gsap.from($$('.line > span', el), {
      yPercent: 112, duration: 1.25, ease: 'expo.out', stagger: 0.09,
      scrollTrigger: { trigger: el, start: 'top 88%', once: true },
    });
  });
  $$('[data-words]').forEach((el) => {
    gsap.from(splitWords(el), {
      opacity: 0, y: '0.7em', duration: 0.9, ease: 'expo.out', stagger: 0.012,
      scrollTrigger: { trigger: el, start: 'top 85%', once: true },
    });
  });
  $$('[data-fade]').forEach((el) => {
    gsap.from(el, { opacity: 0, y: 26, duration: 1.1, ease: 'expo.out', scrollTrigger: { trigger: el, start: 'top 92%', once: true } });
  });
  $$('.marks').forEach((el) => {
    if (el.closest('#hero') || el.closest('#pipeline')) return;
    gsap.from(el.children, { opacity: 0, rotate: 90, scale: 0.4, duration: 0.9, ease: 'expo.out', stagger: 0.06, scrollTrigger: { trigger: el, start: 'top 95%', once: true } });
  });

  // Blue ribbon draws itself as the intro scrolls.
  const path = $('#ribbon-path');
  const len = path.getTotalLength();
  gsap.set(path, { strokeDasharray: len, strokeDashoffset: len });
  gsap.to(path, { strokeDashoffset: 0, ease: 'none', scrollTrigger: { trigger: '#intro', start: 'top 75%', end: 'bottom 30%', scrub: 0.6 } });

  // The CTA letters already carry a CSS transition for the hover roll, so they are
  // revealed with a class instead of a tween (the two would fight over `transform`).
  ScrollTrigger.create({ trigger: '#cta', start: 'top 60%', once: true, onEnter: () => $('.cta-big').classList.add('in') });
}

/* ---------------- header, menu, modal, anchors ---------------- */
function setupChrome({ lenis, hero, tunnel, data }) {
  const scrollTo = (hash) => {
    const el = $(hash);
    if (!el) return;
    if (lenis) lenis.scrollTo(el, { duration: 1.8, easing: (t) => 1 - Math.pow(1 - t, 4) });
    else el.scrollIntoView();
  };
  const menu = $('#menu'), btnMenu = $('#btn-menu');
  const setMenu = (open) => {
    btnMenu.setAttribute('aria-expanded', String(open));
    btnMenu.firstElementChild.setAttribute('aria-label', open ? 'Close' : 'Menu');
    if (open) {
      menu.hidden = false;
      gsap.fromTo($$('.menu-card', menu), { opacity: 0, y: -18, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.6, ease: 'expo.out', stagger: 0.07, transformOrigin: '100% 0%' });
    } else if (!menu.hidden) {
      gsap.to($$('.menu-card', menu), { opacity: 0, y: -10, duration: 0.25, ease: 'power2.in', onComplete: () => { menu.hidden = true; } });
    }
  };
  btnMenu.addEventListener('click', () => setMenu(menu.hidden));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { setMenu(false); closeModal(); } });
  document.addEventListener('click', (e) => { if (!menu.hidden && !e.target.closest('#menu, #btn-menu')) setMenu(false); });

  $$('a[data-scroll]').forEach((a) => a.addEventListener('click', (e) => {
    e.preventDefault(); setMenu(false); scrollTo(a.getAttribute('href'));
  }));

  // Pause / resume the 3D scenes.
  const btnMotion = $('#btn-motion');
  btnMotion.addEventListener('click', () => {
    const paused = btnMotion.getAttribute('aria-pressed') !== 'true';
    btnMotion.setAttribute('aria-pressed', String(paused));
    btnMotion.setAttribute('aria-label', paused ? 'Resume 3D motion' : 'Pause 3D motion');
    hero.setPaused(paused); tunnel.setPaused(paused);
  });

  // Explainer modal.
  const modal = $('#modal'), video = $('#modal-video');
  const openModal = () => {
    if (!data.assets.explainer) return;
    setMenu(false);
    if (!video.src) { video.src = asset(data.assets.explainer); if (data.assets.poster) video.poster = asset(data.assets.poster); }
    modal.hidden = false; lenis?.stop();
    gsap.fromTo(modal, { opacity: 0 }, { opacity: 1, duration: 0.4 });
    gsap.fromTo(video, { scale: 0.92, y: 30 }, { scale: 1, y: 0, duration: 0.9, ease: 'expo.out' });
    video.play().catch(() => {});
  };
  function closeModal() {
    if (modal.hidden) return;
    video.pause();
    gsap.to(modal, { opacity: 0, duration: 0.3, onComplete: () => { modal.hidden = true; lenis?.start(); } });
  }
  $('#reel').addEventListener('click', openModal);
  $('#menu-explainer').addEventListener('click', openModal);
  $('#modal-close').addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

  // Logo turns white while it sits over a dark surface.
  const darkEls = [...$$('.dark'), $('#hero-panel'), $('#reel')];
  const logo = $('.logo');
  const check = () => {
    const lr = logo.getBoundingClientRect();
    const y = lr.top + lr.height / 2, x = lr.left + lr.width / 2;
    const dark = darkEls.some((el) => { const r = el.getBoundingClientRect(); return r.top <= y && r.bottom >= y && r.left <= x && r.right >= x; });
    document.body.classList.toggle('on-dark', dark);
  };
  if (lenis) lenis.on('scroll', check);
  addEventListener('scroll', check, { passive: true });
  addEventListener('resize', check);
  check();
}

/* ---------------- intro (loader exit) ---------------- */
function intro(hero, lenis) {
  const el = loader.el;
  const heroLines = $$('#hero .line > span');
  const tl = gsap.timeline({ defaults: { ease: 'expo.inOut' } });
  if (reduced) { el.remove(); hero.start(); lenis?.start(); return; }
  gsap.set(heroLines, { yPercent: 112 });
  gsap.set('#hero-panel', { clipPath: 'inset(46% 42% 46% 42% round 1.4rem)' });
  gsap.set(['#hdr > *', '.hero-marks > *', '#hero-meter'], { opacity: 0, y: 14 });
  tl.to('.ld-digits .strip', { yPercent: -12, opacity: 0, duration: 0.7, stagger: 0.04, ease: 'expo.in' }, 0)
    .to('.ld-label', { opacity: 0, duration: 0.3 }, 0)
    .to(loader.bar, { width: '100vw', height: '100vh', duration: 1.15 }, 0.25)
    .to(loader.fill, { backgroundColor: '#f0f1fa', duration: 0.9 }, 0.35)
    .add(() => { hero.start(); lenis?.start(); }, 0.9)
    .set(el, { display: 'none' }, 1.4)
    .to('#hero-panel', { clipPath: 'inset(0% 0% 0% 0% round 1.4rem)', duration: 1.5, ease: 'expo.out', clearProps: 'clipPath' }, 1.35)
    .to(heroLines, { yPercent: 0, duration: 1.3, ease: 'expo.out', stagger: 0.09 }, 1.5)
    .to(['#hdr > *', '.hero-marks > *', '#hero-meter'], { opacity: 1, y: 0, duration: 1, ease: 'expo.out', stagger: 0.05, clearProps: 'transform' }, 1.7)
    .add(() => el.remove());
}

boot().catch((err) => {
  console.error(err);
  loader.el.innerHTML = `<p style="position:absolute;left:5vw;bottom:5vw;font:16px/1.5 monospace;max-width:80vw">Could not start: ${String(err.message || err)}<br>Please refresh the page.</p>`;
});
