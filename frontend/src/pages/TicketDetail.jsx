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
import ConfirmButton from "../components/ConfirmButton.jsx";
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

function utcToLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function heuresRestantes72h(iso) {
  if (!iso) return null;
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return null;
  const ms = (d.getTime() + 72 * 3600 * 1000) - Date.now();
  return Math.round(ms / (3600 * 1000));
}

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
  const [securite, setSecurite] = useState(null);
  const [secForm, setSecForm] = useState({
    sous_categorie: "",
    violation_donnees_potentielle: false,
    date_decouverte_violation: "",
    notification_dpo_le: "",
    notification_cnil_requise: "a_evaluer",
    confine_le: "",
    cause_racine: "",
    actions_correctives: "",
  });
  const [natures, setNatures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [contenu, setContenu] = useState("");
  const [interne, setInterne] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [thumbs, setThumbs] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, n, sec] = await Promise.all([
        api.get(`/tickets/${id}`),
        api.get("/tickets/natures?inclure_inactives=true"),
        api.get(`/tickets/${id}/securite`),
      ]);
      setTicket(t);
      setNatures((n || []).filter((x) => x.actif || x.code === t.nature_code));
      if (sec && sec.dossier !== null) {
        setSecurite(sec);
        setSecForm({
          sous_categorie: sec.sous_categorie || "",
          violation_donnees_potentielle: Boolean(sec.violation_donnees_potentielle),
          date_decouverte_violation: utcToLocalInput(sec.date_decouverte_violation),
          notification_dpo_le: utcToLocalInput(sec.notification_dpo_le),
          notification_cnil_requise: sec.notification_cnil_requise || "a_evaluer",
          confine_le: utcToLocalInput(sec.confine_le),
          cause_racine: sec.cause_racine || "",
          actions_correctives: sec.actions_correctives || "",
        });
      } else {
        setSecurite(null);
      }
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
    } catch (e2) {
      setErr(errorText(e2));
    } finally {
      setUploading(false);
    }
  };

  const onDeletePj = async (pjId) => {
    setErr(null); setMsg(null);
    try {
      await api.del(`/tickets/${id}/pieces-jointes/${pjId}`);
      setMsg("Piece jointe supprimee.");
      await load();
    } catch (e2) {
      setErr(errorText(e2));
    }
  };

  const changerNiveauSec = async (niveau) => {
    setErr(null); setMsg(null);
    try {
      await api.post(`/tickets/${id}/securite/niveau`, { niveau_securite: niveau });
      setMsg(`Niveau de securite passe a ${niveau}.`);
      rechargerCompteurs();
      await load();
    } catch (e2) { setErr(errorText(e2)); }
  };

  const sauverSecurite = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    try {
      await api.put(`/tickets/${id}/securite`, {
        sous_categorie: secForm.sous_categorie || null,
        violation_donnees_potentielle: secForm.violation_donnees_potentielle,
        date_decouverte_violation: secForm.date_decouverte_violation ? new Date(secForm.date_decouverte_violation).toISOString() : null,
        notification_dpo_le: secForm.notification_dpo_le ? new Date(secForm.notification_dpo_le).toISOString() : null,
        notification_cnil_requise: secForm.violation_donnees_potentielle ? secForm.notification_cnil_requise : null,
        confine_le: secForm.confine_le ? new Date(secForm.confine_le).toISOString() : null,
        cause_racine: secForm.cause_racine || null,
        actions_correctives: secForm.actions_correctives || null,
      });
      setMsg("Dossier securite enregistre.");
      await load();
    } catch (e2) { setErr(errorText(e2)); }
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

      <div className="card" style={ticket.niveau_securite !== "aucun" ? { borderColor: "var(--danger)" } : undefined}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Securite et dossier d'investigation (IT uniquement)</h3>
          <span className={`badge ${ticket.niveau_securite === "signale" || ticket.niveau_securite === "incident" ? "bad" : ""}`}>
            Niveau : {ticket.niveau_securite}
          </span>
        </div>
        {!estFinal && (
          <div className="row" style={{ marginBottom: 12 }}>
            {ticket.niveau_securite === "aucun" && <button type="button" className="ghost" onClick={() => changerNiveauSec("signale")}>Signaler un evenement de securite</button>}
            {ticket.niveau_securite === "signale" && (
              <>
                <button type="button" className="danger" onClick={() => changerNiveauSec("incident")}>Escalader en incident</button>
                <button type="button" className="ghost" onClick={() => changerNiveauSec("sans_suite")}>Classer sans suite</button>
              </>
            )}
            {ticket.niveau_securite === "incident" && (
              <>
                <button type="button" className="ghost" onClick={() => changerNiveauSec("sans_suite")}>Retrograder sans suite</button>
                <button type="button" className="ghost" onClick={() => changerNiveauSec("signale")}>Retrograder en signale</button>
              </>
            )}
            {ticket.niveau_securite === "sans_suite" && (
              <>
                <button type="button" className="ghost" onClick={() => changerNiveauSec("signale")}>Reprendre en signale</button>
                <button type="button" className="danger" onClick={() => changerNiveauSec("incident")}>Escalader en incident</button>
              </>
            )}
          </div>
        )}
        {securite && (
          <form className="grid" onSubmit={sauverSecurite}>
            <label>Sous-categorie
              <select value={secForm.sous_categorie} onChange={(e) => setSecForm({ ...secForm, sous_categorie: e.target.value })}>
                <option value="">- Non precisee -</option>
                <option value="phishing">Phishing</option>
                <option value="perte_vol_materiel">Perte / vol de materiel</option>
                <option value="malware">Malware</option>
                <option value="acces_non_autorise">Acces non autorise</option>
                <option value="fuite_donnees">Fuite de donnees</option>
                <option value="autre">Autre</option>
              </select>
            </label>
            <label>Confinement termine le
              <input type="datetime-local" value={secForm.confine_le} onChange={(e) => setSecForm({ ...secForm, confine_le: e.target.value })} />
            </label>
            <label className="check" style={{ gridColumn: "1 / -1" }}>
              <input type="checkbox" checked={secForm.violation_donnees_potentielle}
                onChange={(e) => setSecForm({ ...secForm, violation_donnees_potentielle: e.target.checked })} />
              Violation potentielle de donnees personnelles (suivi delai 72 h - RGPD art. 33)
            </label>
            {secForm.violation_donnees_potentielle && (
              <>
                {securite?.date_decouverte_violation && (
                  <div className="card warn" style={{ gridColumn: "1 / -1", marginBottom: 0 }}>
                    <strong>Suivi RGPD art. 33 (72 h) :</strong>{" "}
                    {(() => {
                      const h = heuresRestantes72h(securite.date_decouverte_violation);
                      return h !== null && h >= 0 ? `environ ${h} h restantes` : "delai indicatif de 72 h depasse";
                    })()}
                  </div>
                )}
                <label>Date de decouverte de la violation (obligatoire)
                  <input type="datetime-local" value={secForm.date_decouverte_violation}
                    onChange={(e) => setSecForm({ ...secForm, date_decouverte_violation: e.target.value })} required />
                </label>
                <label>Notification DPO le
                  <input type="datetime-local" value={secForm.notification_dpo_le}
                    onChange={(e) => setSecForm({ ...secForm, notification_dpo_le: e.target.value })} />
                </label>
                <label>Notification CNIL requise
                  <select value={secForm.notification_cnil_requise} onChange={(e) => setSecForm({ ...secForm, notification_cnil_requise: e.target.value })}>
                    <option value="a_evaluer">A evaluer (bloque la cloture)</option>
                    <option value="oui">Oui</option>
                    <option value="non">Non</option>
                  </select>
                </label>
                <div />
              </>
            )}
            <label style={{ gridColumn: "1 / -1" }}>Cause racine (rediger sans nommer aucune personne)
              <textarea rows={2} value={secForm.cause_racine} onChange={(e) => setSecForm({ ...secForm, cause_racine: e.target.value })} maxLength={3000} />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>Actions correctives (rediger sans nommer aucune personne)
              <textarea rows={2} value={secForm.actions_correctives} onChange={(e) => setSecForm({ ...secForm, actions_correctives: e.target.value })} maxLength={3000} />
            </label>
            <div className="row" style={{ gridColumn: "1 / -1" }}>
              <button type="submit">Enregistrer le dossier securite</button>
            </div>
          </form>
        )}
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Pieces jointes ({(ticket.pieces_jointes || []).length} / 5)</h3>
          {!estFinal && (ticket.pieces_jointes || []).length < 5 && (
            <label className="ghost" style={{ cursor: "pointer" }}>
              <input type="file" onChange={onUpload} disabled={uploading} style={{ display: "none" }}
                accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.log" />
              <span className="chip">{uploading ? "Envoi..." : "+ Ajouter un fichier"}</span>
            </label>
          )}
        </div>
        <p className="muted" style={{ marginTop: 0 }}>Formats autorises : PNG, JPEG, WEBP (re-encodes sans EXIF), PDF, TXT, LOG.</p>
        {(ticket.pieces_jointes || []).length === 0 ? (
          <p className="muted">Aucune piece jointe.</p>
        ) : (
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
                <div className="row">
                  <button type="button" className="ghost btn-petit" onClick={() => downloadFile(`/tickets/${id}/pieces-jointes/${pj.id}`, pj.display_name).catch((e) => setErr(errorText(e)))}>
                    Telecharger
                  </button>
                  {!estFinal && (
                    <ConfirmButton confirmLabel="Supprimer" onConfirm={() => onDeletePj(pj.id)}>Supprimer</ConfirmButton>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
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
