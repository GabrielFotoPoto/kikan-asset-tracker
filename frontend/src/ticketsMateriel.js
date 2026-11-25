/**
 * Separe la liste du parc materiel entre les actifs affectes au salarie selectionne
 * et le reste du parc (pour les <optgroup> du formulaire de creation de ticket IT).
 */
export function grouperMaterielPourSalarie(assets, userAssetIds) {
  const list = Array.isArray(assets) ? assets : [];
  if (!userAssetIds || userAssetIds.size === 0) {
    return { affectes: [], autres: list };
  }
  const affectes = [];
  const autres = [];
  for (const a of list) {
    if (userAssetIds.has(a.id)) affectes.push(a);
    else autres.push(a);
  }
  return { affectes, autres };
}
