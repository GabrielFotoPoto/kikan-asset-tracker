import { useEffect, useState } from "react";
import { api } from "../api.js";

function Bars({ items, label, value }) {
  const max = Math.max(1, ...items.map((i) => i[value]));
  return (
    <table>
      <tbody>
        {items.map((it, idx) => (
          <tr key={idx}>
            <td style={{ width: "45%" }}>{label(it)}</td>
            <td>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ height: 14, width: `${(it[value] / max) * 100}%`, minWidth: 2, background: "var(--brand)", borderRadius: 3 }} />
                <span className="muted">{it[value]}</span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Stats() {
  const [s, setS] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api.get("/stats").then(setS).catch((e) => setErr(e.message)); }, []);

  if (err) return <div><h2>Statistiques</h2><p className="err">{err}</p></div>;
  if (!s) return <div><h2>Statistiques</h2><p className="muted">Chargement...</p></div>;

  return (
    <div>
      <h2>Statistiques du parc</h2>
      <div className="tiles">
        <div className="card tile"><div className="n">{s.actifs_total}</div><div className="l">Actifs au total</div></div>
        <div className="card tile"><div className="n">{s.taux_equipement.pourcentage}%</div><div className="l">Salaries actifs equipes</div></div>
        <div className="card tile"><div className="n">{s.age_moyen_annees ?? "-"}</div><div className="l">Age moyen du parc (ans)</div></div>
        <div className="card tile"><div className="n">{s.renouvellements_12m.count}</div><div className="l">Renouvellements sous 12 mois</div></div>
      </div>

      <div className="card">
        <h3>Modeles les plus distribues</h3>
        {s.top_modeles.length === 0 ? <p className="muted">Aucun actif affecte.</p> :
          <Bars items={s.top_modeles} value="count" label={(i) => `${i.type} ${i.marque} ${i.modele}`} />}
      </div>

      <div className="card">
        <h3>Repartition par entite</h3>
        {s.par_entite.length === 0 ? <p className="muted">-</p> :
          <Bars items={s.par_entite} value="count" label={(i) => i.entite} />}
      </div>

      <div className="card">
        <h3>Repartition par service</h3>
        {s.par_service.length === 0 ? <p className="muted">-</p> :
          <Bars items={s.par_service} value="count" label={(i) => i.service} />}
      </div>

      <div className="card">
        <h3>Renouvellements a venir (12 mois)</h3>
        {s.renouvellements_12m.count === 0 ? <p className="muted">Aucun.</p> : (
          <table>
            <thead><tr><th>Id interne</th><th>Type</th><th>Marque</th><th>Modele</th><th>Echeance</th></tr></thead>
            <tbody>
              {s.renouvellements_12m.items.map((r) => (
                <tr key={r.id}>
                  <td>{r.identifiant_interne || "-"}</td><td>{r.type}</td>
                  <td>{r.marque}</td><td>{r.modele}</td><td>{r.echeance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
