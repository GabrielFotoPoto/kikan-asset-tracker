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
import { useAuth } from "../auth.jsx";
import { Feedback } from "../components/Notifications.jsx";
import { ErrorState, Loading } from "../components/State.jsx";

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

function Repartition({ titre, items, cle, label }) {
  return (
    <div className="card">
      <h3>{titre}</h3>
      {items.length === 0 ? <p className="muted">Aucune echeance.</p> : (
        <div className="table-scroll"><table>
          <thead><tr><th>{label}</th><th>Materiels</th><th>Budget estime</th><th>Sans estimation</th></tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i[cle]}><td>{i[cle]}</td><td>{i.nombre}</td><td>{eur.format(i.montant)}</td><td>{i.sans_estimation || "-"}</td></tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}

export default function Previsions() {
  const { user } = useAuth();
  const [p, setP] = useState(null);
  const [err, setErr] = useState(null);
  const [entites, setEntites] = useState([]);
  const [entiteId, setEntiteId] = useState("");
  const [du, setDu] = useState("");
  const [au, setAu] = useState("");

  const query = (fmt) => {
    const q = new URLSearchParams({ format: fmt });
    if (entiteId) q.set("entite_id", entiteId);
    if (du) q.set("du", du);
    if (au) q.set("au", au);
    return `/previsions?${q}`;
  };
  useEffect(() => { api.get("/entites").then(setEntites).catch(() => {}); }, []);
  useEffect(() => {
    setErr(null);
    api.get(query("json")).then(setP).catch((e) => setErr(e.message));
  }, [entiteId, du, au]);

  const dl = async (fmt) => {
    setErr(null);
    try { await downloadFile(query(fmt), `kikan-previsions.${fmt}`); } catch (e) { setErr(e.message); }
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
        <label>Echeances du
          <input type="date" value={du} max={au || undefined} onChange={(e) => setDu(e.target.value)} />
        </label>
        <label>au
          <input type="date" value={au} min={du || undefined} onChange={(e) => setAu(e.target.value)} />
        </label>
        {(du || au) && <button onClick={() => { setDu(""); setAu(""); }}>12 mois a venir</button>}
        <button onClick={() => dl("csv")}>Exporter CSV</button>
        <button onClick={() => dl("xlsx")}>Exporter Excel</button>
        <button onClick={() => dl("pdf")}>Exporter PDF</button>
      </div>
      <p className="muted">
        Budget estime = somme des couts de remplacement du materiel dont l'echeance de renouvellement tombe dans la periode
        (materiel reforme exclu). Sans periode : du mois en cours aux 12 mois suivants.
      </p>
    </div>
  );

  if (!p) return (
    <div><h2>Previsions de renouvellement</h2>{filtres}
      {err ? <ErrorState message={err} onRetry={() => { setErr(null); api.get(query("json")).then(setP).catch((e) => setErr(e.message)); }} /> : <Loading />}</div>
  );
  const t = p.total;
  const maxMois = Math.max(1, ...p.par_mois.map((m) => m.montant));

  return (
    <div>
      <h2>Previsions de renouvellement</h2>
      <Feedback err={err} />
      {filtres}
      <div className="tiles">
        <div className="card tile"><div className="n">{eur.format(t.montant)}</div><div className="l">Budget estime du {p.periode.du} au {p.periode.au}</div></div>
        <div className="card tile"><div className="n">{t.nombre}</div><div className="l">Materiels a renouveler</div></div>
        <div className="card tile"><div className="n">{t.sans_estimation}</div><div className="l">Sans estimation de cout</div></div>
        <div className="card tile"><div className="n">{p.en_retard.nombre}</div><div className="l">Echeances depassees avant la periode ({eur.format(p.en_retard.montant)})</div></div>
      </div>
      {(t.sans_estimation > 0 || p.couts_renseignes === 0) && (
        <div className="card" role="status">
          {p.couts_renseignes === 0 ? "Aucun cout de remplacement n'est renseigne : le budget est a zero. " : `${t.sans_estimation} materiel(s) n'ont pas de cout et ne sont pas dans le budget. `}
          {user.role === "informatique" ? "Renseignez-les dans Parametrage, onglet Couts de remplacement." : "L'informatique peut les renseigner dans le Parametrage."}
        </div>
      )}

      <div className="card">
        <h3>Par mois</h3>
        <div className="table-scroll"><table>
          <thead><tr><th>Mois</th><th>Materiels</th><th>Budget estime</th><th></th></tr></thead>
          <tbody>
            {p.par_mois.map((m) => (
              <tr key={m.mois}>
                <td>{m.mois}</td><td>{m.nombre}</td><td>{eur.format(m.montant)}{m.sans_estimation > 0 && <span className="muted"> (+{m.sans_estimation} sans cout)</span>}</td>
                <td style={{ width: "35%" }}>
                  <div style={{ height: 12, width: `${(m.montant / maxMois) * 100}%`, minWidth: m.montant ? 2 : 0, background: "var(--brand)", borderRadius: 3 }} />
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      <Repartition titre="Par annee" items={p.par_annee} cle="annee" label="Annee" />
      <Repartition titre="Par type de materiel" items={p.par_type} cle="type" label="Type" />
      <Repartition titre="Par entite" items={p.par_entite} cle="entite" label="Entite" />

      <div className="card">
        <h3>Detail des materiels a renouveler</h3>
        {p.items.length === 0 ? <p className="muted">Aucune echeance sur la periode.</p> : (
          <div className="table-scroll"><table>
            <thead><tr><th>Echeance</th><th>Entite</th><th>Id interne</th><th>Type</th><th>Marque</th><th>Modele</th><th>Cout estime</th></tr></thead>
            <tbody>
              {p.items.map((i) => (
                <tr key={i.id}>
                  <td>{i.echeance}</td><td>{i.entite}</td><td>{i.identifiant_interne || "-"}</td><td>{i.type}</td><td>{i.marque}</td><td>{i.modele}</td>
                  <td>{i.cout === null ? <span className="muted">non renseigne</span> : eur.format(i.cout)}
                    {i.source_cout === "modele" && <span className="muted"> (modele)</span>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}
