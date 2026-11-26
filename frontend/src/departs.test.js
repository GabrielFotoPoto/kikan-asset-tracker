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

import test from "node:test";
import assert from "node:assert/strict";
import { trierDeparts } from "./departs.js";

test("trierDeparts filtre uniquement en_depart et sorti sans muter l'entree", () => {
  const input = [
    { id: 1, nom: "Actif", prenom: "A", statut: "actif", date_sortie: null },
    { id: 2, nom: "Prevu", prenom: "B", statut: "prevu", date_sortie: null },
    { id: 3, nom: "Sorti", prenom: "C", statut: "sorti", date_sortie: "2026-10-01" },
    { id: 4, nom: "Depart", prenom: "D", statut: "en_depart", date_sortie: "2026-12-01" },
  ];
  const res = trierDeparts(input);
  assert.deepEqual(res.map((u) => u.id), [4, 3]);
  assert.equal(input.length, 4);
});

test("trierDeparts trie en_depart par date croissante et sorti par date decroissante, sans date en fin", () => {
  const input = [
    { id: 1, nom: "Ancien", prenom: "A", statut: "sorti", date_sortie: "2026-01-15" },
    { id: 2, nom: "SansDateSorti", prenom: "B", statut: "sorti", date_sortie: null },
    { id: 3, nom: "Recent", prenom: "C", statut: "sorti", date_sortie: "2026-11-10" },
    { id: 4, nom: "Lointain", prenom: "D", statut: "en_depart", date_sortie: "2026-12-20" },
    { id: 5, nom: "SansDateDepart", prenom: "E", statut: "en_depart", date_sortie: null },
    { id: 6, nom: "Proche", prenom: "F", statut: "en_depart", date_sortie: "2026-11-30" },
  ];
  const res = trierDeparts(input);
  assert.deepEqual(res.map((u) => u.id), [6, 4, 5, 3, 1, 2]);
});

test("trierDeparts departage les dates egales par nom puis prenom", () => {
  const input = [
    { id: 1, nom: "Martin", prenom: "Zoe", statut: "en_depart", date_sortie: "2026-12-01" },
    { id: 2, nom: "Bernard", prenom: "Luc", statut: "en_depart", date_sortie: "2026-12-01" },
    { id: 3, nom: "Martin", prenom: "Alice", statut: "en_depart", date_sortie: "2026-12-01" },
  ];
  const res = trierDeparts(input);
  assert.deepEqual(res.map((u) => u.id), [2, 3, 1]);
});
