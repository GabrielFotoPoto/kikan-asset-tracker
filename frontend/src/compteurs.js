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

// Compteurs du menu et du tableau de bord (besoins a traiter, anomalies d'acces, echeances depassees) : une seule source,
// partagee, pour ne pas charger les memes donnees deux fois a l'ouverture ni a chaque retour de focus.

export const DELAI_MIN_MS = 5000;

// Un rechargement demande moins de DELAI_MIN_MS apres le precedent est ignore (les donnees viennent d'etre lues).
export function fautRecharger(dernier, maintenant, delai = DELAI_MIN_MS) {
  return dernier == null || maintenant - dernier >= delai;
}
