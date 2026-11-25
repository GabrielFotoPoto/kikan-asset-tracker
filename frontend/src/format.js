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
 * Formatage des dates (JJ/MM/AAAA et JJ/MM/AAAA HH:MM) et libelles lisibles des statuts.
 */

export const STATUT_TICKET_LABELS = {
  nouveau: "Nouveau",
  en_cours: "En cours",
  en_attente: "En attente",
  resolu: "Resolu",
  ferme: "Ferme",
  annule: "Annule",
};

export const CRITICITE_TICKET_LABELS = {
  faible: "Faible",
  moyenne: "Moyenne",
  haute: "Haute",
  critique: "Critique",
};

export const SECURITE_TICKET_LABELS = {
  aucun: "Aucun",
  signale: "Signale",
  incident: "Incident",
  sans_suite: "Sans suite",
};

export const CANAL_TICKET_LABELS = {
  portail: "Portail",
  it: "IT",
  api: "API",
  email: "E-mail",
};

export const STATUT_SALARIE_LABELS = {
  prevu: "Prevu",
  actif: "Actif",
  en_depart: "En depart",
  sorti: "Sorti",
};

export function libelleStatutTicket(code) {
  return STATUT_TICKET_LABELS[code] || code || "-";
}

export function libelleCriticiteTicket(code) {
  return CRITICITE_TICKET_LABELS[code] || code || "-";
}

export function libelleSecuriteTicket(code) {
  return SECURITE_TICKET_LABELS[code] || code || "-";
}

export function libelleCanalTicket(code) {
  return CANAL_TICKET_LABELS[code] || code || "-";
}

export function libelleStatutSalarie(code) {
  return STATUT_SALARIE_LABELS[code] || code || "-";
}

const pad2 = (n) => String(n).padStart(2, "0");

/**
 * Formate une date ISO (AAAA-MM-JJ) en JJ/MM/AAAA sans decalage de fuseau horaire.
 */
export function formaterDate(val, vide = "-") {
  if (!val) return vide;
  const s = String(val).trim();
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (m) return `${m[3]}/${m[2]}/${m[1]}`;
  return formaterDateHeure(s, vide);
}

/**
 * Formate un horodatage ISO (UTC sans fuseau, espace ou T, ou avec fuseau) en JJ/MM/AAAA HH:MM.
 */
export function formaterDateHeure(val, vide = "-") {
  if (!val) return vide;
  const s = String(val).trim();
  if (!s) return vide;
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return formaterDate(s, vide);
  const normalized = s.includes(" ") && !s.includes("T") ? s.replace(" ", "T") : s;
  const withTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(normalized) ? normalized : `${normalized}Z`;
  const d = new Date(withTz);
  if (Number.isNaN(d.getTime())) return s;
  return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}
