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

const empty = { code: "", nom: "", code_parent: "", actif: true };

export default function Entites() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "entites");
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = () => api.get("/entites").then(setItems).catch((e) => setErr(errorText(e)));
  useEffect(() => { load(); }, []);

  const startEdit = (x) => {
    setEditing(x);
    setForm({ code: x.code, nom: x.nom, code_parent: x.code_parent || "", actif: x.actif });
    setErr(null); setMsg(null);
    window.scrollTo({ top: 0 });
  };
  const cancel = () => { setEditing(null); setForm(empty); setErr(null); };

  const submit = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    const payload = { ...form, code_parent: form.code_parent || null };
    try {
      if (editing) {
        await api.put(`/entites/${editing.id}`, payload);
        setMsg(`Entite ${form.code} modifiee.`);
      } else {
        await api.post("/entites", payload);
        setMsg(`Entite ${form.code} ajoutee.`);
      }
      cancel();
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const remove = async (x) => {
    setErr(null); setMsg(null);
    try {
      await api.del(`/entites/${x.id}`);
      setMsg(`Entite ${x.code} supprimee.`);
      if (editing && editing.id === x.id) cancel();
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const parents = items.filter((x) => !editing || x.id !== editing.id);

  return (
    <div>
      <h2>Entites / filiales</h2>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}
      {writable && (
      <div className="card">
        <h3>{editing ? `Modifier : ${editing.nom}` : "Ajouter"}</h3>
        <form className="grid" onSubmit={submit}>
          <label>Code<input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required /></label>
          <label>Nom<input value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} required /></label>
          <label>Entite parente
            <select value={form.code_parent} onChange={(e) => setForm({ ...form, code_parent: e.target.value })}>
              <option value="">- (aucune)</option>
              {parents.map((x) => <option key={x.id} value={x.code}>{x.code} - {x.nom}</option>)}
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={form.actif} onChange={(e) => setForm({ ...form, actif: e.target.checked })} /><span>Active</span></label>
          <div className="row" style={{ alignSelf: "end" }}>
            <button type="submit">{editing ? "Enregistrer" : "Ajouter"}</button>
            {editing && <button type="button" className="ghost" onClick={cancel}>Annuler</button>}
          </div>
        </form>
        {editing && form.code !== editing.code && (
          <p className="muted">Le code change : les entites filles suivent automatiquement.</p>
        )}
      </div>
      )}
      <div className="card">
        <table>
          <thead><tr><th>Code</th><th>Nom</th><th>Parent</th><th>Active</th>{writable && <th></th>}</tr></thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.id}>
                <td>{x.code}</td><td>{x.nom}</td><td>{x.code_parent || "-"}</td>
                <td>{x.actif ? "oui" : "non"}</td>
                {writable && (
                  <td>
                    <div className="row">
                      <button className="ghost" onClick={() => startEdit(x)}>Modifier</button>
                      <ConfirmButton onConfirm={() => remove(x)}>Supprimer</ConfirmButton>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
