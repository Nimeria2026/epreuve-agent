import assert from "node:assert/strict";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { creerServeurPlanning, lireInstant, rfc3339 } from "../src/serveur.ts";

const V1 = new URL("../../societes/calorelle/v1/", import.meta.url).pathname;
const CLIENT = "c-0124";

function ecrireJson(chemin: string, donnees: unknown): void {
  mkdirSync(path.dirname(chemin), { recursive: true });
  writeFileSync(chemin, `${JSON.stringify(donnees, null, 2)}\n`);
}

/** L'entreprise et les dossiers v1, plus un petit planning : trois techniciens, un rendez-vous. */
function etatDeTest(): string {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-planning-"));
  for (const partie of ["entreprise", "dossiers"]) {
    cpSync(path.join(V1, partie), path.join(etat, partie), { recursive: true });
  }
  const planning = path.join(etat, "planning");
  mkdirSync(planning, { recursive: true });
  writeFileSync(
    path.join(planning, "horaires.yaml"),
    'jours: [1, 2, 3, 4, 5]\nplages: ["08:00-12:00", "13:30-17:30"]\nferies: ["2026-11-11"]\n',
  );
  const techniciens = [
    { id: "thomas.girard", nom: "Thomas Girard", competences: ["chaudiere_gaz", "pompe_a_chaleur"], apprenti: false },
    { id: "enzo.caron", nom: "Enzo Caron", competences: ["chaudiere_gaz"], apprenti: true },
    {
      id: "nicolas.blanc",
      nom: "Nicolas Blanc",
      competences: ["climatisation", "pompe_a_chaleur"],
      apprenti: false,
      indisponibilites: [{ debut: "2026-11-05T00:00:00+01:00", fin: "2026-11-06T00:00:00+01:00" }],
    },
  ];
  for (const t of techniciens) {
    ecrireJson(path.join(planning, "techniciens", `${t.id}.json`), { indisponibilites: [], ...t });
  }
  ecrireJson(path.join(planning, "interventions", "INT-2026-0001.json"), {
    numero: "INT-2026-0001",
    client: CLIENT,
    techniciens: ["thomas.girard"],
    debut: "2026-11-03T08:00:00+01:00",
    fin: "2026-11-03T10:00:00+01:00",
    nature: "visite_annuelle",
    objet: "Entretien de la chaudière",
    statut: "planifiee",
    cree_par: "donnees_initiales",
  });
  return etat;
}

async function clientPour(etat: string, pour: string): Promise<Client> {
  const [coteClient, coteServeur] = InMemoryTransport.createLinkedPair();
  await creerServeurPlanning({ etat, pour }).connect(coteServeur);
  const client = new Client({ name: "test", version: "0" });
  await client.connect(coteClient);
  return client;
}

async function appeler(client: Client, nom: string, args: Record<string, unknown> = {}) {
  const resultat = (await client.callTool({ name: nom, arguments: args })) as CallToolResult;
  const premier = resultat.content[0];
  return { texte: premier?.type === "text" ? premier.text : "", erreur: resultat.isError === true };
}

function intervention(etat: string, numero: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path.join(etat, "planning", "interventions", `${numero}.json`), "utf-8"));
}

describe("heure de Paris", () => {
  it("écrit le décalage d'hiver et d'été, et lit une heure sans décalage comme l'heure de Paris", () => {
    assert.equal(rfc3339(lireInstant("2026-11-05T14:00")), "2026-11-05T14:00:00+01:00");
    assert.equal(rfc3339(lireInstant("2027-03-29T09:30")), "2027-03-29T09:30:00+02:00");
    assert.equal(lireInstant("2026-11-05T14:00:00+01:00"), lireInstant("2026-11-05T13:00:00Z"));
  });
});

describe("planning, pour le responsable planning", () => {
  it("liste les techniciens et le planning, indisponibilités sans motif", async () => {
    const client = await clientPour(etatDeTest(), "marc.duval");
    const liste = await appeler(client, "lister_techniciens");
    assert.match(liste.texte, /enzo\.caron \| Enzo Caron \| chaudiere_gaz \| apprenti/u);
    const planning = await appeler(client, "consulter_planning", { du: "2026-11-02", au: "2026-11-06" });
    assert.match(planning.texte, /INT-2026-0001 \| 2026-11-03 08:00-10:00 \| c-0124 \| thomas\.girard/u);
    assert.match(planning.texte, /nicolas\.blanc indisponible du 2026-11-05T00:00:00\+01:00/u);
  });

  it("planifie dans les heures, et refuse un conflit, un jour férié, un week-end, une plage dépassée", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "marc.duval");
    const ok = await appeler(client, "planifier_intervention", {
      client: CLIENT,
      techniciens: ["thomas.girard", "enzo.caron"],
      debut: "2026-11-03T10:00",
      duree_minutes: 90,
      nature: "visite_annuelle",
      objet: "Entretien annuel",
    });
    assert.equal(ok.erreur, false, ok.texte);
    assert.match(ok.texte, /INT-2026-0002 planifiée le 2026-11-03 à 10:00/u);
    const ecrite = intervention(etat, "INT-2026-0002");
    assert.equal(ecrite.debut, "2026-11-03T10:00:00+01:00");
    assert.equal(ecrite.fin, "2026-11-03T11:30:00+01:00");
    assert.equal(ecrite.cree_par, "marc.duval");
    const essais: [string, number, RegExp][] = [
      ["2026-11-03T09:00:00+01:00", 60, /n'est pas libre/u],
      ["2026-11-11T09:00:00+01:00", 60, /jour férié/u],
      ["2026-11-07T09:00:00+01:00", 60, /samedi 2026-11-07 n'est pas un jour d'intervention/u],
      ["2026-11-04T11:30:00+01:00", 60, /sort des heures d'intervention/u],
    ];
    for (const [debut, duree, attendu] of essais) {
      const refus = await appeler(client, "planifier_intervention", {
        client: CLIENT,
        techniciens: ["thomas.girard"],
        debut,
        duree_minutes: duree,
        nature: "depannage",
        objet: "Panne",
      });
      assert.equal(refus.erreur, true, debut);
      assert.match(refus.texte, attendu, debut);
    }
  });

  it("cherche des créneaux libres : apprenti signalé, compétence filtrée, indisponibilité respectée", async () => {
    const client = await clientPour(etatDeTest(), "marc.duval");
    const creneaux = await appeler(client, "chercher_creneaux", {
      du: "2026-11-03",
      au: "2026-11-03",
      duree_minutes: 120,
    });
    const lignes = creneaux.texte.split("\n");
    assert.equal(lignes[0], "2026-11-03 08:00-10:00 | enzo.caron (apprenti)");
    assert.ok(!lignes.some((l) => l.startsWith("2026-11-03 08:00-10:00 | thomas.girard")));
    const clim = await appeler(client, "chercher_creneaux", {
      du: "2026-11-05",
      au: "2026-11-06",
      duree_minutes: 60,
      competence: "climatisation",
    });
    assert.ok(clim.texte.split("\n").every((l) => l.startsWith("2026-11-06") && l.endsWith("nicolas.blanc")));
  });

  it("arrête après dix ans une recherche de créneaux qui ne trouve rien, sans attendre", async () => {
    const client = await clientPour(etatDeTest(), "marc.duval");
    const debut = Date.now();
    const sansFin = await appeler(client, "chercher_creneaux", {
      du: "2026-11-02",
      au: "9999-12-31",
      duree_minutes: 600,
    });
    assert.equal(sansFin.erreur, true);
    assert.match(sansFin.texte, /recherche arrêtée au \d{4}-\d{2}-\d{2} : 3660 jours parcourus, 0 créneau\(x\)/u);
    assert.ok(Date.now() - debut < 5_000);
    const ouverte = await appeler(client, "chercher_creneaux", {
      du: "2026-11-03",
      au: "9999-12-31",
      duree_minutes: 120,
    });
    assert.equal(ouverte.erreur, false, ouverte.texte);
    assert.equal(ouverte.texte.split("\n")[0], "2026-11-03 08:00-10:00 | enzo.caron (apprenti)");
  });

  it("déplace en gardant la durée, puis annule avec un motif", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "marc.duval");
    const deplace = await appeler(client, "deplacer_intervention", {
      numero: "INT-2026-0001",
      debut: "2026-11-03T09:00:00+01:00",
    });
    assert.equal(deplace.erreur, false, deplace.texte);
    assert.equal(intervention(etat, "INT-2026-0001").fin, "2026-11-03T11:00:00+01:00");
    const annule = await appeler(client, "annuler_intervention", { numero: "INT-2026-0001", motif: "client absent" });
    assert.equal(annule.erreur, false);
    assert.equal(intervention(etat, "INT-2026-0001").statut, "annulee");
    assert.equal(intervention(etat, "INT-2026-0001").motif_annulation, "client absent");
  });
});

describe("planning, droits", () => {
  it("une chargée d'affaires lit le planning sans le modifier ; le magasinier n'y a pas accès", async () => {
    const etat = etatDeTest();
    const julie = await clientPour(etat, "julie.perrin");
    assert.equal((await appeler(julie, "consulter_planning", { du: "2026-11-03", au: "2026-11-03" })).erreur, false);
    const refus = await appeler(julie, "annuler_intervention", { numero: "INT-2026-0001", motif: "essai" });
    assert.equal(refus.erreur, true);
    assert.match(refus.texte, /n'a pas le droit de modifier le planning/u);
    const lucas = await clientPour(etat, "lucas.fontaine");
    assert.match((await appeler(lucas, "lister_techniciens")).texte, /accès refusé au planning/u);
  });
});

const V2 = new URL("../../societes/calorelle/v2/", import.meta.url).pathname;

/** Une copie de l'état v2 : entreprise, dossiers et planning de départ. */
function copieDeV2(): string {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-planning-v2-"));
  for (const partie of ["entreprise", "dossiers", "planning"]) {
    cpSync(path.join(V2, partie), path.join(etat, partie), { recursive: true });
  }
  return etat;
}

describe("planning de départ de l'état v2", () => {
  it("se lit sans écart aux contrats : onze techniciens, neuf rendez-vous le mardi 3 novembre", async () => {
    const client = await clientPour(copieDeV2(), "marc.duval");
    const liste = await appeler(client, "lister_techniciens");
    assert.equal(liste.erreur, false, liste.texte);
    assert.equal(liste.texte.match(/^[a-z]+\.[a-z]+ \| /gmu)?.length, 11);
    assert.match(liste.texte, /^enzo\.caron \| Enzo Caron \| chaudiere_gaz \| apprenti$/mu);
    const mardi = await appeler(client, "consulter_planning", { du: "2026-11-03", au: "2026-11-03" });
    assert.equal(mardi.erreur, false, mardi.texte);
    assert.equal(mardi.texte.match(/^INT-2026-\d{4} \| 2026-11-03 /gmu)?.length, 9);
    assert.equal(mardi.texte.match(/^INT-2026-\d{4} .*thomas\.girard/gmu)?.length, 3);
  });

  it("numérote à la suite du planning de départ et refuse le 11 novembre, férié", async () => {
    const client = await clientPour(copieDeV2(), "marc.duval");
    const demande = {
      client: "c-0066",
      techniciens: ["kevin.lambert"],
      duree_minutes: 90,
      nature: "visite_annuelle",
      objet: "Visite annuelle du contrat Sérénité",
    };
    const ferie = await appeler(client, "planifier_intervention", { ...demande, debut: "2026-11-11T10:00" });
    assert.equal(ferie.erreur, true);
    assert.match(ferie.texte, /jour férié/u);
    const ok = await appeler(client, "planifier_intervention", { ...demande, debut: "2026-11-12T10:00" });
    assert.equal(ok.erreur, false, ok.texte);
    assert.match(ok.texte, /INT-2026-0040 planifiée le 2026-11-12 à 10:00/u);
  });
});
