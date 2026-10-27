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
import { api } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";

export default function Entites() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "entites");
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ code: "", nom: "", code_parent: "", actif: true });
  const [err, setErr] = useState(null);

  const load = () => api.get("/entites").then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    try {
      await api.post("/entites", { ...form, code_parent: form.code_parent || null });
      setForm({ code: "", nom: "", code_parent: "", actif: true });
      load();
    } catch (ex) { setErr(ex.message); }
  };

  return (
    <div>
      <h2>Entites / filiales</h2>
      {err && <p className="err">{err}</p>}
      {writable && (
      <div className="card">
        <h3>Ajouter</h3>
        <form className="grid" onSubmit={submit}>
          <label>Code<input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required /></label>
          <label>Nom<input value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} required /></label>
          <label>Code parent<input value={form.code_parent} onChange={(e) => setForm({ ...form, code_parent: e.target.value })} /></label>
          <div style={{ alignSelf: "end" }}><button type="submit">Ajouter</button></div>
        </form>
      </div>
      )}
      <div className="card">
        <table>
          <thead><tr><th>Code</th><th>Nom</th><th>Parent</th><th>Actif</th></tr></thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.id}>
                <td>{x.code}</td><td>{x.nom}</td><td>{x.code_parent || "-"}</td>
                <td>{x.actif ? "oui" : "non"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
