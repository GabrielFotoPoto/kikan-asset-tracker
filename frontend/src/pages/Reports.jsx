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
