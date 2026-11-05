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

// Logique pure des parcours guides en etapes (arrivee et depart), sans dependance React.
export const QUI_LIBELLES = {
  rh: "RH",
  informatique: "Informatique",
  rh_ou_informatique: "RH ou Informatique",
};

export const ETAT_LIBELLES = {
  fait: "fait",
  courante: "en cours",
  en_cours: "en cours",
  a_venir: "a venir",
  a_faire: "a venir",
  sans_objet: "sans objet",
};

export const MOTIFS_NON_RESTITUTION = [
  { code: "perte", label: "Perte signalee" },
  { code: "vol", label: "Vol declare" },
  { code: "refus_de_restituer", label: "Refus de restituer" },
  { code: "salarie_injoignable", label: "Salarie injoignable" },
  { code: "autre", label: "Autre motif" },
];

export function libelleMotif(code) {
  const m = MOTIFS_NON_RESTITUTION.find((x) => x.code === code);
  return m ? m.label : (code || "");
}

// Libelle d'etat lu par les lecteurs d'ecran (en complement de la puce aria-hidden et de la couleur).
export function libelleEtatEtape(etat, courante = false) {
  if (courante && etat !== "fait") return "en cours";
  return ETAT_LIBELLES[etat] || String(etat || "");
}

// Qui peut agir : les etapes de l'informatique lui sont reservees ; celles des RH ou mixtes sont ouvertes aux RH et a l'informatique.
// Si le serveur fournit deja le booleen `autorise` dans `prochaine_action`, il fait foi.
export function peutAgir(actionOuQui, role) {
  if (actionOuQui && typeof actionOuQui === "object") {
    if (typeof actionOuQui.autorise === "boolean") return actionOuQui.autorise;
    return peutAgir(actionOuQui.qui, role);
  }
  if (!actionOuQui || !role) return false;
  return actionOuQui === "informatique"
    ? role === "informatique"
    : role === "rh" || role === "informatique";
}

// Declenche l'action de l'encart : priorite a action_id (action locale), sinon navigation vers une cible non vide.
export function declencherAction(action, { onAction, onNaviguer } = {}) {
  if (!action) return;
  if (action.action_id && typeof onAction === "function") {
    onAction(action.action_id);
  } else if (typeof action.vers === "string" && action.vers.length > 0 && typeof onNaviguer === "function") {
    onNaviguer(action.vers);
  }
}

// Etat de la pastille d'en-tete d'un parcours. `action` : prochaine action du serveur ; une action locale (action_id) encore a faire
// (cloture du depart) empeche d'afficher « termine ».
export function resumeParcours(etapes = [], etapeCourante = null, reserves = [], action = null) {
  const liste = Array.isArray(etapes) ? etapes : [];
  const indice = etapeCourante ? liste.findIndex((e) => e.cle === etapeCourante) : -1;
  if (indice >= 0) {
    return {
      termine: false,
      avecReserve: false,
      classe: "pastille attention",
      texte: `Etape ${indice + 1} sur ${liste.length} : ${liste[indice].titre}`,
    };
  }
  if (action && action.action_id) {
    return { termine: false, avecReserve: false, classe: "pastille attention", texte: "Cloture du depart en attente" };
  }
  const nbReserves = Array.isArray(reserves) ? reserves.length : 0;
  if (nbReserves > 0) {
    return {
      termine: true,
      avecReserve: true,
      classe: "pastille attention",
      texte: `Parcours termine (avec reserve : ${reserves.join(", ")})`,
    };
  }
  return {
    termine: true,
    avecReserve: false,
    classe: "pastille ok",
    texte: "Parcours termine",
  };
}

// Les dates du serveur sont en UTC sans fuseau : on le precise pour l'afficher en heure locale.
export function formaterQuand(iso) {
  if (!iso) return "";
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z")
    .toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}
