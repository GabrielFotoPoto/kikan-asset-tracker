/*
 * Kikan - suivi des actifs et remise de materiel signee
 * Copyright (C) 2026 Gabriel Chollet
 * Developpe avec l'assistance d'une IA (Gemini, Google DeepMind).
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

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, errorText } from "../api.js";
import { Feedback } from "../components/Notifications.jsx";
import { Empty, Loading } from "../components/State.jsx";
import { formaterDateHeure, libelleStatutTicket } from "../format.js";

export default function MesTickets() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [natures, setNatures] = useState([]);
  const [materiel, setMateriel] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [showForm, setShowForm] = useState(() => searchParams.get("nouveau") === "1");
  const [form, setForm] = useState({
    nature_code: "panne_materiel",
    criticite: "moyenne",
    asset_id: searchParams.get("asset") || "",
    titre: "",
    description: "",
    signaler_securite: false,
  });

  useEffect(() => {
    if (searchParams.get("nouveau") === "1") {
      setShowForm(true);
      const a = searchParams.get("asset");
      if (a) setForm((f) => ({ ...f, asset_id: a }));
    }
  }, [searchParams]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, n, m] = await Promise.all([
        api.get("/tickets"),
        api.get("/tickets/natures"),
        api.get("/mon-espace/materiel"),
      ]);
      setItems(t.items || []);
      setNatures(n || []);
      setMateriel(m || []);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onNatureChange = (code) => {
    const nat = natures.find((n) => n.code === code);
    setForm((f) => ({ ...f, nature_code: code, signaler_securite: nat?.signale_securite ? true : f.signaler_securite }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    try {
      const created = await api.post("/tickets", {
        nature_code: form.nature_code,
        criticite: form.criticite,
        asset_id: form.asset_id ? Number(form.asset_id) : null,
        titre: form.titre,
        description: form.description || null,
        signaler_securite: form.signaler_securite,
      });
      setShowForm(false);
      setSearchParams({});
      navigate(`/mes-tickets/${created.id}`);
    } catch (e2) {
      setErr(errorText(e2));
    }
  };

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <h2 style={{ margin: 0 }}>Mes tickets</h2>
        <button onClick={() => setShowForm((s) => !s)}>{showForm ? "Fermer" : "+ Ouvrir un ticket"}</button>
      </div>
      <Feedback err={err} />

      {showForm && (
        <div className="card">
          <h3>Ouvrir un ticket</h3>
          <p className="muted">Ne saisissez jamais de mot de passe ni de donnee personnelle non necessaire.</p>
          <form className="grid" onSubmit={submit}>
            <label>Nature de la demande
              <select value={form.nature_code} onChange={(e) => onNatureChange(e.target.value)} required>
                {natures.map((n) => <option key={n.code} value={n.code}>{n.libelle}</option>)}
              </select>
            </label>
            <label>Urgence ressentie
              <select value={form.criticite} onChange={(e) => setForm({ ...form, criticite: e.target.value })}>
                <option value="faible">Faible</option>
                <option value="moyenne">Moyenne</option>
                <option value="haute">Haute</option>
                <option value="critique">Critique</option>
              </select>
            </label>
            <label style={{ gridColumn: "1 / -1" }}>Materiel concerne (vos actifs affectes)
              <select value={form.asset_id} onChange={(e) => setForm({ ...form, asset_id: e.target.value })}>
                <option value="">- Aucun materiel specifique -</option>
                {materiel.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.type} - {a.marque} {a.modele} ({a.identifiant_interne || a.numero_serie || `#${a.id}`})
                  </option>
                ))}
              </select>
            </label>
            <label style={{ gridColumn: "1 / -1" }}>Objet
              <input value={form.titre} onChange={(e) => setForm({ ...form, titre: e.target.value })} maxLength={200} required />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>Description
              <textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={5000} />
            </label>
            <label className="check" style={{ gridColumn: "1 / -1" }}>
              <input type="checkbox" checked={form.signaler_securite}
                onChange={(e) => setForm({ ...form, signaler_securite: e.target.checked })} />
              Cela concerne un evenement de securite (phishing, perte/vol, acces suspect...)
            </label>
            {form.signaler_securite && (
              <div className="card warn" style={{ gridColumn: "1 / -1", marginBottom: 0 }}>
                En cas d'urgence critique (perte/vol immediat ou suspicion de compromission), appelez directement l'astreinte informatique. Ne collez aucun mot de passe.
              </div>
            )}
            <div className="row" style={{ gridColumn: "1 / -1" }}>
              <button type="submit">Envoyer le ticket</button>
              <button type="button" className="ghost" onClick={() => setShowForm(false)}>Annuler</button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        {loading ? <Loading /> : items.length === 0 ? <Empty message="Vous n'avez aucun ticket pour le moment." /> : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Reference</th><th>Objet</th><th>Statut</th><th>Derniere mise a jour</th></tr>
              </thead>
              <tbody>
                {items.map((t) => (
                  <tr key={t.id}>
                    <td><Link to={`/mes-tickets/${t.id}`}><strong>{t.reference}</strong></Link></td>
                    <td>
                      <div><Link to={`/mes-tickets/${t.id}`}>{t.titre}</Link></div>
                      <div className="muted">
                        {t.nature_libelle}
                        {t.signalement_securite && <span className="badge" style={{ marginLeft: 6 }}>Signalement de securite pris en compte</span>}
                      </div>
                    </td>
                    <td><span className={`badge ${t.statut === "resolu" || t.statut === "ferme" ? "ok" : t.statut === "en_attente" ? "warn" : ""}`}>{libelleStatutTicket(t.statut)}</span></td>
                    <td className="muted">{formaterDateHeure(t.maj_publique_le)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
