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

import { Link, useLocation } from "react-router-dom";
import { fil } from "../nav.js";

// Fil d'Ariane : Accueil, section, page. La derniere entree est la page courante (aria-current).
export default function Breadcrumb() {
  const { pathname } = useLocation();
  const miettes = fil(pathname);
  if (pathname === "/" || !miettes.length) return null; // le tableau de bord n'a pas de fil : son titre suffit
  return (
    <nav aria-label="Fil d'Ariane" className="fil">
      <Link to="/">Accueil</Link><span aria-hidden="true">/</span>
      {miettes.map((m, i) => {
        const derniere = i === miettes.length - 1;
        return (
          <span key={m.label} className="fil-item">
            {m.to && !derniere ? <Link to={m.to}>{m.label}</Link> : <span aria-current={derniere ? "page" : undefined}>{m.label}</span>}
            {!derniere && <span aria-hidden="true">/</span>}
          </span>
        );
      })}
    </nav>
  );
}
