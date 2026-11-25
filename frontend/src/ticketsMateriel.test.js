import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { conserverAssetPourSalarie, listeMaterielProposee } from "./ticketsMateriel.js";

describe("ticketsMateriel", () => {
  const parc = [
    { id: 1, identifiant_interne: "PC-01" },
    { id: 2, identifiant_interne: "PC-02" },
    { id: 3, identifiant_interne: "IMP-01" },
  ];
  const salarieA = [{ id: 2, identifiant_interne: "PC-02" }];

  it("sans salarie : renvoie tout le parc", () => {
    assert.deepEqual(
      listeMaterielProposee({ userId: "", assetsParc: parc, assetsSalarie: salarieA, horsAffectation: false }),
      parc,
    );
  });

  it("avec salarie et horsAffectation=false : renvoie uniquement ses actifs affectes", () => {
    assert.deepEqual(
      listeMaterielProposee({ userId: "10", assetsParc: parc, assetsSalarie: salarieA, horsAffectation: false }),
      salarieA,
    );
  });

  it("avec salarie et horsAffectation=true : rouvre tout le parc", () => {
    assert.deepEqual(
      listeMaterielProposee({ userId: "10", assetsParc: parc, assetsSalarie: salarieA, horsAffectation: true }),
      parc,
    );
  });

  it("changement de salarie : vide assetId si absent des actifs du nouveau salarie", () => {
    assert.equal(conserverAssetPourSalarie("2", salarieA), "2");
    assert.equal(conserverAssetPourSalarie("1", salarieA), "");
    assert.equal(conserverAssetPourSalarie("", salarieA), "");
  });
});
