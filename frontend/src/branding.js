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

// Icone de l'application : logo Kikan par defaut, remplace par l'icone deposee (Parametrage, Apparence) quand il y en a une.
import { useEffect, useState } from "react";
import { api } from "./api.js";

export const ICONE_DEFAUT = "/icon-192.png";
export const iconUrl = (hash) => (hash ? `/api/branding/icone?v=${hash}` : null);

// Declenche le rechargement de l'icone partout (apres un depot ou une suppression).
export const brandingChanged = () => window.dispatchEvent(new Event("kikan-branding"));

// Remplace les icones d'onglet et d'ecran d'accueil par l'icone personnalisee, ou remet celles du produit.
function appliquerFavicons(url) {
  document.querySelectorAll("link[rel='icon'], link[rel='apple-touch-icon']").forEach((l) => {
    if (!l.dataset.defaut) l.dataset.defaut = JSON.stringify({ href: l.getAttribute("href"), type: l.getAttribute("type"), sizes: l.getAttribute("sizes") });
    const d = JSON.parse(l.dataset.defaut);
    const set = (k, v) => (v ? l.setAttribute(k, v) : l.removeAttribute(k));
    if (url) { set("href", url); set("type", "image/png"); l.removeAttribute("sizes"); } else { set("href", d.href); set("type", d.type); set("sizes", d.sizes); }
  });
}

// Adresse de l'icone a afficher (personnalisee, sinon le logo Kikan) ; met aussi a jour l'icone de l'onglet.
export function useBranding() {
  const [hash, setHash] = useState(null);
  useEffect(() => {
    const load = () => api.get("/branding").then((b) => setHash(b.icone || null)).catch(() => {});
    load();
    window.addEventListener("kikan-branding", load);
    return () => window.removeEventListener("kikan-branding", load);
  }, []);
  useEffect(() => { appliquerFavicons(iconUrl(hash)); }, [hash]);
  return iconUrl(hash) || ICONE_DEFAUT;
}
