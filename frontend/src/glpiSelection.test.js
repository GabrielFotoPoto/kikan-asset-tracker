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

// Tests du filtrage et de la selection des salaries GLPI : node --test frontend/src/glpiSelection.test.js.
import assert from "node:assert/strict";
import { test } from "node:test";
import { FILTRES_U_VIDES, cocherSalaries, entitesSalaries, filtrerSalaries, toutDecocherSalaries } from "./glpiSelection.js";

const salaries = [
  { externe_id: "User:1", login: "alice.m", prenom: "Élodie", nom: "Martin", email: "elodie@exemple.test", matricule: "M-001", etat_import: "nouveau", entite_glpi: "Siège", importable: true },
  { externe_id: "User:2", login: "bob.d", prenom: "Bob", nom: "Durand", email: "bob@exemple.test", matricule: "M-002", etat_import: "correspondance", entite_glpi: "Filiale Nord", importable: true },
  { externe_id: "User:3", login: "chloe.p", prenom: "Chloé", nom: "Petit", email: "chloe@exemple.test", matricule: null, etat_import: "homonyme", entite_glpi: "Siège", importable: true },
  { externe_id: "User:4", login: "inc.x", prenom: null, nom: "Incomplet", email: null, matricule: null, etat_import: "incomplet", entite_glpi: "Filiale Nord", importable: false },
  { externe_id: "User:5", login: "deja.l", prenom: "Marc", nom: "Déjà", email: "marc@exemple.test", matricule: "M-005", etat_import: "deja_lie", entite_glpi: null, importable: false },
];

const ids = (l) => l.map((u) => u.externe_id);

test("recherche libre sans accent ni casse sur login, prenom, nom, e-mail et matricule", () => {
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, q: "elodie" })), ["User:1"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, q: "ÉLODIE" })), ["User:1"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, q: "bob.d" })), ["User:2"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, q: "chloe@exemple" })), ["User:3"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, q: "m-005" })), ["User:5"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, q: "introuvable" })), []);
});

test("filtre par etat d'import", () => {
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, etat: "nouveau" })), ["User:1"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, etat: "homonyme" })), ["User:3"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, etat: "incomplet" })), ["User:4"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, etat: "deja_lie" })), ["User:5"]);
});

test("filtre par entite GLPI et option 'Tous sauf cette entite'", () => {
  assert.deepEqual(entitesSalaries(salaries), ["Filiale Nord", "Siège"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, entite: "Siège", sauf: false })), ["User:1", "User:3"]);
  assert.deepEqual(ids(filtrerSalaries(salaries, { ...FILTRES_U_VIDES, entite: "Siège", sauf: true })), ["User:2", "User:4", "User:5"]);
});

test("cocher les affiches : seuls les importables non homonymes sont coches", () => {
  const { pickU, homonyme } = cocherSalaries({}, {}, salaries, true);
  assert.equal(pickU["User:1"], true);
  assert.equal(pickU["User:2"], true);
  assert.equal(Boolean(pickU["User:3"]), false); // homonyme exclu du cochage en masse
  assert.equal(Boolean(pickU["User:4"]), false); // incomplet non importable
  assert.equal(Boolean(pickU["User:5"]), false); // deja lie non importable
  assert.deepEqual(homonyme, {});
});

test("decocher les affiches : decoche aussi un homonyme affiche et remet sa liste deroulante a vide", () => {
  const initPick = { "User:1": true, "User:2": true, "User:3": true };
  const initHom = { "User:3": "lier" };
  const siege = filtrerSalaries(salaries, { ...FILTRES_U_VIDES, entite: "Siège" }); // User:1 et User:3
  const { pickU, homonyme } = cocherSalaries(initPick, initHom, siege, false);
  assert.equal(Boolean(pickU["User:1"]), false);
  assert.equal(Boolean(pickU["User:3"]), false);
  assert.equal(homonyme["User:3"], "");
  // User:2 (hors filtre) survit a l'operation.
  assert.equal(pickU["User:2"], true);
});

test("survie de la selection hors filtre et tout decocher", () => {
  // User:1 et User:2 coches ; on filtre sur Filiale Nord (User:2, User:4) puis on coche les affiches : User:1 reste coche.
  const depart = { "User:1": true, "User:3": true };
  const departHom = { "User:3": "creer" };
  const nord = filtrerSalaries(salaries, { ...FILTRES_U_VIDES, entite: "Filiale Nord" });
  const { pickU, homonyme } = cocherSalaries(depart, departHom, nord, true);
  assert.equal(pickU["User:1"], true);
  assert.equal(pickU["User:2"], true);
  assert.equal(pickU["User:3"], true);
  assert.equal(homonyme["User:3"], "creer");
  assert.equal(Object.values(pickU).filter(Boolean).length, 3);

  // Tout decocher vide toute la selection et tous les choix d'homonyme.
  const vide = toutDecocherSalaries();
  assert.deepEqual(vide, { pickU: {}, homonyme: {} });
});
