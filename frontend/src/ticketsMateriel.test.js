import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { grouperMaterielPourSalarie } from "./ticketsMateriel.js";

describe("grouperMaterielPourSalarie", () => {
  const parc = [
    { id: 1, identifiant_interne: "PC-01" },
    { id: 2, identifiant_interne: "PC-02" },
    { id: 3, identifiant_interne: "IMP-01" },
  ];

  it("sans salarie ou sans materiel affecte : tout reste dans autres", () => {
    const r1 = grouperMaterielPourSalarie(parc, null);
    assert.deepEqual(r1.affectes, []);
    assert.equal(r1.autres.length, 3);
    const r2 = grouperMaterielPourSalarie(parc, new Set());
    assert.deepEqual(r2.affectes, []);
    assert.equal(r2.autres.length, 3);
  });

  it("place les actifs du salarie en tete sans doublon dans autres", () => {
    const { affectes, autres } = grouperMaterielPourSalarie(parc, new Set([2]));
    assert.deepEqual(affectes.map((a) => a.id), [2]);
    assert.deepEqual(autres.map((a) => a.id), [1, 3]);
  });

  it("gere une liste vide sans erreur", () => {
    const res = grouperMaterielPourSalarie([], new Set([1]));
    assert.deepEqual(res, { affectes: [], autres: [] });
  });
});
