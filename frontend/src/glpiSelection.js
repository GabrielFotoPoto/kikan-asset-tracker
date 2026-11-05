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

// Filtrage et selection des salaries dans l'apercu d'import GLPI. Fonctions pures testees sans navigateur
// (node --test frontend/src/glpiSelection.test.js).

export const FILTRES_U_VIDES = { q: "", entite: "", sauf: false, etat: "" };
export const ETATS_IMPORT_U = ["nouveau", "correspondance", "homonyme", "incomplet", "deja_lie"];

export const sansAccent = (v) => String(v || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

export function entitesSalaries(salaries) {
  return [...new Set((salaries || []).map((u) => u.entite_glpi).filter(Boolean))].sort((x, y) => x.localeCompare(y));
}

export function filtrerSalaries(salaries, fu = FILTRES_U_VIDES) {
  const q = sansAccent(fu.q).trim();
  return (salaries || []).filter((u) => {
    if (fu.etat && u.etat_import !== fu.etat) return false;
    if (fu.entite && ((u.entite_glpi || "") === fu.entite) === fu.sauf) return false;
    return !q || sansAccent([u.login, u.prenom, u.nom, u.email, u.matricule].join(" ")).includes(q);
  });
}

// Cocher en masse : seuls les salaries importables non homonymes sont coches (un homonyme exige un choix explicite).
// Decocher : retire aussi les homonymes affiches et remet leur choix a "" ("Ne pas importer").
export function cocherSalaries(pickU, homonyme, visibles, valeur) {
  const nextPick = { ...pickU };
  const nextHom = { ...homonyme };
  if (valeur) {
    visibles.filter((u) => u.importable && u.etat_import !== "homonyme").forEach((u) => {
      nextPick[u.externe_id] = true;
    });
  } else {
    visibles.forEach((u) => {
      nextPick[u.externe_id] = false;
      if (u.etat_import === "homonyme" && u.externe_id in nextHom) nextHom[u.externe_id] = "";
    });
  }
  return { pickU: nextPick, homonyme: nextHom };
}

export function toutDecocherSalaries() {
  return { pickU: {}, homonyme: {} };
}
