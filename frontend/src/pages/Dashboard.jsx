import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Dashboard() {
  const [users, setUsers] = useState([]);
  const [assets, setAssets] = useState([]);
  const [err, setErr] = useState(null);

  useEffect(() => {
    Promise.all([api.get("/users"), api.get("/assets")])
      .then(([u, a]) => { setUsers(u); setAssets(a); })
      .catch((e) => setErr(e.message));
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
