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
import { Link } from "react-router-dom";
import { api } from "../api.js";

export default function Dashboard() {
  const [users, setUsers] = useState([]);
  const [assets, setAssets] = useState([]);
  const [besoins, setBesoins] = useState(0);
  const [err, setErr] = useState(null);

  useEffect(() => {
    Promise.all([api.get("/users"), api.get("/assets")])
      .then(([u, a]) => { setUsers(u); setAssets(a); })
      .catch((e) => setErr(e.message));
    api.get("/stats").then((s) => setBesoins(s.besoins_a_traiter || 0)).catch(() => {});
  }, []);

  const byStatus = (s) => assets.filter((a) => a.statut === s).length;
  const sortants = users.filter((u) => u.statut === "en_depart" || u.statut === "sorti");

  return (
    <div>
      <h2>Tableau de bord</h2>
      {err && <p className="err">{err}</p>}
      <div className="tiles">
        <div className="card tile"><div className="n">{users.length}</div><div className="l">Utilisateurs</div></div>
        <div className="card tile"><div className="n">{assets.length}</div><div className="l">Actifs</div></div>
        <div className="card tile"><div className="n">{byStatus("affecte")}</div><div className="l">Affectes</div></div>
        <div className="card tile"><div className="n">{byStatus("stock")}</div><div className="l">En stock</div></div>
        <Link to="/besoins" className="card tile" style={{ textDecoration: "none", color: "inherit" }}><div className="n">{besoins}</div><div className="l">Besoins a traiter</div></Link>
      </div>

      <div className="card">
        <h3>Departs a suivre</h3>
        {sortants.length === 0 ? (
          <p className="muted">Aucun depart en cours.</p>
        ) : (
          <table>
            <thead><tr><th>Salarie</th><th>Statut</th><th>Date de sortie</th></tr></thead>
            <tbody>
              {sortants.map((u) => (
                <tr key={u.id}>
                  <td>{u.prenom} {u.nom}</td>
                  <td><span className="badge">{u.statut}</span></td>
                  <td>{u.date_sortie || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
