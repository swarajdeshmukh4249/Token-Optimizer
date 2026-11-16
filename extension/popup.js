const $ = (id) => document.getElementById(id);
const fmt = (n) => n.toLocaleString("en-US");

chrome.storage.local.get({ enabled: true }, (v) => ($("enabled").checked = v.enabled));
$("enabled").onchange = (e) => chrome.storage.local.set({ enabled: e.target.checked });

chrome.runtime.sendMessage({ type: "ping" }, (r) => {
  const ok = r && r.ok;
  $("dot").className = "dot " + (ok ? "ok" : "bad");
  $("status").innerHTML = ok ? "Local engine running on 127.0.0.1:8420"
    : "Engine not running. Start it with <code>.venv/bin/python web/server.py</code>";
});

function run(file) {
  if (!file || !file.type.startsWith("image/")) return;
  $("result").innerHTML = `<div class="big">Optimizing…</div>`;
  const reader = new FileReader();
  reader.onload = () => chrome.runtime.sendMessage(
    { type: "optimize", image: reader.result, provider: $("provider").value, session: "popup" },
    (res) => {
      if (!res || res.error) { $("result").innerHTML = `<p class="muted">${(res && res.error) || "No response"}</p>`; return; }
      const links = res.images.map((im) =>
        `<a href="${im.data}" download="tokenopt-${im.name}.png" title="${im.name} · ${im.width}×${im.height} · ${im.tokens} tokens"><img src="${im.data}"></a>`).join("");
      $("result").innerHTML = `
        <div class="big"><s>${fmt(res.full_tokens)}</s> → ${fmt(res.tokens)} <span class="pct">${res.fallback ? "" : "−" + res.reduction + "%"}</span></div>
        <div class="muted">${res.mode}${res.fallback ? " · original kept" : ""} · ${res.ms} ms · estimate from ${res.formula}</div>
        <div class="thumbs">${links}</div>
        ${res.note ? `<p class="muted">${res.note}</p>` : ""}`;
    });
  reader.readAsDataURL(file);
}

$("drop").onclick = () => $("file").click();
$("file").onchange = (e) => run(e.target.files[0]);
document.addEventListener("paste", (e) => {
  const it = [...e.clipboardData.items].find((i) => i.kind === "file" && i.type.startsWith("image/"));
  if (it) run(it.getAsFile());
});
