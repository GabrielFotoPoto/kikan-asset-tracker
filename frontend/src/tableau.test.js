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

// Tests du tri et de la pagination : node --test frontend/src/tableau.test.js (aucune dependance).
import assert from "node:assert/strict";
import { test } from "node:test";
import { fold, paginer, pagesAffichees, pagination, tailleMemorisee, tailleParDefaut, trier } from "./tableau.js";

const lot = [
  { id: 1, marque: "Lenovo", modele: "PC-10", numero_serie: null },
  { id: 2, marque: "dell", modele: "PC-2", numero_serie: "" },
  { id: 3, marque: "Apple", modele: "PC-1", numero_serie: "SN-3" },
  { id: 4, marque: null, modele: "pc-3", numero_serie: "SN-1" },
  { id: 5, marque: "Éco", modele: "PC-20", numero_serie: "SN-2" },
];
const ids = (l) => l.map((x) => x.id);

test("tri croissant : sans casse ni accents, les valeurs vides en fin", () => {
  assert.deepEqual(ids(trier(lot, "marque", "asc")), [3, 2, 5, 1, 4]);
});

test("tri decroissant : les valeurs vides restent en fin", () => {
  assert.deepEqual(ids(trier(lot, "marque", "desc")), [1, 5, 2, 3, 4]);
  assert.deepEqual(ids(trier(lot, "numero_serie", "desc")), [3, 5, 4, 1, 2]);
});

test("les nombres dans un texte se comparent comme des nombres (PC-2 avant PC-10)", () => {
  assert.deepEqual(ids(trier(lot, "modele", "asc")), [3, 2, 4, 1, 5]);
});

test("tri numerique par id, y compris decroissant (plus recents d'abord)", () => {
  assert.deepEqual(ids(trier(lot, "id", "desc")), [5, 4, 3, 2, 1]);
});

test("tri stable : a valeur egale, l'ordre d'ajout departage", () => {
  const egaux = [{ id: 9, m: "a" }, { id: 4, m: "a" }, { id: 7, m: "a" }];
  assert.deepEqual(ids(trier(egaux, "m", "asc")), [4, 7, 9]);
  assert.deepEqual(ids(trier(egaux, "m", "desc")), [4, 7, 9]);
});

test("le tri ne modifie pas la liste d'origine", () => {
  const copie = ids(lot);
  trier(lot, "marque", "desc");
  assert.deepEqual(ids(lot), copie);
});

test("pagination : 300 elements, pages de 20", () => {
  const trois = Array.from({ length: 300 }, (_, i) => ({ id: i + 1 }));
  const p1 = paginer(trois, 1, 20);
  assert.equal(p1.tranche.length, 20);
  assert.equal(p1.pages, 15);
  assert.deepEqual([p1.de, p1.a, p1.total], [1, 20, 300]);
  const p15 = paginer(trois, 15, 20);
  assert.deepEqual([p15.de, p15.a, p15.tranche.length], [281, 300, 20]);
});

test("pagination : derniere page incomplete", () => {
  const cent = Array.from({ length: 105 }, (_, i) => ({ id: i }));
  const p = paginer(cent, 6, 20);
  assert.deepEqual([p.pages, p.tranche.length, p.de, p.a], [6, 5, 101, 105]);
});

test("pagination : page hors limites ramenee dans les limites, liste vide sans page 0", () => {
  const dix = Array.from({ length: 10 }, (_, i) => ({ id: i }));
  assert.equal(paginer(dix, 99, 20).page, 1);
  assert.equal(paginer(dix, -4, 20).page, 1);
  assert.equal(paginer(dix, "abc", 20).page, 1);
  const vide = paginer([], 3, 20);
  assert.deepEqual([vide.page, vide.pages, vide.de, vide.a, vide.tranche.length], [1, 1, 0, 0, 0]);
});

test("numeros de pages affiches", () => {
  assert.deepEqual(pagesAffichees(1, 1), [1]);
  assert.deepEqual(pagesAffichees(2, 4), [1, 2, 3, 4]);
  assert.deepEqual(pagesAffichees(1, 15), [1, 2, "…", 15]);
  assert.deepEqual(pagesAffichees(8, 15), [1, "…", 7, 8, 9, "…", 15]);
  assert.deepEqual(pagesAffichees(15, 15), [1, "…", 14, 15]);
  assert.deepEqual(pagesAffichees(4, 15), [1, 2, 3, 4, 5, "…", 15]);
});

test("taille par defaut selon l'ecran : telephone 10, normal 20, grand ecran 50", () => {
  const ecran = (...vraies) => (q) => vraies.includes(q);
  assert.equal(tailleParDefaut(ecran("(max-width: 720px)")), 10);
  assert.equal(tailleParDefaut(ecran()), 20);
  assert.equal(tailleParDefaut(ecran("(min-width: 1400px) and (min-height: 1000px)")), 50);
  // Le petit ecran l'emporte sur toute autre regle.
  assert.equal(tailleParDefaut(ecran("(max-width: 720px)", "(min-width: 1400px) and (min-height: 1000px)")), 10);
});

test("memoire du navigateur indisponible : aucune erreur, pas de valeur", () => {
  assert.equal(tailleMemorisee(), null); // pas de window ni de localStorage sous node
});

test("fold : sans accent ni casse, valeurs vides tolerees", () => {
  assert.equal(fold("\u00c9cran D\u00c9LL"), "ecran dell");
  assert.equal(fold(null), "");
  assert.equal(fold(undefined), "");
});

test("pagination() : reperes d'une liste dont seul le total est connu (journal d'audit)", () => {
  assert.deepEqual(pagination(12345, 1, 20), { total: 12345, pages: 618, page: 1, de: 1, a: 20 });
  assert.deepEqual(pagination(12345, 618, 20), { total: 12345, pages: 618, page: 618, de: 12341, a: 12345 });
  assert.deepEqual(pagination(40, 2, 20), { total: 40, pages: 2, page: 2, de: 21, a: 40 });
  assert.equal(pagination(40, 9, 20).page, 2); // page hors limites ramenee a la derniere
  assert.deepEqual(pagination(0, 3, 20), { total: 0, pages: 1, page: 1, de: 0, a: 0 });
});

test("pagination() et paginer() donnent les memes reperes", () => {
  const liste = Array.from({ length: 105 }, (_, i) => ({ id: i }));
  for (const page of [1, 3, 6, 9]) {
    const { tranche, ...repere } = paginer(liste, page, 20);
    assert.deepEqual(repere, pagination(105, page, 20));
    assert.equal(tranche.length, repere.a - (repere.de ? repere.de - 1 : 0));
  }
});
