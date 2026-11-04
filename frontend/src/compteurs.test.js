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

// Tests de la regle de rechargement des compteurs : node --test frontend/src/compteurs.test.js (aucune dependance).
import assert from "node:assert/strict";
import { test } from "node:test";
import { DELAI_MIN_MS, fautRecharger } from "./compteurs.js";

test("premier chargement : toujours autorise", () => {
  assert.equal(fautRecharger(null, 1000), true);
  assert.equal(fautRecharger(undefined, 1000), true);
});

test("rechargement immediat (ouverture de l'accueil juste apres le menu) : ignore", () => {
  assert.equal(fautRecharger(1000, 1000), false);
  assert.equal(fautRecharger(1000, 1000 + DELAI_MIN_MS - 1), false);
});

test("rechargement apres le delai (retour sur l'accueil, focus, minuteur) : autorise", () => {
  assert.equal(fautRecharger(1000, 1000 + DELAI_MIN_MS), true);
  assert.equal(fautRecharger(1000, 1000 + 5 * 60 * 1000), true);
});

test("delai personnalise", () => {
  assert.equal(fautRecharger(0, 50, 100), false);
  assert.equal(fautRecharger(0, 100, 100), true);
});
