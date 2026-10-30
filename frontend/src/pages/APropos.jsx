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

import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function APropos() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api.get("/apropos").then(setD).catch((e) => setErr(e.message)); }, []);

  if (err) return <div><h2>A propos</h2><p className="err">{err}</p></div>;
  if (!d) return <div><h2>A propos</h2><p className="muted">Chargement...</p></div>;

  return (
    <div>
      <h2>A propos de {d.application}</h2>

      <div className="card">
        <h3>Version</h3>
        {d.developpement ? (
          <p><strong>Version de developpement</strong>{" "}
            <span className="muted">(construction locale : le numero de version n'est renseigne que sur les images publiees)</span></p>
        ) : (
          <p><strong>{d.version}</strong>{d.date_publication && <span className="muted"> - publiee le {d.date_publication}</span>}</p>
        )}
        <p>
          {d.liens.version && <><a href={d.liens.version} target="_blank" rel="noopener noreferrer">Notes de cette version</a> - </>}
          <a href={d.liens.journal} target="_blank" rel="noopener noreferrer">Historique des changements</a>
        </p>
        <p className="muted">Python {d.python}</p>
      </div>

      <div className="card">
        <h3>Licence et auteur</h3>
        <p>{d.copyright}.</p>
        <p>
          Logiciel libre distribue sous licence <strong>{d.licence.nom}</strong>.{" "}
          <a href={d.licence.texte} target="_blank" rel="noopener noreferrer">Texte de la licence</a>
        </p>
        <p className="muted">Ce programme est distribue dans l'espoir qu'il sera utile, mais SANS AUCUNE GARANTIE. {d.ia}</p>
        <p>
          <a href={d.liens.depot} target="_blank" rel="noopener noreferrer">Code source sur GitHub</a> -{" "}
          <a href={d.liens.problemes} target="_blank" rel="noopener noreferrer">Signaler un probleme</a>
        </p>
      </div>

      <div className="card">
        <h3>Composants et licences tierces</h3>
        <table>
          <thead><tr><th>Composant</th><th>Role</th><th>Version</th><th>Licence</th></tr></thead>
          <tbody>
            {d.composants.map((c) => (
              <tr key={c.nom}><td>{c.nom}</td><td>{c.role}</td><td>{c.version || "-"}</td><td>{c.licence}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
