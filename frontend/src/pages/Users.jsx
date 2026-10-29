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
import { Link } from "react-router-dom";
import { api, errorText } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";
import Autocomplete from "../components/Autocomplete.jsx";
import ConfirmButton from "../components/ConfirmButton.jsx";

// Le depart (en_depart, sorti) se declare depuis la page Sorties, avec restitution du materiel.
const STATUTS = ["prevu", "actif"];
const empty = { matricule: "", acronyme: "", nom: "", prenom: "", entite_id: "", service: "", email: "", statut: "actif", date_arrivee: "", date_sortie: "" };

// Acronyme propose (comme le serveur) : initiale du prenom + 2 premieres lettres du nom, sans accent.
const lettres = (v) => (v || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().replace(/[^A-Z]/g, "");
const acronymePropose = (prenom, nom) => (lettres(prenom).slice(0, 1) + lettres(nom).slice(0, 2)).padEnd(3, "X").slice(0, 3);
const cle = (v) => (v || "").trim().toLowerCase();

export default function Users() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "users");
  const canDelete = user.role === "informatique";
  const [items, setItems] = useState([]);
  const [entites, setEntites] = useState([]);
  const [services, setServices] = useState([]);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);
  const [q, setQ] = useState("");
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [types, setTypes] = useState([]);
  const [besoins, setBesoins] = useState([]);

  const load = () => api.get("/users" + (q ? `?q=${encodeURIComponent(q)}` : "")).then(setItems).catch((e) => setErr(errorText(e)));
  useEffect(() => { api.get("/entites").then(setEntites); }, []);
  useEffect(() => { api.get("/besoins/categories").then(setTypes).catch(() => {}); }, []);
  useEffect(() => { api.get("/users/catalogue/services").then(setServices).catch(() => {}); }, [items]);
  useEffect(() => { load(); }, [q]);

  const entiteNom = (id) => entites.find((e) => e.id === id)?.nom || "-";
  const locked = editing && ["en_depart", "sorti"].includes(editing.statut);

  const startEdit = (u) => {
    setEditing(u);
    setForm({
      matricule: u.matricule || "", acronyme: u.acronyme || "", nom: u.nom, prenom: u.prenom, entite_id: u.entite_id ?? "",
      service: u.service || "", email: u.email || "", statut: u.statut,
      date_arrivee: u.date_arrivee || "", date_sortie: u.date_sortie || "",
    });
    setErr(null); setMsg(null);
    window.scrollTo({ top: 0 });
  };
  const cancel = () => { setEditing(null); setForm(empty); setBesoins([]); setErr(null); };
  const toggleBesoin = (t) => setBesoins((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  const submit = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    const payload = {
      ...form,
      entite_id: form.entite_id ? Number(form.entite_id) : null,
      date_arrivee: form.date_arrivee || null,
      date_sortie: form.date_sortie || null,
      matricule: form.matricule || null,
      acronyme: form.acronyme || null,
      service: form.service || null,
      email: form.email || null,
    };
    try {
      if (editing) {
        await api.put(`/users/${editing.id}`, payload);
        cancel();
        setMsg(`Fiche de ${form.prenom} ${form.nom} modifiee.`);
      } else {
        const homonyme = items.find((u) => cle(u.nom) === cle(form.nom) && cle(u.prenom) === cle(form.prenom));
        if (homonyme && !window.confirm(`Un salarie ${homonyme.prenom} ${homonyme.nom} existe deja (${entiteNom(homonyme.entite_id)}). Creer quand meme ? (homonyme : pensez a differencier l'acronyme)`)) return;
        const created = await api.post("/users", payload);
        const failed = [];
        for (const type of besoins) {
          try { await api.post("/besoins", { user_id: created.id, type }); } catch { failed.push(type); }
        }
        const ok = besoins.length - failed.length;
        cancel();
        setMsg(`${form.prenom} ${form.nom} ajoute${ok ? `, ${ok} besoin(s) de materiel enregistre(s)` : ""}.`);
        if (failed.length) setErr(`Besoin non enregistre (${failed.join(", ")}) : a saisir depuis la page Besoins.`);
      }
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const remove = async (u) => {
    setErr(null); setMsg(null);
    try {
      await api.del(`/users/${u.id}`);
      setMsg(`Fiche de ${u.prenom} ${u.nom} supprimee.`);
      if (editing && editing.id === u.id) cancel();
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  return (
    <div>
      <h2>Utilisateurs</h2>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}
      {writable && (
      <div className="card">
        <h3>{editing ? `Modifier : ${editing.prenom} ${editing.nom}` : "Ajouter (formulaire d'entree)"}</h3>
        <form className="grid" onSubmit={submit}>
          <label>Matricule<input value={form.matricule} onChange={(e) => setForm({ ...form, matricule: e.target.value })} /></label>
          <label>Acronyme (3 lettres)
            <input value={form.acronyme} maxLength={3} placeholder={acronymePropose(form.prenom, form.nom)}
                   onChange={(e) => setForm({ ...form, acronyme: e.target.value.toUpperCase() })} />
          </label>
          <label>Nom<input value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} required /></label>
          <label>Prenom<input value={form.prenom} onChange={(e) => setForm({ ...form, prenom: e.target.value })} required /></label>
          <label>E-mail<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>Filiale / entite
            <select value={form.entite_id} onChange={(e) => setForm({ ...form, entite_id: e.target.value })}>
              <option value="">-</option>
              {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
            </select>
          </label>
          <label>Service
            <Autocomplete value={form.service} items={services} nouveau="Nouveau service"
                          onChange={(v) => setForm({ ...form, service: v })} />
          </label>
          <label>Statut
            <select value={form.statut} disabled={locked} onChange={(e) => setForm({ ...form, statut: e.target.value })}>
              {locked ? <option value={form.statut}>{form.statut}</option> : STATUTS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Date d'arrivee<input type="date" value={form.date_arrivee} onChange={(e) => setForm({ ...form, date_arrivee: e.target.value })} /></label>
          <label>Date de sortie<input type="date" value={form.date_sortie} onChange={(e) => setForm({ ...form, date_sortie: e.target.value })} /></label>
          {!editing && types.length > 0 && (
            <fieldset style={{ gridColumn: "1 / -1" }}>
              <legend>Materiel necessaire</legend>
              <div className="row">
                {types.map((t) => (
                  <label key={t} className="row" style={{ gap: 6 }}>
                    <input type="checkbox" checked={besoins.includes(t)} onChange={() => toggleBesoin(t)} />{t}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <div className="row" style={{ alignSelf: "end" }}>
            <button type="submit">{editing ? "Enregistrer" : "Ajouter"}</button>
            {editing && <button type="button" className="ghost" onClick={cancel}>Annuler</button>}
          </div>
        </form>
        {locked && <p className="muted">Ce salarie est en depart ou sorti : le statut se gere depuis la page Sorties.</p>}
      </div>
      )}
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <input placeholder="Rechercher nom / prenom / matricule" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <table>
          <thead><tr><th>Matricule</th><th>Nom</th><th>Filiale</th><th>Service</th><th>Statut</th><th>Arrivee</th>{writable && <th></th>}</tr></thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td>{u.matricule || "-"}</td>
                <td>{u.prenom} {u.nom}</td>
                <td>{entiteNom(u.entite_id)}</td>
                <td>{u.service || "-"}</td>
                <td><span className="badge">{u.statut}</span></td>
                <td>{u.date_arrivee || "-"}</td>
                {writable && (
                  <td>
                    <div className="row">
                      <button className="ghost" onClick={() => startEdit(u)}>Modifier</button>
                      <Link to={`/besoins?user=${u.id}`} className="ghost" style={{ padding: "6px 10px" }}>Besoins</Link>
                      {canDelete && <ConfirmButton onConfirm={() => remove(u)}>Supprimer</ConfirmButton>}
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
