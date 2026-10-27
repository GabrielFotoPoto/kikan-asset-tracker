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

const STATUTS = ["stock", "affecte", "rendu", "reforme"];
const empty = {
  identifiant_interne: "", type: "", marque: "", modele: "", numero_serie: "",
  date_achat: "", fin_garantie: "", echeance_renouvellement: "", statut: "stock", entite_id: "", notes: "",
};

export default function Assets() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "materiel");
  const [items, setItems] = useState([]);
  const [entites, setEntites] = useState([]);
  const [marques, setMarques] = useState([]);
  const [form, setForm] = useState(empty);
  const [filtre, setFiltre] = useState("");
  const [err, setErr] = useState(null);

  const load = () => api.get("/assets" + (filtre ? `?statut=${filtre}` : "")).then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { api.get("/entites").then(setEntites); }, []);
  useEffect(() => { load(); }, [filtre]);
  useEffect(() => { api.get("/assets/catalogue/marques").then(setMarques).catch(() => {}); }, [items]);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    const payload = { ...form, entite_id: form.entite_id ? Number(form.entite_id) : null };
    for (const k of ["date_achat", "fin_garantie", "echeance_renouvellement", "identifiant_interne", "type", "marque", "modele", "numero_serie", "notes"]) {
      if (payload[k] === "") payload[k] = null;
    }
    try {
      await api.post("/assets", payload);
      setForm(empty);
      load();
    } catch (ex) { setErr(ex.message); }
  };

  return (
    <div>
      <h2>Materiel</h2>
      {err && <p className="err">{err}</p>}
      {writable && (
      <div className="card">
        <h3>Ajouter</h3>
        <form className="grid" onSubmit={submit}>
          <label>Id interne<input value={form.identifiant_interne} onChange={(e) => setForm({ ...form, identifiant_interne: e.target.value })} /></label>
          <label>Type<input value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} placeholder="PC portable, Smartphone..." /></label>
          <label>Marque
            <input list="marques" value={form.marque} onChange={(e) => setForm({ ...form, marque: e.target.value })} />
            <datalist id="marques">{marques.map((m) => <option key={m} value={m} />)}</datalist>
          </label>
          <label>Modele<input value={form.modele} onChange={(e) => setForm({ ...form, modele: e.target.value })} /></label>
          <label>N de serie<input value={form.numero_serie} onChange={(e) => setForm({ ...form, numero_serie: e.target.value })} /></label>
          <label>Statut
            <select value={form.statut} onChange={(e) => setForm({ ...form, statut: e.target.value })}>
              {STATUTS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Date d'achat<input type="date" value={form.date_achat} onChange={(e) => setForm({ ...form, date_achat: e.target.value })} /></label>
          <label>Echeance renouvellement<input type="date" value={form.echeance_renouvellement} onChange={(e) => setForm({ ...form, echeance_renouvellement: e.target.value })} /></label>
          <label>Filiale / entite
            <select value={form.entite_id} onChange={(e) => setForm({ ...form, entite_id: e.target.value })}>
              <option value="">-</option>
              {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
            </select>
          </label>
          <div style={{ alignSelf: "end" }}><button type="submit">Ajouter</button></div>
        </form>
      </div>
      )}
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>Filtrer par statut
            <select value={filtre} onChange={(e) => setFiltre(e.target.value)}>
              <option value="">tous</option>
              {STATUTS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>
        <table>
          <thead><tr><th>Id interne</th><th>Type</th><th>Marque</th><th>Modele</th><th>N serie</th><th>Statut</th></tr></thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>{a.identifiant_interne || "-"}</td>
                <td>{a.type || "-"}</td>
                <td>{a.marque || "-"}</td>
                <td>{a.modele || "-"}</td>
                <td>{a.numero_serie || "-"}</td>
                <td><span className="badge">{a.statut}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
