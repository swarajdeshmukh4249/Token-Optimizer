// TokenOpt content script for chatgpt.com and claude.ai.
//  1. Catches an image paste, asks the local engine what to send instead, and puts
//     the optimized image(s) into the chat box. If anything fails it pastes the
//     original image, so the chat never breaks.
//  2. Notices when a prompt is sent (Enter or the send button) and reports its text
//     to the side panel's ledger, then reports the reply's text once it stops streaming.
(() => {
  const PROVIDER = location.hostname.endsWith("claude.ai") ? "claude" : "openai";
  const COMPOSER = PROVIDER === "claude"
    ? ['div.ProseMirror[contenteditable="true"]', '[contenteditable="true"]', "textarea"]
    : ["#prompt-textarea", '[contenteditable="true"]', "textarea"];
  const ASSISTANT = PROVIDER === "claude"
    ? '.font-claude-response, .font-claude-message, [data-testid="assistant-message"]'
    : '[data-message-author-role="assistant"]';
  const STREAMING = PROVIDER === "claude"
    ? '[data-is-streaming="true"]'
    : '[data-testid="stop-button"], button[aria-label*="Stop" i]';

  let enabled = true;
  let busy = false;
  chrome.storage.local.get({ enabled: true }, (v) => (enabled = v.enabled));
  chrome.storage.onChanged.addListener((c) => { if (c.enabled) enabled = c.enabled.newValue; });

  const fmt = (n) => n.toLocaleString("en-US");
  const send = (msg) => new Promise((ok) => chrome.runtime.sendMessage(msg, ok));
  const readAsDataURL = (blob) => new Promise((ok, err) => {
    const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = err; r.readAsDataURL(blob);
  });
  const toFile = async (dataUrl, name) => new File([await (await fetch(dataUrl)).blob()], name, { type: "image/png" });

  // ---------------------------------------------------------------- paste
  function pastedImage(e) {
    const items = [...((e.clipboardData && e.clipboardData.items) || [])];
    const it = items.find((i) => i.kind === "file" && i.type.startsWith("image/"));
    return it ? it.getAsFile() : null;
  }

  // Hand files to the page the way a real paste would; fall back to its file input.
  function insertFiles(files, target) {
    const dt = new DataTransfer();
    files.forEach((f) => dt.items.add(f));
    const ev = new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true });
    (target || document.activeElement || document.body).dispatchEvent(ev);
    if (!ev.defaultPrevented) {
      const input = document.querySelector('input[type="file"]');
      if (input) {
        input.files = dt.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  }

  function insertText(text, target) {
    const el = target && target.isContentEditable ? target : document.querySelector('[contenteditable="true"]');
    if (el) { el.focus(); document.execCommand("insertText", false, text + " "); return; }
    const ta = document.querySelector("textarea");
    if (ta) {
      ta.focus();
      ta.setRangeText(text + " ", ta.selectionStart, ta.selectionEnd, "end");
      ta.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  async function onPaste(e) {
    if (!e.isTrusted || busy) return; // our own re-dispatched paste is untrusted: let it through
    const file = pastedImage(e);
    if (!file) return;
    const target = e.target;

    if (!enabled) { // off: the original goes through, but the ledger still records its cost
      readAsDataURL(file).then((image) => send({ type: "optimize", image, provider: PROVIDER, commit: false }))
        .then((res) => res && !res.error && toast.show(`Screenshot: ${fmt(res.full_tokens)} tokens (TokenOpt off)`));
      return;
    }

    e.preventDefault();
    e.stopImmediatePropagation();
    busy = true;
    toast.show("optimizing screenshot…", 0);
    try {
      const res = await send({ type: "optimize", image: await readAsDataURL(file), provider: PROVIDER });
      if (!res || res.error) throw new Error((res && res.error) || "no response from TokenOpt");
      const files = await Promise.all(res.images.map((im) => toFile(im.data, `tokenopt-${im.name}.png`)));
      if (files.length) insertFiles(files, target);
      if (res.note) insertText(`[${res.note}]`, target);
      toast.show(res.fallback
        ? `Screenshot: ${fmt(res.full_tokens)} tokens · original kept (no saving possible)`
        : `Screenshot: ${fmt(res.full_tokens)} → ${fmt(res.tokens)} tokens (−${res.reduction}%) · ${res.mode}`);
    } catch (err) {
      insertFiles([file], target); // fail open: the user still gets their paste
      toast.show(`${err.message} · sent the original image`, 8000, true);
    } finally {
      busy = false;
    }
  }
  window.addEventListener("paste", onPaste, true);

  // ---------------------------------------------------------------- prompt + reply
  function composer() {
    for (const sel of COMPOSER) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }
  const composerText = () => {
    const el = composer();
    if (!el) return "";
    return (el.tagName === "TEXTAREA" ? el.value : el.innerText).trim();
  };
  let lastText = "";
  document.addEventListener("input", () => { lastText = composerText() || lastText; }, true);

  let lastSent = 0;
  async function promptSent() {
    const now = Date.now();
    if (now - lastSent < 1000) return; // Enter and a button click for the same prompt
    lastSent = now;
    const text = composerText() || lastText;
    lastText = "";
    const before = document.querySelectorAll(ASSISTANT).length;
    const res = await send({ type: "prompt", text, provider: PROVIDER, on: enabled, url: location.pathname });
    if (res && res.id) watchReply(res.id, before);
  }

  // The reply is "done" once a new assistant message exists, nothing is streaming,
  // and its text has not changed for three seconds. Gives up after five minutes.
  function watchReply(id, before) {
    let last = "", stable = 0, ticks = 0;
    const timer = setInterval(() => {
      ticks += 1;
      const all = document.querySelectorAll(ASSISTANT);
      if (all.length > before) {
        const text = all[all.length - 1].innerText.trim();
        const streaming = !!document.querySelector(STREAMING);
        stable = text && text === last && !streaming ? stable + 1 : 0;
        last = text;
        if (stable >= 3) { clearInterval(timer); send({ type: "reply", id, text, provider: PROVIDER }); return; }
      }
      if (ticks > 300) clearInterval(timer);
    }, 1000);
  }

  const inComposer = (el) => { const c = composer(); return !!(c && el && (c === el || c.contains(el))); };
  window.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && inComposer(e.target)) promptSent();
  }, true);
  window.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("button");
    if (!btn) return;
    const label = `${btn.getAttribute("data-testid") || ""} ${btn.getAttribute("aria-label") || ""}`;
    if (/send/i.test(label)) promptSent();
  }, true);

  // ---------------------------------------------------------------- toast
  const toast = (() => {
    const host = document.createElement("div");
    host.style.cssText = "position:fixed;right:20px;bottom:96px;z-index:2147483647;";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>
      .t{font:13px/1.4 -apple-system,system-ui,sans-serif;color:#e8eaed;background:#16181d;border:1px solid #2f333b;
         border-radius:12px;padding:10px 14px;max-width:340px;box-shadow:0 12px 32px rgba(0,0,0,.35)}
      .t.err{border-color:#f28b82} .k{color:#8ab4f8;font-weight:600}</style>
      <div class="t" hidden><span class="k">TokenOpt</span> <span class="m"></span></div>`;
    const box = root.querySelector(".t"), msg = root.querySelector(".m");
    let timer;
    return {
      show(text, ms = 4000, err = false) {
        if (!host.isConnected) document.documentElement.appendChild(host);
        msg.textContent = text;
        box.className = "t" + (err ? " err" : "");
        box.hidden = false;
        clearTimeout(timer);
        if (ms) timer = setTimeout(() => (box.hidden = true), ms);
      },
    };
  })();
})();
