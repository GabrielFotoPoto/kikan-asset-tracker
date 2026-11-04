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

// Composants visuels partages entre le parcours d'arrivee (/arrivee/:id) et le parcours de depart (/depart/:id).
import { QUI_LIBELLES, formaterQuand, peutAgir, resumeParcours } from "../parcours.js";

export { QUI_LIBELLES, formaterQuand, peutAgir, resumeParcours };

export function PastilleParcours({ etapes, etapeCourante, reserves }) {
  const r = resumeParcours(etapes, etapeCourante, reserves);
  return <span className={r.classe}>{r.texte}</span>;
}

export function EtapesParcours({ etapes = [], etapeCourante = null }) {
  const cols = etapes.length === 6 ? "etapes etapes-6" : "etapes";
  return (
    <ol className={cols} aria-label="Avancement du parcours">
      {etapes.map((e, i) => {
        const courante = e.cle === etapeCourante;
        const puce = e.etat === "fait" ? "\u2713" : e.etat === "sans_objet" ? "-" : i + 1;
        return (
          <li
            key={e.cle}
            className={`etape ${e.etat}${courante ? " courante" : ""}`}
            aria-current={courante ? "step" : undefined}
          >
            <span className="etape-puce" aria-hidden="true">{puce}</span>
            <strong>{e.titre}</strong>
            <span className="muted">{QUI_LIBELLES[e.qui] || e.qui}</span>
            <span className={e.retard_jours ? "etape-detail err" : "etape-detail"}>{e.detail}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function JournalParcours({ journal = [] }) {
  return (
    <div className="card">
      <h3>Journal du parcours</h3>
      {journal.length === 0 ? <p className="muted">Rien pour l'instant.</p> : (
        <ol className="journal">
          {journal.map((j, i) => (
            <li key={i}>
              <span className="muted">{formaterQuand(j.quand)}</span>
              <span>{j.texte}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function EncartProchaineAction({
  action,
  role,
  libellesBouton = {},
  onNaviguer,
  messageAttente = null,
  texteTermine = "Le parcours est termine.",
  reserves = [],
}) {
  const libQui = action ? (QUI_LIBELLES[action.qui] || action.qui) : "";
  const autorise = action ? peutAgir(action, role) : false;
  return (
    <div className="card action-suivante" role="region" aria-label="Prochaine action">
      {action ? (
        <>
          <span><strong>Prochaine action ({libQui}) :</strong> {action.texte}</span>
          {autorise ? (
            <button type="button" onClick={() => onNaviguer(action.vers)}>
              {libellesBouton[action.etape] || "Ouvrir"}
            </button>
          ) : (
            <span className="muted">En attente de {libQui}.</span>
          )}
        </>
      ) : messageAttente ? (
        <span><strong>En attente :</strong> {messageAttente}</span>
      ) : reserves && reserves.length > 0 ? (
        <span><strong>Parcours termine avec reserve :</strong> {reserves.join(" - ")}.</span>
      ) : (
        <span><strong>Le parcours est termine :</strong> {texteTermine}</span>
      )}
    </div>
  );
}
