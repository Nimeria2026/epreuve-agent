import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { classer } from "../src/rejeu.ts";

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
