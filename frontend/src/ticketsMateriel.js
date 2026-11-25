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

/**
 * Regles de selection du materiel dans le formulaire de creation de ticket IT.
 * - Sans salarie choisi : tout le parc est propose.
 * - Avec salarie choisi : seuls ses actifs affectes par defaut, sauf si horsAffectation est coche.
 * - Au changement de salarie : le materiel selectionne est vide s'il n'appartient pas au nouveau salarie.
 */
export function listeMaterielProposee({ userId, assetsParc, assetsSalarie, horsAffectation }) {
  const parc = Array.isArray(assetsParc) ? assetsParc : [];
  const affectes = Array.isArray(assetsSalarie) ? assetsSalarie : [];
  if (!userId || horsAffectation) return parc;
  return affectes;
}

export function conserverAssetPourSalarie(assetId, assetsSalarie) {
  if (!assetId) return "";
  const idNum = Number(assetId);
  const affectes = Array.isArray(assetsSalarie) ? assetsSalarie : [];
  return affectes.some((a) => a.id === idNum) ? String(assetId) : "";
}
