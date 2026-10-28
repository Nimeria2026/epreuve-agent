import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { classer, etatDeDepart } from "../src/rejeu.ts";

describe("rejeu du gardien", () => {
  it("un avoir que la gérante simulée accepte n'est pas un blocage (t13)", () => {
    assert.equal(classer("validation", "accepter", false, true), "validation_acceptee");
    assert.equal(classer("validation", "accepter", true, true), "validation_acceptee");
  });

  it("un refus dans un run passé par le gardien a eu lieu ; il n'est pas à tort parce que l'exécution réussit (t10)", () => {
    assert.equal(classer("validation", "refuser", true, true), "refus_reel");
    assert.equal(classer("bloque", "refuser", true, false), "refus_reel");
  });

  it("sans gardien, un refus au rejeu est à tort probable si l'exécution réussit, une faute arrêtée sinon", () => {
    assert.equal(classer("bloque", "refuser", false, true), "a_tort_probable");
    assert.equal(classer("validation", "refuser", false, false), "faute_arretee");
  });
});

describe("état de départ d'une exécution rejouée", () => {
  it("pose le complément de la tâche sur l'état de la version, comme la remise à zéro d'EASE (t33)", () => {
    const racine = mkdtempSync(path.join(os.tmpdir(), "poa-rejeu-test-"));
    try {
      const version = path.join(racine, "v3");
      const complement = path.join(racine, "complement");
      mkdirSync(path.join(version, "messagerie", "boite"), { recursive: true });
      mkdirSync(path.join(complement, "messagerie", "boite"), { recursive: true });
      writeFileSync(path.join(version, "messagerie", "boite", "ancien.json"), "version");
      writeFileSync(path.join(version, "messagerie", "boite", "remplace.json"), "version");
      writeFileSync(path.join(complement, "messagerie", "boite", "m-sl-201.json"), "complément");
      writeFileSync(path.join(complement, "messagerie", "boite", "remplace.json"), "complément");
      writeFileSync(path.join(complement, "README.md"), "hors des parties d'un état");
      const depart = etatDeDepart(version, complement, racine);
      const lire = (nom: string) => readFileSync(path.join(depart, "messagerie", "boite", nom), "utf-8");
      assert.equal(lire("ancien.json"), "version");
      assert.equal(lire("m-sl-201.json"), "complément");
      assert.equal(lire("remplace.json"), "complément");
      assert.throws(() => readFileSync(path.join(depart, "README.md")));
      assert.equal(etatDeDepart(version, null, racine), version);
    } finally {
      rmSync(racine, { recursive: true, force: true });
    }
  });
});
