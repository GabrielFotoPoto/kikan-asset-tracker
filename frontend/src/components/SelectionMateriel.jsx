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

import { useMemo, useState } from "react";
import { fold } from "../tableau.js";

const PAS = 20;

const libelle = (a) => [a.type, a.marque, a.modele].filter(Boolean).join(" ") || "Materiel";
const serie = (a) => a.numero_serie || a.identifiant_interne || a.id;

// Liste de materiel a cocher (remise, renouvellement) : une recherche, 20 lignes a la fois ("Afficher plus"), et la selection
// toujours visible en haut, meme si la recherche ou la limite la masquerait. Les derniers ajoutes viennent en premier.
// `choisis` : identifiants coches ; `onBasculer(id)` coche ou decoche ; `onVider()` (facultatif) decoche tout.
export default function SelectionMateriel({ items, choisis, onBasculer, onVider }) {
  const [recherche, setRecherche] = useState("");
  const [limite, setLimite] = useState(PAS);
  const termes = fold(recherche).split(/\s+/).filter(Boolean);

  const selection = useMemo(() => items.filter((a) => choisis.includes(a.id)), [items, choisis]);
  const trouves = useMemo(() => {
    const t = fold(recherche).split(/\s+/).filter(Boolean);
    return items
      .filter((a) => !choisis.includes(a.id))
      .filter((a) => !t.length || t.every((x) => fold([a.type, a.marque, a.modele, a.numero_serie, a.identifiant_interne].filter(Boolean).join(" ")).includes(x)))
      .sort((a, b) => b.id - a.id);
  }, [items, choisis, recherche]);
  const montres = trouves.slice(0, limite);

  const ligne = (a) => (
    <label key={a.id} className="check" style={{ marginBottom: 4 }}>
      <input type="checkbox" checked={choisis.includes(a.id)} onChange={() => onBasculer(a.id)} />
      <span>{libelle(a)} <span className="muted">({serie(a)})</span></span>
    </label>
  );

  return (
    <div>
      <input style={{ width: "100%" }} type="search" value={recherche} placeholder="Rechercher (type, marque, modele, serie...)"
             aria-label="Rechercher dans le materiel en stock"
             onChange={(e) => { setRecherche(e.target.value); setLimite(PAS); }} />
      {selection.length > 0 && (
        <div style={{ margin: "10px 0" }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>Selection : {selection.length}</strong>
            {onVider && <button type="button" className="ghost" onClick={onVider}>Tout deselectionner</button>}
          </div>
          {selection.map(ligne)}
        </div>
      )}
      {items.length === 0 && <p className="muted">Aucun materiel en stock.</p>}
      {items.length > 0 && trouves.length === 0 && (
        <p className="muted">{termes.length ? "Aucun materiel ne correspond a cette recherche." : "Tout le materiel en stock est deja selectionne."}</p>
      )}
      {montres.map(ligne)}
      {trouves.length > 0 && (
        <div className="row" style={{ marginTop: 8 }}>
          <span className="muted" role="status">{montres.length} sur {trouves.length} materiel(s) en stock{termes.length ? " (recherche)" : ""}</span>
          {trouves.length > montres.length && (
            <button type="button" className="ghost" onClick={() => setLimite((n) => n + PAS)}>
              Afficher {Math.min(PAS, trouves.length - montres.length)} de plus
            </button>
          )}
        </div>
      )}
    </div>
  );
}
