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

// En-tete de colonne triable : un bouton (utilisable au clavier) dans la cellule, avec aria-sort pour les lecteurs d'ecran.
// Le tri courant (`tri`, `sens`) est garde par la page ; onTri(cle) est appele au clic.
export default function ThTri({ cle, children, tri, sens, onTri }) {
  const actif = tri === cle;
  const descend = actif && sens === "desc";
  return (
    <th aria-sort={actif ? (descend ? "descending" : "ascending") : "none"}>
      <button type="button" className="th-tri" onClick={() => onTri(cle)}
              title={actif ? (descend ? "Tri decroissant : cliquer pour revenir a l'ordre par defaut" : "Tri croissant : cliquer pour inverser") : "Trier par cette colonne"}>
        {children}
        <span className="th-fleche" aria-hidden="true">{actif ? (descend ? "▼" : "▲") : "⇕"}</span>
      </button>
    </th>
  );
}
