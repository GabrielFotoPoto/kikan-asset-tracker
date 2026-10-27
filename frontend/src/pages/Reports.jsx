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
import { api, downloadFile } from "../api.js";

export default function Reports() {
  const [entites, setEntites] = useState([]);
  const [entiteId, setEntiteId] = useState("");
  const [data, setData] = useState({ date: "", count: 0, rows: [] });
  const [err, setErr] = useState(null);

  const query = () => (entiteId ? `&entite_id=${entiteId}` : "");
  const load = () => api.get(`/reports/holdings?format=json${query()}`).then(setData).catch((e) => setErr(e.message));
  useEffect(() => { api.get("/entites").then(setEntites); }, []);
  useEffect(() => { load(); }, [entiteId]);

  const dl = async (fmt) => {
    setErr(null);
    try {
      await downloadFile(`/reports/holdings?format=${fmt}${query()}`, `kikan-detentions.${fmt}`);
    } catch (e) { setErr(e.message); }
  };

  return (
    <div>
      <h2>Rapports - detentions a l'instant T</h2>
      {err && <p className="err">{err}</p>}
      <div className="card">
        <div className="row">
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>Filiale / entite
            <select value={entiteId} onChange={(e) => setEntiteId(e.target.value)}>
              <option value="">toutes</option>
              {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
            </select>
          </label>
          <button onClick={() => dl("csv")}>Exporter CSV</button>
          <button onClick={() => dl("pdf")}>Exporter PDF</button>
          <span className="muted">{data.count} ligne(s) - edite le {data.date}</span>
        </div>
      </div>
      <div className="card">
        <table>
          <thead><tr>
            <th>Entite</th><th>Service</th><th>Salarie</th><th>Type</th><th>Marque</th>
            <th>Modele</th><th>N serie</th><th>Remise</th>
          </tr></thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={i}>
                <td>{r.entite}</td><td>{r.service}</td><td>{r.prenom} {r.nom}</td>
                <td>{r.type}</td><td>{r.marque}</td><td>{r.modele}</td>
                <td>{r.numero_serie}</td><td>{r.date_remise}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
