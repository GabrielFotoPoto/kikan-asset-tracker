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

// Parcours de depart d'un salarie (Lot 1 de SPEC.md 6.3bis) : vue en lecture seule calculee par GET /parcours/depart/{id}.
// Les RH et le role lecture voient 5 etapes ; l'informatique voit aussi l'etape 6 (purge RGPD possible).
const ACTIONS_DEPART = {
  depart: "Declarer le depart",
  restitution: "Restituer et signer",
};

export default function DepartParcours() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  const load = () => {
    setErr(null);
    api.get(`/parcours/depart/${id}`).then(setData).catch((e) => setErr(errorText(e)));
  };
  useEffect(() => { setData(null); load(); }, [id]);

  if (err) return <div><h2>Parcours de depart</h2><ErrorState message={err} onRetry={load} /></div>;
  if (!data) return <div><h2>Parcours de depart</h2><Loading label="Chargement du parcours" /></div>;

  const s = data.salarie;
  const mats = data.materiel_a_recuperer || [];

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

      <div className="deux-colonnes">
        <div className="card">
          <h3>Materiel a recuperer ({mats.length})</h3>
          {mats.length === 0 ? (
            <p className="muted">Aucun materiel actuellement detenu par ce salarie.</p>
          ) : (
            <ul className="liste-simple">
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
        messageAttente={data.message_attente}
        reserves={data.reserves}
        texteTermine="materiel restitue et salarie sorti."
      />
    </div>
  );
}
