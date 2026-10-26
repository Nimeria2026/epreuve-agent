import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";
import { setTimeout as attendre } from "node:timers/promises";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { SortieCandidat } from "@poa/commun/contrats/sortie_candidat";
import { z } from "zod";
import { Pme } from "../src/pme.ts";
import { creerPoste } from "../src/serveur.ts";

// Une PME réduite, servie deux fois comme par le relais d'EASE : l'accès des actions, qui offre tous
// les outils, et l'accès en lecture seule, qui n'offre que les outils déclarés en lecture.
type Appel = { readonly acces: string; readonly outil: string; readonly arguments: Record<string, unknown> };

const BOITE = "contact@calorelle.example";
const COURRIEL = [
  "Identifiant : m-ctc-501",
  "De : Agnès Martin <agnes.martin@exemple.example>",
  "Objet : Panne de chaudière",
  "Pièces jointes : photo.jpg (2048 octets)",
  "",
  "Bonjour, ma chaudière est en panne.",
].join("\n");

function pmeReduite(acces: string, journal: Appel[], actions: boolean): McpServer {
  const serveur = new McpServer({ name: `pme-${acces}`, version: "0" });
  const noter = (outil: string, arguments_: Record<string, unknown>, texte: string) => {
    journal.push({ acces, outil, arguments: arguments_ });
    return { content: [{ type: "text" as const, text: texte }] };
  };
  const lecture = { readOnlyHint: true };
  serveur.registerTool("lister_boites", { annotations: lecture }, () => noter("lister_boites", {}, BOITE));
  serveur.registerTool(
    "lister_courriels",
    {
      annotations: lecture,
      inputSchema: { boite: z.string().optional(), dossier: z.enum(["reception", "envoyes"]).default("reception") },
    },
    (a) =>
      noter(
        "lister_courriels",
        a,
        "m-ctc-501 | 2026-11-02T07:48:00+01:00 | Agnès Martin | Panne de chaudière | non lu | 1 pièce(s) jointe(s)",
      ),
  );
  serveur.registerTool(
    "lire_courriel",
    { annotations: lecture, inputSchema: { boite: z.string().optional(), identifiant: z.string() } },
    (a) => noter("lire_courriel", a, COURRIEL),
  );
  if (actions) {
    serveur.registerTool(
      "repondre",
      {
        annotations: { readOnlyHint: false },
        inputSchema: { boite: z.string().optional(), identifiant: z.string(), texte: z.string() },
      },
      (a) => noter("repondre", a, "Réponse envoyée : m-env-001"),
    );
    serveur.registerTool(
      "enregistrer_piece_jointe",
      {
        annotations: { readOnlyHint: false },
        inputSchema: { boite: z.string().optional(), identifiant: z.string(), piece: z.string(), dossier: z.string() },
      },
      (a) => noter("enregistrer_piece_jointe", a, "Enregistrée"),
    );
    serveur.registerTool("consulter_tarif", { title: "Consulter le tarif", annotations: lecture }, () =>
      noter("consulter_tarif", {}, "RAD-01 | radiateur | 180,00 €"),
    );
  }
  return serveur;
}

async function relier(serveur: McpServer): Promise<Client> {
  const [coteClient, coteServeur] = InMemoryTransport.createLinkedPair();
  await serveur.connect(coteServeur);
  const client = new Client({ name: "poste-test", version: "0" });
  await client.connect(coteClient);
  return client;
}

interface Banc {
  adresse: string;
  readonly journal: Appel[];
  readonly sorties: SortieCandidat[];
  arrets: number;
  heure: number;
}

async function ouvrirBanc(): Promise<{ banc: Banc; fermer: () => Promise<void> }> {
  const banc: Banc = { adresse: "", journal: [], sorties: [], arrets: 0, heure: 1_000 };
  const pme = new Pme(
    await relier(pmeReduite("actions", banc.journal, true)),
    await relier(pmeReduite("lecture", banc.journal, false)),
  );
  const serveur = creerPoste({
    pme,
    enonce: "Tu es l'assistant de Sonia Lefèvre. Trie la boîte contact@.",
    ecrireSortie: (s) => banc.sorties.push(s),
    quitter: () => {
      banc.arrets += 1;
    },
    maintenant: () => banc.heure,
  });
  await new Promise<void>((pret) => serveur.listen(0, "127.0.0.1", pret));
  banc.adresse = `http://127.0.0.1:${(serveur.address() as AddressInfo).port}`;
  return { banc, fermer: () => new Promise((fin) => serveur.close(() => fin())) };
}

async function obtenir(banc: Banc, chemin: string): Promise<Response> {
  return fetch(`${banc.adresse}${chemin}`, { redirect: "manual" });
}

async function poster(banc: Banc, chemin: string, champs: Record<string, string> = {}): Promise<Response> {
  return fetch(`${banc.adresse}${chemin}`, {
    method: "POST",
    redirect: "manual",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(champs).toString(),
  });
}

describe("poste humain", () => {
  let banc: Banc;
  let fermer: () => Promise<void>;

  before(async () => {
    ({ banc, fermer } = await ouvrirBanc());
  });
  after(async () => {
    await fermer();
  });

  it("attend « Commencer » sans montrer l'énoncé ni ouvrir la PME", async () => {
    const accueil = await (await obtenir(banc, "/")).text();
    assert.ok(accueil.includes("Commencer"));
    assert.ok(!accueil.includes("Sonia Lefèvre"));
    const messagerie = await obtenir(banc, "/messagerie");
    assert.equal(messagerie.status, 303);
    assert.equal(messagerie.headers.get("location"), "/");
    assert.deepEqual(banc.journal, []);
  });

  it("affiche par l'accès en lecture, lit un courriel et répond par les actions", async () => {
    const depart = await poster(banc, "/commencer");
    assert.equal(depart.headers.get("location"), "/accueil");
    const boite = await (await obtenir(banc, "/messagerie")).text();
    assert.ok(boite.includes("Sonia Lefèvre") && boite.includes("Panne de chaudière"));
    assert.deepEqual(
      banc.journal.map((a) => `${a.acces}:${a.outil}`),
      ["lecture:lister_boites", "lecture:lister_courriels"],
    );
    const courriel = await (await obtenir(banc, `/messagerie/lire?boite=${BOITE}&identifiant=m-ctc-501`)).text();
    assert.ok(courriel.includes("ma chaudière est en panne"));
    assert.ok(courriel.includes('<option value="photo.jpg" selected>photo.jpg</option>'));
    assert.equal(banc.journal.at(-1)?.acces, "actions");
    const reponse = await poster(banc, "/outil/repondre", {
      boite: BOITE,
      identifiant: "m-ctc-501",
      texte: "Un technicien vous rappelle.",
      _retour: "/messagerie",
    });
    assert.ok((await reponse.text()).includes("Réponse envoyée : m-env-001"));
    assert.deepEqual(banc.journal.at(-1), {
      acces: "actions",
      outil: "repondre",
      arguments: { boite: BOITE, identifiant: "m-ctc-501", texte: "Un technicien vous rappelle." },
    });
  });

  it("range un outil sans vue dédiée dans son service, et un formulaire mal rempli n'appelle rien", async () => {
    const facturation = await (await obtenir(banc, "/service/facturation")).text();
    assert.ok(facturation.includes("Consulter le tarif"));
    const avant = banc.journal.length;
    const refus = await (await poster(banc, "/outil/repondre", { identifiant: "m-ctc-501", texte: " " })).text();
    assert.ok(refus.includes("texte : un texte est attendu"));
    assert.ok(!refus.includes("Réponse envoyée"));
    assert.equal(banc.journal.length, avant);
  });

  it("arrête le chronomètre à « J'ai fini » confirmé et écrit la durée dans la sortie", async () => {
    banc.heure = 61_500;
    const confirmation = await (await poster(banc, "/fini")).text();
    assert.ok(confirmation.includes('action="/fini/confirmer"'));
    assert.equal(banc.sorties.length, 0);
    const merci = await (await poster(banc, "/fini/confirmer")).text();
    assert.ok(merci.includes("Merci, tâche suivante."));
    assert.ok(!merci.includes("réussi"));
    assert.deepEqual(banc.sorties, [
      {
        fin: "termine",
        detail: null,
        appels_modele: 0,
        consommation: {},
        modeles_renvoyes: {},
        duree_chronometree_secondes: 60.5,
      },
    ]);
    await attendre(400);
    assert.equal(banc.arrets, 1);
    const etat = (await (await obtenir(banc, "/etat")).json()) as { etat: string };
    assert.equal(etat.etat, "fini");
  });
});

describe("abandon d'un essai", () => {
  it("écrit une sortie en erreur, sans durée, pour que l'essai soit écarté", async () => {
    const { banc, fermer } = await ouvrirBanc();
    try {
      await poster(banc, "/commencer");
      await poster(banc, "/abandon/confirmer");
      assert.equal(banc.sorties.length, 1);
      assert.equal(banc.sorties[0]?.fin, "erreur");
      assert.equal(banc.sorties[0]?.duree_chronometree_secondes, undefined);
    } finally {
      await attendre(400);
      await fermer();
    }
  });
});
