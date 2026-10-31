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
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api.js";
import { ACCUEIL, SECTIONS, sectionDe, visible } from "../nav.js";
import { usePalette } from "./Palette.jsx";

const CLE = "kikan_nav";

const lire = () => {
  try { return JSON.parse(localStorage.getItem(CLE)) || {}; } catch { return {}; }
};
const ecrire = (pref) => {
  try { localStorage.setItem(CLE, JSON.stringify(pref)); } catch { /* navigation privee : le repli n'est pas memorise */ }
};

// Compteurs des entrees de menu : relus a l'ouverture, au retour sur l'onglet et toutes les 5 minutes.
function useCompteurs(role) {
  const [c, setC] = useState({});
  useEffect(() => {
    let vivant = true;
    const mettre = (cle) => (valeur) => { if (vivant) setC((o) => ({ ...o, [cle]: valeur })); };
    const charger = () => {
      if (role !== "rh") api.get("/stats").then((s) => mettre("besoins")(s.besoins_a_traiter || 0)).catch(() => {});
      api.get("/revues/anomalies").then((r) => mettre("anomalies")(r.count || 0)).catch(() => {});
      if (role === "informatique") api.get("/renouvellements?horizon_mois=0").then((r) => mettre("retard")(r.totaux.en_retard)).catch(() => {});
    };
    charger();
    const minuteur = setInterval(charger, 5 * 60 * 1000);
    window.addEventListener("focus", charger);
    return () => { vivant = false; clearInterval(minuteur); window.removeEventListener("focus", charger); };
  }, [role]);
  return c;
}

export default function NavPrincipale({ role }) {
  const { pathname } = useLocation();
  const { ouvrir } = usePalette();
  const compteurs = useCompteurs(role);
  const [pref, setPref] = useState(lire);
  const actuelle = sectionDe(pathname)?.section.id;
  const touche = /Mac/i.test(navigator.platform || "") ? "Cmd K" : "Ctrl K";

  const ouverte = (s) => (pref[s.id] !== undefined ? pref[s.id] : !s.replie);

  // Arriver sur une page d'une section repliee (lien, palette, adresse) ouvre cette section.
  useEffect(() => {
    const s = SECTIONS.find((x) => x.id === actuelle);
    if (s && !ouverte(s)) {
      const suivant = { ...pref, [s.id]: true };
      setPref(suivant); ecrire(suivant);
    }
  }, [actuelle]);
  const basculer = (s) => {
    const suivant = { ...pref, [s.id]: !ouverte(s) };
    setPref(suivant); ecrire(suivant);
  };

  return (
    <nav aria-label="Navigation principale">
      <button type="button" className="nav-search" onClick={ouvrir}>
        <span>Rechercher</span><kbd>{touche}</kbd>
      </button>
      <NavLink to={ACCUEIL.to} end>{ACCUEIL.label}</NavLink>
      {SECTIONS.map((s) => {
        const items = s.items.filter((i) => visible(i, role));
        if (!items.length) return null;
        const id = "nav-" + s.id;
        return (
          <div key={s.id} className="nav-section">
            <button type="button" className="nav-section-titre" aria-expanded={ouverte(s)} aria-controls={id} onClick={() => basculer(s)}>
              <span>{s.label}</span>
              <span aria-hidden="true" className={ouverte(s) ? "nav-chevron ouvert" : "nav-chevron"}>{"▾"}</span>
            </button>
            {ouverte(s) && (
              <div id={id}>
                {items.map((i) => {
                  const n = i.badge ? compteurs[i.badge] : 0;
                  return (
                    <NavLink key={i.to} to={i.to}>
                      <span>{i.label}</span>
                      {n > 0 && <span className={i.alerte ? "nav-badge alerte" : "nav-badge"} aria-label={`${n} a traiter`}>{n}</span>}
                    </NavLink>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      <NavLink to="/compte" className="nav-compte">Mon compte</NavLink>
    </nav>
  );
}
