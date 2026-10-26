import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { Devis } from "@poa/commun/contrats/devis";
import type { Tarif } from "@poa/commun/contrats/tarif";
import { pdfUnePage } from "@poa/commun/pdf";
import { ecartsContrat } from "@poa/commun/validation";
import { chiffrer } from "../src/chiffrage.ts";
import { creerServeurFacturation, lignesPdfDevis } from "../src/serveur.ts";

const ENTREPRISE_V2 = new URL("../../societes/calorelle/v2/entreprise/", import.meta.url).pathname;

const TARIF: Tarif = {
  annee: 2026,
  lignes: [
    { code: "CHA-01", libelle: "Chaudière à condensation", unite: "unité", prix_ht_euros: 3200 },
    { code: "MO-01", libelle: "Main-d'œuvre", unite: "heure", prix_ht_euros: 12.35 },
    { code: "DEP-01", libelle: "Dépose de l'ancien appareil", unite: "forfait", prix_ht_euros: 123.45 },
  ],
};

const ANCIEN: Devis = {
  numero: "DV-2026-012",
  client: "c-0142",
  objet: "Climatisation réversible",
  lignes: [
    {
      code: "DEP-01",
      libelle: "Dépose de l'ancien appareil",
      quantite: 1,
      prix_unitaire_ht_euros: 123.45,
      taux_tva: 10,
      montant_ht_euros: 123.45,
    },
  ],
  remise_pourcent: 0,
  total_ht_euros: 123.45,
  total_tva_euros: 12.35,
  total_ttc_euros: 135.8,
  statut: "envoye",
  cree_le: "2026-09-01T10:00:00+02:00",
  cree_par: "julie.perrin",
  envoye_le: "2026-09-01T11:00:00+02:00",
  reponse_le: null,
};

/** L'entreprise v2, un tarif, un client, un devis déjà envoyé. */
function etatDeTest(): string {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-devis-"));
  cpSync(ENTREPRISE_V2, path.join(etat, "entreprise"), { recursive: true });
  mkdirSync(path.join(etat, "facturation", "devis"), { recursive: true });
  writeFileSync(path.join(etat, "facturation", "tarif.json"), JSON.stringify(TARIF));
  writeFileSync(path.join(etat, "facturation", "devis", `${ANCIEN.numero}.json`), JSON.stringify(ANCIEN));
  const fiche = path.join(etat, "dossiers", "clients", "c-0142");
  mkdirSync(fiche, { recursive: true });
  writeFileSync(
    path.join(fiche, "fiche_client.yaml"),
    'code: "c-0142"\nnom: "Bernard Lemoine"\nadresse: "8 allée des Peupliers, 45999 Valmont-sur-Loire (FICTIF)"\n',
  );
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

function lireDevis(etat: string, numero: string): Devis {
  return JSON.parse(readFileSync(path.join(etat, "facturation", "devis", `${numero}.json`), "utf-8")) as Devis;
}

const DEMANDE = {
  client: "c-0142",
  objet: "Remplacement de chaudière",
  lignes: [
    { code: "CHA-01", quantite: 1, taux_tva: 20 },
    { code: "MO-01", quantite: 1.5, taux_tva: 5.5 },
  ],
};

describe("chiffrage d'un devis", () => {
  it("arrondit chaque ligne puis la TVA de chaque taux au centime, la moitié vers le haut", () => {
    // 1,5 × 12,35 = 18,525 → 18,53 ; TVA 5,5 % de 18,53 = 1,01915 → 1,02 ; TVA 20 % de 3 200 = 640.
    const chiffrage = chiffrer(TARIF, DEMANDE.lignes, 0);
    assert.deepEqual(
      chiffrage.lignes.map((l) => l.montant_ht_euros),
      [3200, 18.53],
    );
    assert.deepEqual(
      [chiffrage.total_ht_euros, chiffrage.total_tva_euros, chiffrage.total_ttc_euros],
      [3218.53, 641.02, 3859.55],
    );
  });

  it("ne dépend pas des flottants : 5,5 % de 123,45 € vaut 6,79 €", () => {
    // 12 345 centimes × 5,5 % = 678,975 centimes, arrondi à 679.
    const chiffrage = chiffrer(TARIF, [{ code: "DEP-01", quantite: 1, taux_tva: 5.5 }], 0);
    assert.equal(chiffrage.total_tva_euros, 6.79);
  });

  it("applique la remise à chaque ligne avant la TVA", () => {
    // 3 200 × 15 % = 480 ; 18,53 × 15 % = 2,7795 → 2,78 ; bases 2 720 et 15,75.
    const chiffrage = chiffrer(TARIF, DEMANDE.lignes, 15);
    assert.deepEqual([chiffrage.total_ht_euros, chiffrage.total_tva_euros], [2735.75, 544.87]);
  });
});

describe("devis, pour une chargée d'affaires", () => {
  it("annonce les outils des comptes clients et des devis", async () => {
    const client = await clientPour(etatDeTest(), "julie.perrin");
    assert.deepEqual((await client.listTools()).tools.map((t) => t.name).sort(), [
      "abandonner_devis",
      "consulter_compte_client",
      "consulter_devis",
      "consulter_tarif",
      "creer_devis",
      "emettre_avoir",
      "enregistrer_envoi",
      "enregistrer_reponse",
      "lister_devis",
    ]);
    const grille = await appeler(client, "consulter_tarif");
    assert.equal(grille.texte.split("\n")[1], "CHA-01 | Chaudière à condensation | unité | 3 200,00 €");
  });

  it("nomme dans la description du tarif la société de l'état, Calorelle sans societe.yaml", async () => {
    const description = async (etat: string): Promise<string | undefined> =>
      (await (await clientPour(etat, "julie.perrin")).listTools()).tools.find((t) => t.name === "consulter_tarif")
        ?.description;
    assert.equal(
      await description(etatDeTest()),
      "Montre la grille de prix de Calorelle : code, libellé, unité et prix hors taxes de chaque ligne.",
    );
    const autre = etatDeTest();
    writeFileSync(
      path.join(autre, "entreprise", "societe.yaml"),
      "nom: Négovelle\ndomaine: negovelle.example\ndossier_fiches_fournisseurs: fournisseurs\n",
    );
    assert.match((await description(autre)) ?? "", /^Montre la grille de prix de Négovelle :/u);
  });

  it("crée un brouillon conforme au contrat, numéroté à la suite, avec son PDF", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "julie.perrin");
    const resultat = await appeler(client, "creer_devis", DEMANDE);
    assert.equal(
      resultat.texte,
      "Devis DV-2026-013 créé en brouillon pour c-0142 : 3 859,55 € TTC. PDF : commercial/devis/2026/dv-2026-013.pdf",
    );
    const devis = lireDevis(etat, "DV-2026-013");
    assert.deepEqual(ecartsContrat("devis", devis), []);
    assert.equal(devis.statut, "brouillon");
    assert.equal(devis.cree_par, "julie.perrin");
    assert.equal(devis.cree_le, "2026-11-02T09:00:00+01:00");
    const pdf = readFileSync(path.join(etat, "dossiers", "commercial", "devis", "2026", "dv-2026-013.pdf"));
    const attendu = pdfUnePage(
      lignesPdfDevis(devis, {
        nom: "Bernard Lemoine",
        adresse: "8 allée des Peupliers, 45999 Valmont-sur-Loire (FICTIF)",
      }),
    );
    assert.deepEqual(new Uint8Array(pdf), attendu);
    assert.match(Buffer.from(pdf).toString("latin1"), /\(Total TTC : 3 859,55 \x80\) Tj/u);
  });

  it("numérote après le dernier PDF de l'année, même sans fiche de devis", async () => {
    const etat = etatDeTest();
    const dossier = path.join(etat, "dossiers", "commercial", "devis", "2026");
    mkdirSync(dossier, { recursive: true });
    writeFileSync(path.join(dossier, "dv-2026-020.pdf"), "ancien");
    const client = await clientPour(etat, "julie.perrin");
    assert.match((await appeler(client, "creer_devis", DEMANDE)).texte, /^Devis DV-2026-021 créé/u);
  });

  it("ne compte que les fichiers exactement nommés pour numéroter : un devis signé rangé là ne gêne pas", async () => {
    const etat = etatDeTest();
    const dossier = path.join(etat, "dossiers", "commercial", "devis", "2026");
    mkdirSync(dossier, { recursive: true });
    writeFileSync(path.join(dossier, "dv-2026-030-signe.pdf"), "signé");
    const client = await clientPour(etat, "julie.perrin");
    assert.match((await appeler(client, "creer_devis", DEMANDE)).texte, /^Devis DV-2026-013 créé/u);
  });

  it("refuse un objet que le PDF ne sait pas imprimer, sans rien écrire ni consommer de numéro", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "julie.perrin");
    const refus = await appeler(client, "creer_devis", { ...DEMANDE, objet: "Chaudière ≥ 25 kW" });
    assert.deepEqual(refus, { texte: "devis non créé : caractère absent de Windows-1252 : ≥", erreur: true });
    assert.equal(existsSync(path.join(etat, "facturation", "devis", "DV-2026-013.json")), false);
    assert.match((await appeler(client, "creer_devis", DEMANDE)).texte, /^Devis DV-2026-013 créé/u);
  });

  it("enregistre l'envoi d'un brouillon, puis la réponse, et pas dans le désordre", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "julie.perrin");
    await appeler(client, "creer_devis", DEMANDE);
    const tropTot = await appeler(client, "enregistrer_reponse", { numero: "DV-2026-013", reponse: "acceptation" });
    assert.deepEqual(tropTot, { texte: "le devis DV-2026-013 n'attend pas de réponse (brouillon)", erreur: true });
    assert.equal(
      (await appeler(client, "enregistrer_envoi", { numero: "DV-2026-013" })).texte,
      "Envoi du devis DV-2026-013 enregistré.",
    );
    assert.equal((await appeler(client, "enregistrer_envoi", { numero: "DV-2026-013" })).erreur, true);
    await appeler(client, "enregistrer_reponse", { numero: "DV-2026-012", reponse: "refus" });
    const liste = await appeler(client, "lister_devis", { client: "c-0142" });
    assert.equal(
      liste.texte,
      [
        "DV-2026-012 | c-0142 | 2026-09-01 | Climatisation réversible | 135,80 € TTC | refusé le 2026-11-02",
        "DV-2026-013 | c-0142 | 2026-11-02 | Remplacement de chaudière | 3 859,55 € TTC | envoyé le 2026-11-02",
      ].join("\n"),
    );
    assert.equal((await appeler(client, "lister_devis", { statut: "accepte" })).texte, "(aucun devis)");
  });

  it("abandonne un brouillon fait par erreur, et lui seul ; le numéro suivant ne le réutilise pas", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "julie.perrin");
    await appeler(client, "creer_devis", DEMANDE);
    assert.equal(
      (await appeler(client, "abandonner_devis", { numero: "DV-2026-013" })).texte,
      "Brouillon DV-2026-013 abandonné.",
    );
    assert.equal(lireDevis(etat, "DV-2026-013").statut, "abandonne");
    assert.equal(existsSync(path.join(etat, "dossiers", "commercial", "devis", "2026", "dv-2026-013.pdf")), true);
    const refus = await appeler(client, "abandonner_devis", { numero: "DV-2026-012" });
    assert.deepEqual(refus, {
      texte: "seul un brouillon s'abandonne ; le devis DV-2026-012 est envoyé le 2026-09-01",
      erreur: true,
    });
    assert.equal((await appeler(client, "enregistrer_envoi", { numero: "DV-2026-013" })).erreur, true);
    assert.match((await appeler(client, "creer_devis", DEMANDE)).texte, /^Devis DV-2026-014 créé/u);
  });

  it("montre un devis en détail, remise comprise", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "julie.perrin");
    await appeler(client, "creer_devis", { ...DEMANDE, remise_pourcent: 15 });
    const detail = await appeler(client, "consulter_devis", { numero: "DV-2026-013" });
    assert.equal(
      detail.texte,
      [
        "Devis DV-2026-013, client c-0142 (Bernard Lemoine)",
        "Objet : Remplacement de chaudière",
        "Créé le 2026-11-02 par julie.perrin ; statut : brouillon",
        "Lignes :",
        "CHA-01 | Chaudière à condensation | 1 × 3 200,00 € = 3 200,00 € HT | TVA 20 %",
        "MO-01 | Main-d'œuvre | 1,5 × 12,35 € = 18,53 € HT | TVA 5,5 %",
        "Remise : 15 % sur chaque ligne",
        "Total HT : 2 735,75 € ; TVA : 544,87 € ; Total TTC : 3 280,62 €",
        "PDF : commercial/devis/2026/dv-2026-013.pdf",
      ].join("\n"),
    );
  });

  it("refuse un code hors tarif, un taux inconnu, un client sans fiche, sans rien écrire", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "julie.perrin");
    const refus = [
      await appeler(client, "creer_devis", { ...DEMANDE, lignes: [{ code: "XXX-99", quantite: 1, taux_tva: 20 }] }),
      await appeler(client, "creer_devis", { ...DEMANDE, lignes: [{ code: "CHA-01", quantite: 1, taux_tva: 7 }] }),
      await appeler(client, "creer_devis", { ...DEMANDE, client: "c-0999" }),
      await appeler(client, "creer_devis", { ...DEMANDE, lignes: [{ code: "CHA-01", quantite: 0.333, taux_tva: 20 }] }),
    ];
    assert.deepEqual(
      refus.map((r) => r.texte),
      [
        "code absent du tarif : XXX-99 (consulter_tarif)",
        "taux de TVA invalide : 7 (5.5, 10 ou 20)",
        "client inconnu : c-0999 (aucune fiche client)",
        "quantité invalide : 0.333 (positive, au centième près)",
      ],
    );
    assert.ok(refus.every((r) => r.erreur));
    assert.equal(existsSync(path.join(etat, "facturation", "devis", "DV-2026-013.json")), false);
  });
});

describe("devis, pour le comptable", () => {
  it("garde les comptes clients et refuse les devis", async () => {
    const client = await clientPour(etatDeTest(), "patrick.roux");
    const refus = await appeler(client, "lister_devis");
    assert.deepEqual(refus, { texte: "accès refusé aux devis pour Patrick Roux", erreur: true });
  });
});
