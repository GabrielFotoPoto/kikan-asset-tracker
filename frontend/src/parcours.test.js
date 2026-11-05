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

// Tests de la logique des parcours (arrivee et depart) et du fil d'Ariane : node --test frontend/src/parcours.test.js.
import assert from "node:assert/strict";
import { test } from "node:test";
import { fil } from "./nav.js";
import {
  MOTIFS_NON_RESTITUTION,
  declencherAction,
  formaterQuand,
  libelleEtatEtape,
  libelleMotif,
  peutAgir,
  resumeParcours,
} from "./parcours.js";

const etapesDepartRh = [
  { cle: "depart", titre: "Depart declare", etat: "fait" },
  { cle: "materiel", titre: "Materiel a recuperer", etat: "fait" },
  { cle: "restitution", titre: "Materiel recupere", etat: "courante" },
  { cle: "acces", titre: "Acces applicatifs retires", etat: "a_venir" },
  { cle: "sorti", titre: "Salarie sorti", etat: "a_venir" },
];

test("resumeParcours : etape courante affichee avec son rang et le total", () => {
  const r = resumeParcours(etapesDepartRh, "restitution");
  assert.equal(r.termine, false);
  assert.equal(r.avecReserve, false);
  assert.equal(r.classe, "pastille attention");
  assert.equal(r.texte, "Etape 3 sur 5 : Materiel recupere");
});

test("resumeParcours : parcours termine sans reserve", () => {
  const r = resumeParcours(etapesDepartRh, null, []);
  assert.deepEqual(r, {
    termine: true,
    avecReserve: false,
    classe: "pastille ok",
    texte: "Parcours termine",
  });
});

test("resumeParcours : parcours termine avec reserve (acces restants)", () => {
  const r = resumeParcours(etapesDepartRh, null, ["1 acces a retirer"]);
  assert.equal(r.termine, true);
  assert.equal(r.avecReserve, true);
  assert.equal(r.classe, "pastille attention");
  assert.equal(r.texte, "Parcours termine (avec reserve : 1 acces a retirer)");
});

test("libelleEtatEtape : correspondance etat -> libelle pour lecteur d'ecran (depart et arrivee)", () => {
  assert.equal(libelleEtatEtape("fait", false), "fait");
  assert.equal(libelleEtatEtape("courante", true), "en cours");
  assert.equal(libelleEtatEtape("en_cours", true), "en cours");
  assert.equal(libelleEtatEtape("a_faire", true), "en cours");
  assert.equal(libelleEtatEtape("a_venir", false), "a venir");
  assert.equal(libelleEtatEtape("a_faire", false), "a venir");
  assert.equal(libelleEtatEtape("sans_objet", false), "sans objet");
});

test("peutAgir : respecte le booleen autorise du serveur ou deduit selon le role", () => {
  assert.equal(peutAgir({ qui: "rh_ou_informatique", autorise: false }, "lecture"), false);
  assert.equal(peutAgir({ qui: "rh_ou_informatique", autorise: true }, "rh"), true);
  assert.equal(peutAgir("informatique", "informatique"), true);
  assert.equal(peutAgir("informatique", "rh"), false);
  assert.equal(peutAgir("rh", "rh"), true);
  assert.equal(peutAgir("rh", "informatique"), true);
  assert.equal(peutAgir("rh", "lecture"), false);
});

test("MOTIFS_NON_RESTITUTION et libelleMotif : liste fermee et correspondance de libelle", () => {
  assert.equal(MOTIFS_NON_RESTITUTION.length, 5);
  const codes = MOTIFS_NON_RESTITUTION.map((m) => m.code);
  assert.deepEqual(codes, ["perte", "vol", "refus_de_restituer", "salarie_injoignable", "autre"]);
  assert.equal(libelleMotif("perte"), "Perte signalee");
  assert.equal(libelleMotif("vol"), "Vol declare");
  assert.equal(libelleMotif("refus_de_restituer"), "Refus de restituer");
  assert.equal(libelleMotif("inconnu"), "inconnu");
  assert.equal(libelleMotif(""), "");
});

test("declencherAction : appelle onAction pour action_id et ignore vers null ou vide sans naviguer", () => {
  const appels = [];
  const handlers = {
    onAction: (id) => appels.push(["action", id]),
    onNaviguer: (vers) => appels.push(["nav", vers]),
  };
  declencherAction({ etape: "sorti", vers: null, action_id: "cloturer_depart" }, handlers);
  declencherAction({ etape: "restitution", vers: "/signer/restitution/5" }, handlers);
  declencherAction({ etape: "autre", vers: null }, handlers);
  declencherAction({ etape: "autre", vers: "" }, handlers);
  assert.deepEqual(appels, [
    ["action", "cloturer_depart"],
    ["nav", "/signer/restitution/5"],
  ]);
});

test("formaterQuand : accepte une date ISO sans fuseau ou vide", () => {
  assert.equal(formaterQuand(""), "");
  assert.equal(formaterQuand(null), "");
  assert.ok(formaterQuand("2026-11-04T20:00:00").length > 0);
});

test("fil d'Ariane : /depart/:id et /arrivee/:id sont reconnus", () => {
  assert.deepEqual(fil("/depart/42"), [
    { label: "Cycle de vie" },
    { label: "Sorties", to: "/sorties" },
    { label: "Parcours de depart" },
  ]);
  assert.deepEqual(fil("/arrivee/42"), [
    { label: "Personnes" },
    { label: "Utilisateurs", to: "/utilisateurs" },
    { label: "Parcours d'arrivee" },
  ]);
});
