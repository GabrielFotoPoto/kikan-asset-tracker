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

export default function Departures() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "users"); // RH ou informatique
  const [users, setUsers] = useState([]);
  const [holdings, setHoldings] = useState({});
  const [depId, setDepId] = useState("");
  const [depDate, setDepDate] = useState("");
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = async () => {
    const all = await api.get("/users");
    setUsers(all);
    const partants = all.filter((u) => u.statut === "en_depart");
    const h = {};
    await Promise.all(partants.map(async (u) => { h[u.id] = await api.get(`/lifecycle/holdings/${u.id}`); }));
    setHoldings(h);
  };
  useEffect(() => { load().catch((e) => setErr(e.message)); }, []);

  const actifs = users.filter((u) => u.statut === "actif" || u.statut === "prevu");
  const partants = users.filter((u) => u.statut === "en_depart");

  const declarer = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    if (!depId || !depDate) { setErr("Choisir un salarie et une date de sortie."); return; }
    try {
      const r = await api.post(`/lifecycle/depart/${depId}`, { date_sortie: depDate });
      setMsg(`Depart enregistre. Materiel a recuperer : ${r.materiel_a_recuperer.length}.`);
      setDepId(""); setDepDate("");
      await load();
    } catch (ex) { setErr(ex.message); }
  };

  const restituer = async (u) => {
    const signataire = window.prompt(`Restitution de ${u.prenom} ${u.nom} - nom du signataire :`);
    if (!signataire) return;
    setErr(null); setMsg(null);
    try {
      await api.post("/lifecycle/restituer", { user_id: u.id, signataire });
      setMsg("Restitution signee et scellee.");
      await load();
    } catch (ex) { setErr(ex.message); }
  };

  return (
    <div>
      <h2>Sorties et restitutions</h2>
      {err && <p className="err">{err}</p>}
      {msg && <p className="muted">{msg}</p>}

      {writable && (
      <div className="card">
        <h3>Declarer un depart</h3>
        <form className="row" onSubmit={declarer}>
          <label>Salarie
            <select value={depId} onChange={(e) => setDepId(e.target.value)}>
              <option value="">-</option>
              {actifs.map((u) => <option key={u.id} value={u.id}>{u.prenom} {u.nom}</option>)}
            </select>
          </label>
          <label>Date de sortie
            <input type="date" value={depDate} onChange={(e) => setDepDate(e.target.value)} />
          </label>
          <div style={{ alignSelf: "end" }}><button type="submit">Enregistrer le depart</button></div>
        </form>
      </div>
      )}

      <div className="card">
        <h3>Departs en cours - materiel a recuperer</h3>
        {partants.length === 0 ? (
          <p className="muted">Aucun depart en cours.</p>
        ) : (
          <table>
            <thead><tr><th>Salarie</th><th>Date de sortie</th><th>Materiel detenu</th><th></th></tr></thead>
            <tbody>
              {partants.map((u) => {
                const held = holdings[u.id] || [];
                return (
                  <tr key={u.id}>
                    <td>{u.prenom} {u.nom}</td>
                    <td>{u.date_sortie || "-"}</td>
                    <td>
                      {held.length === 0 ? <span className="muted">tout rendu</span> :
                        held.map((a) => <div key={a.id}>{a.type} {a.marque} {a.modele} ({a.numero_serie || a.identifiant_interne})</div>)}
                    </td>
                    <td>
                      {writable && held.length > 0 &&
                        <button className="ghost" onClick={() => restituer(u)}>Restituer et signer</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
