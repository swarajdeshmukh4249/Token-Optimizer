// TokenOpt content script for chatgpt.com and claude.ai.
// Catches an image paste, asks the local engine what to send instead, puts the
// optimized image(s) into the chat box and shows a badge with the token estimate.
// If anything fails it pastes the original image, so the chat never breaks.
(() => {
  const PROVIDER = location.hostname.endsWith("claude.ai") ? "claude" : "openai";
  const LABEL = PROVIDER === "claude" ? "Claude" : "ChatGPT";
  let enabled = true;
  let busy = false;
  let resetNext = false;
  chrome.storage.local.get({ enabled: true }, (v) => (enabled = v.enabled));
  chrome.storage.onChanged.addListener((c) => { if (c.enabled) enabled = c.enabled.newValue; });

  const fmt = (n) => n.toLocaleString("en-US");
  const readAsDataURL = (blob) => new Promise((ok, err) => {
    const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = err; r.readAsDataURL(blob);
  });
  const toFile = async (dataUrl, name) => new File([await (await fetch(dataUrl)).blob()], name, { type: "image/png" });

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

    if (!enabled) { // off: let the original through, but still show what it costs
      readAsDataURL(file).then((image) =>
        chrome.runtime.sendMessage({ type: "optimize", image, provider: PROVIDER, commit: false },
          (res) => res && !res.error && badge.off(res)));
      return;
    }

    e.preventDefault();
    e.stopImmediatePropagation();
    busy = true;
    badge.loading();
    try {
      const image = await readAsDataURL(file);
      const res = await chrome.runtime.sendMessage({ type: "optimize", image, provider: PROVIDER, reset: resetNext });
      resetNext = false;
      if (!res || res.error) throw new Error((res && res.error) || "no response from TokenOpt");
      const files = await Promise.all(res.images.map((im) => toFile(im.data, `tokenopt-${im.name}.png`)));
      if (files.length) insertFiles(files, target);
      if (res.note) insertText(`[${res.note}]`, target);
      badge.show(res);
    } catch (err) {
      insertFiles([file], target); // fail open: the user still gets their paste
      badge.error(err.message);
    } finally {
      busy = false;
    }
  }
  window.addEventListener("paste", onPaste, true);

  // ---- badge (shadow DOM so the chat page's CSS cannot touch it) ----
  const badge = (() => {
    const host = document.createElement("div");
    host.style.cssText = "position:fixed;right:20px;bottom:96px;z-index:2147483647;";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        .card{font:13px/1.4 -apple-system,system-ui,sans-serif;color:#e8eaed;background:#16181d;
              border:1px solid #2f333b;border-radius:14px;padding:12px 14px;width:290px;
              box-shadow:0 12px 32px rgba(0,0,0,.35)}
        .top{display:flex;justify-content:space-between;align-items:center;color:#9aa0a6;font-size:12px}
        .big{font-size:22px;font-weight:650;margin:6px 0 2px;letter-spacing:-.01em}
        .big s{color:#80868b;font-weight:500}
        .pct{color:#5ee08a}
        .sub{color:#9aa0a6;font-size:12px}
        .row{display:flex;gap:8px;margin-top:10px}
        button{all:unset;cursor:pointer;font-size:12px;color:#8ab4f8}
        button:hover{text-decoration:underline}
        .x{color:#80868b;font-size:15px}
        .err{color:#f28b82}
      </style>
      <div class="card" hidden><div class="top"><span>TokenOpt · ${LABEL}</span><button class="x" title="Close">×</button></div>
      <div class="body"></div></div>`;
    const card = root.querySelector(".card");
    const body = root.querySelector(".body");
    root.querySelector(".x").onclick = () => (card.hidden = true);
    const mount = () => { if (!host.isConnected) document.documentElement.appendChild(host); card.hidden = false; };
    const modeText = { new: "new screen", delta: "only the changed regions", duplicate: "duplicate of the previous screenshot" };
    return {
      loading() { mount(); body.innerHTML = `<div class="big">Optimizing…</div>`; },
      error(msg) { mount(); body.innerHTML = `<div class="sub err">${msg}</div><div class="sub">Sent the original image instead.</div>`; },
      off(res) {
        mount();
        body.innerHTML = `<div class="big">${fmt(res.full_tokens)} tokens</div>
          <div class="sub">TokenOpt is off · full screenshot sent · estimate from ${res.formula}</div>`;
      },
      show(res) {
        mount();
        const n = res.images.length;
        const what = res.fallback ? "original kept (optimizing would not save enough)"
          : res.mode === "duplicate" ? "nothing sent"
          : `${n} image${n === 1 ? "" : "s"} · ${modeText[res.mode]}`;
        body.innerHTML = `
          <div class="big"><s>${fmt(res.full_tokens)}</s> → ${fmt(res.tokens)} tokens
            <span class="pct">${res.fallback ? "" : `−${res.reduction}%`}</span></div>
          <div class="sub">${what} · ${res.ms} ms</div>
          <div class="sub">Estimate from ${res.formula}</div>
          <div class="row"><button class="reset">Treat next paste as a new screen</button></div>`;
        root.querySelector(".reset").onclick = () => { resetNext = true; card.hidden = true; };
      },
    };
  })();
})();
