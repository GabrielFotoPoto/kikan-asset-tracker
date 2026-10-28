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
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, errorText } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";
import ConfirmButton from "../components/ConfirmButton.jsx";

const STATUTS = { demande: "Demande", en_preparation: "En preparation", satisfait: "Satisfait", annule: "Annule" };
const BADGE = { demande: "badge", en_preparation: "badge", satisfait: "badge ok", annule: "badge bad" };
const empty = { user_id: "", type: "", quantite: 1, commentaire: "", date_souhaitee: "" };
const row = { display: "flex", flexDirection: "row", alignItems: "center", gap: 8 };

// Besoins de materiel : saisis par les RH a l'arrivee d'un salarie, traites par l'informatique, soldes par la remise.
export default function Besoins() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const writable = canWrite(user.role, "besoins");
  const it = user.role === "informatique";
  const [items, setItems] = useState([]);
  const [users, setUsers] = useState([]);
  const [types, setTypes] = useState([]);
  const [filtre, setFiltre] = useState("ouverts");
  const [forUser, setForUser] = useState(params.get("user") || "");
  const [form, setForm] = useState({ ...empty, user_id: params.get("user") || "" });
  const [editing, setEditing] = useState(null);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = async () => {
    const q = new URLSearchParams();
    if (filtre) q.set("statut", filtre);
    if (forUser) q.set("user_id", forUser);
    const [b, u, t] = await Promise.all([api.get("/besoins?" + q), api.get("/users"), api.get("/assets/catalogue/types")]);
    setItems(b); setUsers(u); setTypes(t);
  };
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, [filtre, forUser]);

  const run = async (fn, ok) => {
    setErr(null); setMsg(null);
    try { await fn(); if (ok) setMsg(ok); await load(); } catch (ex) { setErr(errorText(ex)); }
  };

  const submit = (e) => {
    e.preventDefault();
    const payload = {
      type: form.type, quantite: Number(form.quantite) || 1,
      commentaire: form.commentaire || null, date_souhaitee: form.date_souhaitee || null,
    };
    if (editing) {
      run(async () => { await api.put(`/besoins/${editing}`, payload); setEditing(null); setForm(empty); }, "Besoin modifie.");
    } else {
      if (!form.user_id || !form.type) { setErr("Choisissez un salarie et un type de materiel."); return; }
      run(async () => { await api.post("/besoins", { ...payload, user_id: Number(form.user_id) }); setForm({ ...empty, user_id: form.user_id }); }, "Besoin enregistre.");
    }
  };

  const startEdit = (b) => {
    setEditing(b.id);
    setForm({ user_id: String(b.user_id), type: b.type, quantite: b.quantite, commentaire: b.commentaire || "", date_souhaitee: b.date_souhaitee || "" });
    window.scrollTo({ top: 0 });
  };
  const statut = (b, s, ok) => run(() => api.post(`/besoins/${b.id}/statut`, { statut: s }), ok);
  const editable = (b) => b.statut === "demande" || (it && b.statut === "en_preparation");
  const selectedUser = users.find((u) => String(u.id) === String(form.user_id));

  return (
    <div>
      <h2>Besoins de materiel</h2>
      <p className="muted">
        Les RH declarent le materiel necessaire a un salarie (typiquement a son arrivee) ; l'informatique le prepare puis le remet
        depuis la page Remises, ce qui solde automatiquement le besoin.
      </p>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}

      {writable && (
        <div className="card">
          <h3>{editing ? "Modifier un besoin" : "Declarer un besoin"}</h3>
          <form onSubmit={submit}>
            <div className="grid">
              <label>Salarie
                <select value={form.user_id} disabled={!!editing} onChange={(e) => setForm({ ...form, user_id: e.target.value })}>
                  <option value="">-</option>
                  {users.filter((u) => u.statut !== "sorti").map((u) => (
                    <option key={u.id} value={u.id}>{u.prenom} {u.nom}{u.statut === "prevu" ? " (arrivee prevue)" : ""}</option>
                  ))}
                </select>
              </label>
              <label>Type de materiel
                <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                  <option value="">-</option>
                  {types.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label>Quantite
                <input type="number" min="1" max="20" value={form.quantite} onChange={(e) => setForm({ ...form, quantite: e.target.value })} />
              </label>
              <label>Date souhaitee {selectedUser?.date_arrivee && !form.date_souhaitee && <span className="muted">(par defaut : arrivee le {selectedUser.date_arrivee})</span>}
                <input type="date" value={form.date_souhaitee} onChange={(e) => setForm({ ...form, date_souhaitee: e.target.value })} />
              </label>
            </div>
            <label>Precisions (facultatif, 200 caracteres)
              <input value={form.commentaire} maxLength={200} onChange={(e) => setForm({ ...form, commentaire: e.target.value })} placeholder="ex. avec double ecran" />
            </label>
            <div className="row" style={{ marginTop: 10 }}>
              <button type="submit">{editing ? "Enregistrer" : "Ajouter le besoin"}</button>
              {editing && <button type="button" className="ghost" onClick={() => { setEditing(null); setForm(empty); }}>Annuler</button>}
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <label style={row}>Afficher :
            <select style={{ width: "auto" }} value={filtre} onChange={(e) => setFiltre(e.target.value)}>
              <option value="ouverts">A traiter (demande, en preparation)</option>
              <option value="">Tous</option>
              {Object.entries(STATUTS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          {forUser && <button className="ghost" onClick={() => setForUser("")}>Voir tous les salaries</button>}
        </div>
        {items.length === 0 ? <p className="muted">Aucun besoin pour ce filtre.</p> : (
          <table>
            <thead><tr><th>Salarie</th><th>Arrivee</th><th>Materiel</th><th>Souhaite le</th><th>Precisions</th><th>Statut</th>{writable && <th></th>}</tr></thead>
            <tbody>
              {items.map((b) => (
                <tr key={b.id}>
                  <td>{b.salarie}{b.matricule && <div className="muted">{b.matricule}</div>}</td>
                  <td>{b.date_arrivee || "-"}</td>
                  <td>{b.quantite} x {b.type}</td>
                  <td>{b.date_souhaitee || "-"}</td>
                  <td>{b.commentaire || "-"}</td>
                  <td>
                    <span className={BADGE[b.statut]}>{STATUTS[b.statut]}</span>
                    {b.statut === "satisfait" && b.assignment_id && <div className="muted">remise #{b.assignment_id}</div>}
                  </td>
                  {writable && (
                    <td>
                      <div className="row">
                        {editable(b) && <button className="ghost" onClick={() => startEdit(b)}>Modifier</button>}
                        {it && b.statut === "demande" && <button className="ghost" onClick={() => statut(b, "en_preparation", "Besoin mis en preparation.")}>Prendre en charge</button>}
                        {it && b.statut === "en_preparation" && <button className="ghost" onClick={() => statut(b, "demande", "Besoin remis en demande.")}>Remettre en demande</button>}
                        {it && b.statut !== "satisfait" && b.statut !== "annule" && (
                          <button onClick={() => navigate(`/remises?user=${b.user_id}`)}>Remettre le materiel</button>
                        )}
                        {(b.statut === "demande" || (it && b.statut === "en_preparation")) && (
                          <ConfirmButton confirmLabel="Confirmer l'annulation" onConfirm={() => statut(b, "annule", "Besoin annule.")}>Annuler</ConfirmButton>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
