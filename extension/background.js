// TokenOpt service worker: talks to the local server and owns the per-tab ledger.
// Extension pages may call http://127.0.0.1 thanks to host_permissions; the chat
// page itself cannot, so the content script asks us instead.
//
// Ledger (chrome.storage.local "ledger"): { [tabId]: { draft: [image...], resetNext, entries: [entry...] } }
//   image = { full, sent, mode, fallback, resized, names, noteTokens, on }   one attached screenshot
//   entry = { id, t, on, provider, url, prompt, textTokens, method, images, noteTokens, reply }
const SERVER = "http://127.0.0.1:8420";
const MAX_ENTRIES = 100;
const CHAT_URLS = ["https://chatgpt.com/*", "https://chat.openai.com/*", "https://claude.ai/*"];

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
const serverError = (e) => (/fetch|network/i.test(String(e.message)) ?
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
init(); // every time the worker starts, not only on install
chrome.runtime.onStartup.addListener(init);
chrome.runtime.onInstalled.addListener(async () => {
  init();
  await chrome.storage.local.remove("ledger"); // tab ids and old-format entries do not carry over
  // Chat tabs opened before this install still run the previous content script
  // (or none): reload them once so the new one attaches.
  try {
    for (const tab of await chrome.tabs.query({ url: CHAT_URLS })) chrome.tabs.reload(tab.id);
  } catch { /* no access: the side panel tells the user to refresh */ }
});
chrome.storage.onChanged.addListener((c) => { if (c.enabled) setBadge(c.enabled.newValue); });
chrome.tabs.onRemoved.addListener((tabId) => withLedger(tabId, (_t, ledger) => { delete ledger[tabId]; }));

const inflight = {}; // tabId -> promise of the screenshots still being processed

chrome.runtime.onMessage.addListener((msg, sender, send) => {
  const tabId = msg.tabId ?? (sender.tab ? sender.tab.id : null);

  if (msg.type === "optimize") {
    const job = (async () => {
      const reset = tabId != null && (await withLedger(tabId, (t) => {
        const r = t.resetNext; t.resetNext = false; return r;
      }));
      // One screenshot memory per conversation, so follow-ups in the same chat become deltas.
      const res = await post("/api/paste", {
        image: msg.image, provider: msg.provider, dpr: msg.dpr || 1,
        session: msg.session || `tab-${tabId ?? "popup"}-${msg.conv ?? 0}`,
        reset: reset || !!msg.reset, commit: msg.commit !== false,
      });
      if (tabId != null && msg.track !== false) {
        const on = msg.commit !== false;
        await withLedger(tabId, (t) => { t.draft.push({
          full: res.full_tokens, sent: on ? res.tokens : res.full_tokens, mode: on ? res.mode : "off",
          fallback: on ? !!res.fallback : false, resized: on && !!res.resized,
          names: on ? res.images.map((im) => `tokenopt-${im.name}.png`) : [msg.name || ""],
          noteTokens: on ? res.note_tokens || 0 : 0, on,
        }); });
      }
      return res;
    })();
    if (tabId != null) inflight[tabId] = Promise.all([inflight[tabId], job.catch(() => {})]);
    job.then(send).catch((e) => send({ error: serverError(e) }));
    return true; // async response
  }

  if (msg.type === "prompt" && tabId != null) {
    (async () => {
      const { tokens, method } = await countTexts([msg.text || ""], msg.provider);
      await inflight[tabId]; // a screenshot still being measured belongs to this prompt
      return withLedger(tabId, (t) => {
        const images = t.draft;
        t.draft = [];
        const entry = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, t: Date.now(), on: !!msg.on,
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
    })).then(() => send({ ok: true })).catch(() => send({ ok: false }));
    return true;
  }

  // The user removed an attachment from the chat box before sending.
  if (msg.type === "undraft" && tabId != null) {
    withLedger(tabId, (t) => {
      for (let i = t.draft.length - 1; i >= 0; i -= 1) {
        const at = (t.draft[i].names || []).indexOf(msg.name);
        if (at < 0) continue;
        t.draft[i].names.splice(at, 1);
        if (!t.draft[i].names.length) {
          t.draft.splice(i, 1);
          t.resetNext = true; // the chat never got that screenshot: send the next one whole
        }
        break;
      }
    }).then(() => send({ ok: true })).catch(() => send({ ok: false }));
    return true;
  }

  // The tab moved to another chat: attachments typed there are gone.
  if (msg.type === "new-conversation" && tabId != null) {
    withLedger(tabId, (t) => { t.draft = []; t.resetNext = false; })
      .then(() => send({ ok: true })).catch(() => send({ ok: false }));
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
