import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { SERVICES, TITRES } from "../src/pme.ts";

const DOSSIER_PME = new URL("../../", import.meta.url);

describe("outils de la PME connus du poste", () => {
  it("chaque service range les outils que son serveur déclare, avec leur titre", () => {
    for (const service of SERVICES) {
      const source = readFileSync(new URL(`${service.cle}/src/serveur.ts`, DOSSIER_PME), "utf-8");
      const declares = [...source.matchAll(/registerTool\(\s*"([a-z_]+)",\s*\{\s*title:\s*"([^"]+)"/g)];
      assert.deepEqual([...service.outils].sort(), declares.map((d) => d[1]).sort(), `outils de ${service.cle}`);
      for (const [, nom = "", titre] of declares) {
        assert.equal(TITRES[nom], titre, `titre de ${nom}`);
      }
    }
  });
});
