/*
 * Kikan - suivi des actifs et remise de materiel signee
 * Copyright (C) 2026 Gabriel Chollet
 * Developpe avec l'assistance d'une IA (Claude, Anthropic).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

const BASE = "/api";

// La session est un cookie HttpOnly pose par l'API : le JavaScript ne voit jamais le jeton (une faille XSS ne peut pas le voler).
// Seul un indicateur NON secret est gardé, pour ne pas interroger /auth/me (et provoquer un 401 journalise) a chaque
// visite d'un utilisateur deconnecte. Le serveur reste seul juge de la validite de la session.
const SESSION_HINT = "kikan_session";
try { localStorage.removeItem("kikan_token"); } catch { /* ignore */ }  // ancien stockage du jeton : purge

export function hasSession() {
  try { return localStorage.getItem(SESSION_HINT) === "1"; } catch { return false; }
}
export function setSession(on) {
  try { on ? localStorage.setItem(SESSION_HINT, "1") : localStorage.removeItem(SESSION_HINT); } catch { /* ignore */ }
}

// En-tete obligatoire sur toute requete qui modifie quand la session passe par le cookie (protection CSRF : un site tiers
// ne peut pas l'ajouter sans autorisation CORS, que l'API n'accorde pas).
const CSRF = { "X-Kikan-Request": "1" };

// Ferme la session : le serveur efface le cookie.
export async function endSession() {
  setSession(false);
  try { await fetch(BASE + "/auth/logout", { method: "POST", headers: CSRF }); } catch { /* ignore */ }
}

async function req(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...CSRF, ...(opts.headers || {}) };

  const res = await fetch(BASE + path, { ...opts, headers });

  if (res.status === 401) {
    setSession(false);
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
  const headers = { ...CSRF };
  const res = await fetch(BASE + path, { headers });
  if (res.status === 401) {
    setSession(false);
    window.dispatchEvent(new Event("kikan-unauth"));
    throw new Error("Session expiree, reconnectez-vous.");
  }
  if (!res.ok) throw new Error((await res.text()) || `Erreur ${res.status}`);
  const blob = await res.blob();
  // Le nom propose par le serveur (en-tete Content-Disposition) prime sur le nom par defaut de l'appelant.
  const served = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1];
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = served || filename || "telechargement";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Depot de fichier (multipart) : le navigateur fixe lui-meme le type de contenu et la separation.
export async function postForm(path, form) {
  const headers = { ...CSRF };
  const res = await fetch(BASE + path, { method: "POST", headers, body: form });
  if (res.status === 401) {
    setSession(false);
    window.dispatchEvent(new Event("kikan-unauth"));
    throw new Error("Session expiree, reconnectez-vous.");
  }
  if (!res.ok) throw new Error((await res.text()) || `Erreur ${res.status}`);
  return res.json();
}

// Image protegee par la session, renvoyee sous forme d'URL data: (la CSP n'autorise pas blob:).
export async function fetchDataUrl(path) {
  const headers = { ...CSRF };
  const res = await fetch(BASE + path, { headers });
  if (!res.ok) throw new Error((await res.text()) || `Erreur ${res.status}`);
  const blob = await res.blob();
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(new Error("Lecture de l'image impossible"));
    r.readAsDataURL(blob);
  });
}

// Message lisible a partir d'une erreur de l'API ({"detail": "..."}).
export function errorText(ex) {
  try {
    const d = JSON.parse(ex.message).detail;
    return typeof d === "string" ? d : ex.message;
  } catch { return ex.message; }
}

export const api = {
  get: (p) => req(p),
  post: (p, b) => req(p, { method: "POST", body: JSON.stringify(b) }),
  put: (p, b) => req(p, { method: "PUT", body: JSON.stringify(b) }),
  del: (p) => req(p, { method: "DELETE" }),
};
