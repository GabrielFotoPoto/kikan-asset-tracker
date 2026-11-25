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
import { useCompteurs } from "../compteurs.jsx";
import {
  CRITICITE_TICKET_LABELS as CRITICITE_LABELS,
  STATUT_TICKET_LABELS as STATUT_LABELS,
  libelleCanalTicket,
  libelleSecuriteTicket,
} from "../format.js";
import { conserverAssetPourSalarie, listeMaterielProposee } from "../ticketsMateriel.js";

export default function Tickets() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { recharger: rechargerCompteurs } = useCompteurs();

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [compteurs, setCompteurs] = useState(null);
  const [natures, setNatures] = useState([]);
  const [users, setUsers] = useState([]);
  const [assets, setAssets] = useState([]);
  const [assetsSalarie, setAssetsSalarie] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const [statut, setStatut] = useState("");
  const [nature, setNature] = useState("");
  const [criticite, setCriticite] = useState("");
  const [securite, setSecurite] = useState("");
  const [q, setQ] = useState("");

  const [showForm, setShowForm] = useState(() => searchParams.get("nouveau") === "1");
  useEffect(() => {
    if (searchParams.get("nouveau") === "1") setShowForm(true);
  }, [searchParams]);
  const [form, setForm] = useState({
    nature_code: "panne_materiel",
    criticite: "moyenne",
    user_id: "",
    asset_id: "",
    materiel_hors_affectation: false,
    titre: "",
    description: "",
    signaler_securite: false,
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (statut) qs.set("statut", statut);
      if (nature) qs.set("nature", nature);
      if (criticite) qs.set("criticite", criticite);
      if (securite) qs.set("niveau_securite", securite);
      if (q.trim()) qs.set("q", q.trim());
      const [listRes, cptRes] = await Promise.all([
        api.get(`/tickets?${qs.toString()}`),
        api.get("/tickets/compteurs"),
      ]);
      setItems(listRes.items || []);
      setTotal(listRes.total || 0);
      setCompteurs(cptRes);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setLoading(false);
    }
  }, [statut, nature, criticite, securite, q]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    Promise.all([
      api.get("/tickets/natures"),
      api.get("/users?limit=500"),
      api.get("/assets?limit=500"),
    ]).then(([n, u, a]) => {
      setNatures(n || []);
      setUsers(Array.isArray(u) ? u : (u.items || []));
      setAssets(Array.isArray(a) ? a : (a.items || []));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const requestedUserId = form.user_id;
    if (!requestedUserId) {
      setAssetsSalarie([]);
      return;
    }
    let cancelled = false;
    setAssetsSalarie([]);
    api.get(`/tickets/materiel-salarie/${requestedUserId}`)
      .then((rows) => {
        if (cancelled) return;
        const list = Array.isArray(rows) ? rows : [];
        setAssetsSalarie(list);
        setForm((f) => {
          if (String(f.user_id) !== String(requestedUserId)) return f;
          return {
            ...f,
            asset_id: f.materiel_hors_affectation ? f.asset_id : conserverAssetPourSalarie(f.asset_id, list),
          };
        });
      })
      .catch(() => {
        if (!cancelled) setAssetsSalarie([]);
      });
    return () => { cancelled = true; };
  }, [form.user_id]);

  const onUserChange = (nextUserId) => {
    setForm((f) => ({
      ...f,
      user_id: nextUserId,
      asset_id: f.materiel_hors_affectation ? f.asset_id : "",
      materiel_hors_affectation: nextUserId ? f.materiel_hors_affectation : false,
    }));
  };

  const assetsVisibles = listeMaterielProposee({
    userId: form.user_id,
    assetsParc: assets,
    assetsSalarie,
    horsAffectation: form.materiel_hors_affectation,
  });

  const onNatureChange = (code) => {
    const nat = natures.find((n) => n.code === code);
    setForm((f) => ({ ...f, nature_code: code, signaler_securite: nat?.signale_securite ? true : f.signaler_securite }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const created = await api.post("/tickets", {
        nature_code: form.nature_code,
        criticite: form.criticite,
        user_id: form.user_id ? Number(form.user_id) : null,
        asset_id: form.asset_id ? Number(form.asset_id) : null,
        materiel_hors_affectation: Boolean(form.user_id && form.materiel_hors_affectation),
        titre: form.titre,
        description: form.description || null,
        signaler_securite: form.signaler_securite,
      });
      setShowForm(false);
      if (searchParams.get("nouveau")) setSearchParams({});
      rechargerCompteurs();
      navigate(`/tickets/${created.id}`);
    } catch (e2) {
      setErr(errorText(e2));
    }
  };

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <h2 style={{ margin: 0 }}>Tickets</h2>
        <button onClick={() => setShowForm((s) => !s)}>{showForm ? "Fermer le formulaire" : "+ Nouveau ticket"}</button>
      </div>

      <Feedback err={err} msg={msg} />

      {compteurs && (
        <div className="tiles" style={{ marginBottom: 18 }}>
          <div className="card" style={{ flex: "1 1 130px", marginBottom: 0 }}>
            <div className="muted">Nouveaux</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{compteurs.nouveaux}</div>
          </div>
          <div className="card" style={{ flex: "1 1 130px", marginBottom: 0 }}>
            <div className="muted">En cours</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{compteurs.en_cours}</div>
          </div>
          <div className="card" style={{ flex: "1 1 130px", marginBottom: 0 }}>
            <div className="muted">En attente</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{compteurs.en_attente}</div>
          </div>
          <div className="card" style={{ flex: "1 1 150px", marginBottom: 0 }}>
            <div className="muted">Securite a qualifier</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: compteurs.securite_a_qualifier ? "var(--danger)" : "inherit" }}>
              {compteurs.securite_a_qualifier}
            </div>
          </div>
          <div className="card" style={{ flex: "1 1 150px", marginBottom: 0 }}>
            <div className="muted">Delai cible depasse</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: compteurs.hors_delai ? "var(--warn)" : "inherit" }}>
              {compteurs.hors_delai}
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <div className="card">
          <h3>Nouveau ticket (saisie informatique)</h3>
          <p className="muted">Ne saisissez ni mot de passe ni donnee personnelle non necessaire.</p>
          <form className="grid" onSubmit={submit}>
            <label>Nature
              <select value={form.nature_code} onChange={(e) => onNatureChange(e.target.value)} required>
                {natures.map((n) => <option key={n.code} value={n.code}>{n.libelle}</option>)}
              </select>
            </label>
            <label>Criticite
              <select value={form.criticite} onChange={(e) => setForm({ ...form, criticite: e.target.value })}>
                {Object.entries(CRITICITE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label>Salarie (optionnel, vide = ticket interne IT)
              <select value={form.user_id} onChange={(e) => onUserChange(e.target.value)}>
                <option value="">- Aucun (interne IT) -</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.prenom} {u.nom} {u.matricule ? `(${u.matricule})` : ""}</option>)}
              </select>
            </label>
            <label>
              {form.user_id
                ? (form.materiel_hors_affectation ? "Materiel concerne (tout le parc - hors affectation)" : "Materiel concerne (affecte a ce salarie)")
                : "Materiel concerne (optionnel - tout le parc)"}
              <select value={form.asset_id} onChange={(e) => setForm({ ...form, asset_id: e.target.value })}>
                <option value="">- Aucun materiel -</option>
                {assetsVisibles.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.identifiant_interne || a.numero_serie || `#${a.id}`} - {a.marque} {a.modele}
                  </option>
                ))}
              </select>
            </label>
            {form.user_id && (
              <label className="check" style={{ gridColumn: "1 / -1" }}>
                <input
                  type="checkbox"
                  checked={form.materiel_hors_affectation}
                  onChange={(e) => {
                    const checked = e.target.checked;
                    setForm((f) => ({
                      ...f,
                      materiel_hors_affectation: checked,
                      asset_id: checked ? f.asset_id : conserverAssetPourSalarie(f.asset_id, assetsSalarie),
                    }));
                  }}
                />
                Autre materiel (hors affectation : materiel rendu, en preparation, perte/vol ou partage)
              </label>
            )}
            <label style={{ gridColumn: "1 / -1" }}>Titre
              <input value={form.titre} onChange={(e) => setForm({ ...form, titre: e.target.value })} maxLength={200} required />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>Description (texte brut)
              <textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={5000} />
            </label>
            <label className="check" style={{ gridColumn: "1 / -1" }}>
              <input type="checkbox" checked={form.signaler_securite} onChange={(e) => setForm({ ...form, signaler_securite: e.target.checked })} />
              Signaler comme evenement de securite
            </label>
            <div className="row" style={{ gridColumn: "1 / -1" }}>
              <button type="submit">Creer le ticket</button>
              <button type="button" className="ghost" onClick={() => setShowForm(false)}>Annuler</button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <div className="filtres" style={{ marginBottom: 14 }}>
          <select value={statut} onChange={(e) => setStatut(e.target.value)}>
            <option value="">Tous les statuts</option>
            {Object.entries(STATUT_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={nature} onChange={(e) => setNature(e.target.value)}>
            <option value="">Toutes les natures</option>
            {natures.map((n) => <option key={n.code} value={n.code}>{n.libelle}</option>)}
          </select>
          <select value={criticite} onChange={(e) => setCriticite(e.target.value)}>
            <option value="">Toutes les criticites</option>
            {Object.entries(CRITICITE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={securite} onChange={(e) => setSecurite(e.target.value)}>
            <option value="">Securite : tous</option>
            <option value="signale">A qualifier (signale)</option>
            <option value="incident">Incident</option>
            <option value="sans_suite">Sans suite</option>
            <option value="aucun">Ordinaires</option>
          </select>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher ref, titre, salarie..." />
        </div>

        {loading ? <Loading /> : items.length === 0 ? <Empty message="Aucun ticket ne correspond aux filtres." /> : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Titre & Nature</th>
                  <th>Salarie / Materiel</th>
                  <th>Criticite</th>
                  <th>Statut</th>
                  <th>Securite</th>
                </tr>
              </thead>
              <tbody>
                {items.map((t) => (
                  <tr key={t.id}>
                    <td><Link to={`/tickets/${t.id}`}><strong>{t.reference}</strong></Link></td>
                    <td>
                      <div><Link to={`/tickets/${t.id}`}>{t.titre}</Link></div>
                      <div className="muted">{t.nature_libelle} - {libelleCanalTicket(t.canal)}{!t.demandeur_verifie ? " (non verifie)" : ""}</div>
                    </td>
                    <td>
                      <div>{t.user_nom || <span className="muted">Interne IT</span>}</div>
                      {t.materiel_modele && <div className="muted">{t.materiel_marque} {t.materiel_modele}</div>}
                    </td>
                    <td>
                      <span className={`badge ${t.criticite === "critique" || t.criticite === "haute" ? "bad" : t.criticite === "moyenne" ? "warn" : ""}`}>
                        {CRITICITE_LABELS[t.criticite] || t.criticite}
                      </span>
                    </td>
                    <td>
                      <div className="badge-group">
                        <span className={`badge ${t.statut === "resolu" || t.statut === "ferme" ? "ok" : t.statut === "en_attente" ? "warn" : ""}`}>
                          {STATUT_LABELS[t.statut] || t.statut}
                        </span>
                        {t.hors_delai && <span className="badge warn">Hors delai</span>}
                      </div>
                    </td>
                    <td>
                      {t.niveau_securite !== "aucun" ? (
                        <span className={`badge ${t.niveau_securite === "sans_suite" ? "" : "bad"}`}>
                          {libelleSecuriteTicket(t.niveau_securite)}
                        </span>
                      ) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted" style={{ marginTop: 10 }}>{total} ticket(s)</p>
      </div>
    </div>
  );
}
