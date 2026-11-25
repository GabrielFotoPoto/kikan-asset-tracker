/*
 * Kikan - suivi des actifs et remise de materiel signee
 * Copyright (C) 2026 Gabriel Chollet
 * Developpe avec l'assistance d'une IA (Gemini, Google DeepMind).
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
import { Link } from "react-router-dom";
import { api, errorText } from "../api.js";
import { Feedback } from "../components/Notifications.jsx";
import { Empty, Loading } from "../components/State.jsx";
import { formaterDateHeure } from "../format.js";

export default function MonMateriel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.get("/mon-espace/materiel")
      .then((r) => setItems(r || []))
      .catch((e) => setErr(errorText(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h2>Mon materiel</h2>
      <p className="muted">Liste en lecture seule du materiel qui vous est actuellement affecte.</p>
      <Feedback err={err} />
      <div className="card">
        {loading ? <Loading /> : items.length === 0 ? <Empty message="Aucun materiel ne vous est affecte." /> : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Type</th><th>Marque et modele</th><th>Identifiant</th><th>Date de remise</th><th></th></tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id}>
                    <td>{a.type}</td>
                    <td><strong>{a.marque} {a.modele}</strong></td>
                    <td>{a.identifiant_interne || a.numero_serie || "-"}</td>
                    <td>{formaterDateHeure(a.date_remise)}</td>
                    <td><Link to={`/mes-tickets?nouveau=1&asset=${a.id}`}>Signaler un probleme</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
