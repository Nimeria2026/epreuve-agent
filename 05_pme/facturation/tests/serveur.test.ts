import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { FactureClient } from "@poa/commun/contrats/facture_client";
import { ecartsContrat } from "@poa/commun/validation";
import { creerServeurFacturation } from "../src/serveur.ts";

const ENTREPRISE_V1 = new URL("../../societes/calorelle/v1/entreprise/", import.meta.url).pathname;
const PRINCIPAL = new URL("../src/principal.ts", import.meta.url).pathname;

/** L'entreprise v1 et deux factures fictives, de deux clients. */
function etatDeTest(): string {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-facturation-"));
  cpSync(ENTREPRISE_V1, path.join(etat, "entreprise"), { recursive: true });
  const factures: FactureClient[] = [
    {
      numero: "FC-2026-0412",
      client: "c-0142",
      date: "2026-10-08",
      objet: "Visite d'entretien annuelle",
      montant_ttc_euros: 129,
      payee: true,
    },
    {
      numero: "FC-2026-0413",
      client: "c-0217",
      date: "2026-10-09",
      objet: "Visite d'entretien annuelle",
      montant_ttc_euros: 149,
      payee: false,
    },
  ];
  mkdirSync(path.join(etat, "facturation", "factures"), { recursive: true });
  for (const facture of factures) {
    writeFileSync(path.join(etat, "facturation", "factures", `${facture.numero}.json`), JSON.stringify(facture));
  }
  return etat;
}

async function clientPour(etat: string, pour: string): Promise<Client> {
  const [coteClient, coteServeur] = InMemoryTransport.createLinkedPair();
  await creerServeurFacturation({ etat, pour }).connect(coteServeur);
  const client = new Client({ name: "test", version: "0" });
  await client.connect(coteClient);
  return client;
}

async function appeler(client: Client, nom: string, args: Record<string, unknown> = {}) {
  const resultat = (await client.callTool({ name: nom, arguments: args })) as CallToolResult;
  const premier = resultat.content[0];
  return { texte: premier?.type === "text" ? premier.text : "", erreur: resultat.isError === true };
}

const AVOIR = { client: "c-0142", facture: "FC-2026-0412", montant_euros: 50, motif: "Retard du technicien" };

describe("facturation, pour une chargée d'affaires", () => {
  it("annonce les outils des comptes clients et montre le compte d'un client", async () => {
    const client = await clientPour(etatDeTest(), "julie.perrin");
    const outils = (await client.listTools()).tools.map((t) => t.name);
    assert.ok(outils.includes("consulter_compte_client") && outils.includes("emettre_avoir"));
    const compte = await appeler(client, "consulter_compte_client", { client: "c-0142" });
    assert.equal(
      compte.texte,
      "Factures de c-0142 :\nFC-2026-0412 | 2026-10-08 | Visite d'entretien annuelle | 129,00 € | payée\nAvoirs :\n(aucun avoir)",
    );
  });

  it("émet un avoir conforme au contrat, daté à l'heure simulée, puis le montre", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "julie.perrin");
    const resultat = await appeler(client, "emettre_avoir", AVOIR);
    assert.equal(resultat.texte, "Avoir AV-2026-0001 émis : 50,00 € sur FC-2026-0412 (client c-0142)");
    const avoir: unknown = JSON.parse(
      readFileSync(path.join(etat, "facturation", "avoirs", "AV-2026-0001.json"), "utf-8"),
    );
    assert.deepEqual(ecartsContrat("avoir", avoir), []);
    assert.deepEqual(avoir, {
      numero: "AV-2026-0001",
      client: "c-0142",
      facture: "FC-2026-0412",
      date: "2026-11-02T09:00:00+01:00",
      montant_ttc_euros: 50,
      motif: "Retard du technicien",
      emis_par: "julie.perrin",
    });
    const compte = await appeler(client, "consulter_compte_client", { client: "c-0142" });
    assert.match(compte.texte, /AV-2026-0001 \| 2026-11-02T09:00:00\+01:00 \| sur FC-2026-0412 \| 50,00 € \| Retard/u);
  });

  it("refuse la facture d'un autre client, un montant au-delà du reste, au centime près, sans motif", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "julie.perrin");
    const essais: [Record<string, unknown>, RegExp][] = [
      [{ ...AVOIR, facture: "FC-2026-0413" }, /introuvable pour le client c-0142/u],
      [{ ...AVOIR, montant_euros: 129.01 }, /il reste 129,00 €/u],
      [{ ...AVOIR, montant_euros: 0 }, /montant invalide/u],
      [{ ...AVOIR, montant_euros: 10.005 }, /montant invalide/u],
      [{ ...AVOIR, motif: "  " }, /motif de l'avoir est obligatoire/u],
      [{ ...AVOIR, client: "../c-0142" }, /code client invalide/u],
    ];
    for (const [args, motif] of essais) {
      const resultat = await appeler(client, "emettre_avoir", args);
      assert.equal(resultat.erreur, true, JSON.stringify(args));
      assert.match(resultat.texte, motif);
    }
    assert.ok(!existsSync(path.join(etat, "facturation", "avoirs")));
    await appeler(client, "emettre_avoir", { ...AVOIR, montant_euros: 98.85 });
    await appeler(client, "emettre_avoir", { ...AVOIR, montant_euros: 1.15 });
    const second = await appeler(client, "emettre_avoir", { ...AVOIR, montant_euros: 30 });
    assert.match(second.texte, /il reste 29,00 € à rembourser sur FC-2026-0412/u);
  });

  it("ferme la facturation à qui n'a aucun droit sur les clients ni la comptabilité", async () => {
    const client = await clientPour(etatDeTest(), "lucas.fontaine");
    const resultat = await appeler(client, "consulter_compte_client", { client: "c-0142" });
    assert.deepEqual(resultat, { texte: "accès refusé à la facturation pour Lucas Fontaine", erreur: true });
  });
});

describe("facturation, lancement réel en stdio", () => {
  it("répond en MCP quand on le lance comme un programme", async () => {
    const client = new Client({ name: "test", version: "0" });
    await client.connect(
      new StdioClientTransport({
        command: process.execPath,
        args: [PRINCIPAL, "--etat", etatDeTest(), "--pour", "helene.marchal"],
        stderr: "ignore",
      }),
    );
    const compte = await appeler(client, "consulter_compte_client", { client: "c-0217" });
    assert.match(compte.texte, /FC-2026-0413 .* à payer/u);
    await client.close();
  });
});
