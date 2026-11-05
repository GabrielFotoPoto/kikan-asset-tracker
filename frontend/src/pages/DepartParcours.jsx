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
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, errorText } from "../api.js";
import { useAuth } from "../auth.jsx";
import { EncartProchaineAction, EtapesParcours, JournalParcours, PastilleParcours } from "../components/EtapesParcours.jsx";
import { ErrorState, Loading } from "../components/State.jsx";
import { MOTIFS_NON_RESTITUTION, formaterQuand, libelleMotif } from "../parcours.js";

// Parcours de depart d'un salarie (SPEC.md 6.3bis) : parcours calcule par GET /parcours/depart/{id}.
// Voie d'exception : constat de non-restitution (informatique) et cloture sans materiel (RH/informatique).
const ACTIONS_DEPART = {
  depart: "Declarer le depart",
  restitution: "Restituer et signer",
  sorti: "Cloturer le depart",
};

export default function DepartParcours() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  // Etat du constat de non-restitution (informatique)
  const [constatOpen, setConstatOpen] = useState(false);
  const [selAssets, setSelAssets] = useState(new Set());
  const [motif, setMotif] = useState("perte");
  const [confirmeConstat, setConfirmeConstat] = useState(false);
  const [busyConstat, setBusyConstat] = useState(false);
  const [errConstat, setErrConstat] = useState(null);

  // Etat de la cloture sans materiel (RH ou informatique)
  const [clotureOpen, setClotureOpen] = useState(false);
  const [busyCloture, setBusyCloture] = useState(false);
  const [errCloture, setErrCloture] = useState(null);

  const load = () => {
    setErr(null);
    api.get(`/parcours/depart/${id}`).then(setData).catch((e) => setErr(errorText(e)));
  };
  useEffect(() => { setData(null); load(); }, [id]);

  if (err) return <div><h2>Parcours de depart</h2><ErrorState message={err} onRetry={load} /></div>;
  if (!data) return <div><h2>Parcours de depart</h2><Loading label="Chargement du parcours" /></div>;

  const s = data.salarie;
  const mats = data.materiel_a_recuperer || [];
  const nr = data.materiels_non_restitues || [];
  const estEnDepart = s.statut === "en_depart";
  const peutConstater = user.role === "informatique" && estEnDepart && mats.length > 0;

  const ouvrirConstat = () => {
    setSelAssets(new Set(mats.map((a) => a.id)));
    setMotif("perte");
    setConfirmeConstat(false);
    setErrConstat(null);
    setConstatOpen(true);
  };

  const toggleAsset = (aid) => {
    const next = new Set(selAssets);
    if (next.has(aid)) next.delete(aid);
    else next.add(aid);
    setSelAssets(next);
  };

  const validerConstat = async (e) => {
    e.preventDefault();
    if (selAssets.size === 0 || !confirmeConstat) return;
    setBusyConstat(true);
    setErrConstat(null);
    try {
      await api.post("/lifecycle/non-restitue", {
        user_id: Number(id),
        asset_ids: Array.from(selAssets),
        motif,
      });
      setConstatOpen(false);
      load();
    } catch (ex) {
      setErrConstat(errorText(ex));
    } finally {
      setBusyConstat(false);
    }
  };

  const validerCloture = async () => {
    setBusyCloture(true);
    setErrCloture(null);
    try {
      await api.post(`/lifecycle/depart/${id}/cloturer`);
      setClotureOpen(false);
      load();
    } catch (ex) {
      setErrCloture(errorText(ex));
    } finally {
      setBusyCloture(false);
    }
  };

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>Depart de {s.prenom} {s.nom}</h2>
          <p className="muted" style={{ margin: 0 }}>
            {[s.service, s.date_sortie ? `sortie prevue le ${s.date_sortie}` : "aucune date de sortie declaree", `statut ${s.statut}`].filter(Boolean).join(" - ")}
          </p>
        </div>
        <PastilleParcours etapes={data.etapes} etapeCourante={data.etape_courante} reserves={data.reserves} />
      </div>

      <EtapesParcours etapes={data.etapes} etapeCourante={data.etape_courante} />

      {clotureOpen && (
        <div className="card" role="alertdialog" aria-label="Confirmation de cloture du depart" style={{ borderColor: "var(--color-primary)" }}>
          <h3>Cloturer le depart de {s.prenom} {s.nom} ?</h3>
          <p className="muted" style={{ margin: "4px 0 12px" }}>
            Ce salarie ne detient plus aucun materiel. La cloture passera definitivement son statut a Sorti.
          </p>
          {errCloture && <p className="err" role="alert" style={{ marginBottom: 12 }}>{errCloture}</p>}
          <div className="row" style={{ gap: 8 }}>
            <button type="button" onClick={validerCloture} disabled={busyCloture}>
              {busyCloture ? "Cloture en cours..." : "Confirmer la cloture"}
            </button>
            <button type="button" className="ghost" onClick={() => setClotureOpen(false)} disabled={busyCloture}>
              Annuler
            </button>
          </div>
        </div>
      )}

      {constatOpen && (
        <div className="card" role="dialog" aria-label="Constat de materiel non restitue" style={{ borderColor: "#d97706" }}>
          <h3 style={{ marginTop: 0 }}>Constat de non-restitution (informatique seule)</h3>
          <p className="muted" style={{ margin: "4px 0 12px" }}>
            Action exceptionnelle constatee pour un salarie parti avec du materiel qui ne sera pas recupere. L'actif passe au statut non restitue et sort des renouvellements.
          </p>

          <form onSubmit={validerConstat}>
            <div style={{ marginBottom: 12 }}>
              <strong>Selectionner les materiels non restitues :</strong>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
                {mats.map((a) => (
                  <label key={a.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      type="checkbox"
                      checked={selAssets.has(a.id)}
                      onChange={() => toggleAsset(a.id)}
                    />
                    <span>
                      <strong>{a.type}</strong> {[a.marque, a.modele].filter(Boolean).join(" ")}
                      {a.numero_serie ? <span className="muted">{` - S/N ${a.numero_serie}`}</span> : null}
                      {a.identifiant_interne ? <span className="badge" style={{ marginLeft: 6 }}>{a.identifiant_interne}</span> : null}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <label htmlFor="motif-select">
                <strong>Motif de non-restitution (obligatoire) :</strong>
              </label>
              <select
                id="motif-select"
                value={motif}
                onChange={(e) => setMotif(e.target.value)}
                style={{ marginTop: 4, display: "block", maxWidth: 300 }}
              >
                {MOTIFS_NON_RESTITUTION.map((m) => (
                  <option key={m.code} value={m.code}>{m.label}</option>
                ))}
              </select>
            </div>

            <div className="card" style={{ backgroundColor: "#fffbeb", borderColor: "#fef3c7", padding: "10px 14px", marginBottom: 12 }}>
              <p style={{ margin: 0, fontSize: "0.92rem" }}>
                <strong>Recapitulatif :</strong> {selAssets.size} materiel(s) constate(s) non restitue(s).
                {selAssets.size === mats.length
                  ? " Tous les materiels etant traites, le salarie passera automatiquement au statut Sorti avec reserve."
                  : " Il restera du materiel affecte a ce salarie."}
              </p>
            </div>

            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 16 }}>
              <input
                type="checkbox"
                id="confirme-constat"
                checked={confirmeConstat}
                onChange={(e) => setConfirmeConstat(e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                Je confirme le constat d'impossibilite de restitution pour ce(s) materiel(s). Cette action est irreversible et consignee au journal d'audit.
              </span>
            </label>

            {errConstat && <p className="err" role="alert" style={{ marginBottom: 12 }}>{errConstat}</p>}

            <div className="row" style={{ gap: 8 }}>
              <button type="submit" disabled={selAssets.size === 0 || !confirmeConstat || busyConstat}>
                {busyConstat ? "Enregistrement..." : "Valider le constat"}
              </button>
              <button type="button" className="ghost" onClick={() => setConstatOpen(false)} disabled={busyConstat}>
                Annuler
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="deux-colonnes">
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Materiel a recuperer ({mats.length})</h3>
            {peutConstater && !constatOpen && (
              <button type="button" className="ghost" style={{ fontSize: "0.85rem", padding: "4px 8px" }} onClick={ouvrirConstat}>
                Constater une non-restitution...
              </button>
            )}
          </div>

          {mats.length === 0 ? (
            <p className="muted" style={{ marginTop: 8 }}>Aucun materiel actuellement detenu par ce salarie.</p>
          ) : (
            <ul className="liste-simple" style={{ marginTop: 8 }}>
              {mats.map((a) => (
                <li key={a.id}>
                  <span>
                    <strong>{a.type}</strong> {[a.marque, a.modele].filter(Boolean).join(" ")}
                    {a.numero_serie ? <span className="muted">{` - S/N ${a.numero_serie}`}</span> : null}
                  </span>
                  {a.identifiant_interne ? <span className="badge">{a.identifiant_interne}</span> : null}
                </li>
              ))}
            </ul>
          )}

          {user.role === "informatique" && nr.length > 0 && (
            <div style={{ marginTop: 16, borderTop: "1px solid var(--color-border)", paddingTop: 12 }}>
              <h4 style={{ margin: "0 0 8px", fontSize: "0.95rem" }}>
                Materiel(s) non restitue(s) ({nr.length})
              </h4>
              <ul className="liste-simple">
                {nr.map((a) => (
                  <li key={a.id}>
                    <span>
                      <strong>{a.type}</strong> {[a.marque, a.modele].filter(Boolean).join(" ")}
                      {a.numero_serie ? <span className="muted">{` - S/N ${a.numero_serie}`}</span> : null}
                      <span className="muted">{` - Motif : ${libelleMotif(a.motif)}`}</span>
                      {a.constate_le ? <span className="muted">{` (${formaterQuand(a.constate_le)})`}</span> : null}
                    </span>
                    <span className="badge" style={{ backgroundColor: "#fef3c7", color: "#92400e" }}>non restitue</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="muted" style={{ marginTop: 12, marginBottom: 0 }}>
            {data.acces_restants > 0 ? (
              <>
                <strong>{data.acces_restants} acces applicatif(s) actif(s)</strong> a retirer (etape informative) -{" "}
                <Link to="/acces">ouvrir Acces applicatifs</Link>.
              </>
            ) : (
              "Aucun acces applicatif actif."
            )}
          </p>
        </div>
        <JournalParcours journal={data.journal} />
      </div>

      <EncartProchaineAction
        action={data.prochaine_action}
        role={user.role}
        libellesBouton={ACTIONS_DEPART}
        onNaviguer={navigate}
        onAction={(actId) => {
          if (actId === "cloturer_depart") {
            setClotureOpen(true);
          }
        }}
        reserves={data.reserves}
        texteTermine="materiel restitue et salarie sorti."
      />
    </div>
  );
}
