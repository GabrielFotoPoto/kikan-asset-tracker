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

import { useEffect, useRef, useState } from "react";
import { api, downloadFile, errorText, postForm } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";
import PolicyViewer from "../components/PolicyViewer.jsx";

const FORMATS = { pdf: "PDF", markdown: "Markdown", docx: "Word" };

// Chartes informatiques : fichier depose par l'informatique, globale ou propre a une entite.
export default function Policies() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "chartes");
  const fileRef = useRef(null);
  const [items, setItems] = useState([]);
  const [entites, setEntites] = useState([]);
  const [applied, setApplied] = useState({});
  const [titre, setTitre] = useState("Charte informatique");
  const [entiteId, setEntiteId] = useState("");
  const [file, setFile] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = async () => {
    const [p, e] = await Promise.all([api.get("/policies"), api.get("/entites")]);
    setItems(p);
    setEntites(e);
    const pairs = await Promise.all(
      [null, ...e.map((x) => x.id)].map(async (id) => [
        id === null ? "global" : id,
        await api.get("/policies/applicable" + (id === null ? "" : `?entite_id=${id}`)),
      ]),
    );
    setApplied(Object.fromEntries(pairs));
  };
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, []);

  const activeOfScope = () =>
    items.find((p) => p.statut === "active" && String(p.entite_id ?? "") === String(entiteId));

  const startUpload = (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    if (!file) { setErr("Choisir un fichier (PDF, Word ou Markdown)."); return; }
    const old = activeOfScope();
    if (old && !confirm) { setConfirm(old); return; }
    send();
  };

  const send = async () => {
    setBusy(true); setConfirm(null);
    try {
      const form = new FormData();
      form.append("titre", titre);
      if (entiteId) form.append("entite_id", entiteId);
      form.append("file", file);
      const p = await postForm("/policies", form);
      setMsg(`Charte deposee : ${p.titre}, version ${p.version} (${p.portee}), ${p.nb_pages} page(s). Elle est maintenant jointe aux nouvelles remises.`);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      setPreview(p.id);
      await load();
    } catch (ex) { setErr(errorText(ex)); } finally { setBusy(false); }
  };

  const archive = async (p) => {
    setErr(null); setMsg(null);
    try {
      await api.post(`/policies/${p.id}/archiver`, {});
      setMsg(`Charte ${p.version} archivee (${p.portee}).`);
      if (preview === p.id) setPreview(null);
      await load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const previewed = items.find((p) => p.id === preview);
  const label = (p) => (p ? `${p.titre} ${p.version} (${p.portee})` : null);

  return (
    <div>
      <h2>Chartes informatiques</h2>
      <p className="muted">
        Une charte globale s'applique a toutes les entites ; une entite peut avoir la sienne. A la remise, la charte de
        l'entite du salarie est jointe d'office (sinon celle de l'entite parente, sinon la charte globale). Pour mettre
        a jour une charte, deposez simplement le nouveau fichier : l'ancienne version est archivee et conservee.
      </p>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}

      {writable && (
        <div className="card">
          <h3>Deposer une charte</h3>
          <form className="grid" onSubmit={startUpload}>
            <label>Portee
              <select value={entiteId} onChange={(e) => { setEntiteId(e.target.value); setConfirm(null); }}>
                <option value="">Globale (toutes les entites)</option>
                {entites.map((x) => <option key={x.id} value={x.id}>Entite : {x.nom}</option>)}
              </select>
            </label>
            <label>Titre
              <input value={titre} maxLength={120} onChange={(e) => setTitre(e.target.value)} required />
            </label>
            <label>Fichier (Word, PDF ou Markdown)
              <input ref={fileRef} type="file" accept=".docx,.pdf,.md,.markdown,.txt"
                     onChange={(e) => { setFile(e.target.files[0] || null); setConfirm(null); }} />
            </label>
            <div style={{ alignSelf: "end" }}>
              <button type="submit" disabled={busy}>{busy ? "Depot en cours..." : "Deposer"}</button>
            </div>
          </form>
          {confirm && (
            <div className="warn" style={{ marginTop: 12 }}>
              <p style={{ margin: "0 0 8px" }}>
                La version <b>{confirm.version}</b> ({confirm.portee}) sera archivee et remplacee par ce nouveau fichier.
                Les documents deja signes ne changent pas.
              </p>
              <div className="row">
                <button onClick={send} disabled={busy}>Confirmer le remplacement</button>
                <button className="ghost" onClick={() => setConfirm(null)}>Annuler</button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h3>Chartes deposees</h3>
        {items.length === 0 && <p className="muted">Aucune charte deposee : les remises sont signees sans charte.</p>}
        {items.length > 0 && (
          <table>
            <thead>
              <tr><th>Portee</th><th>Titre</th><th>Version</th><th>Statut</th><th>Format</th><th>Pages</th><th>Depot</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id}>
                  <td>{p.portee}</td>
                  <td>{p.titre}</td>
                  <td>{p.version}</td>
                  <td><span className={p.statut === "active" ? "badge ok" : "badge"}>{p.statut === "active" ? "active" : "archivee"}</span></td>
                  <td>{FORMATS[p.format_source] || p.format_source}</td>
                  <td>{p.nb_pages}</td>
                  <td>{(p.depose_le || "").slice(0, 10)} <span className="muted">{p.depose_par}</span></td>
                  <td>
                    <div className="row">
                      <button className="ghost" onClick={() => setPreview(preview === p.id ? null : p.id)}>
                        {preview === p.id ? "Masquer" : "Apercu"}
                      </button>
                      <button className="ghost" onClick={() => downloadFile(`/policies/${p.id}/fichier`, `charte_${p.id}_${p.version}.pdf`)}>PDF</button>
                      <button className="ghost" onClick={() => downloadFile(`/policies/${p.id}/source`, p.source_nom || `charte_${p.id}`)}>Original</button>
                      {writable && p.statut === "active" && <button className="ghost" onClick={() => archive(p)}>Archiver</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {previewed && (
        <div className="card">
          <h3>Apercu : {previewed.titre} ({previewed.version}, {previewed.nb_pages} page(s))</h3>
          <p className="muted">Empreinte SHA-256 : {previewed.sha256}</p>
          <PolicyViewer policyId={previewed.id} nbPages={previewed.nb_pages} />
        </div>
      )}

      <div className="card">
        <h3>Charte appliquee a chaque entite</h3>
        <table>
          <thead><tr><th>Entite</th><th>Charte jointe a la remise</th></tr></thead>
          <tbody>
            <tr>
              <td><i>Sans entite</i></td>
              <td>{label(applied.global) || <span className="muted">Aucune</span>}</td>
            </tr>
            {entites.map((x) => (
              <tr key={x.id}>
                <td>{x.nom}</td>
                <td>{label(applied[x.id]) || <span className="muted">Aucune</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
