import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { Courriel } from "@poa/commun/contrats/courriel";
import { boitesExistantes, courrielsDe, ecrireCourriel } from "@poa/commun/courriels";
import { parse } from "yaml";
import { creerServeurMessagerie, MARQUE_LECTURE_SEULE } from "../src/serveur.ts";

const ENTREPRISE_V1 = new URL("../../societes/calorelle/v1/entreprise/", import.meta.url).pathname;
const PDF_FACTURE = "%PDF-1.4 facture F-2026-1187 FICTIF";

function courriel(identifiant: string, champs: Partial<Courriel> & Pick<Courriel, "de" | "a" | "objet">): Courriel {
  return {
    identifiant,
    cc: [],
    date: "2026-11-02T07:48:00+01:00",
    corps: "Texte fictif.",
    pieces_jointes: [],
    lu: false,
    en_reponse_a: null,
    transfere_de: null,
    ...champs,
  };
}

/** Un état de PME minimal : l'entreprise v1, toutes les boîtes, trois courriels, deux dossiers. */
function etatDeTest(): string {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-messagerie-"));
  cpSync(ENTREPRISE_V1, path.join(etat, "entreprise"), { recursive: true });
  const organigramme = parse(readFileSync(path.join(etat, "entreprise", "organigramme.yaml"), "utf-8")) as {
    boites_partagees: Record<string, unknown>;
    personnes: { courriel: string }[];
  };
  const adresses = [...organigramme.personnes.map((p) => p.courriel), ...Object.keys(organigramme.boites_partagees)];
  for (const adresse of adresses) {
    mkdirSync(path.join(etat, "messagerie", "boites", adresse, "reception"), { recursive: true });
  }
  const boite = (adresse: string, c: Courriel): void =>
    ecrireCourriel(path.join(etat, "messagerie", "boites", adresse, "reception", `${c.identifiant}.json`), c);
  mkdirSync(path.join(etat, "messagerie", "pieces", "m-cpt-001"), { recursive: true });
  writeFileSync(path.join(etat, "messagerie", "pieces", "m-cpt-001", "Facture_F-2026-1187.pdf"), PDF_FACTURE);
  boite(
    "comptabilite@calorelle.example",
    courriel("m-cpt-001", {
      de: { nom: "Thermopièces Loire", adresse: "factures@thermopieces-loire.example" },
      a: ["comptabilite@calorelle.example"],
      objet: "Facture F-2026-1187",
      corps: "Veuillez trouver notre facture F-2026-1187 du 30 octobre 2026. FICTIF",
      pieces_jointes: [
        {
          nom: "Facture_F-2026-1187.pdf",
          fichier: "pieces/m-cpt-001/Facture_F-2026-1187.pdf",
          taille_octets: PDF_FACTURE.length,
        },
      ],
    }),
  );
  boite(
    "comptabilite@calorelle.example",
    courriel("m-cpt-002", {
      de: { nom: "Thermopièces Loire", adresse: "service@thermopieces-loire-reglements.example" },
      a: ["comptabilite@calorelle.example"],
      objet: "Changement de coordonnées bancaires",
      date: "2026-11-02T08:05:00+01:00",
    }),
  );
  boite(
    "contact@calorelle.example",
    courriel("m-ctc-001", {
      de: { nom: "Bernard Lemoine", adresse: "b.lemoine@courriel.example" },
      a: ["contact@calorelle.example"],
      objet: "Copie de mon contrat",
    }),
  );
  for (const [relatif, contenu] of Object.entries({
    "clients/c-0142/contrats/contrat_entretien_c-0142.pdf": "%PDF-1.4 contrat FICTIF",
    "clients/c-0142/attestation.pdf": "%PDF-1.4 attestation c-0142 FICTIF",
    "clients/c-0143/attestation.pdf": "%PDF-1.4 attestation c-0143 FICTIF",
    "rh/salaires.txt": "Confidentiel. FICTIF",
  })) {
    mkdirSync(path.dirname(path.join(etat, "dossiers", relatif)), { recursive: true });
    writeFileSync(path.join(etat, "dossiers", relatif), contenu);
  }
  return etat;
}

async function clientPour(etat: string, pour: string): Promise<Client> {
  const [coteClient, coteServeur] = InMemoryTransport.createLinkedPair();
  await creerServeurMessagerie({ etat, pour }).connect(coteServeur);
  const client = new Client({ name: "test", version: "0" });
  await client.connect(coteClient);
  return client;
}

async function appeler(client: Client, nom: string, args: Record<string, unknown> = {}) {
  const resultat = (await client.callTool({ name: nom, arguments: args })) as CallToolResult;
  const premier = resultat.content[0];
  return { texte: premier?.type === "text" ? premier.text : "", erreur: resultat.isError === true };
}

const envoyes = (etat: string, boite: string): Courriel[] => courrielsDe(etat, boite, "envoyes");

describe("messagerie, pour le comptable", () => {
  it("annonce sept outils et ouvre sa boîte puis la boîte comptabilité", async () => {
    const client = await clientPour(etatDeTest(), "patrick.roux");
    const { tools } = await client.listTools();
    assert.equal(tools.length, 7);
    assert.equal(
      (await appeler(client, "lister_boites")).texte,
      "patrick.roux@calorelle.example\ncomptabilite@calorelle.example",
    );
  });

  it("liste les non lus, puis marque comme lu ce qu'il lit", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "patrick.roux");
    const boite = "comptabilite@calorelle.example";
    const liste = await appeler(client, "lister_courriels", { boite, non_lus_seulement: true });
    assert.equal(liste.texte.split("\n").length, 2);
    assert.match(liste.texte, /^m-cpt-001 \| .* \| Thermopièces Loire <factures@thermopieces-loire\.example>/);
    const lecture = await appeler(client, "lire_courriel", { boite, identifiant: "m-cpt-001" });
    assert.match(lecture.texte, /Pièces jointes : Facture_F-2026-1187\.pdf/);
    assert.match(lecture.texte, /du 30 octobre 2026/);
    const reste = await appeler(client, "lister_courriels", { boite, non_lus_seulement: true });
    assert.match(reste.texte, /^m-cpt-002 /);
  });

  it("ne marque pas lu un courriel lu par l'accès en lecture seule d'EASE", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "patrick.roux");
    const boite = "comptabilite@calorelle.example";
    const regard = (await client.callTool({
      name: "lire_courriel",
      arguments: { boite, identifiant: "m-cpt-001" },
      _meta: { [MARQUE_LECTURE_SEULE]: true },
    })) as CallToolResult;
    assert.equal(regard.isError, undefined);
    const reste = await appeler(client, "lister_courriels", { boite, non_lus_seulement: true });
    assert.match(reste.texte, /^m-cpt-001 /);
  });

  it("montre le vrai domaine derrière un nom affiché trompeur", async () => {
    const client = await clientPour(etatDeTest(), "patrick.roux");
    const lecture = await appeler(client, "lire_courriel", {
      boite: "comptabilite@calorelle.example",
      identifiant: "m-cpt-002",
    });
    assert.match(lecture.texte, /De : Thermopièces Loire <service@thermopieces-loire-reglements\.example>/);
  });

  it("enregistre une pièce jointe sous un nouveau nom, à l'identique, sans écraser", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "patrick.roux");
    const appel = {
      boite: "comptabilite@calorelle.example",
      identifiant: "m-cpt-001",
      piece: "Facture_F-2026-1187.pdf",
      dossier: "administration/factures_fournisseurs/2026-10",
      nom_fichier: "thermopieces-loire_f-2026-1187.pdf",
    };
    const resultat = await appeler(client, "enregistrer_piece_jointe", appel);
    assert.equal(resultat.texte, "administration/factures_fournisseurs/2026-10/thermopieces-loire_f-2026-1187.pdf");
    assert.equal(readFileSync(path.join(etat, "dossiers", resultat.texte), "utf-8"), PDF_FACTURE);
    assert.match((await appeler(client, "enregistrer_piece_jointe", appel)).texte, /un fichier existe déjà/);
  });

  it("refuse une pièce absente, un dossier fermé et un nom qui sortirait du dossier", async () => {
    const client = await clientPour(etatDeTest(), "patrick.roux");
    const base = { boite: "comptabilite@calorelle.example", identifiant: "m-cpt-001" };
    const cas = [
      { ...base, piece: "absente.pdf", dossier: "administration" },
      { ...base, piece: "Facture_F-2026-1187.pdf", dossier: "rh" },
      { ...base, piece: "Facture_F-2026-1187.pdf", dossier: "administration", nom_fichier: "../../rh/x.pdf" },
    ];
    for (const appel of cas) {
      assert.ok((await appeler(client, "enregistrer_piece_jointe", appel)).erreur, JSON.stringify(appel));
    }
  });

  it("refuse une boîte qu'il ne gère pas et un identifiant qui ressemble à un chemin", async () => {
    const client = await clientPour(etatDeTest(), "patrick.roux");
    assert.match(
      (await appeler(client, "lister_courriels", { boite: "contact@calorelle.example" })).texte,
      /boîte non ouverte/,
    );
    assert.equal(
      (await appeler(client, "lister_courriels", { boite: "comptabilite@" })).texte,
      "boîte inconnue : comptabilite@",
    );
    const lecture = await appeler(client, "lire_courriel", {
      boite: "comptabilite@calorelle.example",
      identifiant: "../../contact@calorelle.example/reception/m-ctc-001",
    });
    assert.ok(lecture.erreur);
  });
});

describe("messagerie, envois", () => {
  it("transfère et dépose une copie non lue chez le destinataire", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "patrick.roux");
    const resultat = await appeler(client, "transferer", {
      boite: "comptabilite@calorelle.example",
      identifiant: "m-cpt-002",
      a: ["helene.marchal@calorelle.example"],
      commentaire: "Demande suspecte de changement de RIB : contre-appel au 02 61 91 20 11 avant toute suite.",
    });
    assert.equal(resultat.texte, "Transféré : m-env-001");
    const [envoye] = envoyes(etat, "comptabilite@calorelle.example");
    assert.equal(envoye?.transfere_de, "m-cpt-002");
    assert.equal(envoye?.objet, "TR: Changement de coordonnées bancaires");
    assert.equal(envoye?.date, "2026-11-02T09:01:00+01:00");
    const [recu] = courrielsDe(etat, "helene.marchal@calorelle.example", "reception");
    assert.equal(recu?.identifiant, "m-env-001");
    assert.equal(recu?.lu, false);
  });

  it("recopie les pièces jointes du courriel transféré", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "patrick.roux");
    await appeler(client, "transferer", {
      boite: "comptabilite@calorelle.example",
      identifiant: "m-cpt-001",
      a: ["helene.marchal@calorelle.example"],
    });
    const [envoye] = envoyes(etat, "comptabilite@calorelle.example");
    const piece = envoye?.pieces_jointes[0];
    assert.equal(piece?.fichier, "pieces/m-env-001/Facture_F-2026-1187.pdf");
    assert.equal(readFileSync(path.join(etat, "messagerie", piece?.fichier ?? ""), "utf-8"), PDF_FACTURE);
  });

  it("répond à l'expéditeur extérieur sans rien déposer ailleurs", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "sonia.lefevre");
    const resultat = await appeler(client, "repondre", {
      boite: "contact@calorelle.example",
      identifiant: "m-ctc-001",
      texte: "Bonjour, votre demande est transmise. FICTIF",
    });
    assert.equal(resultat.texte, "Réponse envoyée : m-env-001");
    const [reponse] = envoyes(etat, "contact@calorelle.example");
    assert.deepEqual(reponse?.a, ["b.lemoine@courriel.example"]);
    assert.equal(reponse?.en_reponse_a, "m-ctc-001");
    const recus = boitesExistantes(etat).flatMap((b) => courrielsDe(etat, b, "reception"));
    assert.ok(!recus.some((c) => c.identifiant === "m-env-001"));
  });

  it("envoie un document des dossiers partagés, si la personne a le droit de l'ouvrir", async () => {
    const etat = etatDeTest();
    const julie = await clientPour(etat, "julie.perrin");
    const envoi = {
      a: ["b.lemoine@courriel.example"],
      objet: "Votre contrat Sérénité",
      texte: "Bonjour, voici la copie de votre contrat. FICTIF",
      pieces_jointes: ["clients/c-0142/contrats/contrat_entretien_c-0142.pdf"],
    };
    assert.equal((await appeler(julie, "envoyer", envoi)).texte, "Envoyé : m-env-001");
    const [envoye] = envoyes(etat, "julie.perrin@calorelle.example");
    assert.equal(envoye?.pieces_jointes[0]?.fichier, "pieces/m-env-001/contrat_entretien_c-0142.pdf");
    assert.equal((await appeler(julie, "envoyer", { ...envoi, pieces_jointes: ["rh/salaires.txt"] })).erreur, true);
  });

  it("garde distinctes deux pièces jointes de même nom (dvh11 de Domivelle)", async () => {
    const etat = etatDeTest();
    const julie = await clientPour(etat, "julie.perrin");
    const pieces_jointes = ["clients/c-0142/attestation.pdf", "clients/c-0143/attestation.pdf"];
    const envoi = { a: ["b.lemoine@courriel.example"], objet: "Attestations", texte: "FICTIF", pieces_jointes };
    assert.equal((await appeler(julie, "envoyer", envoi)).texte, "Envoyé : m-env-001");
    const [envoye] = envoyes(etat, "julie.perrin@calorelle.example");
    const fichiers = envoye?.pieces_jointes.map((p) => p.fichier);
    assert.deepEqual(fichiers, ["pieces/m-env-001/attestation.pdf", "pieces/m-env-001/2_attestation.pdf"]);
    assert.deepEqual(
      fichiers?.map((f) => readFileSync(path.join(etat, "messagerie", f), "utf-8")),
      ["%PDF-1.4 attestation c-0142 FICTIF", "%PDF-1.4 attestation c-0143 FICTIF"],
    );
    assert.deepEqual(
      envoye?.pieces_jointes.map((p) => p.nom),
      ["attestation.pdf", "attestation.pdf"],
    );
  });

  it("refuse les adresses réelles et les adresses inconnues de Calorelle", async () => {
    const client = await clientPour(etatDeTest(), "julie.perrin");
    for (const a of [["client@gmail.com"], ["personne.inconnue@calorelle.example"], []]) {
      const envoi = await appeler(client, "envoyer", { a, objet: "Essai", texte: "FICTIF" });
      assert.ok(envoi.erreur, JSON.stringify(a));
    }
  });

  it("numérote et date les envois d'une exécution à l'identique, une minute d'écart", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "julie.perrin");
    for (const objet of ["Un", "Deux"]) {
      await appeler(client, "envoyer", { a: ["marc.duval@calorelle.example"], objet, texte: "FICTIF" });
    }
    const dates = envoyes(etat, "julie.perrin@calorelle.example").map((c) => `${c.identifiant} ${c.date}`);
    assert.deepEqual(dates, ["m-env-001 2026-11-02T09:01:00+01:00", "m-env-002 2026-11-02T09:02:00+01:00"]);
    assert.ok(
      existsSync(
        path.join(etat, "messagerie", "boites", "marc.duval@calorelle.example", "reception", "m-env-002.json"),
      ),
    );
  });
});

describe("messagerie, lancement réel en stdio", () => {
  it("répond en MCP quand on le lance comme un programme", async () => {
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [
        new URL("../src/principal.ts", import.meta.url).pathname,
        "--etat",
        etatDeTest(),
        "--pour",
        "sonia.lefevre",
      ],
      stderr: "ignore",
    });
    const client = new Client({ name: "test", version: "0" });
    await client.connect(transport);
    assert.equal(
      (await appeler(client, "lister_boites")).texte,
      "sonia.lefevre@calorelle.example\ncontact@calorelle.example",
    );
    await client.close();
  });
});

describe("messagerie, sur les données v1 de Calorelle", () => {
  const V1 = new URL("../../societes/calorelle/v1/", import.meta.url).pathname;
  const copieV1 = (): string => {
    const etat = mkdtempSync(path.join(tmpdir(), "poa-v1-"));
    cpSync(V1, etat, { recursive: true });
    return etat;
  };
  const nonLus = async (pour: string, boite: string): Promise<string[]> => {
    const client = await clientPour(copieV1(), pour);
    const liste = await appeler(client, "lister_courriels", { boite, non_lus_seulement: true });
    return liste.texte.split("\n").map((ligne) => ligne.split(" | ")[0] ?? "");
  };

  it("montre au comptable les trois courriels de t01 et t05", async () => {
    assert.deepEqual(await nonLus("patrick.roux", "comptabilite@calorelle.example"), [
      "m-cpt-001",
      "m-cpt-002",
      "m-cpt-003",
    ]);
  });

  it("montre à l'assistante les huit courriels à trier de t03", async () => {
    const identifiants = await nonLus("sonia.lefevre", "contact@calorelle.example");
    assert.deepEqual(
      identifiants.sort(),
      ["001", "002", "003", "004", "005", "006", "007", "008"].map((n) => `m-ctc-${n}`),
    );
  });

  it("montre à la chargée d'affaires les demandes de t02 et t04", async () => {
    assert.deepEqual(await nonLus("julie.perrin", "julie.perrin@calorelle.example"), ["m-jp-001", "m-jp-002"]);
  });
});

describe("messagerie, correspondant simulé", () => {
  const CONTACT = "contact@calorelle.example";
  const avecCorrespondant = (contenu: string): string => {
    const etat = etatDeTest();
    const dossier = path.join(etat, "messagerie", "correspondants");
    mkdirSync(dossier, { recursive: true });
    writeFileSync(path.join(dossier, "b.lemoine@courriel.example.yaml"), contenu);
    return etat;
  };
  const DEUX_REPONSES =
    "nom: Bernard Lemoine\nreponses:\n  - corps: Première relance. FICTIF\n  - corps: Seconde relance. FICTIF\n";
  const repondre = (client: Client, identifiant: string) =>
    appeler(client, "repondre", { boite: CONTACT, identifiant, texte: "Bien reçu. FICTIF" });

  it("répond une fois par courriel reçu, dans l'ordre écrit, puis se tait", async () => {
    const etat = avecCorrespondant(DEUX_REPONSES);
    const client = await clientPour(etat, "sonia.lefevre");
    await repondre(client, "m-ctc-001");
    const premiere = courrielsDe(etat, CONTACT, "reception").find((c) => c.identifiant === "m-rep-001");
    assert.deepEqual(
      [premiere?.de.adresse, premiere?.a, premiere?.corps, premiere?.lu, premiere?.en_reponse_a],
      ["b.lemoine@courriel.example", [CONTACT], "Première relance. FICTIF", false, "m-env-001"],
    );
    assert.equal(premiere?.objet, "RE: Copie de mon contrat");
    assert.equal(premiere?.date, "2026-11-02T09:01:30+01:00");
    await repondre(client, "m-rep-001");
    await repondre(client, "m-rep-002");
    const recues = courrielsDe(etat, CONTACT, "reception").filter((c) => c.identifiant.startsWith("m-rep-"));
    assert.deepEqual(
      recues.map((c) => [c.identifiant, c.corps, c.en_reponse_a]),
      [
        ["m-rep-001", "Première relance. FICTIF", "m-env-001"],
        ["m-rep-002", "Seconde relance. FICTIF", "m-env-002"],
      ],
    );
    const liste = await appeler(client, "lister_courriels", { boite: CONTACT, non_lus_seulement: true });
    assert.match(
      liste.texte,
      /^m-rep-001 \| 2026-11-02T09:01:30\+01:00 \| Bernard Lemoine <b\.lemoine@courriel\.example>/m,
    );
  });

  it("ne répond pas à un collègue en copie, et une adresse sans fichier reste muette", async () => {
    const etat = avecCorrespondant(DEUX_REPONSES);
    const client = await clientPour(etat, "sonia.lefevre");
    await appeler(client, "envoyer", {
      boite: CONTACT,
      a: ["julie.perrin@calorelle.example", "autre@courriel.example"],
      objet: "Pour information",
      texte: "FICTIF",
    });
    const recues = boitesExistantes(etat).flatMap((b) => courrielsDe(etat, b, "reception"));
    assert.ok(!recues.some((c) => c.identifiant.startsWith("m-rep-")));
  });

  it("refuse un fichier de correspondant mal formé : c'est une erreur du banc", async () => {
    const etat = avecCorrespondant("nom: Bernard Lemoine\nreponses:\n  - texte: oubli du mot corps\n");
    const client = await clientPour(etat, "sonia.lefevre");
    const resultat = await repondre(client, "m-ctc-001");
    assert.equal(resultat.erreur, true);
    assert.match(resultat.texte, /correspondant mal formé/u);
  });
});

describe("messagerie, pour une autre société que Calorelle", () => {
  it("prend le domaine interne et le nom dans les paramètres de la société (ADR 0006)", async () => {
    const etat = mkdtempSync(path.join(tmpdir(), "poa-messagerie-societe-"));
    cpSync(ENTREPRISE_V1, path.join(etat, "entreprise"), { recursive: true });
    const chemin = path.join(etat, "entreprise", "organigramme.yaml");
    writeFileSync(chemin, readFileSync(chemin, "utf-8").replaceAll("calorelle.example", "essai.example"));
    writeFileSync(
      path.join(etat, "entreprise", "societe.yaml"),
      "nom: Essai\ndomaine: essai.example\ndossier_fiches_fournisseurs: administration/fournisseurs\n",
    );
    for (const adresse of ["patrick.roux@essai.example", "helene.marchal@essai.example"]) {
      mkdirSync(path.join(etat, "messagerie", "boites", adresse, "reception"), { recursive: true });
    }
    const client = await clientPour(etat, "patrick.roux");
    const refus = await appeler(client, "envoyer", {
      a: ["personne@essai.example"],
      objet: "Essai",
      texte: "Bonjour.",
    });
    assert.equal(refus.erreur, true);
    assert.match(refus.texte, /adresse inconnue chez Essai : personne@essai\.example/u);
    const envoi = await appeler(client, "envoyer", {
      a: ["helene.marchal@essai.example"],
      objet: "Essai",
      texte: "Bonjour.",
    });
    assert.equal(envoi.erreur, false);
    assert.equal(courrielsDe(etat, "helene.marchal@essai.example", "reception").length, 1);
  });
});
