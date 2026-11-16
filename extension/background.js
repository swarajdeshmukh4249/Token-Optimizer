// TokenOpt service worker: the only part that talks to the local server.
// Extension pages may call http://127.0.0.1 thanks to host_permissions; the
// chat page itself cannot, so the content script asks us instead.
const SERVER = "http://127.0.0.1:8420";

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

function setBadge(enabled) {
  chrome.action.setBadgeText({ text: enabled ? "ON" : "" });
  chrome.action.setBadgeBackgroundColor({ color: "#1a73e8" });
}

chrome.runtime.onInstalled.addListener(() => chrome.storage.local.get({ enabled: true }, (v) => setBadge(v.enabled)));
chrome.runtime.onStartup.addListener(() => chrome.storage.local.get({ enabled: true }, (v) => setBadge(v.enabled)));
chrome.storage.onChanged.addListener((c) => { if (c.enabled) setBadge(c.enabled.newValue); });

chrome.runtime.onMessage.addListener((msg, sender, send) => {
  if (msg.type === "optimize") {
    // One conversation memory per tab, so follow-up screenshots become deltas.
    const session = msg.session || `tab-${sender.tab ? sender.tab.id : "popup"}`;
    post("/api/paste", { image: msg.image, provider: msg.provider, session, reset: !!msg.reset, commit: msg.commit !== false })
      .then(send)
      .catch((e) => send({ error: e.message.includes("fetch") ?
        "TokenOpt server is not running. Start it with: .venv/bin/python web/server.py" : e.message }));
    return true; // async response
  }
  if (msg.type === "ping") {
    fetch(SERVER + "/api/samples").then((r) => send({ ok: r.ok })).catch(() => send({ ok: false }));
    return true;
  }
});
