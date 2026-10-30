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

// Icone de l'application (Parametrage, Apparence) : adresse de l'image, favicon, rafraichissement apres changement.
import { useEffect, useState } from "react";
import { api } from "./api.js";

export const iconUrl = (hash) => (hash ? `/api/branding/icone?v=${hash}` : null);

// Declenche le rechargement de l'icone partout (apres un depot ou une suppression).
export const brandingChanged = () => window.dispatchEvent(new Event("kikan-branding"));

// Adresse de l'icone (ou null) ; met aussi a jour l'icone de l'onglet du navigateur.
export function useBranding() {
  const [hash, setHash] = useState(null);
  useEffect(() => {
    const load = () => api.get("/branding").then((b) => setHash(b.icone || null)).catch(() => {});
    load();
    window.addEventListener("kikan-branding", load);
    return () => window.removeEventListener("kikan-branding", load);
  }, []);
  useEffect(() => {
    let link = document.querySelector("link[rel='icon']");
    if (!hash) { if (link) link.remove(); return; }
    if (!link) { link = document.createElement("link"); link.rel = "icon"; document.head.appendChild(link); }
    link.type = "image/png";
    link.href = iconUrl(hash);
  }, [hash]);
  return iconUrl(hash);
}
