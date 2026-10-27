import { useEffect, useState } from "react";
import { api } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";

const STATUTS = ["prevu", "actif", "en_depart", "sorti"];
const empty = { matricule: "", nom: "", prenom: "", entite_id: "", service: "", statut: "actif", date_arrivee: "", date_sortie: "" };

export default function Users() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "users");
  const [items, setItems] = useState([]);
  const [entites, setEntites] = useState([]);
  const [form, setForm] = useState(empty);
  const [q, setQ] = useState("");
  const [err, setErr] = useState(null);

  const load = () => api.get("/users" + (q ? `?q=${encodeURIComponent(q)}` : "")).then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { api.get("/entites").then(setEntites); }, []);
  useEffect(() => { load(); }, [q]);

  const entiteNom = (id) => entites.find((e) => e.id === id)?.nom || "-";

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    const payload = {
      ...form,
      entite_id: form.entite_id ? Number(form.entite_id) : null,
      date_arrivee: form.date_arrivee || null,
      date_sortie: form.date_sortie || null,
      matricule: form.matricule || null,
    };
    try {
      await api.post("/users", payload);
      setForm(empty);
      load();
    } catch (ex) { setErr(ex.message); }
  };

  return (
    <div>
      <h2>Utilisateurs</h2>
      {err && <p className="err">{err}</p>}
      {writable && (
      <div className="card">
        <h3>Ajouter (formulaire d'entree)</h3>
        <form className="grid" onSubmit={submit}>
          <label>Matricule<input value={form.matricule} onChange={(e) => setForm({ ...form, matricule: e.target.value })} /></label>
          <label>Nom<input value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} required /></label>
          <label>Prenom<input value={form.prenom} onChange={(e) => setForm({ ...form, prenom: e.target.value })} required /></label>
          <label>Filiale / entite
            <select value={form.entite_id} onChange={(e) => setForm({ ...form, entite_id: e.target.value })}>
              <option value="">-</option>
              {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
            </select>
          </label>
          <label>Service<input value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} /></label>
          <label>Statut
            <select value={form.statut} onChange={(e) => setForm({ ...form, statut: e.target.value })}>
              {STATUTS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Date d'arrivee<input type="date" value={form.date_arrivee} onChange={(e) => setForm({ ...form, date_arrivee: e.target.value })} /></label>
          <label>Date de sortie<input type="date" value={form.date_sortie} onChange={(e) => setForm({ ...form, date_sortie: e.target.value })} /></label>
          <div style={{ alignSelf: "end" }}><button type="submit">Ajouter</button></div>
        </form>
      </div>
      )}
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <input placeholder="Rechercher nom / prenom / matricule" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <table>
          <thead><tr><th>Matricule</th><th>Nom</th><th>Filiale</th><th>Service</th><th>Statut</th><th>Arrivee</th></tr></thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td>{u.matricule || "-"}</td>
                <td>{u.prenom} {u.nom}</td>
                <td>{entiteNom(u.entite_id)}</td>
                <td>{u.service || "-"}</td>
                <td><span className="badge">{u.statut}</span></td>
                <td>{u.date_arrivee || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
