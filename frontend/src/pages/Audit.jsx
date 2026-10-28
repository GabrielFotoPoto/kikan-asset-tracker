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
import { useAuth } from "../auth.jsx";

export default function Audit() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [err, setErr] = useState(null);

  const load = () => {
    const p = new URLSearchParams({ limit: "300" });
    if (actor) p.set("actor", actor);
    if (action) p.set("action", action);
    api.get("/audit?" + p.toString()).then(setRows).catch((e) => setErr(e.message));
  };
  useEffect(() => { if (user.role === "informatique") load(); }, []);

  if (user.role !== "informatique") {
    return <div><h2>Journal d'audit</h2><p className="muted">Reserve au role informatique.</p></div>;
  }

  return (
    <div>
      <h2>Journal d'audit</h2>
      {err && <p className="err">{err}</p>}
      <div className="card">
        <div className="row">
          <label>Compte<input value={actor} onChange={(e) => setActor(e.target.value)} /></label>
          <label>Action (debut)<input value={action} onChange={(e) => setAction(e.target.value)} placeholder="ex: POST, login" /></label>
          <div style={{ alignSelf: "end" }}><button onClick={load}>Filtrer</button></div>
        </div>
      </div>
      <div className="card">
        <table>
          <thead><tr><th>Date (UTC)</th><th>Compte</th><th>Action</th><th>Statut</th><th>IP</th><th>Detail</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{(r.ts || "").replace("T", " ").slice(0, 19)}</td>
                <td>{r.actor}</td>
                <td>{r.action}{r.target ? ` (${r.target})` : ""}</td>
                <td>{r.status ?? "-"}</td>
                <td>{r.ip || "-"}</td>
                <td>{r.detail || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
