// TokenOpt service worker: talks to the local server and owns the per-tab ledger.
// Extension pages may call http://127.0.0.1 thanks to host_permissions; the chat
// page itself cannot, so the content script asks us instead.
//
// Ledger (chrome.storage.local "ledger"): { [tabId]: { draft: [image...], resetNext, entries: [entry...] } }
//   image = { full, sent, mode, fallback, noteTokens, on }   one pasted screenshot
//   entry = { id, t, on, provider, url, prompt, textTokens, method, images, noteTokens, reply }
const SERVER = "http://127.0.0.1:8420";
const MAX_ENTRIES = 100;

async function post(path, body) {
  const r = await fetch(SERVER + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await r.json();
  if (!r.ok) throw new Error(json.error || `server returned ${r.status}`);
  return json;
}
const serverError = (e) => (String(e.message).includes("fetch") ?
  "TokenOpt server is not running. Start it with: .venv/bin/python web/server.py" : e.message);

// Text tokens: exact o200k counts from the server when it runs, else ~4 chars per token.
async function countTexts(texts, provider) {
  try {
    const r = await post("/api/tokens", { texts, provider });
    return { tokens: r.tokens, method: r.method };
  } catch {
    return { tokens: texts.map((t) => Math.ceil(t.length / 4)), method: "estimate (chars/4)" };
  }
}

// Serialize every ledger change so concurrent messages never overwrite each other.
let queue = Promise.resolve();
function withLedger(tabId, fn) {
  const run = queue.then(async () => {
    const { ledger = {} } = await chrome.storage.local.get("ledger");
    const tab = ledger[tabId] || (ledger[tabId] = { draft: [], resetNext: false, entries: [] });
    const out = await fn(tab, ledger);
    await chrome.storage.local.set({ ledger });
    return out;
  });
  queue = run.catch(() => {});
  return run;
}

function setBadge(enabled) {
  chrome.action.setBadgeText({ text: enabled ? "ON" : "" });
  chrome.action.setBadgeBackgroundColor({ color: "#1a73e8" });
}
function init() {
  chrome.storage.local.get({ enabled: true }, (v) => setBadge(v.enabled));
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
}
chrome.runtime.onInstalled.addListener(init);
chrome.runtime.onStartup.addListener(init);
chrome.storage.onChanged.addListener((c) => { if (c.enabled) setBadge(c.enabled.newValue); });
chrome.tabs.onRemoved.addListener((tabId) => withLedger(tabId, (_t, ledger) => { delete ledger[tabId]; }));

chrome.runtime.onMessage.addListener((msg, sender, send) => {
  const tabId = msg.tabId ?? (sender.tab ? sender.tab.id : null);

  if (msg.type === "optimize") {
    (async () => {
      // One conversation memory per tab, so follow-up screenshots become deltas.
      const reset = tabId != null && (await withLedger(tabId, (t) => {
        const r = t.resetNext; t.resetNext = false; return r;
      }));
      const res = await post("/api/paste", {
        image: msg.image, provider: msg.provider, session: msg.session || `tab-${tabId ?? "popup"}`,
        reset: reset || !!msg.reset, commit: msg.commit !== false,
      });
      if (tabId != null && msg.track !== false) {
        const on = msg.commit !== false;
        await withLedger(tabId, (t) => { t.draft.push({
          full: res.full_tokens, sent: on ? res.tokens : res.full_tokens, mode: on ? res.mode : "off",
          fallback: res.fallback, noteTokens: on ? res.note_tokens || 0 : 0, on,
        }); });
      }
      return res;
    })().then(send).catch((e) => send({ error: serverError(e) }));
    return true; // async response
  }

  if (msg.type === "prompt" && tabId != null) {
    (async () => {
      const { tokens, method } = await countTexts([msg.text || ""], msg.provider);
      return withLedger(tabId, (t) => {
        const images = t.draft;
        t.draft = [];
        const entry = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, t: Date.now(), on: msg.on,
          provider: msg.provider, url: msg.url, prompt: (msg.text || "").slice(0, 160),
          textTokens: tokens[0], method, images,
          noteTokens: images.reduce((s, im) => s + im.noteTokens, 0), reply: null,
        };
        t.entries.push(entry);
        t.entries = t.entries.slice(-MAX_ENTRIES);
        return entry.id;
      });
    })().then((id) => send({ id })).catch((e) => send({ error: e.message }));
    return true;
  }

  if (msg.type === "reply" && tabId != null) {
    countTexts([msg.text || ""], msg.provider).then(({ tokens }) => withLedger(tabId, (t) => {
      const e = t.entries.find((x) => x.id === msg.id);
      if (e) e.reply = tokens[0];
    })).then(() => send({ ok: true }));
    return true;
  }

  if (msg.type === "reset-screen" && tabId != null) {
    withLedger(tabId, (t) => { t.resetNext = true; }).then(() => send({ ok: true }));
    return true;
  }

  if (msg.type === "clear" && tabId != null) {
    withLedger(tabId, (t) => { t.entries = []; t.draft = []; }).then(() => send({ ok: true }));
    return true;
  }

  if (msg.type === "ping") {
    fetch(SERVER + "/api/samples").then((r) => send({ ok: r.ok })).catch(() => send({ ok: false }));
    return true;
  }
});
