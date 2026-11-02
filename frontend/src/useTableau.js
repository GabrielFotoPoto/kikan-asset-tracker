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

import { useState } from "react";
import { TAILLES, memoriserTaille, tailleMemorisee, tailleParDefaut } from "./tableau.js";

// Etat de tri et de pagination d'une liste, garde dans l'adresse (tri, sens, taille, page) : retour arriere et lien copie
// conservent la vue, et les valeurs inconnues de l'adresse sont ignorees. La page passe ses parametres d'adresse
// (useSearchParams) et la liste de ses colonnes triables [[cle, libelle], ...] ; elle garde la main sur ses autres parametres.
export function useTableau(params, setParams, colonnes) {
  const tri = colonnes.some(([c]) => c === params.get("tri")) ? params.get("tri") : "";
  const sens = params.get("sens") === "desc" ? "desc" : "asc";
  // Nombre de lignes : choix dans l'adresse, sinon dernier choix memorise, sinon valeur adaptee a l'ecran.
  const [tailleAuto] = useState(() => tailleMemorisee() || tailleParDefaut());
  const taille = TAILLES.includes(Number(params.get("taille"))) ? Number(params.get("taille")) : tailleAuto;
  const page = Number(params.get("page")) || 1;

  // Forme fonctionnelle : une mise a jour differee (frappe) ne ramene pas un autre parametre a son ancienne valeur.
  // Tout changement de filtre, de tri ou de taille ramene a la premiere page ; seul un changement de page la conserve.
  const setParam = (cle, valeur) => setParams((prev) => {
    const p = new URLSearchParams(prev);
    if (valeur) p.set(cle, valeur); else p.delete(cle);
    if (cle !== "page") p.delete("page");
    return p;
  }, { replace: true });

  // Clic sur un en-tete : croissant, puis decroissant, puis retour a l'ordre par defaut.
  const changerTri = (cle) => setParams((prev) => {
    const p = new URLSearchParams(prev);
    p.delete("page");
    if (tri !== cle) { p.set("tri", cle); p.set("sens", "asc"); }
    else if (sens === "asc") p.set("sens", "desc");
    else { p.delete("tri"); p.delete("sens"); }
    return p;
  }, { replace: true });
  // Sur petit ecran (cartes, sans en-tetes) : menu de tri et bouton de sens.
  const choisirTri = (cle) => setParams((prev) => {
    const p = new URLSearchParams(prev);
    p.delete("page");
    if (cle) { p.set("tri", cle); if (!p.get("sens")) p.set("sens", "asc"); } else { p.delete("tri"); p.delete("sens"); }
    return p;
  }, { replace: true });
  const inverserSens = () => setParam("sens", sens === "asc" ? "desc" : "asc");
  const changerTaille = (n) => { memoriserTaille(n); setParam("taille", String(n)); };
  const changerPage = (n) => setParam("page", n > 1 ? String(n) : "");

  return { tri, sens, taille, page, setParam, changerTri, choisirTri, inverserSens, changerTaille, changerPage };
}
