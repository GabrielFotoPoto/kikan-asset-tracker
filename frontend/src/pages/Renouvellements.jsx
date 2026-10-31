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

import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText } from "../api.js";
import { Feedback } from "../components/Notifications.jsx";

const HORIZONS = [[0, "Echeances depassees seulement"], [1, "Jusqu'a 1 mois"], [3, "Jusqu'a 3 mois"], [6, "Jusqu'a 6 mois"], [12, "Jusqu'a 12 mois"]];
const BADGE = { en_retard: "badge bad", ce_mois: "badge", a_venir: "badge ok" };

const dansTroisMois = () => { const d = new Date(); d.setMonth(d.getMonth() + 3); return d.toISOString().slice(0, 10); };

// Renouvellements (informatique) : l'informatique decide quand renouveler ; l'echeance n'est qu'un repere. Elle peut renouveler
// avant ou apres, ou reporter (ou avancer) l'echeance, avec un motif facultatif.
export default function Renouvellements() {
  const [data, setData] = useState(null);
  const [entites, setEntites] = useState([]);
  const [horizon, setHorizon] = useState(3);
  const [entiteId, setEntiteId] = useState("");
  const [edit, setEdit] = useState(null);   // { id, nouvelle, motif }
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const charger = () => {
    const q = new URLSearchParams({ horizon_mois: String(horizon) });
    if (entiteId) q.set("entite_id", entiteId);
    return api.get(`/renouvellements?${q}`).then(setData).catch((e) => setErr(errorText(e)));
  };
  useEffect(() => { api.get("/entites").then(setEntites).catch(() => {}); }, []);
  useEffect(() => { setErr(null); charger(); }, [horizon, entiteId]);

  const reporter = async (nouvelle) => {
    setErr(null); setMsg(null);
    try {
      await api.post(`/renouvellements/${edit.id}/reporter`, { nouvelle, motif: edit.motif.trim() || null });
      setMsg(nouvelle ? `Echeance reportee au ${nouvelle}.` : "Aucun renouvellement prevu : l'echeance est supprimee.");
      setEdit(null);
      charger();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const t = data?.totaux;
  return (
    <div>
      <h2>Renouvellements</h2>
      <p className="muted">
        Vous decidez quand renouveler : l'echeance n'est qu'un repere. Renouvelez avant ou apres, ou reportez l'echeance d'un materiel qui peut encore servir.
        Le renouvellement remet le nouveau materiel et recupere l'ancien en une seule operation, avec un seul document signe.
      </p>
      <Feedback err={err} msg={msg} />

      <div className="card">
        <div className="row">
          <label>Horizon
            <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
              {HORIZONS.map(([m, l]) => <option key={m} value={m}>{l}</option>)}
            </select>
          </label>
          <label>Filiale / entite (sous-entites incluses)
            <select value={entiteId} onChange={(e) => setEntiteId(e.target.value)}>
              <option value="">toutes</option>
              {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
            </select>
          </label>
        </div>
      </div>

      {t && (
        <div className="tiles">
          <div className="card tile"><div className="n" style={t.en_retard ? { color: "var(--danger)" } : undefined}>{t.en_retard}</div><div className="l">Echeances depassees</div></div>
          <div className="card tile"><div className="n">{t.ce_mois}</div><div className="l">Ce mois-ci</div></div>
          <div className="card tile"><div className="n">{t.a_venir}</div><div className="l">A venir (dans l'horizon)</div></div>
        </div>
      )}

      <div className="card">
        {!data ? <p className="muted">Chargement...</p> : data.items.length === 0 ? <p className="muted">Aucun materiel a renouveler sur cet horizon.</p> : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Echeance</th><th>Materiel</th><th>Detenteur</th><th>Entite</th><th></th></tr></thead>
              <tbody>
                {data.items.map((i) => (
                  <Fragment key={i.id}>
                    <tr>
                      <td>
                        {i.echeance}
                        <div><span className={BADGE[i.situation]}>{i.jours < 0 ? `depassee de ${-i.jours} j` : i.jours === 0 ? "aujourd'hui" : `dans ${i.jours} j`}</span></div>
                        {i.dernier_report && (
                          <div className="muted">
                            Echeance modifiee le {i.dernier_report.le} ({i.dernier_report.ancienne || "aucune"} vers {i.dernier_report.nouvelle || "aucune"})
                            {i.dernier_report.motif ? ` : ${i.dernier_report.motif}` : ""}
                          </div>
                        )}
                      </td>
                      <td>{i.type} {i.marque} {i.modele}<div className="muted">{i.identifiant_interne || i.numero_serie || i.id}</div></td>
                      <td>{i.detenteur ? i.detenteur.nom : <span className="muted">en stock</span>}</td>
                      <td>{i.entite || "-"}</td>
                      <td>
                        <div className="row">
                          {i.detenteur && <Link to={`/renouveler?asset=${i.id}`} className="ghost" style={{ padding: "6px 10px" }}>Renouveler</Link>}
                          <button className="ghost" onClick={() => setEdit(edit?.id === i.id ? null : { id: i.id, nouvelle: dansTroisMois(), motif: "" })}>Reporter</button>
                        </div>
                      </td>
                    </tr>
                    {edit?.id === i.id && (
                      <tr>
                        <td colSpan={5}>
                          <div className="row">
                            <label>Nouvelle echeance
                              <input type="date" value={edit.nouvelle} min={data.date} onChange={(e) => setEdit({ ...edit, nouvelle: e.target.value })} />
                            </label>
                            <label style={{ flex: 1 }}>Motif (facultatif)
                              <input value={edit.motif} maxLength={200} placeholder="ex. materiel encore en bon etat" onChange={(e) => setEdit({ ...edit, motif: e.target.value })} />
                            </label>
                            <button disabled={!edit.nouvelle} onClick={() => reporter(edit.nouvelle)}>Enregistrer</button>
                            <button className="ghost" onClick={() => reporter(null)}>Aucun renouvellement prevu</button>
                            <button className="ghost" onClick={() => setEdit(null)}>Annuler</button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
