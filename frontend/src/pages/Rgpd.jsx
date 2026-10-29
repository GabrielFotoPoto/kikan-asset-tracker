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
import { api, errorText } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";

const row = { display: "flex", flexDirection: "row", alignItems: "center", gap: 8 };
const num = { width: 90 };

// Purge RGPD : duree de conservation et delai de grace (reglages), salaries a purger, quarantaine des PDF du partage, liste pour la GED.
export default function Rgpd() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "entites"); // informatique
  const [reg, setReg] = useState({ mois: 12, delai_grace_jours: 30 });
  const [etat, setEtat] = useState(null);
  const [preview, setPreview] = useState(null);
  const [docs, setDocs] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = async () => {
    const [r, e, d] = await Promise.all([api.get("/rgpd/retention"), api.get("/rgpd/etat"), api.get("/rgpd/documents")]);
    setReg(r); setEtat(e); setDocs(d.documents);
  };
  useEffect(() => { if (writable) load().catch((e) => setErr(errorText(e))); }, [writable]);

  const run = async (fn, ok) => {
    setErr(null); setMsg(null);
    try { const r = await fn(); if (ok) setMsg(ok(r)); await load(); } catch (e) { setErr(errorText(e)); }
  };

  const save = () => run(
    () => api.put("/rgpd/retention", { mois: Number(reg.mois), delai_grace_jours: Number(reg.delai_grace_jours) }),
    () => "Reglages enregistres.");
  const doPreview = () => run(async () => { setPreview(await api.get("/rgpd/purge-preview")); });
  const doPurge = () => {
    if (!preview || preview.count === 0) return;
    if (!window.confirm(`Purger ${preview.count} salarie(s) sorti(s) ? Leurs donnees sont supprimees de Kikan (irreversible). `
      + `Les PDF du partage vont en quarantaine ${reg.delai_grace_jours} jour(s) ; ceux de la GED sont a faire supprimer par l'equipe de la GED.`)) return;
    run(async () => { const r = await api.post("/rgpd/purge", { ids: preview.candidats.map((c) => c.id) }); setPreview(null); return r; },
      (r) => `${r.count} salarie(s) purge(s), ${r.documents} document(s) suivi(s)` + (r.en_attente ? `, ${r.en_attente} a reessayer (partage indisponible).` : "."));
  };
  const retry = () => run(() => api.post("/rgpd/purge", { ids: [] }), (r) => `${r.deplaces} document(s) range(s) en quarantaine, ${r.en_attente} encore en attente.`);
  const suppr = () => {
    if (!window.confirm("Supprimer definitivement les PDF dont le delai de grace est ecoule ? Irreversible.")) return;
    run(() => api.post("/rgpd/quarantaine/supprimer", {}), (r) => `${r.supprimes} document(s) supprime(s)` + (r.echecs ? `, ${r.echecs} echec(s)` : "") + ".");
  };
  const restore = (d) => run(() => api.post("/rgpd/quarantaine/restaurer", { ids: [d.id] }), () => "Document remis a son emplacement d'origine.");
  const confirmGed = () => {
    const ids = ged.map((d) => d.id);
    if (!window.confirm(`Confirmer que l'equipe de la GED a supprime ces ${ids.length} document(s) ?`)) return;
    run(() => api.post("/rgpd/ged/confirmer", { ids }), (r) => `${r.confirmes} document(s) confirme(s).`);
  };
  const copy = () => navigator.clipboard?.writeText(ged.map((d) => `${d.moteur}\t${d.reference}\t${d.echeance}`).join("\n")).then(() => setMsg("Liste copiee."));

  if (!writable) return <div><h2>Retention RGPD</h2><p className="muted">Reserve au role informatique.</p></div>;

  const quarantaine = docs.filter((d) => d.statut === "quarantaine");
  const attente = docs.filter((d) => d.statut === "a_deplacer");
  const ged = docs.filter((d) => d.statut === "ged_a_supprimer");
  const echus = quarantaine.filter((d) => d.echu).length;

  return (
    <div>
      <h2>Retention RGPD</h2>
      <p className="muted">
        Un salarie sorti est conserve jusqu'a sa date de sortie + la duree de conservation. La purge supprime ses donnees de Kikan ; ses PDF scelles
        vont dans le dossier A_PURGER du partage (quarantaine) puis sont supprimes apres le delai de grace. SharePoint et DocuWare : Kikan liste les
        documents, l'equipe de la GED les supprime.
      </p>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}

      <div className="card">
        <h3>Reglages</h3>
        <div className="row">
          <label style={row}>Conservation apres sortie
            <input type="number" min="0" max="240" value={reg.mois} onChange={(e) => setReg({ ...reg, mois: e.target.value })} style={num} /> mois</label>
          <label style={row}>Delai de grace avant suppression des PDF
            <input type="number" min="0" max="365" value={reg.delai_grace_jours} onChange={(e) => setReg({ ...reg, delai_grace_jours: e.target.value })} style={num} /> jours</label>
          <button onClick={save}>Enregistrer</button>
        </div>
        <p className="muted">Le delai de grace s'applique aux PDF purges a partir de maintenant. Le rappel par e-mail se regle dans Parametrage, E-mails.</p>
      </div>

      {etat && (etat.candidats > 0 || echus > 0 || etat.ged_echus > 0 || etat.a_deplacer > 0) && (
        <div className="card">
          <h3>A traiter</h3>
          <ul>
            {etat.candidats > 0 && <li>{etat.candidats} salarie(s) a purger.</li>}
            {echus > 0 && <li>{echus} document(s) en quarantaine dont le delai de grace est ecoule.</li>}
            {etat.ged_echus > 0 && <li>{etat.ged_echus} document(s) a faire supprimer par l'equipe de la GED.</li>}
            {etat.a_deplacer > 0 && <li>{etat.a_deplacer} document(s) pas encore ranges en quarantaine (partage indisponible).</li>}
          </ul>
        </div>
      )}

      <div className="card">
        <h3>1. Salaries a purger</h3>
        <div className="row" style={{ marginBottom: 12 }}>
          <button className="ghost" onClick={doPreview}>Previsualiser</button>
          {preview && preview.count > 0 && <button onClick={doPurge}>Purger ({preview.count})</button>}
          {attente.length > 0 && <button className="ghost" onClick={retry}>Reessayer le rangement ({attente.length})</button>}
        </div>
        {preview && (
          preview.count === 0 ? <p className="muted">Aucun salarie a purger pour l'instant.</p> : (
            <table>
              <thead><tr><th>Matricule</th><th>Salarie</th><th>Date de sortie</th><th>Echeance de conservation</th></tr></thead>
              <tbody>
                {preview.candidats.map((c) => (
                  <tr key={c.id}><td>{c.matricule || "-"}</td><td>{c.prenom} {c.nom}</td><td>{c.date_sortie}</td><td>{c.suppression_prevue}</td></tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>

      <div className="card">
        <h3>2. Quarantaine du partage (dossier A_PURGER)</h3>
        {quarantaine.length === 0 ? <p className="muted">Aucun document en quarantaine.</p> : (
          <>
            <div className="row" style={{ marginBottom: 12 }}>
              <button disabled={echus === 0} onClick={suppr}>Supprimer definitivement les documents echus ({echus})</button>
            </div>
            <table>
              <thead><tr><th>Emplacement</th><th>Suppression possible le</th><th></th></tr></thead>
              <tbody>
                {quarantaine.map((d) => (
                  <tr key={d.id}>
                    <td>{d.moteur}</td>
                    <td>{d.echeance} {d.echu && <span className="badge bad">echu</span>}</td>
                    <td><button className="ghost" onClick={() => restore(d)}>Remettre a l'origine</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="card">
        <h3>3. Documents a faire supprimer par l'equipe de la GED</h3>
        {ged.length === 0 ? <p className="muted">Aucun document en attente.</p> : (
          <>
            <div className="row" style={{ marginBottom: 12 }}>
              <button className="ghost" onClick={copy}>Copier la liste</button>
              <button onClick={confirmGed}>La GED a supprime ces documents ({ged.length})</button>
            </div>
            <table>
              <thead><tr><th>GED</th><th>Reference</th><th>A supprimer avant le</th></tr></thead>
              <tbody>
                {ged.map((d) => (
                  <tr key={d.id}><td>{d.moteur}</td><td>{d.reference}</td><td>{d.echeance} {d.echu && <span className="badge bad">echu</span>}</td></tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
