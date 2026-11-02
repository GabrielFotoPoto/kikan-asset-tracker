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

import { TAILLES, pagesAffichees } from "../tableau.js";

// Barre de pagination d'une liste : plage affichee, nombre de lignes par page, precedent / numeros / suivant.
// `pag` vient de paginer() (tableau.js) ; la page courante et la taille sont gardees par la page, dans l'adresse.
export default function Pagination({ pag, taille, onPage, onTaille, objet = "resultat(s)" }) {
  if (pag.total === 0) return null;
  return (
    <div className="pagination">
      <p className="muted" role="status">
        <strong>{pag.de}-{pag.a}</strong> sur {pag.total} {objet}
      </p>
      <label className="pagination-taille">Lignes par page
        <select value={taille} onChange={(e) => onTaille(Number(e.target.value))}>
          {TAILLES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </label>
      {pag.pages > 1 && (
        <nav aria-label="Pagination">
          <ul>
            <li>
              <button type="button" className="ghost" disabled={pag.page <= 1} onClick={() => onPage(pag.page - 1)}>
                <span aria-hidden="true">{"‹"} </span>Precedent
              </button>
            </li>
            {pagesAffichees(pag.page, pag.pages).map((n, i) => (
              <li key={`${n}-${i}`}>
                {n === "…"
                  ? <span className="pagination-trou" aria-hidden="true">{n}</span>
                  : (
                    <button type="button" className={n === pag.page ? undefined : "ghost"}
                            aria-current={n === pag.page ? "page" : undefined}
                            aria-label={`Page ${n}`} onClick={() => onPage(n)}>{n}</button>
                  )}
              </li>
            ))}
            <li>
              <button type="button" className="ghost" disabled={pag.page >= pag.pages} onClick={() => onPage(pag.page + 1)}>
                Suivant<span aria-hidden="true"> {"›"}</span>
              </button>
            </li>
          </ul>
        </nav>
      )}
    </div>
  );
}
