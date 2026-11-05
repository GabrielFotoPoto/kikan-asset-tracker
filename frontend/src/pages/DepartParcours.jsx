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

import { useEffect, useRef, useState } from "react";
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
  const constatRef = useRef(null);
  const btnConstatRef = useRef(null);

  // Etat de la cloture sans materiel (RH ou informatique)
  const [clotureOpen, setClotureOpen] = useState(false);
  const [busyCloture, setBusyCloture] = useState(false);
  const [errCloture, setErrCloture] = useState(null);
  const clotureRef = useRef(null);
  const origineClotureRef = useRef(null);

  const load = () => {
    setErr(null);
    api.get(`/parcours/depart/${id}`).then(setData).catch((e) => setErr(errorText(e)));
  };
  useEffect(() => { setData(null); load(); }, [id]);

  useEffect(() => {
    if (constatOpen && constatRef.current) {
      constatRef.current.focus();
    }
  }, [constatOpen]);

  useEffect(() => {
    if (clotureOpen && clotureRef.current) {
      clotureRef.current.focus();
    }
  }, [clotureOpen]);

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

  const fermerConstat = () => {
    setConstatOpen(false);
    if (btnConstatRef.current) btnConstatRef.current.focus();
  };

  const ouvrirCloture = () => {
    origineClotureRef.current = document.activeElement;
    setErrCloture(null);
    setClotureOpen(true);
  };

  const fermerCloture = () => {
    setClotureOpen(false);
    if (origineClotureRef.current && typeof origineClotureRef.current.focus === "function") {
      origineClotureRef.current.focus();
    }
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
      <div className="row entete-parcours">
        <div>
          <h2 className="mb4">Depart de {s.prenom} {s.nom}</h2>
          <p className="muted m0">
            {[s.service, s.date_sortie ? `sortie prevue le ${s.date_sortie}` : "aucune date de sortie declaree", `statut ${s.statut}`].filter(Boolean).join(" - ")}
          </p>
        </div>
        <PastilleParcours etapes={data.etapes} etapeCourante={data.etape_courante} reserves={data.reserves} />
      </div>

      <EtapesParcours etapes={data.etapes} etapeCourante={data.etape_courante} />

      {clotureOpen && (
        <section
          className="card panneau-confirmation"
          aria-labelledby="titre-cloture"
          tabIndex={-1}
          ref={clotureRef}
          onKeyDown={(e) => {
            if (e.key === "Escape" && !busyCloture) fermerCloture();
          }}
        >
          <h3 id="titre-cloture">Cloturer le depart de {s.prenom} {s.nom} ?</h3>
          <p className="muted constat-bloc">
            Ce salarie ne detient plus aucun materiel. La cloture passera definitivement son statut a Sorti.
          </p>
          {errCloture && <p className="err constat-bloc" role="alert">{errCloture}</p>}
          <div className="row">
            <button type="button" onClick={validerCloture} disabled={busyCloture} aria-busy={busyCloture}>
              {busyCloture ? "Cloture en cours..." : "Confirmer la cloture"}
            </button>
            <button type="button" className="ghost" onClick={fermerCloture} disabled={busyCloture}>
              Annuler
            </button>
          </div>
        </section>
      )}

      {constatOpen && (
        <section
          className="card panneau-constat"
          aria-labelledby="titre-constat"
          tabIndex={-1}
          ref={constatRef}
          onKeyDown={(e) => {
            if (e.key === "Escape" && !busyConstat) fermerConstat();
          }}
        >
          <h3 id="titre-constat">Constat de non-restitution (informatique seule)</h3>
          <p className="muted constat-bloc">
            Action exceptionnelle constatee pour un salarie parti avec du materiel qui ne sera pas recupere. L'actif passe au statut non restitue et sort des renouvellements.
          </p>

          <form onSubmit={validerConstat}>
            <div className="constat-bloc">
              <strong>Selectionner les materiels non restitues :</strong>
              <div className="constat-actifs">
                {mats.map((a) => (
                  <label key={a.id} className="constat-choix">
                    <input
                      type="checkbox"
                      checked={selAssets.has(a.id)}
                      onChange={() => toggleAsset(a.id)}
                    />
                    <span>
                      <strong>{a.type}</strong> {[a.marque, a.modele].filter(Boolean).join(" ")}
                      {a.numero_serie ? <span className="muted">{` - S/N ${a.numero_serie}`}</span> : null}
                      {a.identifiant_interne ? <span className="badge">{a.identifiant_interne}</span> : null}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div className="constat-bloc">
              <label htmlFor="motif-select">
                <strong>Motif de non-restitution (obligatoire) :</strong>
              </label>
              <select
                id="motif-select"
                className="constat-motif"
                value={motif}
                onChange={(e) => setMotif(e.target.value)}
              >
                {MOTIFS_NON_RESTITUTION.map((m) => (
                  <option key={m.code} value={m.code}>{m.label}</option>
                ))}
              </select>
            </div>

            <div className="warn constat-bloc">
              <p className="m0">
                <strong>Recapitulatif :</strong> {selAssets.size} materiel(s) constate(s) non restitue(s).
                {selAssets.size === mats.length
                  ? " Tous les materiels etant traites, le salarie passera automatiquement au statut Sorti avec reserve."
                  : " Il restera du materiel affecte a ce salarie."}
              </p>
            </div>

            <label className="constat-consent">
              <input
                type="checkbox"
                id="confirme-constat"
                checked={confirmeConstat}
                onChange={(e) => setConfirmeConstat(e.target.checked)}
              />
              <span>
                Je confirme le constat d'impossibilite de restitution pour ce(s) materiel(s). Cette action est irreversible et consignee au journal d'audit.
              </span>
            </label>

            {errConstat && <p className="err constat-bloc" role="alert">{errConstat}</p>}

            <div className="row">
              <button type="submit" disabled={selAssets.size === 0 || !confirmeConstat || busyConstat} aria-busy={busyConstat}>
                {busyConstat ? "Enregistrement en cours..." : "Valider le constat"}
              </button>
              <button type="button" className="ghost" onClick={fermerConstat} disabled={busyConstat}>
                Annuler
              </button>
            </div>
          </form>
        </section>
      )}

      <div className="deux-colonnes">
        <div className="card">
          <div className="row entete-carte">
            <h3 className="m0">Materiel a recuperer ({mats.length})</h3>
            {peutConstater && !constatOpen && (
              <button type="button" className="ghost btn-petit" ref={btnConstatRef} onClick={ouvrirConstat}>
                Constater une non-restitution...
              </button>
            )}
          </div>

          {mats.length === 0 ? (
            <p className="muted mt8">Aucun materiel actuellement detenu par ce salarie.</p>
          ) : (
            <ul className="liste-simple mt8">
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
            <div className="bloc-non-restitues">
              <h4>Materiel(s) non restitue(s) ({nr.length})</h4>
              <ul className="liste-simple">
                {nr.map((a) => (
                  <li key={a.id}>
                    <span>
                      <strong>{a.type}</strong> {[a.marque, a.modele].filter(Boolean).join(" ")}
                      {a.numero_serie ? <span className="muted">{` - S/N ${a.numero_serie}`}</span> : null}
                      <span className="muted">{` - Motif : ${libelleMotif(a.motif)}`}</span>
                      {a.constate_le ? <span className="muted">{` (${formaterQuand(a.constate_le)})`}</span> : null}
                    </span>
                    <span className="badge warn">non restitue</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="muted mt12 m0">
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
            ouvrirCloture();
          }
        }}
        reserves={data.reserves}
        texteTermine="materiel restitue et salarie sorti."
      />
    </div>
  );
}
