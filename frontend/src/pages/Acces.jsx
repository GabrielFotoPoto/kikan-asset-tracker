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
import ConfirmButton from "../components/ConfirmButton.jsx";

const emptyApp = { nom: "", description: "", entite_id: "", actif: true };

export default function Acces() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "users"); // RH ou informatique
  const [users, setUsers] = useState([]);
  const [apps, setApps] = useState([]);
  const [entites, setEntites] = useState([]);
  const [appForm, setAppForm] = useState(emptyApp);
  const [appEditing, setAppEditing] = useState(null);
  const isIT = user.role === "informatique";
  const [userId, setUserId] = useState("");
  const [state, setState] = useState({}); // application_id -> {acces, note, id}
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    Promise.all([api.get("/users"), api.get("/applications"), api.get("/entites")])
      .then(([u, a, e]) => { setUsers(u); setApps(a); setEntites(e); })
      .catch((e) => setErr(e.message));
  }, []);

  const loadAcces = async (uid) => {
    setMsg(null);
    if (!uid) { setState({}); return; }
    const rows = await api.get(`/users/${uid}/applications`);
    const m = {};
    for (const r of rows) m[r.application_id] = { acces: r.acces, note: r.note || "", id: r.id };
    setState(m);
  };
  useEffect(() => { loadAcces(userId).catch((e) => setErr(e.message)); }, [userId]);

  // --- Catalogue des applications (informatique) ---
  const reloadApps = () => api.get("/applications").then(setApps);
  const entiteNom = (id) => entites.find((e) => e.id === id)?.nom || "Toutes";
  const cancelApp = () => { setAppEditing(null); setAppForm(emptyApp); };
  const startEditApp = (a) => {
    setAppEditing(a);
    setAppForm({ nom: a.nom, description: a.description || "", entite_id: a.entite_id ?? "", actif: a.actif });
    setErr(null); setMsg(null);
  };
  const submitApp = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    const payload = { ...appForm, description: appForm.description || null, entite_id: appForm.entite_id ? Number(appForm.entite_id) : null };
    try {
      if (appEditing) {
        await api.put(`/applications/${appEditing.id}`, payload);
        setMsg(`Application ${appForm.nom} modifiee.`);
      } else {
        await api.post("/applications", payload);
        setMsg(`Application ${appForm.nom} ajoutee.`);
      }
      cancelApp();
      await reloadApps();
    } catch (ex) { setErr(errorText(ex)); }
  };
  const removeApp = async (a) => {
    setErr(null); setMsg(null);
    try {
      await api.del(`/applications/${a.id}`);
      setMsg(`Application ${a.nom} supprimee.`);
      if (appEditing && appEditing.id === a.id) cancelApp();
      await reloadApps();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const setField = (appId, field, value) =>
    setState((s) => ({ ...s, [appId]: { ...(s[appId] || { acces: false, note: "" }), [field]: value } }));

  const save = async (appId) => {
    setErr(null); setMsg(null);
    const cur = state[appId] || { acces: false, note: "" };
    try {
      await api.post(`/users/${userId}/applications`, {
        application_id: appId, acces: !!cur.acces, note: cur.note || null,
      });
      setMsg("Acces enregistre.");
      await loadAcces(userId);
    } catch (e) { setErr(errorText(e)); }
  };

  return (
    <div>
      <h2>Acces applicatifs</h2>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}

      {isIT && (
        <div className="card">
          <h3>Catalogue des applications</h3>
          <form className="grid" onSubmit={submitApp}>
            <label>Nom<input value={appForm.nom} onChange={(e) => setAppForm({ ...appForm, nom: e.target.value })} required /></label>
            <label>Description<input value={appForm.description} onChange={(e) => setAppForm({ ...appForm, description: e.target.value })} /></label>
            <label>Entite concernee
              <select value={appForm.entite_id} onChange={(e) => setAppForm({ ...appForm, entite_id: e.target.value })}>
                <option value="">Toutes</option>
                {entites.map((x) => <option key={x.id} value={x.id}>{x.nom}</option>)}
              </select>
            </label>
            <label className="check"><input type="checkbox" checked={appForm.actif} onChange={(e) => setAppForm({ ...appForm, actif: e.target.checked })} /><span>Active</span></label>
            <div className="row" style={{ alignSelf: "end" }}>
              <button type="submit">{appEditing ? "Enregistrer" : "Ajouter"}</button>
              {appEditing && <button type="button" className="ghost" onClick={cancelApp}>Annuler</button>}
            </div>
          </form>
          {apps.length > 0 && (
            <table style={{ marginTop: 12 }}>
              <thead><tr><th>Application</th><th>Description</th><th>Entite</th><th>Active</th><th></th></tr></thead>
              <tbody>
                {apps.map((a) => (
                  <tr key={a.id}>
                    <td>{a.nom}</td><td>{a.description || "-"}</td><td>{entiteNom(a.entite_id)}</td><td>{a.actif ? "oui" : "non"}</td>
                    <td>
                      <div className="row">
                        <button className="ghost" onClick={() => startEditApp(a)}>Modifier</button>
                        <ConfirmButton onConfirm={() => removeApp(a)}>Supprimer</ConfirmButton>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="card">
        <label style={{ maxWidth: 360 }}>Salarie
          <select value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">-</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.prenom} {u.nom}</option>)}
          </select>
        </label>
      </div>

      {userId && (
        <div className="card">
          <h3>Applications</h3>
          {apps.length === 0 && <p className="muted">Aucune application dans le catalogue.</p>}
          <table>
            <thead><tr><th>Application</th><th>Acces</th><th>Note (niveau)</th>{writable && <th></th>}</tr></thead>
            <tbody>
              {apps.map((a) => {
                const cur = state[a.id] || { acces: false, note: "" };
                return (
                  <tr key={a.id}>
                    <td>{a.nom}</td>
                    <td>
                      <input type="checkbox" checked={!!cur.acces} disabled={!writable}
                        onChange={(e) => setField(a.id, "acces", e.target.checked)} />
                    </td>
                    <td>
                      <input value={cur.note} disabled={!writable} placeholder="ex: admin, memes droits que..."
                        onChange={(e) => setField(a.id, "note", e.target.value)} style={{ width: "100%" }} />
                    </td>
                    {writable && <td><button className="ghost" onClick={() => save(a.id)}>Enregistrer</button></td>}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
