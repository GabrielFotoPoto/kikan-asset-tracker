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

const FILTRES = ["stock", "affecte", "rendu", "reforme"];
// Les statuts affecte et rendu viennent de la remise et de la restitution, jamais d'une saisie manuelle.
const SAISISSABLES = ["stock", "reforme"];
const DATES = ["date_achat", "fin_garantie", "echeance_renouvellement"];
const TEXTES = ["identifiant_interne", "type", "marque", "modele", "numero_serie", "notes"];
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
  const [editing, setEditing] = useState(null);
  const [filtre, setFiltre] = useState("");
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = () => api.get("/assets" + (filtre ? `?statut=${filtre}` : "")).then(setItems).catch((e) => setErr(errorText(e)));
  useEffect(() => { api.get("/entites").then(setEntites); }, []);
  useEffect(() => { load(); }, [filtre]);
  useEffect(() => { api.get("/assets/catalogue/marques").then(setMarques).catch(() => {}); }, [items]);

  const lockedStatus = editing && editing.statut === "affecte";
  const options = editing && editing.statut === "rendu" ? ["rendu", ...SAISISSABLES] : SAISISSABLES;

  const startEdit = (a) => {
    setEditing(a);
    const f = { ...empty, statut: a.statut, entite_id: a.entite_id ?? "" };
    for (const k of [...TEXTES, ...DATES]) f[k] = a[k] || "";
    setForm(f);
    setErr(null); setMsg(null);
    window.scrollTo({ top: 0 });
  };
  const cancel = () => { setEditing(null); setForm(empty); setErr(null); };

  const submit = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    const payload = { ...form, entite_id: form.entite_id ? Number(form.entite_id) : null };
    for (const k of [...DATES, ...TEXTES]) if (payload[k] === "") payload[k] = null;
    // Champs non affiches dans le formulaire : conserves tels quels a la modification.
    if (editing) { payload.source = editing.source; payload.id_externe = editing.id_externe; }
    try {
      if (editing) {
        await api.put(`/assets/${editing.id}`, payload);
        setMsg("Materiel modifie.");
      } else {
        await api.post("/assets", payload);
        setMsg("Materiel ajoute.");
      }
      cancel();
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const remove = async (a) => {
    setErr(null); setMsg(null);
    try {
      await api.del(`/assets/${a.id}`);
      setMsg("Materiel supprime.");
      if (editing && editing.id === a.id) cancel();
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div>
      <h2>Materiel</h2>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}
      {writable && (
      <div className="card">
        <h3>{editing ? `Modifier : ${editing.type || "materiel"} ${editing.numero_serie || editing.identifiant_interne || ""}` : "Ajouter"}</h3>
        <form className="grid" onSubmit={submit}>
          <label>Id interne<input value={form.identifiant_interne} onChange={set("identifiant_interne")} /></label>
          <label>Type<input value={form.type} onChange={set("type")} placeholder="PC portable, Smartphone..." /></label>
          <label>Marque
            <input list="marques" value={form.marque} onChange={set("marque")} />
            <datalist id="marques">{marques.map((m) => <option key={m} value={m} />)}</datalist>
          </label>
          <label>Modele<input value={form.modele} onChange={set("modele")} /></label>
          <label>N de serie<input value={form.numero_serie} onChange={set("numero_serie")} /></label>
          <label>Statut
            <select value={form.statut} disabled={lockedStatus} onChange={set("statut")}>
              {lockedStatus ? <option value={form.statut}>{form.statut}</option> : options.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Date d'achat<input type="date" value={form.date_achat} onChange={set("date_achat")} /></label>
          <label>Fin de garantie<input type="date" value={form.fin_garantie} onChange={set("fin_garantie")} /></label>
          <label>Echeance renouvellement<input type="date" value={form.echeance_renouvellement} onChange={set("echeance_renouvellement")} /></label>
          <label>Filiale / entite
            <select value={form.entite_id} onChange={set("entite_id")}>
              <option value="">-</option>
              {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
            </select>
          </label>
          <label>Notes<input value={form.notes} onChange={set("notes")} /></label>
          <div className="row" style={{ alignSelf: "end" }}>
            <button type="submit">{editing ? "Enregistrer" : "Ajouter"}</button>
            {editing && <button type="button" className="ghost" onClick={cancel}>Annuler</button>}
          </div>
        </form>
        {lockedStatus && (
          <p className="muted">Ce materiel est affecte : il se libere par la restitution du salarie (page Sorties).</p>
        )}
      </div>
      )}
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>Filtrer par statut
            <select value={filtre} onChange={(e) => setFiltre(e.target.value)}>
              <option value="">tous</option>
              {FILTRES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>
        <table>
          <thead><tr><th>Id interne</th><th>Type</th><th>Marque</th><th>Modele</th><th>N serie</th><th>Statut</th>{writable && <th></th>}</tr></thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>{a.identifiant_interne || "-"}</td>
                <td>{a.type || "-"}</td>
                <td>{a.marque || "-"}</td>
                <td>{a.modele || "-"}</td>
                <td>{a.numero_serie || "-"}</td>
                <td><span className="badge">{a.statut}</span></td>
                {writable && (
                  <td>
                    <div className="row">
                      <button className="ghost" onClick={() => startEdit(a)}>Modifier</button>
                      <ConfirmButton onConfirm={() => remove(a)}>Supprimer</ConfirmButton>
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
