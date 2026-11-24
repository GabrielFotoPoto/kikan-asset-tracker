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
import { Link, useParams } from "react-router-dom";
import { api, errorText } from "../api.js";
import { Feedback } from "../components/Notifications.jsx";
import { Loading } from "../components/State.jsx";
import { useCompteurs } from "../compteurs.jsx";

const TRANSITIONS = {
  nouveau: [
    { statut: "en_cours", label: "Prendre en charge" },
    { statut: "annule", label: "Annuler", ghost: true },
  ],
  en_cours: [
    { statut: "en_attente", label: "Mettre en attente", ghost: true },
    { statut: "resolu", label: "Marquer resolu" },
  ],
  en_attente: [
    { statut: "en_cours", label: "Reprendre en cours" },
  ],
  resolu: [
    { statut: "ferme", label: "Fermer definitivement" },
    { statut: "en_cours", label: "Reouvrir", ghost: true },
  ],
  ferme: [],
  annule: [],
};

function formatDuree(sec) {
  if (sec === null || sec === undefined) return "-";
  if (sec < 60) return `${sec} s`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const rem = min % 60;
  return `${h} h ${rem} min`;
}

export default function TicketDetail() {
  const { id } = useParams();
  const { recharger: rechargerCompteurs } = useCompteurs();
  const [ticket, setTicket] = useState(null);
  const [natures, setNatures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [contenu, setContenu] = useState("");
  const [interne, setInterne] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, n] = await Promise.all([api.get(`/tickets/${id}`), api.get("/tickets/natures?inclure_inactives=true")]);
      setTicket(t);
      setNatures((n || []).filter((x) => x.actif || x.code === t.nature_code));
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const transition = async (nouveauStatut) => {
    setErr(null); setMsg(null);
    try {
      await api.post(`/tickets/${id}/statut`, { statut: nouveauStatut });
      setMsg(`Statut passe a ${nouveauStatut}.`);
      rechargerCompteurs();
      await load();
    } catch (e) {
      setErr(errorText(e));
    }
  };

  const qualifier = async (patch) => {
    setErr(null); setMsg(null);
    try {
      await api.put(`/tickets/${id}`, patch);
      setMsg("Ticket mis a jour.");
      await load();
    } catch (e) {
      setErr(errorText(e));
    }
  };

  const publier = async (e) => {
    e.preventDefault();
    if (!contenu.trim()) return;
    setErr(null); setMsg(null);
    try {
      await api.post(`/tickets/${id}/commentaires`, { contenu, interne });
      setContenu("");
      setMsg(interne ? "Note interne ajoutee." : "Reponse publique publiee.");
      await load();
    } catch (e2) {
      setErr(errorText(e2));
    }
  };

  if (loading) return <Loading />;
  if (!ticket) return <div><Feedback err={err || "Ticket introuvable."} /><Link to="/tickets">Retour aux tickets</Link></div>;

  const estFinal = ticket.statut === "ferme" || ticket.statut === "annule";
  const actions = TRANSITIONS[ticket.statut] || [];

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <Link to="/tickets">&larr; Retour aux tickets</Link>
          <h2 style={{ margin: "6px 0 2px" }}>{ticket.reference} - {ticket.titre}</h2>
          <div className="row">
            <span className="badge">{ticket.statut}</span>
            <span className={`badge ${ticket.criticite === "critique" || ticket.criticite === "haute" ? "bad" : ""}`}>
              Criticite : {ticket.criticite}
            </span>
            {ticket.niveau_securite !== "aucun" && (
              <span className="badge bad">Securite : {ticket.niveau_securite}</span>
            )}
            <span className="badge">Canal : {ticket.canal}</span>
          </div>
        </div>
        <div className="row">
          {actions.map((a) => (
            <button key={a.statut} className={a.ghost ? "ghost" : ""} onClick={() => transition(a.statut)}>
              {a.label}
            </button>
          ))}
        </div>
      </div>

      <Feedback err={err} msg={msg} />

      {!ticket.demandeur_verifie && (
        <div className="card warn">
          <strong>Expediteur non verifie :</strong> ce ticket provient d'un canal externe ({ticket.canal}).{" "}
          {!estFinal && (
            <button className="btn-petit" onClick={() => qualifier({ demandeur_verifie: true })}>
              Confirmer le demandeur
            </button>
          )}
        </div>
      )}

      <div className="card">
        <h3>Informations & qualification</h3>
        <div className="grid">
          <div><span className="muted">Salarie :</span> <strong>{ticket.user_nom || "Interne IT"}</strong></div>
          <div><span className="muted">Entite :</span> {ticket.entite_nom || "-"}</div>
          <div><span className="muted">Materiel :</span> {ticket.materiel_modele ? `${ticket.materiel_marque || ""} ${ticket.materiel_modele}` : "-"}</div>
          <div><span className="muted">Assigne a :</span> {ticket.assigne_a || "-"}</div>
          <div><span className="muted">MTTA :</span> {formatDuree(ticket.mtta_sec)}</div>
          <div><span className="muted">MTTR net :</span> {formatDuree(ticket.mttr_sec)}</div>
          {!estFinal && (
            <>
              <label>Nature
                <select value={ticket.nature_code} onChange={(e) => qualifier({ nature_code: e.target.value })}>
                  {natures.map((n) => <option key={n.code} value={n.code}>{n.libelle}</option>)}
                </select>
              </label>
              <label>Criticite qualifiee
                <select value={ticket.criticite} onChange={(e) => qualifier({ criticite: e.target.value })}>
                  <option value="faible">Faible</option>
                  <option value="moyenne">Moyenne</option>
                  <option value="haute">Haute</option>
                  <option value="critique">Critique</option>
                </select>
              </label>
            </>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Description</h3>
        <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{ticket.description || <span className="muted">Aucune description.</span>}</p>
      </div>

      <div className="card">
        <h3>Echanges et notes internes</h3>
        {(ticket.commentaires || []).length === 0 ? (
          <p className="muted">Aucun commentaire pour le moment.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
            {ticket.commentaires.map((c) => (
              <div key={c.id} className={c.interne ? "card warn" : "card"} style={{ marginBottom: 0 }}>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
                  <strong>{c.auteur || "Informatique"} {c.interne ? "(Note interne IT - invisible du salarie)" : "(Public)"}</strong>
                  <span className="muted">{c.cree_le}</span>
                </div>
                <div style={{ whiteSpace: "pre-wrap" }}>{c.contenu}</div>
              </div>
            ))}
          </div>
        )}

        {!estFinal && (
          <form onSubmit={publier} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="row">
              <button type="button" className={!interne ? "" : "ghost"} onClick={() => setInterne(false)}>Reponse publique</button>
              <button type="button" className={interne ? "" : "ghost"} onClick={() => setInterne(true)}>Note interne IT</button>
            </div>
            <textarea rows={3} value={contenu} onChange={(e) => setContenu(e.target.value)} maxLength={4000}
              placeholder={interne ? "Note interne (invisible du salarie, aucun e-mail envoye)..." : "Reponse publique (texte brut)..."} required />
            <div className="row">
              <button type="submit">{interne ? "Enregistrer la note interne" : "Publier la reponse"}</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
