import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { Commande } from "@poa/commun/contrats/commande";
import { creerServeurVentes } from "../src/serveur.ts";

/**
 * Le service sur l'état v1 de Négovelle (09_outillage/scripts/generer_negovelle_v1.py) : il lit son
 * catalogue et ses fiches, et il chiffre une commande comme le générateur, au centime près.
 */
const V1 = new URL("../../societes/negovelle/v1/", import.meta.url).pathname;

function etatDeNegovelle(): string {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-negovelle-"));
  for (const partie of ["entreprise", "dossiers", "facturation", "ventes"]) {
    cpSync(path.join(V1, partie), path.join(etat, partie), { recursive: true });
  }
  return etat;
}

async function clientPour(etat: string, pour: string): Promise<Client> {
  const [coteClient, coteServeur] = InMemoryTransport.createLinkedPair();
  await creerServeurVentes({ etat, pour }).connect(coteServeur);
  const client = new Client({ name: "test", version: "0" });
  await client.connect(coteClient);
  return client;
}

async function appeler(client: Client, nom: string, args: Record<string, unknown> = {}) {
  const resultat = (await client.callTool({ name: nom, arguments: args })) as CallToolResult;
  const premier = resultat.content[0];
  return { texte: premier?.type === "text" ? premier.text : "", erreur: resultat.isError === true };
}

function commandes(etat: string): Commande[] {
  const dossier = path.join(etat, "ventes", "commandes");
  return readdirSync(dossier)
    .sort()
    .map((nom) => JSON.parse(readFileSync(path.join(dossier, nom), "utf-8")) as Commande);
}

describe("ventes, sur l'état v1 de Négovelle", () => {
  it("chiffre une commande comme le générateur de l'état, au centime près", async () => {
    const etat = etatDeNegovelle();
    const client = await clientPour(etat, "corinne.vidal");
    const modeles = commandes(etat).filter((c) => c.reliquat_de === null && c.livraison.code !== null);
    assert.ok(modeles.length > 100);
    for (const modele of modeles.filter((_, rang) => rang % 10 === 0)) {
      const cree = await appeler(client, "creer_commande", {
        client: modele.client,
        lignes: modele.lignes.map((l) => ({ reference: l.reference, quantite: l.quantite })),
        livraison: modele.livraison.code,
        mode: modele.mode,
      });
      assert.equal(cree.erreur, false, cree.texte);
      const numero = /^Commande (CO-\d{4}-\d{5})/u.exec(cree.texte)?.[1] ?? "";
      const nouvelle = JSON.parse(
        readFileSync(path.join(etat, "ventes", "commandes", `${numero}.json`), "utf-8"),
      ) as Commande;
      assert.deepEqual(
        nouvelle.lignes.map((l) => [l.reference, l.prix_net_ht_euros, l.remise_pourcent, l.montant_ht_euros]),
        modele.lignes.map((l) => [l.reference, l.prix_net_ht_euros, l.remise_pourcent, l.montant_ht_euros]),
        modele.numero,
      );
      assert.deepEqual(
        [nouvelle.port_ht_euros, nouvelle.total_ht_euros, nouvelle.total_tva_euros, nouvelle.total_ttc_euros],
        [modele.port_ht_euros, modele.total_ht_euros, modele.total_tva_euros, modele.total_ttc_euros],
        modele.numero,
      );
    }
  });

  it("ne laisse aucun client ouvert au-delà de sa limite d'encours", async () => {
    const etat = etatDeNegovelle();
    const client = await clientPour(etat, "isabelle.royer");
    const codes = readdirSync(path.join(etat, "dossiers", "clients"))
      .filter((nom) => /^c-\d{4}$/u.test(nom))
      .sort();
    assert.equal(codes.length, 350);
    let bloques = 0;
    for (const code of codes) {
      const fiche = (await appeler(client, "consulter_client", { client: code })).texte;
      if (/^Statut : bloqué/mu.test(fiche)) {
        bloques += 1;
        continue;
      }
      assert.doesNotMatch(fiche, /reste -/u, code);
    }
    assert.equal(bloques, 5);
  });
});
