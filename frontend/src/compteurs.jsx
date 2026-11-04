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

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import { fautRecharger } from "./compteurs.js";

const CompteursContext = createContext({ valeurs: {}, recharger: () => {} });

// Compteurs du menu et du tableau de bord : lus a l'ouverture, au retour sur l'onglet et toutes les 5 minutes.
// Les composants qui en ont besoin les lisent ici au lieu de les recharger ; `recharger()` ne rappelle le serveur
// que si la derniere lecture date de plus de quelques secondes.
export function CompteursProvider({ role, children }) {
  const [valeurs, setValeurs] = useState({});
  const dernier = useRef(null);
  const vivant = useRef(true);  // les effets des enfants (accueil) s'executent avant ceux du parent : `dernier` ne doit pas etre remis a zero ici

  const recharger = useCallback(() => {
    const maintenant = Date.now();
    if (!fautRecharger(dernier.current, maintenant)) return;
    dernier.current = maintenant;
    const mettre = (cle) => (valeur) => { if (vivant.current) setValeurs((o) => ({ ...o, [cle]: valeur })); };
    if (role !== "rh") api.get("/stats").then((s) => mettre("besoins")(s.besoins_a_traiter || 0)).catch(() => {});
    api.get("/revues/anomalies").then((r) => mettre("anomalies")(r.count || 0)).catch(() => {});
    if (role === "informatique") api.get("/renouvellements?horizon_mois=0").then((r) => mettre("retard")(r.totaux.en_retard)).catch(() => {});
  }, [role]);

  useEffect(() => {
    vivant.current = true;
    recharger();
    const minuteur = setInterval(recharger, 5 * 60 * 1000);
    window.addEventListener("focus", recharger);
    return () => { vivant.current = false; clearInterval(minuteur); window.removeEventListener("focus", recharger); };
  }, [recharger]);

  const valeur = useMemo(() => ({ valeurs, recharger }), [valeurs, recharger]);
  return <CompteursContext.Provider value={valeur}>{children}</CompteursContext.Provider>;
}

export const useCompteurs = () => useContext(CompteursContext);
