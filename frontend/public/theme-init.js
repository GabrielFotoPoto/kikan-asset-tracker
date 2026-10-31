/*
 * Kikan - suivi des actifs et remise de materiel signee
 * Copyright (C) 2026 Gabriel Chollet
 * Developpe avec l'assistance d'une IA (Claude, Anthropic).
 * Licence GPLv3 (voir LICENSE).
 */
// Applique le theme choisi avant le premier affichage (pas de flash clair). Fichier externe : la politique de securite
// du contenu interdit les scripts en ligne. Sans choix enregistre, la page suit le theme du systeme.
(function () {
  try {
    var choix = localStorage.getItem("kikan_theme");
    if (choix === "clair") document.documentElement.setAttribute("data-theme", "light");
    else if (choix === "sombre") document.documentElement.setAttribute("data-theme", "dark");
  } catch (e) { /* navigation privee : theme du systeme */ }
})();
