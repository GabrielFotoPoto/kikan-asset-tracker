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

// Tri et pagination des listes, cote navigateur. Fonctions pures : elles se testent sans navigateur
// (node --test frontend/src/tableau.test.js).

export const TAILLES = [10, 20, 50];
export const TAILLE_DEFAUT = 20;

// Nombre de lignes par defaut selon l'ecran, evalue une fois a l'ouverture de la page (pas a chaque
// redimensionnement : l'affichage ne doit pas sauter). Petit ecran : des cartes hautes, donc peu de lignes.
// Le choix explicite de l'utilisateur (adresse, puis memoire du navigateur) l'emporte toujours.
export function tailleParDefaut(correspond = (q) => typeof window !== "undefined" && window.matchMedia(q).matches) {
  if (correspond("(max-width: 720px)")) return 10;
  if (correspond("(min-width: 1400px) and (min-height: 1000px)")) return 50;
  return TAILLE_DEFAUT;
}

// Derniere taille choisie par l'utilisateur, gardee dans ce navigateur (confort : jamais indispensable, d'ou les try/catch).
const CLE_TAILLE = "kikan.lignes-par-page";
export function tailleMemorisee() {
  try {
    const n = Number(window.localStorage.getItem(CLE_TAILLE));
    return TAILLES.includes(n) ? n : null;
  } catch { return null; }
}
export function memoriserTaille(n) {
  try { window.localStorage.setItem(CLE_TAILLE, String(n)); } catch { /* navigation privee ou stockage bloque */ }
}

// Comparaison francaise, insensible a la casse et aux accents, avec les nombres compares comme des nombres
// (PC-2 avant PC-10).
const collator = new Intl.Collator("fr", { numeric: true, sensitivity: "base" });

const vide = (v) => v === null || v === undefined || String(v).trim() === "";

// Recherche sans accent ni casse : "Ecran" trouve "Écran".
export const fold = (v) => (v || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

// Trie sans modifier la liste. Les valeurs vides vont toujours en fin de liste, croissant ou decroissant ;
// a valeur egale, l'ordre d'ajout (id) departage, pour qu'un tri soit stable d'un affichage a l'autre.
export function trier(items, cle, sens = "asc") {
  const dir = sens === "desc" ? -1 : 1;
  return [...items].sort((a, b) => {
    const va = a[cle];
    const vb = b[cle];
    if (vide(va) !== vide(vb)) return vide(va) ? 1 : -1;
    const ordre = vide(va) ? 0
      : typeof va === "number" && typeof vb === "number" ? va - vb
      : collator.compare(String(va), String(vb));
    return ordre * dir || (a.id ?? 0) - (b.id ?? 0);
  });
}

// Decoupe une liste en pages. Une page hors limites (liste raccourcie par un filtre ou une suppression)
// est ramenee dans les limites : on ne tombe jamais sur une page vide.
export function paginer(items, page, taille = TAILLE_DEFAUT) {
  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / taille));
  const courante = Math.min(Math.max(1, Math.floor(page) || 1), pages);
  const debut = (courante - 1) * taille;
  const tranche = items.slice(debut, debut + taille);
  return { tranche, total, pages, page: courante, de: total ? debut + 1 : 0, a: debut + tranche.length };
}

// Numeros de pages a afficher : premiere, derniere, la page courante et ses voisines, "…" pour les trous.
export function pagesAffichees(page, pages) {
  const voulues = new Set([1, pages, page - 1, page, page + 1]);
  const nums = [...voulues].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  const out = [];
  nums.forEach((n, i) => {
    if (i > 0 && n - nums[i - 1] === 2) out.push(n - 1);
    else if (i > 0 && n - nums[i - 1] > 2) out.push("…");
    out.push(n);
  });
  return out;
}
