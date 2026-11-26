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

const cmpNom = (a, b) =>
  String(a.nom || "").localeCompare(String(b.nom || ""), "fr")
  || String(a.prenom || "").localeCompare(String(b.prenom || ""), "fr");

/**
 * Filtre et trie les "Departs a suivre" du tableau de bord :
 * - salaries en_depart d'abord, par date_sortie croissante (les plus proches en premier, sans date en fin) ;
 * - salaries sorti ensuite, par date_sortie decroissante (les plus recents en premier, sans date en fin).
 */
export function trierDeparts(users) {
  return (users || [])
    .filter((u) => u.statut === "en_depart" || u.statut === "sorti")
    .sort((a, b) => {
      if (a.statut !== b.statut) return a.statut === "en_depart" ? -1 : 1;
      const da = a.date_sortie || "";
      const db = b.date_sortie || "";
      if (da !== db) {
        if (!da) return 1;
        if (!db) return -1;
        return a.statut === "en_depart" ? da.localeCompare(db) : db.localeCompare(da);
      }
      return cmpNom(a, b);
    });
}
