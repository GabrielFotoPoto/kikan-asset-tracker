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
import { Feedback } from "../components/Notifications.jsx";
import { ErrorState, Loading } from "../components/State.jsx";

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
  const [entites, setEntites] = useState([]);
  const [entiteId, setEntiteId] = useState("");
  const [du, setDu] = useState("");
  const [au, setAu] = useState("");

  const query = (fmt) => {
    const p = new URLSearchParams({ format: fmt });
    if (entiteId) p.set("entite_id", entiteId);
    if (du) p.set("du", du);
    if (au) p.set("au", au);
    return `/stats?${p}`;
  };
  useEffect(() => { api.get("/entites").then(setEntites).catch(() => {}); }, []);
  useEffect(() => {
    setErr(null);
    api.get(query("json")).then(setS).catch((e) => setErr(e.message));
  }, [entiteId, du, au]);

  const dl = async (fmt) => {
    setErr(null);
    try { await downloadFile(query(fmt), `kikan-statistiques.${fmt}`); } catch (e) { setErr(e.message); }
  };

  const filtres = (
    <div className="card">
      <div className="row">
        <label>Filiale / entite (sous-entites incluses)
          <select value={entiteId} onChange={(e) => setEntiteId(e.target.value)}>
            <option value="">toutes</option>
            {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
          </select>
        </label>
        <label>Periode : du
          <input type="date" value={du} max={au || undefined} onChange={(e) => setDu(e.target.value)} />
        </label>
        <label>au
          <input type="date" value={au} min={du || undefined} onChange={(e) => setAu(e.target.value)} />
        </label>
        {(du || au) && <button onClick={() => { setDu(""); setAu(""); }}>Effacer la periode</button>}
        <button onClick={() => dl("csv")}>Exporter CSV</button>
        <button onClick={() => dl("xlsx")}>Exporter Excel</button>
        <button onClick={() => dl("pdf")}>Exporter PDF</button>
      </div>
      <p className="muted">
        Les repartitions decrivent le parc a ce jour ; la periode porte sur les mouvements (remises, restitutions, achats)
        et sur la fenetre des renouvellements (sans periode : 12 mois a partir d'aujourd'hui).
      </p>
    </div>
  );

  if (!s) return (
    <div><h2>Statistiques</h2>{filtres}
      {err ? <ErrorState message={err} onRetry={() => { setErr(null); api.get(query("json")).then(setS).catch((e) => setErr(e.message)); }} /> : <Loading />}</div>
  );
  const ren = s.renouvellements;
  const mv = s.mouvements;

  return (
    <div>
      <h2>Statistiques du parc</h2>
      <Feedback err={err} />
      {filtres}
      <div className="tiles">
        <div className="card tile"><div className="n">{s.actifs_total}</div><div className="l">Actifs au total</div></div>
        <div className="card tile"><div className="n">{s.taux_equipement.pourcentage}%</div><div className="l">Salaries actifs equipes</div></div>
        <div className="card tile"><div className="n">{s.age_moyen_annees ?? "-"}</div><div className="l">Age moyen du parc (ans)</div></div>
        <div className="card tile"><div className="n">{ren.count}</div><div className="l">Renouvellements du {ren.du} au {ren.au}</div></div>
      </div>

      {mv && (
        <div className="card">
          <h3>Mouvements de la periode</h3>
          <p>{mv.remis} materiel(s) remis - {mv.restitues} restitue(s) - {mv.achetes} achete(s)</p>
          {mv.par_mois.length > 0 && (
            <table>
              <thead><tr><th>Mois</th><th>Remis</th><th>Restitues</th><th>Achetes</th></tr></thead>
              <tbody>
                {mv.par_mois.map((m) => (
                  <tr key={m.mois}><td>{m.mois}</td><td>{m.remis}</td><td>{m.restitues}</td><td>{m.achetes}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

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
        <h3>Renouvellements du {ren.du} au {ren.au}</h3>
        {ren.count === 0 ? <p className="muted">Aucun.</p> : (
          <table>
            <thead><tr><th>Id interne</th><th>Type</th><th>Marque</th><th>Modele</th><th>Echeance</th></tr></thead>
            <tbody>
              {ren.items.map((r) => (
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
