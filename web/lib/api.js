// Thin wrappers around the local Python API (web/server.py).
async function apiRequest(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data;
  try {
    data = await res.json();
  } catch (e) {
    throw new Error(`Server returned ${res.status}. Is web/server.py running?`);
  }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function fmtInt(n) {
  return n == null ? "-" : Number(n).toLocaleString();
}

function fmtDb(x) {
  return x == null ? "lossless" : `${Number(x).toFixed(1)} dB`;
}
