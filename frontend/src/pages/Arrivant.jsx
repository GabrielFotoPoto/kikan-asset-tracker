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
import { useNavigate, useParams } from "react-router-dom";
import { api, errorText } from "../api.js";
import { useAuth } from "../auth.jsx";
import { ErrorState, Loading } from "../components/State.jsx";

// Parcours d'arrivee d'un salarie : les cinq etapes, de la fiche RH a la remise signee et aux acces. Meme vue pour les
// RH (qui suivent) et l'informatique (qui agit) ; l'avancement est calcule par le serveur (GET /arrivee/{id}).
const STATUTS_BESOIN = { demande: "Demande", en_preparation: "En preparation", satisfait: "Satisfait", annule: "Annule" };
const ACTIONS = {
  besoins: "Saisir les besoins",
  preparation: "Preparer le materiel",
  remise: "Ouvrir la remise",
  acces: "Accorder les acces",
};
const QUI = { rh: "RH", informatique: "Informatique", rh_ou_informatique: "RH ou Informatique" };

// Qui peut agir : les etapes RH sont ouvertes aux RH et a l'informatique, celles de l'informatique a elle seule.
const peutAgir = (qui, role) => (qui === "informatique" ? role === "informatique" : role === "rh" || role === "informatique");

// Les dates du serveur sont en UTC sans fuseau : on le precise pour l'afficher en heure locale.
const quand = (iso) => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z")
  .toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });

export default function Arrivant() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  const load = () => {
    setErr(null);
    api.get(`/arrivee/${id}`).then(setData).catch((e) => setErr(errorText(e)));
  };
  useEffect(() => { setData(null); load(); }, [id]);

  if (err) return <div><h2>Parcours d'arrivee</h2><ErrorState message={err} onRetry={load} /></div>;
  if (!data) return <div><h2>Parcours d'arrivee</h2><Loading label="Chargement du parcours" /></div>;

  const s = data.salarie;
  const indice = data.etapes.findIndex((e) => e.cle === data.etape_courante);
  const action = data.prochaine_action;

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>Arrivee de {s.prenom} {s.nom}</h2>
          <p className="muted" style={{ margin: 0 }}>
            {[s.matricule && `Matricule ${s.matricule}`, s.service, s.date_arrivee && `arrive le ${s.date_arrivee}`].filter(Boolean).join(" - ")}
          </p>
        </div>
        <span className={data.etape_courante ? "pastille attention" : "pastille ok"}>
          {data.etape_courante ? `Etape ${indice + 1} sur ${data.etapes.length} : ${data.etapes[indice].titre}` : "Parcours termine"}
        </span>
      </div>

      <ol className="etapes" aria-label="Avancement du parcours">
        {data.etapes.map((e, i) => {
          const courante = e.cle === data.etape_courante;
          return (
            <li key={e.cle} className={`etape ${e.etat}${courante ? " courante" : ""}`} aria-current={courante ? "step" : undefined}>
              <span className="etape-puce" aria-hidden="true">{e.etat === "fait" ? "\u2713" : i + 1}</span>
              <strong>{e.titre}</strong>
              <span className="muted">{QUI[e.qui] || e.qui}</span>
              <span className="etape-detail">{e.detail}</span>
            </li>
          );
        })}
      </ol>

      <div className="deux-colonnes">
        <div className="card">
          <h3>Materiel demande</h3>
          {data.besoins.length === 0 ? <p className="muted">Aucun besoin saisi pour ce salarie.</p> : (
            <ul className="liste-simple">
              {data.besoins.map((b) => (
                <li key={b.id}>
                  <span><strong>{b.type}</strong>{b.gamme ? ` (${b.gamme})` : ""}{b.quantite > 1 ? ` x${b.quantite}` : ""}</span>
                  <span className="badge">{STATUTS_BESOIN[b.statut] || b.statut}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="card">
          <h3>Journal du parcours</h3>
          {data.journal.length === 0 ? <p className="muted">Rien pour l'instant.</p> : (
            <ol className="journal">
              {data.journal.map((j, i) => <li key={i}><span className="muted">{quand(j.quand)}</span><span>{j.texte}</span></li>)}
            </ol>
          )}
        </div>
      </div>

      <div className="card action-suivante" role="region" aria-label="Prochaine action">
        {action ? (
          <>
            <span><strong>Prochaine action ({QUI[action.qui] || action.qui}) :</strong> {action.texte}</span>
            {peutAgir(action.qui, user.role)
              ? <button type="button" onClick={() => navigate(action.vers)}>{ACTIONS[action.etape] || "Ouvrir"}</button>
              : <span className="muted">En attente de {QUI[action.qui] || action.qui}.</span>}
          </>
        ) : <span><strong>Le parcours est termine :</strong> remise signee et acces accordes.</span>}
      </div>
    </div>
  );
}
