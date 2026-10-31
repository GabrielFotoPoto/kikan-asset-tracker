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

import { useState } from "react";

// Theme clair, sombre ou systeme. Le choix est memorise par navigateur ; public/theme-init.js le rejoue au chargement.
const CLE = "kikan_theme";
const CHOIX = [["clair", "Clair"], ["sombre", "Sombre"], ["systeme", "Systeme"]];
const ATTRIBUT = { clair: "light", sombre: "dark" };

const lire = () => {
  try { return localStorage.getItem(CLE) || "systeme"; } catch { return "systeme"; }
};

export default function ThemeSwitch() {
  const [choix, setChoix] = useState(lire);
  const choisir = (valeur) => {
    setChoix(valeur);
    const racine = document.documentElement;
    if (ATTRIBUT[valeur]) racine.setAttribute("data-theme", ATTRIBUT[valeur]); else racine.removeAttribute("data-theme");
    try {
      if (valeur === "systeme") localStorage.removeItem(CLE); else localStorage.setItem(CLE, valeur);
    } catch { /* navigation privee : le choix n'est pas memorise */ }
  };
  return (
    <div className="theme-switch" role="group" aria-label="Theme de l'interface">
      {CHOIX.map(([valeur, libelle]) => (
        <button key={valeur} type="button" aria-pressed={choix === valeur} onClick={() => choisir(valeur)}>{libelle}</button>
      ))}
    </div>
  );
}
