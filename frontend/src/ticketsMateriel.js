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
