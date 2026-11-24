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
import { useSearchParams } from "react-router-dom";
import { api, downloadFile } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Feedback } from "../components/Notifications.jsx";
import { ErrorState, Loading } from "../components/State.jsx";

const CRITICITES = [
  ["faible", "Faible"],
  ["moyenne", "Moyenne"],
  ["haute", "Haute"],
  ["critique", "Critique"],
];

const SOUS_CAT_LABELS = {
  phishing: "Phishing / hameconnage",
  perte_vol_materiel: "Perte ou vol de materiel",
  malware: "Malware / rancongiciel",
  acces_non_autorise: "Acces non autorise",
  fuite_donnees: "Fuite de donnees",
  autre: "Autre",
};

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

function fmtH(v) {
  return v === null || v === undefined ? "-" : `${v} h`;
}

function StatsTickets({ entites }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [natures, setNatures] = useState([]);
  const [entiteId, setEntiteId] = useState("");
  const [du, setDu] = useState("");
  const [au, setAu] = useState("");
  const [nature, setNature] = useState("");
  const [criticite, setCriticite] = useState("");

  const query = (fmt) => {
    const p = new URLSearchParams({ format: fmt });
    if (entiteId) p.set("entite_id", entiteId);
    if (du) p.set("du", du);
    if (au) p.set("au", au);
    if (nature) p.set("nature", nature);
    if (criticite) p.set("criticite", criticite);
    return `/stats/tickets?${p}`;
  };

  useEffect(() => {
    api.get("/tickets/natures").then((r) => setNatures(Array.isArray(r) ? r : [])).catch(() => {});
  }, []);

  useEffect(() => {
    setErr(null);
    api.get(query("json")).then(setData).catch((e) => setErr(e.message));
  }, [entiteId, du, au, nature, criticite]);

  const dl = async (fmt) => {
    setErr(null);
    try { await downloadFile(query(fmt), `kikan-statistiques-tickets.${fmt}`); } catch (e) { setErr(e.message); }
  };

  const resetFilters = () => {
    setEntiteId(""); setDu(""); setAu(""); setNature(""); setCriticite("");
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
        <label>Nature
          <select value={nature} onChange={(e) => setNature(e.target.value)}>
            <option value="">toutes</option>
            {natures.map((n) => <option key={n.code} value={n.code}>{n.libelle}</option>)}
          </select>
        </label>
        <label>Criticite
          <select value={criticite} onChange={(e) => setCriticite(e.target.value)}>
            <option value="">toutes</option>
            {CRITICITES.map(([val, lbl]) => <option key={val} value={val}>{lbl}</option>)}
          </select>
        </label>
        {(entiteId || du || au || nature || criticite) && (
          <button className="ghost" onClick={resetFilters}>Effacer les filtres</button>
        )}
        <button onClick={() => dl("csv")}>Exporter CSV</button>
        <button onClick={() => dl("xlsx")}>Exporter Excel</button>
      </div>
      <p className="muted">
        Indicateurs agreges strictement sans donnee nominative (reserve au role informatique). Le stock ouvert decrit l'instant present.
      </p>
    </div>
  );

  if (!data) {
    return (
      <div>
        {filtres}
        {err ? <ErrorState message={err} onRetry={() => { setErr(null); api.get(query("json")).then(setData).catch((e) => setErr(e.message)); }} /> : <Loading />}
      </div>
    );
  }

  const { activite: a, reactivite: r, fiabilite_parc: f, securite: sec } = data;
  const stockCrit = CRITICITES.map(([k, lbl]) => ({ label: lbl, count: a.stock_ouvert.par_criticite[k] || 0 }));
  const stockAnc = [
    { label: "Moins de 24 h", count: a.stock_ouvert.par_anciennete.moins_24h || 0 },
    { label: "1 a 7 jours", count: a.stock_ouvert.par_anciennete["1_7j"] || 0 },
    { label: "Plus de 7 jours", count: a.stock_ouvert.par_anciennete.plus_7j || 0 },
  ];

  return (
    <div>
      <Feedback err={err} />
      {filtres}

      <div className="tiles">
        <div className="card tile"><div className="n">{a.crees}</div><div className="l">Tickets crees</div></div>
        <div className="card tile"><div className="n">{a.resolus}</div><div className="l">Tickets resolus</div></div>
        <div className="card tile"><div className="n">{a.stock_ouvert.total}</div><div className="l">Stock ouvert actuel</div></div>
        <div className="card tile"><div className="n">{fmtH(r.mttr_heures.mediane)}</div><div className="l">MTTR net median</div></div>
      </div>

      <div className="card">
        <h3>1. Activite et backlog</h3>
        <p className="muted">
          Fermes : {a.fermes} - Annules : {a.annules} - Stock ouvert : {a.stock_ouvert.total}
        </p>
        <div className="row" style={{ alignItems: "flex-start" }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <h4>Stock ouvert par criticite</h4>
            <Bars items={stockCrit} value="count" label={(i) => i.label} />
          </div>
          <div style={{ flex: 1, minWidth: 260 }}>
            <h4>Stock ouvert par anciennete</h4>
            <Bars items={stockAnc} value="count" label={(i) => i.label} />
          </div>
        </div>
        {a.evolution_mensuelle.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <h4>Evolution mensuelle</h4>
            <table>
              <thead><tr><th>Mois</th><th>Crees</th><th>Resolus</th></tr></thead>
              <tbody>
                {a.evolution_mensuelle.map((m) => (
                  <tr key={m.mois}><td>{m.mois}</td><td>{m.crees}</td><td>{m.resolus}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {a.par_canal.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <h4>Repartition par canal</h4>
            <Bars items={a.par_canal} value="count" label={(i) => i.canal} />
          </div>
        )}
      </div>

      <div className="card">
        <h3>2. Reactivite et qualite</h3>
        <div className="tiles">
          <div className="card tile"><div className="n">{fmtH(r.mtta_heures.mediane)}</div><div className="l">MTTA mediane (moy. {fmtH(r.mtta_heures.moyenne)})</div></div>
          <div className="card tile"><div className="n">{fmtH(r.mttr_heures.mediane)}</div><div className="l">MTTR net median (moy. {fmtH(r.mttr_heures.moyenne)})</div></div>
          <div className="card tile"><div className="n">{r.reouvertures.taux_pourcent}%</div><div className="l">Reouvertures ({r.reouvertures.tickets_reouverts} / {r.reouvertures.tickets_resolus})</div></div>
        </div>
      </div>

      <div className="card">
        <h3>3. Fiabilite du parc materiel</h3>
        <h4>Repartition par nature</h4>
        {f.par_nature.length === 0 ? <p className="muted">Aucun ticket sur la periode.</p> : (
          <Bars items={f.par_nature} value="count" label={(i) => i.libelle} />
        )}
        <h4 style={{ marginTop: 14 }}>Modeles les plus touches (pannes materiel)</h4>
        {f.top_materiels.length === 0 ? <p className="muted">Aucune panne materiel sur la periode.</p> : (
          <table>
            <thead><tr><th>Type</th><th>Marque</th><th>Modele</th><th>Incidents</th><th>Parc</th><th>Taux</th></tr></thead>
            <tbody>
              {f.top_materiels.map((m, idx) => (
                <tr key={idx}>
                  <td>{m.type}</td><td>{m.marque}</td><td>{m.modele}</td>
                  <td>{m.incidents}</td><td>{m.parc}</td>
                  <td>{m.taux_pourcent !== null ? `${m.taux_pourcent}%` : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>4. Pilotage securite</h3>
        <div className="tiles">
          <div className="card tile"><div className="n">{sec.signales_total}</div><div className="l">Signales (dem. {sec.par_origine.demandeur} / IT {sec.par_origine.informatique})</div></div>
          <div className="card tile"><div className="n">{sec.escalades_incident}</div><div className="l">Escalades en incident</div></div>
          <div className="card tile"><div className="n">{sec.taux_sans_suite_pourcent}%</div><div className="l">Classes sans suite ({sec.classes_sans_suite})</div></div>
          <div className="card tile"><div className="n">{sec.violations_potentielles}</div><div className="l">Violations potentielles</div></div>
        </div>
        <p className="muted">
          Delai moyen de qualification : {fmtH(sec.qualification_moyenne_heures)} - Retrogradations : {sec.retrogradations}
        </p>
        {sec.par_sous_categorie.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <h4>Repartition par sous-categorie</h4>
            <Bars items={sec.par_sous_categorie} value="count" label={(i) => SOUS_CAT_LABELS[i.sous_categorie] || i.sous_categorie} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function Stats() {
  const { user } = useAuth();
  const isIt = user?.role === "informatique";
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab") === "tickets" ? "tickets" : "parc";
  const tab = isIt ? requestedTab : "parc";

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
    if (tab !== "parc") return;
    setErr(null);
    api.get(query("json")).then(setS).catch((e) => setErr(e.message));
  }, [entiteId, du, au, tab]);

  const dl = async (fmt) => {
    setErr(null);
    try { await downloadFile(query(fmt), `kikan-statistiques.${fmt}`); } catch (e) { setErr(e.message); }
  };

  const switchTab = (next) => {
    const p = new URLSearchParams(searchParams);
    if (next === "tickets") p.set("tab", "tickets");
    else p.delete("tab");
    setSearchParams(p, { replace: true });
  };

  const tabBar = isIt && (
    <div className="row" style={{ marginBottom: 14 }}>
      <button className={tab === "parc" ? "" : "ghost"} onClick={() => switchTab("parc")}>Parc materiel</button>
      <button className={tab === "tickets" ? "" : "ghost"} onClick={() => switchTab("tickets")}>Tickets</button>
    </div>
  );

  if (tab === "tickets") {
    return (
      <div>
        <h2>Statistiques</h2>
        {tabBar}
        <StatsTickets entites={entites} />
      </div>
    );
  }

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
    <div><h2>Statistiques</h2>{tabBar}{filtres}
      {err ? <ErrorState message={err} onRetry={() => { setErr(null); api.get(query("json")).then(setS).catch((e) => setErr(e.message)); }} /> : <Loading />}</div>
  );
  const ren = s.renouvellements;
  const mv = s.mouvements;

  return (
    <div>
      <h2>Statistiques du parc</h2>
      {tabBar}
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
