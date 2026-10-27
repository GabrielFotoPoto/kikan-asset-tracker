const BASE = "/api";
const TOKEN_KEY = "kikan_token";

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

async function req(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(BASE + path, { ...opts, headers });

  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("kikan-unauth"));
    throw new Error("Session expiree, reconnectez-vous.");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Erreur ${res.status}`);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res;
}

export async function downloadFile(path, filename) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(BASE + path, { headers });
  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("kikan-unauth"));
    throw new Error("Session expiree, reconnectez-vous.");
  }
  if (!res.ok) throw new Error((await res.text()) || `Erreur ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "telechargement";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  get: (p) => req(p),
  post: (p, b) => req(p, { method: "POST", body: JSON.stringify(b) }),
  put: (p, b) => req(p, { method: "PUT", body: JSON.stringify(b) }),
  del: (p) => req(p, { method: "DELETE" }),
};
