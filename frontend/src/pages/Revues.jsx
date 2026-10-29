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
import { api, downloadFile, errorText } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";
import ConfirmButton from "../components/ConfirmButton.jsx";

const row = { display: "flex", flexDirection: "row", alignItems: "center", gap: 8 };
const DEC = { a_traiter: "A traiter", maintenu: "Maintenu", a_retirer: "A retirer" };
const BADGE = { a_traiter: "badge", maintenu: "badge ok", a_retirer: "badge bad" };
const fmt = (d) => String(d || "").replace("T", " ").slice(0, 16);

// Revue periodique des droits d'acces (ISO 27001 A.5.18) : anomalies, rapport "qui a acces a quoi", campagnes de validation, retraits.
export default function Revues() {
  const { user } = useAuth();
  const it = user.role === "informatique";
  const [tab, setTab] = useState("anomalies");
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const go = (t) => { setTab(t); setErr(null); setMsg(null); };
  const tabs = [["anomalies", "Anomalies"], ["acces", "Qui a acces a quoi"], ["revues", "Revues"], ...(it ? [["retraits", "Retraits a confirmer"]] : [])];
  return (
    <div>
      <h2>Revue des acces</h2>
      <p className="muted">
        Controle periodique des droits d'acces aux applications (ISO 27001, A.5.18) : reperer les acces qui ne devraient plus exister, faire valider
        chaque acces par les RH de l'entite, puis conserver un rapport scelle de la revue.
      </p>
      <div className="row" style={{ marginBottom: 14 }}>
        {tabs.map(([k, label]) => <button key={k} className={tab === k ? "" : "ghost"} onClick={() => go(k)}>{label}</button>)}
      </div>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}
      {tab === "anomalies" && <Anomalies setErr={setErr} />}
      {tab === "acces" && <AccesRapport setErr={setErr} />}
      {tab === "revues" && <Campagnes it={it} setErr={setErr} setMsg={setMsg} />}
      {tab === "retraits" && it && <Retraits setErr={setErr} setMsg={setMsg} />}
    </div>
  );
}

function Anomalies({ setErr }) {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/revues/anomalies").then(setData).catch((e) => setErr(errorText(e))); }, []);
  if (!data) return <p className="muted">Chargement...</p>;
  return (
    <div className="card">
      <h3>Acces a verifier ({data.count})</h3>
      <p className="muted">Acces actifs d'un salarie sorti ou dont la date de sortie est depassee, ou vers une application desactivee. Sur votre perimetre.</p>
      {data.count === 0 ? <p className="muted">Aucune anomalie.</p> : (
        <table>
          <thead><tr><th>Matricule</th><th>Salarie</th><th>Entite</th><th>Application</th><th>Anomalie</th></tr></thead>
          <tbody>{data.anomalies.map((a) => (
            <tr key={a.acces_id}><td>{a.matricule || "-"}</td><td>{a.salarie}</td><td>{a.entite || "-"}</td><td>{a.application}</td><td><span className="badge bad">{a.anomalie}</span></td></tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}

function AccesRapport({ setErr }) {
  const [rows, setRows] = useState(null);
  const [ents, setEnts] = useState([]);
  const [apps, setApps] = useState([]);
  const [entite, setEntite] = useState("");
  const [appli, setAppli] = useState("");
  const q = () => { const p = new URLSearchParams(); if (entite) p.set("entite_id", entite); if (appli) p.set("application_id", appli); return p; };
  useEffect(() => { Promise.all([api.get("/entites"), api.get("/applications")]).then(([e, a]) => { setEnts(e); setApps(a); }).catch((e) => setErr(errorText(e))); }, []);
  useEffect(() => { api.get("/revues/acces?" + q()).then((r) => setRows(r.rows)).catch((e) => setErr(errorText(e))); }, [entite, appli]);
  const exp = (format) => { const p = q(); p.set("format", format); downloadFile("/revues/acces?" + p, `kikan-acces.${format}`).catch((e) => setErr(errorText(e))); };
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 10 }}>
        <label style={row}>Entite
          <select style={{ width: "auto" }} value={entite} onChange={(e) => setEntite(e.target.value)}>
            <option value="">Toutes</option>{ents.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
          </select></label>
        <label style={row}>Application
          <select style={{ width: "auto" }} value={appli} onChange={(e) => setAppli(e.target.value)}>
            <option value="">Toutes</option>{apps.map((a) => <option key={a.id} value={a.id}>{a.nom}</option>)}
          </select></label>
        <button className="ghost" onClick={() => exp("xlsx")}>Exporter (Excel)</button>
        <button className="ghost" onClick={() => exp("csv")}>Exporter (CSV)</button>
      </div>
      {!rows ? <p className="muted">Chargement...</p> : rows.length === 0 ? <p className="muted">Aucun acces.</p> : (
        <table>
          <thead><tr><th>Matricule</th><th>Salarie</th><th>Entite</th><th>Statut</th><th>Application</th><th>Acces</th><th>Precision</th><th>Anomalie</th></tr></thead>
          <tbody>{rows.slice(0, 500).map((r, i) => (
            <tr key={i}><td>{r.matricule || "-"}</td><td>{r.salarie}</td><td>{r.entite || "-"}</td><td>{r.statut_salarie}</td><td>{r.application}</td>
              <td><span className={r.acces === "oui" ? "badge ok" : "badge"}>{r.acces}</span></td><td>{r.note || "-"}</td><td>{r.anomalie ? <span className="badge bad">{r.anomalie}</span> : "-"}</td></tr>
          ))}</tbody>
        </table>
      )}
      {rows && rows.length > 500 && <p className="muted">{rows.length} acces : les 500 premiers sont affiches, l'export contient tout.</p>}
    </div>
  );
}

function Campagnes({ it, setErr, setMsg }) {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState(null);
  const load = () => api.get("/revues").then(setList).catch((e) => setErr(errorText(e)));
  useEffect(() => { load(); }, []);
  if (sel) return <Detail id={sel} it={it} back={() => { setSel(null); load(); }} setErr={setErr} setMsg={setMsg} />;
  return (
    <div>
      {it && <Lancer onDone={(id) => { setMsg("Revue lancee."); load(); setSel(id); }} setErr={setErr} />}
      <div className="card">
        <h3>Revues</h3>
        {list.length === 0 ? <p className="muted">Aucune revue pour le moment.</p> : (
          <table>
            <thead><tr><th>Revue</th><th>Etat</th><th>Echeance</th><th>Acces</th><th>A traiter</th><th>Maintenus</th><th>A retirer</th><th></th></tr></thead>
            <tbody>{list.map((r) => (
              <tr key={r.id}>
                <td>{r.titre}<div className="muted">lancee le {fmt(r.cree_le)} par {r.cree_par}</div></td>
                <td>{r.statut === "cloturee" ? <span className="badge ok">cloturee</span> : <span className="badge">en cours</span>}</td>
                <td>{r.echeance || "-"}</td><td>{r.total}</td><td>{r.a_traiter}</td><td>{r.maintenu}</td><td>{r.a_retirer}</td>
                <td><button className="ghost" onClick={() => setSel(r.id)}>Ouvrir</button></td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Lancer({ onDone, setErr }) {
  const [ents, setEnts] = useState([]);
  const [apps, setApps] = useState([]);
  const [titre, setTitre] = useState(`Revue des acces ${new Date().getFullYear()}`);
  const [echeance, setEcheance] = useState("");
  const [entIds, setEntIds] = useState([]);
  const [appIds, setAppIds] = useState([]);
  useEffect(() => { Promise.all([api.get("/entites"), api.get("/applications")]).then(([e, a]) => { setEnts(e); setApps(a); }).catch(() => {}); }, []);
  const toggle = (list, set, id) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const go = async (e) => {
    e.preventDefault(); setErr(null);
    try { const r = await api.post("/revues", { titre, echeance: echeance || null, entite_ids: entIds, application_ids: appIds }); onDone(r.id); }
    catch (ex) { setErr(errorText(ex)); }
  };
  return (
    <div className="card">
      <h3>Lancer une revue</h3>
      <form onSubmit={go}>
        <div className="grid">
          <label>Titre<input value={titre} maxLength={120} onChange={(e) => setTitre(e.target.value)} /></label>
          <label>Date limite (facultatif)<input type="date" value={echeance} onChange={(e) => setEcheance(e.target.value)} /></label>
        </div>
        <p className="muted">Entites concernees (aucune cochee = toutes, sous-entites comprises) :</p>
        <div className="row">{ents.map((e) => <label key={e.id} style={row}><input type="checkbox" style={{ width: "auto" }} checked={entIds.includes(e.id)} onChange={() => toggle(entIds, setEntIds, e.id)} />{e.nom}</label>)}</div>
        <p className="muted">Applications concernees (aucune cochee = toutes) :</p>
        <div className="row">{apps.map((a) => <label key={a.id} style={row}><input type="checkbox" style={{ width: "auto" }} checked={appIds.includes(a.id)} onChange={() => toggle(appIds, setAppIds, a.id)} />{a.nom}</label>)}</div>
        <div className="row" style={{ marginTop: 10 }}><button type="submit" disabled={!titre.trim()}>Lancer la revue</button></div>
      </form>
    </div>
  );
}

function Detail({ id, it, back, setErr, setMsg }) {
  const { user } = useAuth();
  const canDecide = canWrite(user.role, "revues");
  const [rev, setRev] = useState(null);
  const [data, setData] = useState({ total: 0, lignes: [] });
  const [filtre, setFiltre] = useState("a_traiter");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState([]);
  const [comment, setComment] = useState("");
  const load = async () => {
    const p = new URLSearchParams({ limit: "500" });
    if (filtre === "anomalies") p.set("anomalies", "true"); else if (filtre) p.set("decision", filtre);
    if (q.trim()) p.set("q", q.trim());
    const [r, l] = await Promise.all([api.get(`/revues/${id}`), api.get(`/revues/${id}/lignes?` + p)]);
    setRev(r); setData(l); setPicked([]);
  };
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, [filtre, q]);
  const run = async (fn, ok) => { setErr(null); setMsg(null); try { const r = await fn(); if (ok) setMsg(ok(r)); await load(); } catch (e) { setErr(errorText(e)); } };
  const decide = (decision) => run(() => api.post(`/revues/${id}/decisions`, { ids: picked, decision, commentaire: comment || null }), (r) => `${r.mises_a_jour} ligne(s) mise(s) a jour.`);
  const close = () => run(() => api.post(`/revues/${id}/cloturer`, {}), (r) => `Revue cloturee : ${r.acces_retires} acces passe(s) a non, rapport scelle enregistre.`);
  const toggle = (lid) => setPicked(picked.includes(lid) ? picked.filter((x) => x !== lid) : [...picked, lid]);
  if (!rev) return <p className="muted">Chargement...</p>;
  const open = rev.statut === "en_cours";
  return (
    <div>
      <p><button className="ghost" onClick={back}>&lt; Retour aux revues</button></p>
      <div className="card">
        <h3>{rev.titre} {open ? <span className="badge">en cours</span> : <span className="badge ok">cloturee</span>}</h3>
        <p className="muted">Lancee le {fmt(rev.cree_le)} par {rev.cree_par}{rev.echeance ? `, a terminer avant le ${rev.echeance}` : ""}{rev.cloture_le ? `. Cloturee le ${fmt(rev.cloture_le)} par ${rev.cloture_par}` : ""}.</p>
        <p>{rev.total} acces dans votre perimetre : <strong>{rev.a_traiter}</strong> a traiter, {rev.maintenu} maintenu(s), {rev.a_retirer} a retirer, {rev.anomalies} anomalie(s).</p>
        <div className="row">
          {it && open && <ConfirmButton confirmLabel="Confirmer la cloture" onConfirm={close}>Cloturer la revue</ConfirmButton>}
          {it && !open && rev.rapport && <button onClick={() => downloadFile(`/revues/${id}/rapport`, `revue-acces-${id}.pdf`).catch((e) => setErr(errorText(e)))}>Telecharger le rapport scelle (PDF)</button>}
        </div>
        {it && open && <p className="muted">La cloture n'est possible que lorsque tous les acces sont decides ; les acces "a retirer" passent alors a "non" dans Kikan et un rapport PDF scelle est enregistre.</p>}
        {rev.empreinte && <p className="muted">Empreinte du rapport (SHA-256) : {rev.empreinte}</p>}
      </div>
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <label style={row}>Afficher
            <select style={{ width: "auto" }} value={filtre} onChange={(e) => setFiltre(e.target.value)}>
              <option value="a_traiter">A traiter</option><option value="anomalies">Anomalies</option><option value="">Tous</option>
              <option value="maintenu">Maintenus</option><option value="a_retirer">A retirer</option>
            </select></label>
          <input style={{ width: 220 }} placeholder="Rechercher (nom, matricule, application)" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {canDecide && open && (
          <div className="row" style={{ marginBottom: 10 }}>
            <input style={{ width: 260 }} maxLength={200} placeholder="Commentaire (facultatif)" value={comment} onChange={(e) => setComment(e.target.value)} />
            <button disabled={!picked.length} onClick={() => decide("maintenu")}>Maintenir ({picked.length})</button>
            <button className="danger" disabled={!picked.length} onClick={() => decide("a_retirer")}>A retirer ({picked.length})</button>
            <button className="ghost" disabled={!picked.length} onClick={() => decide("a_traiter")}>Remettre a traiter</button>
            <button className="ghost" onClick={() => setPicked(picked.length === data.lignes.length ? [] : data.lignes.map((l) => l.id))}>Tout cocher / decocher</button>
          </div>
        )}
        {data.lignes.length === 0 ? <p className="muted">Aucune ligne pour ce filtre.</p> : (
          <table>
            <thead><tr>{canDecide && open && <th></th>}<th>Matricule</th><th>Salarie</th><th>Application</th><th>Precision</th><th>Anomalie</th><th>Decision</th><th>Par</th><th>Commentaire</th></tr></thead>
            <tbody>{data.lignes.map((l) => (
              <tr key={l.id}>
                {canDecide && open && <td><input type="checkbox" style={{ width: "auto" }} checked={picked.includes(l.id)} onChange={() => toggle(l.id)} /></td>}
                <td>{l.matricule || "-"}</td><td>{l.salarie || "-"}</td><td>{l.application}</td><td>{l.note || "-"}</td>
                <td>{l.anomalie ? <span className="badge bad">{l.anomalie}</span> : "-"}</td>
                <td><span className={BADGE[l.decision]}>{DEC[l.decision]}</span></td><td>{l.decide_par || "-"}</td><td>{l.commentaire || "-"}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
        {data.total > data.lignes.length && <p className="muted">{data.total} lignes : les {data.lignes.length} premieres sont affichees, affinez le filtre.</p>}
      </div>
    </div>
  );
}

function Retraits({ setErr, setMsg }) {
  const [rows, setRows] = useState([]);
  const [picked, setPicked] = useState([]);
  const load = () => api.get("/revues/retraits").then((r) => { setRows(r); setPicked([]); }).catch((e) => setErr(errorText(e)));
  useEffect(() => { load(); }, []);
  const toggle = (id) => setPicked(picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id]);
  const confirm = async () => {
    setErr(null); setMsg(null);
    try { const r = await api.post("/revues/retraits/confirmer", { ids: picked }); setMsg(`${r.confirmes} retrait(s) confirme(s).`); load(); } catch (e) { setErr(errorText(e)); }
  };
  return (
    <div className="card">
      <h3>Retraits a effectuer dans les applications ({rows.length})</h3>
      <p className="muted">Kikan est un registre : ces acces sont passes a "non" ici, mais le droit doit encore etre retire dans l'application concernee. Confirmez une fois l'action faite.</p>
      {rows.length === 0 ? <p className="muted">Aucun retrait en attente.</p> : (
        <>
          <div className="row" style={{ marginBottom: 10 }}>
            <button disabled={!picked.length} onClick={confirm}>Retire dans le systeme ({picked.length})</button>
            <button className="ghost" onClick={() => setPicked(picked.length === rows.length ? [] : rows.map((r) => r.id))}>Tout cocher / decocher</button>
          </div>
          <table>
            <thead><tr><th></th><th>Matricule</th><th>Salarie</th><th>Application</th><th>Revue</th><th>Commentaire</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}><td><input type="checkbox" style={{ width: "auto" }} checked={picked.includes(r.id)} onChange={() => toggle(r.id)} /></td>
                <td>{r.matricule || "-"}</td><td>{r.salarie || "-"}</td><td>{r.application}</td><td>{r.revue}<div className="muted">cloturee le {fmt(r.cloture_le)}</div></td><td>{r.commentaire || "-"}</td></tr>
            ))}</tbody>
          </table>
        </>
      )}
    </div>
  );
}
