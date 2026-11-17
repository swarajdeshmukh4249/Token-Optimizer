// TokenOpt content script for chatgpt.com and claude.ai.
//  1. Catches an image that is pasted, dropped or picked with the upload button,
//     asks the local engine what to send instead, and hands the optimized image(s)
//     to the chat box. If anything fails the original image goes through, so the
//     chat never breaks.
//  2. Notices when a prompt is really sent and reports its text to the side
//     panel's ledger, then reports the reply's text once it stops streaming.
(() => {
  const VERSION = chrome.runtime.getManifest().version;
  const PROVIDER = location.hostname.endsWith("claude.ai") ? "claude" : "openai";
  const COMPOSER = ["#prompt-textarea", 'div.ProseMirror[contenteditable="true"]', '[contenteditable="true"]', "textarea"];
  const USER_MSG = PROVIDER === "claude"
    ? '[data-testid="user-message"]'
    : '[data-conversation-role="user"], [data-message-author-role="user"]';
  const IMAGE = /^image\/(png|jpe?g|webp)$/;
  const CONVERSATION = /\/(c|chat)\/[\w-]+/; // a saved conversation, as opposed to a "new chat" page
  const PAGE = Math.random().toString(36).slice(2, 8); // screenshot memory never survives a page reload

  let enabled = true;
  chrome.storage.local.get({ enabled: true }, (v) => { void chrome.runtime.lastError; if (v) enabled = v.enabled; });
  chrome.storage.onChanged.addListener((c) => { if (c.enabled) enabled = c.enabled.newValue; });

  const fmt = (n) => n.toLocaleString("en-US");
  const alive = () => { try { return !!chrome.runtime.id; } catch { return false; } };
  const send = (msg) => new Promise((ok) => {
    try {
      chrome.runtime.sendMessage(msg, (r) => { void chrome.runtime.lastError; ok(r); });
    } catch { ok(null); }
  });
  const readAsDataURL = (blob) => new Promise((ok, err) => {
    const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = err; r.readAsDataURL(blob);
  });
  const toFile = async (dataUrl, name) => new File([await (await fetch(dataUrl)).blob()], name, { type: "image/png" });

  // The side panel asks this to show whether the tab is connected.
  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    if (msg && msg.type === "tokenopt-status") reply({ version: VERSION, provider: PROVIDER });
  });

  // ---------------------------------------------------------------- composer
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
  const inComposer = (el) => { const c = composer(); return !!(c && el && (c === el || c.contains(el))); };

  // ---------------------------------------------------------------- conversation
  // Screenshot memory is per conversation: a new chat must get the full screenshot
  // again, because the model there has never seen the earlier one.
  let pending = null;   // the prompt whose reply we are still waiting for
  let confirming = false; // a send is being confirmed: the URL may be changing because of it
  let convKey = 0, lastPath = location.pathname, sentFromNewChat = false;
  function syncConversation() {
    const path = location.pathname;
    if (path === lastPath || confirming) return;
    const firstSend = !CONVERSATION.test(lastPath) && CONVERSATION.test(path) && sentFromNewChat;
    lastPath = path;
    sentFromNewChat = false;
    if (firstSend) return; // the "new chat" page just became a saved conversation: same chat
    convKey += 1;
    if (pending) pending.finish();
    send({ type: "new-conversation" });
  }
  setInterval(syncConversation, 1000);

  // ---------------------------------------------------------------- images
  // Hand files to the page the way a real paste would; fall back to its file input.
  function insertFiles(files, target) {
    const dt = new DataTransfer();
    files.forEach((f) => dt.items.add(f));
    const ev = new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true });
    const el = target && target.isConnected ? target : composer() || document.activeElement || document.body;
    el.dispatchEvent(ev);
    if (ev.defaultPrevented) return;
    const inputs = [...document.querySelectorAll('input[type="file"]')];
    const input = inputs.find((i) => i.multiple && (!i.accept || i.accept.includes("image"))) || inputs[0];
    if (input) {
      input.files = dt.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function insertText(text) {
    const el = composer();
    if (!el) return;
    el.focus();
    if (el.tagName === "TEXTAREA") {
      el.setRangeText(text + " ", el.selectionStart, el.selectionEnd, "end");
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      document.execCommand("insertText", false, text + " ");
    }
  }

  // One image file -> the engine's plan for it.
  async function optimizeFile(file, on) {
    syncConversation();
    const res = await send({
      type: "optimize", image: await readAsDataURL(file), provider: PROVIDER, name: file.name,
      dpr: window.devicePixelRatio || 1, conv: `${PAGE}-${convKey}`, commit: on,
    });
    if (!res || res.error) {
      throw new Error(alive() ? (res && res.error) || "no response from TokenOpt"
        : "TokenOpt was updated, refresh this tab");
    }
    return res;
  }
  const describe = (res, on) => {
    if (!on) return `Screenshot: ${fmt(res.full_tokens)} tokens (TokenOpt is off)`;
    if (res.mode === "duplicate") {
      return `Same screen as your previous screenshot: nothing attached (saved ${fmt(res.full_tokens)} tokens)`;
    }
    if (res.fallback) return `Screenshot: ${fmt(res.full_tokens)} tokens · original kept (no saving possible)`;
    const why = [res.mode === "delta" ? "only the changed area sent" : "",
      res.resized ? `resized to ${res.resized[0]}×${res.resized[1]}` : ""].filter(Boolean).join(" · ");
    return `Screenshot: ${fmt(res.full_tokens)} → ${fmt(res.tokens)} tokens (−${res.reduction}%)${why ? " · " + why : ""}`;
  };

  // Shared by paste, drag-and-drop and the upload button, one batch at a time.
  // `deliver(files)` hands the final files to the page.
  let chain = Promise.resolve();
  function handleImages(files, deliver) {
    const on = enabled;
    const job = async () => {
      if (!on) { // off: the originals already went through untouched; just record their cost
        for (const f of files) {
          try { toast.show(describe(await optimizeFile(f, false), false)); } catch { /* measuring only */ }
        }
        return;
      }
      toast.show("optimizing screenshot…", 0);
      const out = [], notes = [], msgs = [];
      let failed = false;
      for (const f of files) {
        try {
          const res = await optimizeFile(f, true);
          out.push(...(await Promise.all(res.images.map((im) => toFile(im.data, `tokenopt-${im.name}.png`)))));
          if (res.note) notes.push(`[${res.note}]`);
          msgs.push(describe(res, true));
        } catch (err) {
          failed = true;
          out.push(f); // fail open: the user still gets their image
          msgs.push(`${err.message} · sent the original image`);
        }
      }
      try {
        if (out.length) deliver(out);
        if (notes.length) insertText(notes.join(" "));
      } catch (err) {
        failed = true;
        msgs.push(`could not attach: ${err.message}`);
      }
      toast.show(msgs.join("\n"), failed ? 9000 : 6000, failed);
    };
    chain = chain.then(job, job);
  }
  const imagesOf = (list) => [...(list || [])].filter((f) => f && IMAGE.test(f.type || ""));

  // 1) ⌘V paste
  window.addEventListener("paste", (e) => {
    if (!e.isTrusted) return; // our own re-dispatched paste is untrusted: let it through
    const files = imagesOf([...((e.clipboardData && e.clipboardData.items) || [])]
      .filter((i) => i.kind === "file").map((i) => i.getAsFile()));
    if (!files.length) return;
    if (!enabled) { handleImages(files); return; }
    e.preventDefault();
    e.stopImmediatePropagation();
    const target = e.target;
    handleImages(files, (f) => insertFiles(f, target));
  }, true);

  // 2) drag-and-drop onto the page
  window.addEventListener("drop", (e) => {
    if (!e.isTrusted) return;
    const files = imagesOf(e.dataTransfer && e.dataTransfer.files);
    if (!files.length) return;
    if (!enabled) { handleImages(files); return; }
    e.preventDefault();
    e.stopImmediatePropagation();
    handleImages(files, (f) => insertFiles(f, composer()));
  }, true);

  // 3) the "+" / paperclip upload button (a hidden <input type="file">)
  window.addEventListener("change", (e) => {
    const input = e.target;
    if (!e.isTrusted || !(input instanceof HTMLInputElement) || input.type !== "file") return;
    const files = imagesOf(input.files);
    if (!files.length) return;
    if (!enabled) { handleImages(files); return; }
    e.stopImmediatePropagation();
    const others = [...input.files].filter((f) => !files.includes(f)); // PDFs, videos: untouched
    handleImages(files, (f) => {
      const dt = new DataTransfer();
      [...others, ...f].forEach((x) => dt.items.add(x));
      input.files = dt.files;
      input.dispatchEvent(new Event("change", { bubbles: true })); // untrusted: passes through us
    });
  }, true);

  // Removing an attachment from the chat box takes it out of the next prompt's ledger too.
  window.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("button[aria-label]");
    const m = btn && /^remove\s+(.+)$/i.exec(btn.getAttribute("aria-label"));
    if (m) send({ type: "undraft", name: m[1].trim() });
  }, true);

  // ---------------------------------------------------------------- prompt + reply
  const userCount = () => document.querySelectorAll(USER_MSG).length;

  // Text of every assistant message on the page, oldest first.
  function assistantTexts() {
    if (PROVIDER === "openai") {
      // Current ChatGPT: a screen-reader heading marks each message block.
      const heads = [...document.querySelectorAll('[data-conversation-role="assistant"]')];
      if (heads.length) {
        return heads.map((h) => [...h.parentElement.children].filter((c) => c !== h)
          .map((c) => c.innerText).join("\n").trim());
      }
      return [...document.querySelectorAll('[data-message-author-role="assistant"]')].map((el) => el.innerText.trim());
    }
    for (const sel of ["[data-is-streaming]", ".font-claude-response", ".font-claude-message",
      '[data-testid="assistant-message"]']) {
      const all = document.querySelectorAll(sel);
      if (all.length) return [...all].map((el) => el.innerText.trim());
    }
    return [];
  }

  function streaming() {
    if (document.querySelector('[data-testid="stop-button"], [data-is-streaming="true"]')) return true;
    const c = composer();
    const scope = (c && c.closest("form")) || document;
    return [...scope.querySelectorAll("button[aria-label]")]
      .some((b) => /^stop\b/i.test(b.getAttribute("aria-label")));
  }

  // Last-resort reply text when no known message markup is found: whatever new
  // text appeared in the page since the prompt was sent, minus the prompt itself.
  const threadText = () => (document.querySelector("main") || document.body).innerText;
  function threadDiff(before, prompt) {
    const after = threadText();
    let i = 0;
    while (i < before.length && i < after.length && before[i] === after[i]) i += 1;
    return after.slice(i).replace(prompt, "").replace(/^(You said:|ChatGPT said:)\s*/gm, "").trim();
  }

  // Enter or a click on Send does not always send (empty box, upload in progress,
  // reply still streaming), so wait for proof: the box emptied, a new user message
  // appeared, or streaming began.
  function maybeSent() {
    if (confirming) return;
    syncConversation();
    const text = composerText();
    const before = { users: userCount(), replies: assistantTexts().length, thread: threadText(),
      path: location.pathname, streaming: streaming() };
    confirming = true;
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      const sent = (text && composerText() === "") || userCount() > before.users
        || (!before.streaming && streaming());
      if (!sent && tries < 50) return;
      clearInterval(timer);
      if (sent && !CONVERSATION.test(before.path)) sentFromNewChat = true;
      confirming = false;
      if (!sent) return;
      if (pending) pending.finish(); // a new prompt means the previous reply is complete
      const res = await send({ type: "prompt", text, provider: PROVIDER, on: enabled, url: before.path });
      if (res && res.id) watchReply(res.id, before, text);
    }, 100);
  }

  // The reply is "done" once new assistant text exists, nothing is streaming, and
  // the text has not changed for three seconds. Gives up after ten minutes.
  function watchReply(id, before, prompt) {
    let last = "", stable = 0, ticks = 0, done = false;
    const current = () => {
      const texts = assistantTexts();
      if (!texts.length) return threadDiff(before.thread, prompt);
      return texts.length > before.replies ? texts.slice(before.replies).join("\n").trim() : "";
    };
    const finish = (text) => {
      if (done) return;
      done = true;
      clearInterval(timer);
      if (pending && pending.id === id) pending = null;
      if (text) send({ type: "reply", id, text, provider: PROVIDER });
    };
    const timer = setInterval(() => {
      ticks += 1;
      const text = current();
      stable = text && text === last && !streaming() ? stable + 1 : 0;
      last = text || last;
      if (stable >= 3) finish(text);
      else if (ticks > 600) finish(last);
    }, 1000);
    pending = { id, finish: () => finish(last) };
  }

  window.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && inComposer(e.target)) maybeSent();
  }, true);
  window.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("button");
    if (!btn) return;
    const label = `${btn.getAttribute("data-testid") || ""} ${btn.getAttribute("aria-label") || ""}`;
    if (/send/i.test(label)) maybeSent();
  }, true);
  window.addEventListener("submit", () => maybeSent(), true);

  // ---------------------------------------------------------------- toast
  const toast = (() => {
    const host = document.createElement("div");
    host.style.cssText = "position:fixed;right:20px;bottom:96px;z-index:2147483647;";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>
      .t{font:13px/1.4 -apple-system,system-ui,sans-serif;color:#e8eaed;background:#16181d;border:1px solid #2f333b;
         border-radius:12px;padding:10px 14px;max-width:340px;box-shadow:0 12px 32px rgba(0,0,0,.35)}
      .t.err{border-color:#f28b82} .k{color:#8ab4f8;font-weight:600} .m{white-space:pre-line}</style>
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
