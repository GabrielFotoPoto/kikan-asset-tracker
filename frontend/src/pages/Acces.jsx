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

export default function Acces() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "users"); // RH ou informatique
  const [users, setUsers] = useState([]);
  const [apps, setApps] = useState([]);
  const [userId, setUserId] = useState("");
  const [state, setState] = useState({}); // application_id -> {acces, note, id}
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    Promise.all([api.get("/users"), api.get("/applications")])
      .then(([u, a]) => { setUsers(u); setApps(a); })
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
    } catch (e) { setErr(e.message); }
  };

  return (
    <div>
      <h2>Acces applicatifs</h2>
      {err && <p className="err">{err}</p>}
      {msg && <p className="muted">{msg}</p>}

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
