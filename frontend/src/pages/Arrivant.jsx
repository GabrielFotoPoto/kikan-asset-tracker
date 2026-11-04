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
import { EncartProchaineAction, EtapesParcours, JournalParcours, PastilleParcours } from "../components/EtapesParcours.jsx";
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

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>Arrivee de {s.prenom} {s.nom}</h2>
          <p className="muted" style={{ margin: 0 }}>
            {[s.matricule && `Matricule ${s.matricule}`, s.service, s.date_arrivee && `arrive le ${s.date_arrivee}`].filter(Boolean).join(" - ")}
          </p>
        </div>
        <PastilleParcours etapes={data.etapes} etapeCourante={data.etape_courante} />
      </div>

      <EtapesParcours etapes={data.etapes} etapeCourante={data.etape_courante} />

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
        <JournalParcours journal={data.journal} />
      </div>

      <EncartProchaineAction
        action={data.prochaine_action}
        role={user.role}
        libellesBouton={ACTIONS}
        onNaviguer={navigate}
        texteTermine="remise signee et acces accordes."
      />
    </div>
  );
}
