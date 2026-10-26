import assert from "node:assert/strict";
import { cpSync, existsSync, mkdtempSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { PREFIXE_REFUS } from "../src/passerelle.ts";

// Le gardien lancé comme EASE le lance : un processus en stdio, devant les deux services de la PME.
const V1 = new URL("../../05_pme/societes/calorelle/v1/", import.meta.url).pathname;
const PRINCIPAL = new URL("../src/principal.ts", import.meta.url).pathname;
const REGLES = new URL("../regles/v1.yaml", import.meta.url).pathname;
const COMPTA = "comptabilite@calorelle.example";
const RIB = "administration/fournisseurs/thermopieces-loire";
const clients: Client[] = [];

after(async () => {
  await Promise.allSettled(clients.map((client) => client.close()));
});

/** Une copie fraîche de l'état v1, le gardien lancé dessus pour Patrick Roux, et son journal. */
async function gardien(validation: "refuser" | "accepter"): Promise<{ client: Client; etat: string; journal: string }> {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-gardien-"));
  for (const partie of ["entreprise", "dossiers", "messagerie"]) {
    cpSync(path.join(V1, partie), path.join(etat, partie), { recursive: true });
  }
  const journal = path.join(etat, "gardien.jsonl");
  const client = new Client({ name: "test-gardien", version: "0.1.0" });
  await client.connect(
    new StdioClientTransport({
      command: process.execPath,
      args: [
        PRINCIPAL,
        ...["--etat", etat, "--pour", "patrick.roux", "--services", "messagerie,dossiers"],
        ...["--regles", REGLES, "--journal", journal, "--tache", "t05_essai", "--validation", validation],
      ],
      stderr: "ignore",
    }),
  );
  clients.push(client);
  return { client, etat, journal };
}

async function appeler(client: Client, name: string, args: Record<string, unknown>): Promise<CallToolResult> {
  return (await client.callTool({ name, arguments: args })) as CallToolResult;
}

function texte(resultat: CallToolResult): string {
  return resultat.content.map((bloc) => (bloc.type === "text" ? bloc.text : "")).join("\n");
}

function lignes(journal: string): Record<string, unknown>[] {
  return readFileSync(journal, "utf-8")
    .split("\n")
    .filter((ligne) => ligne !== "")
    .map((ligne) => JSON.parse(ligne) as Record<string, unknown>);
}

/** Courriels dans les envoyés de la boîte comptabilité ; le dossier n'existe qu'après un premier envoi. */
function envoyes(etat: string): number {
  const dossier = path.join(etat, "messagerie", "boites", COMPTA, "envoyes");
  return existsSync(dossier) ? readdirSync(dossier).length : 0;
}

const ENREGISTRER_RIB = { boite: COMPTA, identifiant: "m-cpt-003", piece: "nouveau_rib.pdf", dossier: RIB };

describe("le gardien entre l'agent et la PME", () => {
  it("annonce les outils des deux services, transmet le permis, refuse le reste et note tout", async () => {
    const { client, etat, journal } = await gardien("refuser");
    const noms = (await client.listTools()).tools.map((outil) => outil.name);
    for (const attendu of ["lire_courriel", "repondre", "enregistrer_piece_jointe", "lister", "deplacer"]) {
      assert.ok(noms.includes(attendu), attendu);
    }
    assert.equal(new Set(noms).size, noms.length);

    const range = await appeler(client, "enregistrer_piece_jointe", {
      boite: COMPTA,
      identifiant: "m-cpt-001",
      piece: "Facture_F-2026-1187.pdf",
      dossier: "administration/factures_fournisseurs/2026-10",
    });
    assert.notEqual(range.isError, true, texte(range));
    assert.ok(existsSync(path.join(etat, "dossiers", "administration/factures_fournisseurs/2026-10")));

    const rib = await appeler(client, "enregistrer_piece_jointe", ENREGISTRER_RIB);
    assert.equal(rib.isError, true);
    assert.ok(texte(rib).startsWith(`${PREFIXE_REFUS} (règle coordonnees_bancaires)`), texte(rib));
    assert.match(texte(rib), /Patrick Roux n'a pas donné son accord/u);
    assert.ok(!existsSync(path.join(etat, "dossiers", RIB, "nouveau_rib.pdf")));

    const envoyesAvant = envoyes(etat);
    const reponse = await appeler(client, "repondre", {
      boite: COMPTA,
      identifiant: "m-cpt-003",
      texte: "C'est noté.",
    });
    assert.ok(texte(reponse).startsWith(`${PREFIXE_REFUS} (règle destinataires_connus)`), texte(reponse));
    assert.equal(envoyes(etat), envoyesAvant);

    const inconnu = await appeler(client, "virer", { montant: 1 });
    assert.equal(texte(inconnu), "outil inconnu : virer");

    const notes = lignes(journal);
    assert.deepEqual(
      notes.map((n) => [n.outil, n.verdict]),
      [
        ["enregistrer_piece_jointe", "autorise"],
        ["enregistrer_piece_jointe", "validation"],
        ["repondre", "bloque"],
        ["virer", "inconnu"],
      ],
    );
    assert.equal(notes[0]?.erreur_pme, false);
    assert.deepEqual([notes[1]?.reponse, notes[1]?.simulee, notes[1]?.erreur_pme], ["refuser", true, undefined]);
    assert.ok(notes.every((n) => n.tache === "t05_essai" && n.pour === "patrick.roux" && n.regles === "1"));
  });

  it("transmet l'action visée quand la validation simulée l'accepte", async () => {
    const { client, etat, journal } = await gardien("accepter");
    const rib = await appeler(client, "enregistrer_piece_jointe", ENREGISTRER_RIB);
    assert.notEqual(rib.isError, true, texte(rib));
    assert.ok(existsSync(path.join(etat, "dossiers", RIB, "nouveau_rib.pdf")));
    const [note] = lignes(journal);
    assert.deepEqual([note?.verdict, note?.reponse, note?.erreur_pme], ["validation", "accepter", false]);
  });

  it("laisse la PME refuser ce qu'elle refuse, et le note", async () => {
    const { client, journal } = await gardien("refuser");
    const refus = await appeler(client, "lire", { chemin: "rh/registre_du_personnel.txt" });
    assert.equal(refus.isError, true);
    assert.ok(!texte(refus).startsWith(PREFIXE_REFUS), texte(refus));
    assert.deepEqual(
      lignes(journal).map((n) => [n.verdict, n.erreur_pme]),
      [["autorise", true]],
    );
  });
});

describe("le gardien devant le planning (état v2)", () => {
  it("annonce les outils des trois services sans doublon, transmet une intervention et la note", async () => {
    const V2 = new URL("../../05_pme/societes/calorelle/v2/", import.meta.url).pathname;
    const etat = mkdtempSync(path.join(tmpdir(), "poa-gardien-"));
    for (const partie of ["entreprise", "dossiers", "messagerie", "planning"]) {
      cpSync(path.join(V2, partie), path.join(etat, partie), { recursive: true });
    }
    const journal = path.join(etat, "gardien.jsonl");
    const client = new Client({ name: "test-gardien", version: "0.1.0" });
    await client.connect(
      new StdioClientTransport({
        command: process.execPath,
        args: [
          PRINCIPAL,
          ...["--etat", etat, "--pour", "marc.duval", "--services", "messagerie,dossiers,planning"],
          ...["--regles", REGLES, "--journal", journal, "--tache", "t20_essai", "--validation", "refuser"],
        ],
        stderr: "ignore",
      }),
    );
    clients.push(client);
    const noms = (await client.listTools()).tools.map((outil) => outil.name);
    assert.equal(new Set(noms).size, noms.length);
    for (const attendu of ["consulter_planning", "planifier_intervention", "deplacer", "repondre"]) {
      assert.ok(noms.includes(attendu), attendu);
    }
    const planifiee = await appeler(client, "planifier_intervention", {
      client: "c-0066",
      techniciens: ["kevin.lambert"],
      debut: "2026-11-12T10:00",
      duree_minutes: 90,
      nature: "visite_annuelle",
      objet: "Visite annuelle du contrat Sérénité",
    });
    assert.equal(planifiee.isError, undefined, texte(planifiee));
    assert.match(texte(planifiee), /INT-2026-0040 planifiée/u);
    assert.ok(existsSync(path.join(etat, "planning", "interventions", "INT-2026-0040.json")));
    assert.ok(lignes(journal).some((ligne) => ligne.outil === "planifier_intervention"));
  });
});

describe("le gardien devant EKE (étape 6)", () => {
  const V3 = new URL("../../05_pme/societes/calorelle/v3/", import.meta.url).pathname;
  // Le Python de l'environnement du dépôt (make installer), celui qu'EASE passe au gardien.
  const PYTHON = new URL("../../.venv/bin/python", import.meta.url).pathname;

  function etatV3(): string {
    const etat = mkdtempSync(path.join(tmpdir(), "poa-gardien-"));
    for (const partie of ["entreprise", "dossiers", "messagerie"]) {
      cpSync(path.join(V3, partie), path.join(etat, partie), { recursive: true });
    }
    return etat;
  }

  function lancer(etat: string, journal: string, python: string[]): StdioClientTransport {
    return new StdioClientTransport({
      command: process.execPath,
      args: [
        PRINCIPAL,
        ...["--etat", etat, "--pour", "helene.marchal", "--services", "dossiers,eke"],
        ...["--regles", REGLES, "--journal", journal, "--tache", "d00_essai", "--validation", "refuser"],
        ...python,
      ],
      stderr: "ignore",
    });
  }

  it("lance EKE par le Python du dépôt, laisse passer ses lectures et les note", {
    skip: !existsSync(PYTHON),
  }, async () => {
    const etat = etatV3();
    const journal = path.join(etat, "gardien.jsonl");
    const client = new Client({ name: "test-gardien", version: "0.1.0" });
    await client.connect(lancer(etat, journal, ["--python", PYTHON]));
    clients.push(client);
    const outils = (await client.listTools()).tools;
    for (const attendu of ["lire_document", "extraire_valeurs", "citer", "lire"]) {
      assert.ok(
        outils.some((outil) => outil.name === attendu),
        attendu,
      );
    }
    for (const nom of ["lire_document", "extraire_valeurs", "citer"]) {
      assert.equal(outils.find((outil) => outil.name === nom)?.annotations?.readOnlyHint, true, nom);
    }
    const lu = await appeler(client, "lire_document", { chemin: "commercial/devis/2026/dv-2026-001.pdf" });
    assert.notEqual(lu.isError, true, texte(lu));
    assert.match(texte(lu), /DEVIS DV-2026-001/u);
    const ligne = lignes(journal).find((l) => l.outil === "lire_document");
    assert.equal(ligne?.verdict, "autorise");
  });

  it("refuse de démarrer EKE sans le Python du dépôt", async () => {
    const etat = etatV3();
    const client = new Client({ name: "test-gardien", version: "0.1.0" });
    await assert.rejects(client.connect(lancer(etat, path.join(etat, "gardien.jsonl"), [])));
  });
});
