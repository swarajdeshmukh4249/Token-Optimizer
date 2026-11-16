// TokenOpt side panel: per-prompt token ledger for the active ChatGPT / Claude.ai tab.
//
// Per prompt:
//   used    = prompt text + screenshots as sent + reply
//   without = prompt text (minus our layout note) + screenshots at full size + reply
//   saved   = without - used
// Screenshot tokens are estimates from the providers' published image formulas.
// Text tokens are exact for ChatGPT (OpenAI's o200k tokenizer) and an estimate for Claude.
const $ = (id) => document.getElementById(id);
const fmt = (n) => Math.round(n).toLocaleString("en-US");
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const time = (t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const MODE = { new: "new screen", delta: "changes only", duplicate: "duplicate, not sent", off: "TokenOpt off" };

let tabId = null;

function cost(e) {
  const imgFull = e.images.reduce((s, im) => s + im.full, 0);
  const imgSent = e.images.reduce((s, im) => s + im.sent, 0);
  const reply = e.reply || 0;
  const used = e.textTokens + imgSent + reply;
  const without = Math.max(0, e.textTokens - e.noteTokens) + imgFull + reply;
  return { imgFull, imgSent, reply, used, without, saved: without - used };
}

function renderTotals(entries) {
  const sum = entries.map(cost).reduce((a, c) => ({ used: a.used + c.used, without: a.without + c.without }),
    { used: 0, without: 0 });
  const saved = sum.without - sum.used;
  const pct = sum.without ? (100 * saved) / sum.without : 0;
  $("totals").innerHTML = `
    <div class="label">This conversation · ${entries.length} prompt${entries.length === 1 ? "" : "s"}</div>
    <div class="totals">
      <div><div class="num">${fmt(sum.used)}</div><div class="sub">tokens used</div></div>
      <div><div class="num green">${fmt(saved)}</div><div class="sub">tokens saved (${pct.toFixed(1)}%)</div></div>
      <div><div class="num"><s>${fmt(sum.without)}</s></div><div class="sub">without TokenOpt</div></div>
    </div>
    <div class="bar" title="share saved"><i style="width:${Math.min(100, Math.max(0, pct))}%"></i></div>`;
}

function renderDraft(draft) {
  const el = $("draft");
  if (!draft.length) { el.hidden = true; return; }
  const full = draft.reduce((s, im) => s + im.full, 0), sent = draft.reduce((s, im) => s + im.sent, 0);
  el.hidden = false;
  el.innerHTML = `<b>Next prompt:</b> ${draft.length} screenshot${draft.length === 1 ? "" : "s"} attached ·
    ${full === sent ? `${fmt(full)} tokens` : `<s>${fmt(full)}</s> → <b>${fmt(sent)}</b> tokens`}`;
}

function renderEntry(e, n) {
  const c = cost(e);
  const shots = e.images.length
    ? `<tr><td class="k">Screenshots (${e.images.length}) · ${[...new Set(e.images.map((im) => MODE[im.mode] || im.mode))].join(", ")}</td>
         <td>${c.imgFull === c.imgSent ? fmt(c.imgSent) : `<s>${fmt(c.imgFull)}</s> → ${fmt(c.imgSent)}`}</td></tr>`
    : "";
  const reply = e.reply == null ? `<span class="wait">waiting…</span>` : fmt(e.reply);
  const saved = c.saved > 0
    ? `<span class="saved">−${fmt(c.saved)} (${((100 * c.saved) / c.without).toFixed(0)}%)</span>`
    : `<span class="sub">${e.on ? "0" : "0 · TokenOpt was off"}</span>`;
  return `<section class="card entry">
    <div class="head"><span class="label">Prompt ${n} · ${time(e.t)}</span>
      <span class="tag ${e.on ? "on" : ""}">${e.on ? "TokenOpt on" : "off"}</span></div>
    <div class="prompt ${e.prompt ? "" : "empty"}">${e.prompt ? esc(e.prompt) : "(screenshot only)"}</div>
    <table>
      <tr><td class="k">Prompt text · ${esc(e.method || "")}</td><td>${fmt(e.textTokens)}</td></tr>
      ${shots}
      <tr><td class="k">Reply</td><td>${reply}</td></tr>
      <tr class="total"><td>Used</td><td>${fmt(c.used)}</td></tr>
      <tr><td class="k">Saved by TokenOpt</td><td>${saved}</td></tr>
    </table></section>`;
}

function render(ledger) {
  const tab = (ledger && ledger[tabId]) || { draft: [], entries: [] };
  renderTotals(tab.entries);
  renderDraft(tab.draft);
  const provider = (tab.entries.at(-1) || {}).provider;
  $("site").textContent = provider === "claude" ? "Claude.ai" : provider === "openai" ? "ChatGPT" : "token ledger";
  $("entries").innerHTML = tab.entries.length
    ? tab.entries.map((e, i) => renderEntry(e, i + 1)).reverse().join("")
    : `<div class="empty-state">No prompts recorded in this tab yet.
        <ol><li>Open chatgpt.com or claude.ai in this tab</li><li>Paste a screenshot (⌘⇧⌃4, then ⌘V)</li>
        <li>Type a prompt and send it</li></ol></div>`;
  $("foot").textContent = provider === "claude"
    ? "Claude does not publish its tokenizer: text counts are estimates (o200k). Screenshot costs use Anthropic's published formula ceil(w·h/750)."
    : "Text counts use OpenAI's o200k tokenizer (exact for GPT-4o-class models). Screenshot costs use OpenAI's published formula 85 + 170 per 512 px tile. Only screenshots pasted with ⌘V are tracked.";
}

async function refresh() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  tabId = tab ? tab.id : null;
  const { ledger = {} } = await chrome.storage.local.get("ledger");
  render(ledger);
}

chrome.storage.onChanged.addListener((c) => {
  if (c.ledger) render(c.ledger.newValue);
  if (c.enabled) setToggle(c.enabled.newValue);
});
chrome.tabs.onActivated.addListener(refresh);
chrome.windows.onFocusChanged.addListener(refresh);

function setToggle(on) {
  $("enabled").checked = on;
  $("onoff").textContent = on ? "On" : "Off";
}
chrome.storage.local.get({ enabled: true }, (v) => setToggle(v.enabled));
$("enabled").onchange = (e) => chrome.storage.local.set({ enabled: e.target.checked });

$("reset").onclick = () => chrome.runtime.sendMessage({ type: "reset-screen", tabId }, () => {
  $("reset").textContent = "Next screenshot will be sent as a new screen ✓";
  setTimeout(() => ($("reset").textContent = "Treat next screenshot as a new screen"), 2500);
});
$("clear").onclick = () => chrome.runtime.sendMessage({ type: "clear", tabId });
$("manual").onclick = () => chrome.tabs.create({ url: chrome.runtime.getURL("popup.html") });

function ping() {
  chrome.runtime.sendMessage({ type: "ping" }, (r) => {
    const ok = r && r.ok;
    $("dot").className = "dot " + (ok ? "ok" : "bad");
    $("status").innerHTML = ok ? "Local engine running on 127.0.0.1:8420"
      : "Engine not running. Start it with <code>.venv/bin/python web/server.py</code>";
  });
}
ping();
setInterval(ping, 10000);
refresh();
