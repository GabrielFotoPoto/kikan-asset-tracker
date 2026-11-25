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

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  formaterDate,
  formaterDateHeure,
  libelleCanalTicket,
  libelleCriticiteTicket,
  libelleSecuriteTicket,
  libelleStatutSalarie,
  libelleStatutTicket,
} from "./format.js";

describe("format", () => {
  it("formaterDate : convertit AAAA-MM-JJ en JJ/MM/AAAA", () => {
    assert.equal(formaterDate("2026-11-25"), "25/11/2026");
    assert.equal(formaterDate(""), "-");
    assert.equal(formaterDate(null), "-");
  });

  it("formaterDateHeure : accepte ISO avec T, avec espace, avec fuseau ou vide", () => {
    assert.equal(formaterDateHeure(""), "-");
    assert.equal(formaterDateHeure(null), "-");
    assert.match(formaterDateHeure("2026-11-25T17:01:10.244506"), /^\d{2}\/\d{2}\/2026 \d{2}:\d{2}$/);
    assert.match(formaterDateHeure("2026-11-25 17:01:00.149468"), /^\d{2}\/\d{2}\/2026 \d{2}:\d{2}$/);
    assert.match(formaterDateHeure("2026-11-25T17:01:10Z"), /^\d{2}\/\d{2}\/2026 \d{2}:\d{2}$/);
    assert.equal(formaterDateHeure("2026-11-25"), "25/11/2026");
    assert.equal(formaterDateHeure("texte-invalide"), "texte-invalide");
  });

  it("libelles de statuts, criticite, securite et canal", () => {
    assert.equal(libelleStatutTicket("nouveau"), "Nouveau");
    assert.equal(libelleStatutTicket("en_cours"), "En cours");
    assert.equal(libelleStatutTicket("en_attente"), "En attente");
    assert.equal(libelleStatutTicket("resolu"), "Resolu");
    assert.equal(libelleStatutTicket("ferme"), "Ferme");
    assert.equal(libelleStatutTicket("annule"), "Annule");
    assert.equal(libelleStatutTicket("inconnu"), "inconnu");
    assert.equal(libelleStatutTicket(null), "-");

    assert.equal(libelleCriticiteTicket("critique"), "Critique");
    assert.equal(libelleSecuriteTicket("sans_suite"), "Sans suite");
    assert.equal(libelleCanalTicket("it"), "IT");
    assert.equal(libelleCanalTicket("email"), "E-mail");

    assert.equal(libelleStatutSalarie("en_depart"), "En depart");
    assert.equal(libelleStatutSalarie("sorti"), "Sorti");
    assert.equal(libelleStatutSalarie("actif"), "Actif");
    assert.equal(libelleStatutSalarie("prevu"), "Prevu");
  });
});
