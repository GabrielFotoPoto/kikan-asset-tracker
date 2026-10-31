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

// Structure de navigation unique : la barre laterale, le fil d'Ariane et la palette de recherche s'y appuient.
// roles : seuls ces roles voient l'entree ; sauf : ces roles ne la voient pas ; badge : cle d'un compteur (NavPrincipale).
const IT = ["informatique"];

export const ACCUEIL = { to: "/", label: "Tableau de bord" };

export const SECTIONS = [
  { id: "parc", label: "Parc", items: [
    { to: "/materiel", label: "Materiel" },
    { to: "/besoins", label: "Besoins", sauf: ["rh"], badge: "besoins" },
    { to: "/renouvellements", label: "Renouvellements", roles: IT, badge: "retard", alerte: true },
    { to: "/previsions", label: "Previsions" },
  ] },
  { id: "personnes", label: "Personnes", items: [
    { to: "/utilisateurs", label: "Utilisateurs" },
    { to: "/entites", label: "Entites" },
    { to: "/acces", label: "Acces applicatifs" },
    { to: "/revues", label: "Revue des acces", badge: "anomalies", alerte: true },
  ] },
  { id: "cycle", label: "Cycle de vie", items: [
    { to: "/remises", label: "Remises" },
    { to: "/sorties", label: "Sorties" },
    { to: "/chartes", label: "Chartes" },
  ] },
  { id: "pilotage", label: "Pilotage", items: [
    { to: "/rapports", label: "Rapports" },
    { to: "/statistiques", label: "Statistiques" },
  ] },
  { id: "admin", label: "Administration", replie: true, items: [
    { to: "/rgpd", label: "RGPD", roles: IT },
    { to: "/import", label: "Import", roles: IT },
    { to: "/parametres", label: "Parametrage", roles: IT },
    { to: "/comptes", label: "Comptes", roles: IT },
    { to: "/stockage", label: "Stockage", roles: IT },
    { to: "/sauvegarde", label: "Sauvegarde", roles: IT },
    { to: "/journal", label: "Journal d'audit", roles: IT },
  ] },
];

export const visible = (item, role) =>
  (!item.roles || item.roles.includes(role)) && !(item.sauf && item.sauf.includes(role));

// Section d'une page (pour ouvrir la bonne section et construire le fil d'Ariane).
export function sectionDe(pathname) {
  for (const s of SECTIONS) {
    const it = s.items.find((i) => pathname === i.to || pathname.startsWith(i.to + "/"));
    if (it) return { section: s, item: it };
  }
  return null;
}

// Pages hors menu : chemin, puis fil d'Ariane (to absent = page courante ou section sans page).
const AUTRES = [
  ["/signer", [{ label: "Cycle de vie" }, { label: "Remises", to: "/remises" }, { label: "Signature" }]],
  ["/renouveler", [{ label: "Parc" }, { label: "Renouvellements", to: "/renouvellements" }, { label: "Renouveler" }]],
  ["/compte", [{ label: "Mon compte" }]],
  ["/a-propos", [{ label: "A propos" }]],
];

export function fil(pathname) {
  if (pathname === "/") return [{ label: ACCUEIL.label }];
  const trouve = sectionDe(pathname);
  if (trouve) return [{ label: trouve.section.label }, { label: trouve.item.label }];
  const autre = AUTRES.find(([p]) => pathname === p || pathname.startsWith(p + "/"));
  return autre ? autre[1] : [];
}

// Actions proposees par la palette ; droit = domaine d'ecriture a avoir (voir canWrite dans auth.jsx).
export const ACTIONS = [
  { label: "Ajouter du materiel", to: "/materiel", droit: "materiel" },
  { label: "Ajouter un salarie", to: "/utilisateurs", droit: "users" },
  { label: "Creer une remise", to: "/remises", droit: "remises" },
  { label: "Declarer un depart", to: "/sorties", droit: "users" },
  { label: "Importer un fichier", to: "/import", droit: "import" },
];
