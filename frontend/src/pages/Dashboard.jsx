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
import { useAuth } from "../auth.jsx";
import { Feedback } from "../components/Notifications.jsx";

export default function Dashboard() {
  const { user } = useAuth();
  const [backup, setBackup] = useState(null);
  const [users, setUsers] = useState([]);
  const [assets, setAssets] = useState([]);
  const [besoins, setBesoins] = useState(0);
  const [anomalies, setAnomalies] = useState(0);
  const [retard, setRetard] = useState(0);
  const [err, setErr] = useState(null);

  useEffect(() => {
    Promise.all([api.get("/users"), api.get("/assets")])
      .then(([u, a]) => { setUsers(u); setAssets(a); })
      .catch((e) => setErr(e.message));
    if (user.role === "informatique") api.get("/backup/status").then(setBackup).catch(() => {});
    api.get("/stats").then((s) => setBesoins(s.besoins_a_traiter || 0)).catch(() => {});
    if (user.role === "informatique") api.get("/renouvellements?horizon_mois=0").then((r) => setRetard(r.totaux.en_retard)).catch(() => {});
    api.get("/revues/anomalies").then((r) => setAnomalies(r.count || 0)).catch(() => {});
  }, []);

  const byStatus = (s) => assets.filter((a) => a.statut === s).length;
  const sortants = users.filter((u) => u.statut === "en_depart" || u.statut === "sorti");
  // Chaque tuile mene a la liste deja filtree ; les alertes passent en rouge des qu'elles sont non nulles.
  const tuiles = [
    { cle: "users", label: "Utilisateurs", n: users.length, vers: "/utilisateurs", cible: "Ouvre Utilisateurs" },
    { cle: "actifs", label: "Actifs", n: assets.length, vers: "/materiel", cible: "Ouvre Materiel" },
    { cle: "affectes", label: "Affectes", n: byStatus("affecte"), vers: "/materiel?statut=affecte", cible: "Materiel, statut affecte" },
    { cle: "stock", label: "En stock", n: byStatus("stock"), vers: "/materiel?statut=stock", cible: "Materiel, statut stock" },
    user.role !== "rh" && { cle: "besoins", label: "Besoins a traiter", n: besoins, vers: "/besoins", cible: "Ouvre Besoins" },
    { cle: "anomalies", label: "Anomalies d'acces", n: anomalies, vers: "/revues", cible: "Ouvre Revue des acces", couleur: anomalies ? "var(--danger)" : null },
    user.role === "informatique" && { cle: "retard", label: "Echeances de renouvellement depassees", n: retard, vers: "/renouvellements", cible: "Ouvre Renouvellements", couleur: retard ? "var(--danger)" : null },
  ].filter(Boolean);

  return (
    <div>
      <h2>Tableau de bord</h2>
      <Feedback err={err} />
      {backup?.alerte && (
        <div className="card" role="alert">
          <strong>Sauvegarde a verifier.</strong>{" "}
          {backup.configure ? (backup.dernier_echec ? "La derniere tentative a echoue." : `La derniere sauvegarde reussie date de ${backup.age_heures} h.`) : "Aucune sauvegarde enregistree."}{" "}
          <Link to="/sauvegarde">Voir le detail</Link>
        </div>
      )}
      <div className="tiles">
        {tuiles.map((t) => (
          <Link key={t.cle} to={t.vers} className="card tile">
            <div className="n" style={t.couleur ? { color: t.couleur } : undefined}>{t.n}</div>
            <div className="l">{t.label}</div>
            <div className="go">{t.cible}</div>
          </Link>
        ))}
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
