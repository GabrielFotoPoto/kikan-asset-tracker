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
import { api, downloadFile, errorText, fetchDataUrl, postForm } from "../api.js";
import { Feedback } from "../components/Notifications.jsx";
import { Loading } from "../components/State.jsx";

export default function MonTicketDetail() {
  const { id } = useParams();
  const [ticket, setTicket] = useState(null);
  const [thumbs, setThumbs] = useState({});
  const [contenu, setContenu] = useState("");
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const t = await api.get(`/tickets/${id}`);
      setTicket(t);
      const imgs = (t.pieces_jointes || []).filter((p) => p.mime_type.startsWith("image/"));
      const map = {};
      await Promise.all(imgs.map(async (p) => {
        try { map[p.id] = await fetchDataUrl(`/tickets/${id}/pieces-jointes/${p.id}`); } catch { /* ignore */ }
      }));
      setThumbs(map);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const transition = async (st) => {
    setErr(null); setMsg(null);
    try {
      await api.post(`/tickets/${id}/statut`, { statut: st });
      setMsg("Ticket mis a jour.");
      await load();
    } catch (e) { setErr(errorText(e)); }
  };

  const publier = async (e) => {
    e.preventDefault();
    if (!contenu.trim()) return;
    setErr(null); setMsg(null);
    try {
      await api.post(`/tickets/${id}/commentaires`, { contenu, interne: false });
      setContenu("");
      setMsg("Reponse envoyee.");
      await load();
    } catch (e2) { setErr(errorText(e2)); }
  };

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setErr(null); setMsg(null); setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await postForm(`/tickets/${id}/pieces-jointes`, fd);
      setMsg("Piece jointe ajoutee.");
      await load();
    } catch (e2) { setErr(errorText(e2)); } finally { setUploading(false); }
  };

  if (loading) return <Loading />;
  if (!ticket) return <div><Feedback err={err || "Ticket introuvable."} /><Link to="/mes-tickets">Retour a Mes tickets</Link></div>;

  const estFinal = ticket.statut === "ferme" || ticket.statut === "annule";

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <Link to="/mes-tickets">&larr; Retour a Mes tickets</Link>
          <h2 style={{ margin: "6px 0 2px" }}>{ticket.reference} - {ticket.titre}</h2>
          <div className="row">
            <span className="badge">{ticket.statut}</span>
            {ticket.signalement_securite && <span className="badge">Signalement de securite pris en compte</span>}
          </div>
        </div>
        <div className="row">
          {ticket.statut === "nouveau" && <button className="ghost" onClick={() => transition("annule")}>Annuler le ticket</button>}
          {ticket.statut === "resolu" && (
            <>
              <button onClick={() => transition("ferme")}>Confirmer la cloture</button>
              <button className="ghost" onClick={() => transition("en_cours")}>Reouvrir</button>
            </>
          )}
        </div>
      </div>

      <Feedback err={err} msg={msg} />

      <div className="card">
        <h3>Description</h3>
        <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{ticket.description || <span className="muted">Aucune description.</span>}</p>
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Pieces jointes ({(ticket.pieces_jointes || []).length} / 5)</h3>
          {!estFinal && (ticket.pieces_jointes || []).length < 5 && (
            <label style={{ cursor: "pointer" }}>
              <input type="file" onChange={onUpload} disabled={uploading} style={{ display: "none" }}
                accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.log" />
              <span className="chip">{uploading ? "Envoi..." : "+ Ajouter un fichier"}</span>
            </label>
          )}
        </div>
        {(ticket.pieces_jointes || []).length === 0 ? <p className="muted">Aucune piece jointe.</p> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {ticket.pieces_jointes.map((pj) => (
              <div key={pj.id} className="row" style={{ justifyContent: "space-between", alignItems: "center", padding: 8, border: "1px solid var(--line)", borderRadius: 8 }}>
                <div className="row" style={{ alignItems: "center", gap: 10 }}>
                  {thumbs[pj.id] && <img src={thumbs[pj.id]} alt={pj.display_name} style={{ width: 44, height: 44, objectFit: "cover", borderRadius: 6 }} />}
                  <div>
                    <div><strong>{pj.display_name}</strong></div>
                    <div className="muted">{pj.mime_type} - {Math.max(1, Math.round(pj.size_bytes / 1024))} Kio</div>
                  </div>
                </div>
                <button type="button" className="ghost btn-petit" onClick={() => downloadFile(`/tickets/${id}/pieces-jointes/${pj.id}`, pj.display_name).catch((e) => setErr(errorText(e)))}>
                  Telecharger
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Echanges</h3>
        {(ticket.commentaires || []).length === 0 ? <p className="muted">Aucun echange pour le moment.</p> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
            {ticket.commentaires.map((c) => (
              <div key={c.id} className="card" style={{ marginBottom: 0 }}>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
                  <strong>{c.auteur}</strong>
                  <span className="muted">{c.cree_le}</span>
                </div>
                <div style={{ whiteSpace: "pre-wrap" }}>{c.contenu}</div>
              </div>
            ))}
          </div>
        )}
        {!estFinal && (
          <form onSubmit={publier} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <textarea rows={3} value={contenu} onChange={(e) => setContenu(e.target.value)} maxLength={4000}
              placeholder="Ajouter une precision..." required />
            <div className="row"><button type="submit">Envoyer</button></div>
          </form>
        )}
      </div>
    </div>
  );
}
