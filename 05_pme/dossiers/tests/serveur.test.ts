import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { creerServeurDossiers } from "../src/serveur.ts";

const ENTREPRISE_V1 = new URL("../../societes/calorelle/v1/entreprise/", import.meta.url).pathname;

/** Un état de PME minimal : l'entreprise v1 et quelques dossiers fictifs. */
function etatDeTest(): string {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-dossiers-"));
  cpSync(ENTREPRISE_V1, path.join(etat, "entreprise"), { recursive: true });
  const fichiers: Record<string, string> = {
    "administration/fournisseurs/thermopieces-loire/fiche.md": "Thermopièces Loire. FICTIF",
    "administration/factures_fournisseurs/2026-10/papeterie-du-val_pv-26-0388.pdf": "%PDF-1.4 FICTIF",
    "clients/c-0142/fiche.md": "Client c-0142, Bernard Lemoine. FICTIF",
    "rh/salaires.txt": "Confidentiel. FICTIF",
  };
  for (const [relatif, contenu] of Object.entries(fichiers)) {
    const absolu = path.join(etat, "dossiers", relatif);
    mkdirSync(path.dirname(absolu), { recursive: true });
    writeFileSync(absolu, contenu);
  }
  return etat;
}

async function clientPour(etat: string, pour: string): Promise<Client> {
  const [cote_client, cote_serveur] = InMemoryTransport.createLinkedPair();
  await creerServeurDossiers({ etat, pour }).connect(cote_serveur);
  const client = new Client({ name: "test", version: "0" });
  await client.connect(cote_client);
  return client;
}

async function appeler(
  client: Client,
  nom: string,
  args: Record<string, string>,
): Promise<{ texte: string; erreur: boolean }> {
  const resultat = (await client.callTool({ name: nom, arguments: args })) as CallToolResult;
  const premier = resultat.content[0];
  return { texte: premier?.type === "text" ? premier.text : "", erreur: resultat.isError === true };
}

describe("serveur MCP des dossiers, pour le comptable", () => {
  const etat = etatDeTest();
  let client: Client;
  before(async () => {
    client = await clientPour(etat, "patrick.roux");
  });
  after(async () => {
    await client.close();
  });

  it("annonce quatre outils", async () => {
    const { tools } = await client.listTools();
    assert.deepEqual(tools.map((t) => t.name).sort(), ["copier", "deplacer", "lire", "lister"]);
  });

  it("ne montre à la racine que les dossiers que la personne peut ouvrir", async () => {
    assert.equal((await appeler(client, "lister", {})).texte, "administration/");
  });

  it("liste un dossier et lit un document texte", async () => {
    assert.equal(
      (await appeler(client, "lister", { dossier: "administration" })).texte,
      "factures_fournisseurs/\nfournisseurs/",
    );
    const fiche = await appeler(client, "lire", { chemin: "administration/fournisseurs/thermopieces-loire/fiche.md" });
    assert.equal(fiche.texte, "Thermopièces Loire. FICTIF");
  });

  it("ne lit pas le contenu d'un PDF, seulement sa taille", async () => {
    const pdf = await appeler(client, "lire", {
      chemin: "administration/factures_fournisseurs/2026-10/papeterie-du-val_pv-26-0388.pdf",
    });
    assert.match(pdf.texte, /^Document PDF de 15 octets/);
  });

  it("déplace un document sur le disque, et refuse d'écraser", async () => {
    const source = "administration/factures_fournisseurs/2026-10/papeterie-du-val_pv-26-0388.pdf";
    const deplace = await appeler(client, "deplacer", {
      source,
      destination: "administration/factures_fournisseurs/2026-11",
    });
    assert.equal(deplace.texte, "administration/factures_fournisseurs/2026-11/papeterie-du-val_pv-26-0388.pdf");
    assert.ok(!existsSync(path.join(etat, "dossiers", source)));
    const copie = await appeler(client, "copier", {
      source: deplace.texte,
      destination: "administration/factures_fournisseurs/2026-11",
    });
    assert.ok(copie.erreur);
    assert.match(copie.texte, /un fichier existe déjà/);
  });

  it("refuse un dossier qui n'est pas le sien", async () => {
    const lecture = await appeler(client, "lire", { chemin: "rh/salaires.txt" });
    assert.ok(lecture.erreur);
    assert.match(lecture.texte, /accès refusé à rh\//);
    assert.ok((await appeler(client, "lister", { dossier: "clients" })).erreur);
  });

  it("refuse de sortir des dossiers partagés", async () => {
    for (const chemin of [
      "../entreprise/organigramme.yaml",
      "/etc/hostname",
      "administration/../../entreprise/fiche_entreprise.md",
    ]) {
      const lecture = await appeler(client, "lire", { chemin });
      assert.ok(lecture.erreur, chemin);
      assert.doesNotMatch(lecture.texte, /Calorelle/);
    }
  });

  it("signale un document absent sans planter", async () => {
    const lecture = await appeler(client, "lire", { chemin: "administration/absent.txt" });
    assert.ok(lecture.erreur);
    assert.match(lecture.texte, /fichier introuvable/);
  });
});

describe("serveur MCP des dossiers, autres personnes", () => {
  it("ouvre les dossiers clients à la chargée d'affaires", async () => {
    const client = await clientPour(etatDeTest(), "julie.perrin");
    assert.equal(
      (await appeler(client, "lire", { chemin: "clients/c-0142/fiche.md" })).texte,
      "Client c-0142, Bernard Lemoine. FICTIF",
    );
    await client.close();
  });

  it("refuse de démarrer pour une personne absente de l'organigramme", () => {
    assert.throws(() => creerServeurDossiers({ etat: etatDeTest(), pour: "personne.inconnue" }), /personne inconnue/);
  });
});

describe("lancement réel en stdio", () => {
  it("répond en MCP quand on le lance comme un programme", async () => {
    const etat = etatDeTest();
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [new URL("../src/principal.ts", import.meta.url).pathname, "--etat", etat, "--pour", "patrick.roux"],
      stderr: "ignore",
    });
    const client = new Client({ name: "test", version: "0" });
    await client.connect(transport);
    const fiche = await appeler(client, "lire", { chemin: "administration/fournisseurs/thermopieces-loire/fiche.md" });
    assert.equal(
      fiche.texte,
      readFileSync(path.join(etat, "dossiers/administration/fournisseurs/thermopieces-loire/fiche.md"), "utf-8"),
    );
    await client.close();
  });
});

describe("dossiers, sur les données v1 de Calorelle", () => {
  it("ouvre à la chargée d'affaires les dossiers clients, homonymes compris", async () => {
    const etat = mkdtempSync(path.join(tmpdir(), "poa-v1-"));
    cpSync(new URL("../../societes/calorelle/v1/", import.meta.url).pathname, etat, { recursive: true });
    const client = await clientPour(etat, "julie.perrin");
    const clients = (await appeler(client, "lister", { dossier: "clients" })).texte.split("\n");
    assert.equal(clients.filter((c) => c.endsWith("/")).length, 150);
    assert.ok(clients.includes("c-0142/") && clients.includes("c-0217/") && clients.includes("liste_clients.md"));
    assert.equal((await appeler(client, "lister", {})).texte, "clients/\ncommercial/\ncommun/");
    const fiche = await appeler(client, "lire", { chemin: "clients/c-0088/fiche_client.yaml" });
    assert.match(fiche.texte, /mois_anniversaire: "mars"/);
    await client.close();
  });
});
