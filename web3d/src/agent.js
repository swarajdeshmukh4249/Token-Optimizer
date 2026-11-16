// Agent run: filmstrip of the 20 turns + cumulative context chart, all from agent.json.
import gsap from 'gsap';
import { asset, fmt, reduced } from './util.js';

// agent_filmstrip.png is a 5 x 4 contact sheet; these are the frame boxes inside it.
const SHEET = { w: 1648, h: 968, cols: 5, x0: 9, y0: 9, dx: 328, dy: 240, fw: 318, fh: 198 };

export function initAgent({ data }) {
  const agent = data.agent;
  if (!agent) { document.querySelector('#agent').style.display = 'none'; return; }
  const track = document.querySelector('#film-track');
  const sheet = data.assets.filmstrip ? asset(data.assets.filmstrip) : null;

  agent.turns.forEach((t, i) => {
    const el = document.createElement('div');
    el.className = `turn ${t.role}`;
    const col = i % SHEET.cols, row = Math.floor(i / SHEET.cols);
    const bx = SHEET.x0 + col * SHEET.dx, by = SHEET.y0 + row * SHEET.dy;
    const img = sheet
      ? `style="background-image:url(${sheet});background-size:${(SHEET.w / SHEET.fw) * 100}% ${(SHEET.h / SHEET.fh) * 100}%;background-position:${(bx / (SHEET.w - SHEET.fw)) * 100}% ${(by / (SHEET.h - SHEET.fh)) * 100}%"`
      : '';
    el.innerHTML = `<div class="turn-img" ${img}></div>
      <div class="turn-meta mono"><span>${String(t.turn).padStart(2, '0')} · <span class="role">${t.role}</span></span><span>${fmt(t.tokens)} / ${fmt(t.baseline_tokens)}</span></div>
      <div class="turn-act">${t.action}</div>`;
    track.appendChild(el);
  });

  if (!reduced) {
    gsap.to(track, {
      x: () => -(track.scrollWidth - innerWidth), ease: 'none',
      scrollTrigger: { trigger: '#film', start: 'top 85%', end: 'bottom 5%', scrub: 0.6, invalidateOnRefresh: true },
    });
  } else {
    document.querySelector('#film').style.overflowX = 'auto';
  }

  // Chart
  const svg = document.querySelector('#agent-chart');
  const VW = 1000, VH = 380, n = agent.turns.length;
  const max = agent.summary.context_tokens_baseline;
  const X = (i) => (i / (n - 1)) * VW, Y = (v) => VH - 14 - (v / max) * (VH - 40);
  const line = (key) => agent.turns.map((t, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(t[key]).toFixed(1)}`).join(' ');
  const ticks = agent.turns.map((t, i) => (t.role === 'key' ? `<line x1="${X(i)}" x2="${X(i)}" y1="0" y2="${VH}" stroke="rgba(255,255,255,0.16)" stroke-dasharray="3 5" vector-effect="non-scaling-stroke"/>` : '')).join('');
  svg.innerHTML = `${ticks}
    <path d="${line('context_optimized')} L${VW} ${VH} L0 ${VH} Z" fill="rgba(91,134,255,0.16)"/>
    <path d="${line('context_baseline')}" fill="none" stroke="rgba(255,255,255,0.55)" stroke-width="2" vector-effect="non-scaling-stroke"/>
    <path d="${line('context_optimized')}" fill="none" stroke="#5b86ff" stroke-width="3" vector-effect="non-scaling-stroke"/>`;
  if (!reduced) {
    gsap.fromTo(svg, { clipPath: 'inset(0% 100% 0% 0%)' }, {
      clipPath: 'inset(0% 0% 0% 0%)', ease: 'none',
      scrollTrigger: { trigger: svg, start: 'top 85%', end: 'top 30%', scrub: 0.6 },
    });
  }
}
