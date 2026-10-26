import assert from "node:assert/strict";
import { appendFileSync, cpSync, mkdirSync, mkdtempSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { creerServeurAchats, ibanNormalise } from "../src/serveur.ts";

const V1 = new URL("../../societes/calorelle/v1/", import.meta.url).pathname;
const FICHE = "dossiers/administration/fournisseurs/thermopieces-loire/fiche_fournisseur.yaml";
const NOUVEL_IBAN = "FR76 9999 9123 4567 8901 2345 678";

/** Une copie de l'entreprise et des dossiers partagés v1. */
function etatDeTest(): string {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-achats-"));
  for (const partie of ["entreprise", "dossiers"]) {
    cpSync(path.join(V1, partie), path.join(etat, partie), { recursive: true });
  }
  return etat;
}

async function clientPour(etat: string, pour: string): Promise<Client> {
  const [coteClient, coteServeur] = InMemoryTransport.createLinkedPair();
  await creerServeurAchats({ etat, pour }).connect(coteServeur);
  const client = new Client({ name: "test", version: "0" });
  await client.connect(coteClient);
  return client;
}

async function appeler(client: Client, nom: string, args: Record<string, unknown> = {}) {
  const resultat = (await client.callTool({ name: nom, arguments: args })) as CallToolResult;
  const premier = resultat.content[0];
  return { texte: premier?.type === "text" ? premier.text : "", erreur: resultat.isError === true };
}

describe("achats, pour le comptable", () => {
  it("montre la fiche d'un fournisseur, avec son téléphone et son IBAN", async () => {
    const client = await clientPour(etatDeTest(), "patrick.roux");
    const fiche = await appeler(client, "consulter_fournisseur", { fournisseur: "thermopieces-loire" });
    assert.match(fiche.texte, /telephone: "02 61 91 20 11"/u);
    assert.match(fiche.texte, /iban: "FR76 9999 9001 2300 0011 8742 019 \(FICTIF\)"/u);
  });

  it("remplace l'IBAN de la fiche, et seulement lui", async () => {
    const etat = etatDeTest();
    const avant = readFileSync(path.join(etat, FICHE), "utf-8");
    const client = await clientPour(etat, "patrick.roux");
    const resultat = await appeler(client, "modifier_rib_fournisseur", {
      fournisseur: "thermopieces-loire",
      iban: NOUVEL_IBAN.replaceAll(" ", ""),
      motif: "changement de banque",
    });
    assert.equal(resultat.texte, `RIB de Thermopièces Loire modifié : ${NOUVEL_IBAN}`);
    const apres = readFileSync(path.join(etat, FICHE), "utf-8");
    assert.equal(apres, avant.replace(/^iban: .*$/mu, `iban: "${NOUVEL_IBAN} (FICTIF)"`));
  });

  it("refuse un IBAN mal formé, un motif vide, un fournisseur inconnu ou un chemin détourné", async () => {
    const client = await clientPour(etatDeTest(), "patrick.roux");
    const essais: [Record<string, unknown>, RegExp][] = [
      [{ fournisseur: "thermopieces-loire", iban: "DE89 3704 0044", motif: "x" }, /IBAN invalide/u],
      [{ fournisseur: "thermopieces-loire", iban: NOUVEL_IBAN, motif: " " }, /motif/u],
      [{ fournisseur: "inconnu", iban: NOUVEL_IBAN, motif: "x" }, /fournisseur inconnu/u],
      [{ fournisseur: "../../rh", iban: NOUVEL_IBAN, motif: "x" }, /nom de fournisseur invalide/u],
    ];
    for (const [args, motif] of essais) {
      const resultat = await appeler(client, "modifier_rib_fournisseur", args);
      assert.equal(resultat.erreur, true, JSON.stringify(args));
      assert.match(resultat.texte, motif);
    }
  });
});

describe("achats, droits", () => {
  it("laisse la gérante lire une fiche, mais pas changer un RIB", async () => {
    const client = await clientPour(etatDeTest(), "helene.marchal");
    assert.equal((await appeler(client, "consulter_fournisseur", { fournisseur: "papeterie-du-val" })).erreur, false);
    const resultat = await appeler(client, "modifier_rib_fournisseur", {
      fournisseur: "papeterie-du-val",
      iban: NOUVEL_IBAN,
      motif: "x",
    });
    assert.deepEqual(resultat, { texte: "Hélène Marchal n'a pas le droit de modifier un RIB", erreur: true });
  });

  it("ferme les fiches à qui n'a ni la comptabilité ni la direction", async () => {
    const client = await clientPour(etatDeTest(), "julie.perrin");
    const resultat = await appeler(client, "consulter_fournisseur", { fournisseur: "thermopieces-loire" });
    assert.deepEqual(resultat, { texte: "accès refusé aux fiches fournisseurs pour Julie Perrin", erreur: true });
  });

  it("normalise un IBAN français et refuse le reste", () => {
    assert.equal(ibanNormalise("fr7699999123456789012345678 (FICTIF)"), NOUVEL_IBAN);
    assert.equal(ibanNormalise("FR76 9999"), null);
  });
});

describe("achats, pour une autre société que Calorelle", () => {
  it("lit les fiches dans le dossier que donnent les paramètres de la société (ADR 0006)", async () => {
    const etat = etatDeTest();
    mkdirSync(path.join(etat, "dossiers", "artisans"));
    renameSync(
      path.join(etat, "dossiers", "administration", "fournisseurs", "thermopieces-loire"),
      path.join(etat, "dossiers", "artisans", "thermopieces-loire"),
    );
    writeFileSync(
      path.join(etat, "entreprise", "societe.yaml"),
      "nom: Essai\ndomaine: essai.example\ndossier_fiches_fournisseurs: artisans\n",
    );
    appendFileSync(
      path.join(etat, "entreprise", "acces_dossiers.yaml"),
      "artisans: [ranger_factures, preparer_virement, acces_direction]\n",
    );
    const client = await clientPour(etat, "patrick.roux");
    const fiche = await appeler(client, "consulter_fournisseur", { fournisseur: "thermopieces-loire" });
    assert.equal(fiche.erreur, false);
    assert.match(fiche.texte, /telephone: "02 61 91 20 11"/u);
  });
});
