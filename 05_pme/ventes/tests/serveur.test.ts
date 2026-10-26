import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { BonDeLivraison } from "@poa/commun/contrats/bon_de_livraison";
import type { Article, Catalogue } from "@poa/commun/contrats/catalogue";
import type { Commande } from "@poa/commun/contrats/commande";
import { ecartsContrat } from "@poa/commun/validation";
import { parse } from "yaml";
import { creerServeurVentes } from "../src/serveur.ts";

const PRINCIPAL = new URL("../src/principal.ts", import.meta.url).pathname;

const ORGANIGRAMME = `boites_partagees:
  commandes@negovelle.example: {gere_par: manon.rey}
personnes:
  - id: manon.rey
    nom: Manon Rey
    courriel: manon.rey@negovelle.example
    droits: [saisir_commandes]
  - id: gilles.poirier
    nom: Gilles Poirier
    courriel: gilles.poirier@negovelle.example
    droits: [acces_ventes]
  - id: dylan.moreau
    nom: Dylan Moreau
    courriel: dylan.moreau@negovelle.example
    droits: []
`;

function article(reference: string, libelle: string, autres: Partial<Article>): Article {
  return {
    reference,
    libelle,
    famille: "visserie",
    unite: "pièce",
    conditionnement: 1,
    prix_vente_ht_euros: 10,
    prix_net: false,
    bareme_quantite: [],
    taux_tva: 20,
    achat: {
      fournisseur: "fixations-berry",
      prix_net_facture_ht_euros: 5,
      avantages_financiers_pourcent: 0,
      transport_unitaire_ht_euros: 0,
    },
    stock_physique: 100,
    point_de_commande: 10,
    quantite_reassort: 50,
    reassort: null,
    statut: "courant",
    substituts: [],
    ...autres,
  };
}

const CATALOGUE: Catalogue = {
  annee_tarif: 2026,
  conditions: {
    remises_categories: { A: 0, B: 4, C: 8 },
    port_standard_ht_euros: 15,
    franco_a_partir_de_ht_euros: 300,
    forfait_express_ht_euros: 25,
    taux_tva_port: 20,
  },
  articles: [
    article("VIS-01482", "Vis à bois tête fraisée 5x50, boîte de 200", {
      prix_vente_ht_euros: 12.4,
      bareme_quantite: [
        { a_partir_de: 10, remise_pourcent: 3 },
        { a_partir_de: 50, remise_pourcent: 6 },
      ],
      achat: {
        fournisseur: "fixations-berry",
        prix_net_facture_ht_euros: 7.1,
        avantages_financiers_pourcent: 2,
        transport_unitaire_ht_euros: 0.15,
      },
      stock_physique: 120,
      substituts: ["VIS-01483"],
    }),
    article("VIS-01483", "Vis à bois tête fraisée 5x50 inox, boîte de 200", {
      prix_vente_ht_euros: 13.1,
      stock_physique: 500,
    }),
    article("GAN-00310", "Gants de protection nitrile, taille 9", {
      famille: "protection",
      unite: "paire",
      conditionnement: 12,
      prix_vente_ht_euros: 2.35,
      prix_net: true,
      stock_physique: 240,
    }),
    article("PLB-02210", "Raccord laiton 15x21", {
      famille: "plomberie",
      prix_vente_ht_euros: 4.85,
      stock_physique: 30,
      reassort: { quantite: 100, date_prevue: "2026-07-10" },
    }),
    article("ELE-00775", "Disjoncteur 16 A", {
      famille: "electricite",
      prix_vente_ht_euros: 9.9,
      stock_physique: 14,
      statut: "dereference",
    }),
  ],
};

function fiche(code: string, nom: string, autres: string): string {
  return `code: "${code}"
nom: "${nom}"
type: "artisan"
adresse: "3 rue des Saules, 36999 Vaumoreau-sur-Indre (FICTIF)"
telephone: "02 61 91 50 01"
secteur: "nord"
commercial: "laurent.gimenez"
administration_des_ventes: "manon.rey"
contacts:
  - {nom: "Paul Ferrand", fonction: "gérant", courriel: "paul.ferrand@ferrand-elec.example"}
adresses_livraison:
  - {code: "L1", libelle: "siège", adresse: "3 rue des Saules, 36999 Vaumoreau-sur-Indre (FICTIF)"}
  - {code: "L2", libelle: "dépôt", adresse: "ZA des Grands Prés, 36999 Vaumoreau-sur-Indre (FICTIF)"}
delai_paiement: "30_jours_date_de_facture"
client_depuis: "2019-03-01"
livraisons_partielles: true
substitution_acceptee: false
${autres}`;
}

function commande(numero: string, client: string, statut: Commande["statut"], autres: Partial<Commande>): Commande {
  return {
    numero,
    client,
    reference_client: null,
    cree_le: "2026-07-01T10:00:00+02:00",
    cree_par: "manon.rey",
    mode: "standard",
    livraison: { code: "L1", adresse: "3 rue des Saules, 36999 Vaumoreau-sur-Indre (FICTIF)" },
    lignes: [
      {
        reference: "PLB-02210",
        libelle: "Raccord laiton 15x21",
        quantite: 20,
        prix_tarif_ht_euros: 4.85,
        remise_pourcent: 0,
        prix_net_ht_euros: 4.85,
        prix_derogatoire: false,
        taux_tva: 20,
        montant_ht_euros: 97,
      },
    ],
    port_ht_euros: 0,
    total_ht_euros: 100,
    total_tva_euros: 20,
    total_ttc_euros: 120,
    statut,
    motif_attente: null,
    reliquat_de: null,
    livraisons: [],
    facture: null,
    historique: [],
    ...autres,
  };
}

const LIVRAISON: BonDeLivraison = {
  numero: "BL-2026-00020",
  commande: "CO-2026-00011",
  client: "c-0101",
  date_expedition: "2026-06-30",
  date_livraison: "2026-07-01",
  transport: { mode: "transporteur", transporteur: "messagerie-centre", recepisse: "MC-778120" },
  adresse: "3 rue des Saules, 36999 Vaumoreau-sur-Indre (FICTIF)",
  colis: 2,
  lignes: [
    { reference: "VIS-01482", libelle: "Vis à bois tête fraisée 5x50, boîte de 200", quantite: 20 },
    { reference: "GAN-00310", libelle: "Gants de protection nitrile, taille 9", quantite: 24 },
  ],
  reserves: "un carton enfoncé",
  signataire: "P. Ferrand",
  statut: "livre",
};

function ecrire(chemin: string, contenu: unknown): void {
  mkdirSync(path.dirname(chemin), { recursive: true });
  writeFileSync(chemin, typeof contenu === "string" ? contenu : JSON.stringify(contenu, null, 2));
}

/**
 * Un état de négoce réduit : trois clients, l'un bloqué, l'autre à la limite d'encours basse ; une
 * facture non réglée et un avoir ; une commande validée qui réserve 20 raccords sur 30 ; une commande
 * livrée non facturée ; son bon de livraison.
 */
function etatDeTest(): string {
  const etat = mkdtempSync(path.join(tmpdir(), "poa-ventes-"));
  ecrire(path.join(etat, "entreprise", "organigramme.yaml"), ORGANIGRAMME);
  ecrire(path.join(etat, "entreprise", "horloge.yaml"), 'debut: "2026-07-06T08:00:00+02:00"\n');
  ecrire(path.join(etat, "ventes", "catalogue.json"), CATALOGUE);
  const clients = path.join(etat, "dossiers", "clients");
  ecrire(
    path.join(clients, "c-0101", "fiche_client.yaml"),
    fiche(
      "c-0101",
      "Ferrand Électricité",
      'categorie_remise: "B"\nlimite_encours_euros: 2000\nstatut: "ouvert"\nmotif_blocage: null\n',
    ),
  );
  ecrire(
    path.join(clients, "c-0102", "fiche_client.yaml"),
    fiche(
      "c-0102",
      "Ateliers Morin",
      'categorie_remise: "C"\nlimite_encours_euros: 5000\nstatut: "bloque"\nmotif_blocage: "contentieux, factures de mars"\n',
    ),
  );
  ecrire(
    path.join(clients, "c-0103", "fiche_client.yaml"),
    fiche(
      "c-0103",
      "Plomberie Aubry",
      'categorie_remise: "A"\nlimite_encours_euros: 500\nstatut: "ouvert"\nmotif_blocage: null\n',
    ),
  );
  const facturation = path.join(etat, "facturation");
  ecrire(path.join(facturation, "factures", "FC-2026-0301.json"), {
    numero: "FC-2026-0301",
    client: "c-0101",
    date: "2026-06-02",
    objet: "Commande CO-2026-00004",
    montant_ttc_euros: 900,
    payee: false,
  });
  ecrire(path.join(facturation, "factures", "FC-2026-0302.json"), {
    numero: "FC-2026-0302",
    client: "c-0101",
    date: "2026-05-12",
    objet: "Commande CO-2026-00002",
    montant_ttc_euros: 400,
    payee: true,
  });
  ecrire(path.join(facturation, "avoirs", "AV-2026-0001.json"), {
    numero: "AV-2026-0001",
    client: "c-0101",
    facture: "FC-2026-0301",
    date: "2026-06-10T10:00:00+02:00",
    montant_ttc_euros: 100,
    motif: "article cassé à la livraison",
    emis_par: "remi.joly",
  });
  const commandes = path.join(etat, "ventes", "commandes");
  ecrire(path.join(commandes, "CO-2026-00010.json"), commande("CO-2026-00010", "c-0103", "validee", {}));
  ecrire(
    path.join(commandes, "CO-2026-00011.json"),
    commande("CO-2026-00011", "c-0101", "livree", { total_ht_euros: 250, total_tva_euros: 50, total_ttc_euros: 300 }),
  );
  ecrire(path.join(etat, "ventes", "livraisons", "BL-2026-00020.json"), LIVRAISON);
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

function lireCommande(etat: string, numero: string): Commande {
  const donnees: unknown = JSON.parse(readFileSync(path.join(etat, "ventes", "commandes", `${numero}.json`), "utf-8"));
  assert.deepEqual(ecartsContrat("commande", donnees), []);
  return donnees as Commande;
}

function lireCatalogue(etat: string): Catalogue {
  return JSON.parse(readFileSync(path.join(etat, "ventes", "catalogue.json"), "utf-8")) as Catalogue;
}

const DEUX_LIGNES = [
  { reference: "VIS-01482", quantite: 10 },
  { reference: "GAN-00310", quantite: 24 },
];

describe("ventes, les outils", () => {
  it("déclare quatorze outils, dont six en lecture seule", async () => {
    const client = await clientPour(etatDeTest(), "manon.rey");
    const { tools } = await client.listTools();
    assert.equal(tools.length, 14);
    const lecture = tools.filter((t) => t.annotations?.readOnlyHint === true).map((t) => t.name);
    assert.deepEqual(lecture.sort(), [
      "chercher_articles",
      "consulter_article",
      "consulter_client",
      "consulter_commande",
      "consulter_livraison",
      "lister_commandes",
    ]);
  });
});

describe("ventes, consultation", () => {
  it("cherche sans tenir compte des accents ni des majuscules", async () => {
    const client = await clientPour(etatDeTest(), "gilles.poirier");
    const trouve = await appeler(client, "chercher_articles", { texte: "VIS A BOIS" });
    assert.match(trouve.texte, /^2 article\(s\) :/u);
    assert.match(trouve.texte, /VIS-01482 .* disponible 120 \| courant/u);
  });

  it("calcule le disponible d'un article sur les commandes validées", async () => {
    const client = await clientPour(etatDeTest(), "gilles.poirier");
    const fiche = await appeler(client, "consulter_article", { reference: "PLB-02210" });
    assert.match(fiche.texte, /30 en rayon, 20 réservées, 10 disponibles/u);
    assert.match(fiche.texte, /100 unités attendues le 2026-07-10/u);
  });

  it("donne l'encours d'un client : factures non réglées, avoirs déduits, commandes non facturées", async () => {
    const client = await clientPour(etatDeTest(), "manon.rey");
    const fiche = await appeler(client, "consulter_client", { client: "c-0101" });
    assert.match(
      fiche.texte,
      /Encours : 1 100,00 € TTC \(factures non réglées 800,00 €, commandes non facturées 300,00 €\) ; limite 2 000,00 € ; reste 900,00 €/u,
    );
    assert.match(fiche.texte, /Catégorie de remise : B \(4 %\)/u);
  });
});

describe("ventes, commandes", () => {
  it("chiffre une commande : remise de la catégorie puis barème, prix net sans remise, port sous le franco", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    const cree = await appeler(client, "creer_commande", { client: "c-0101", lignes: DEUX_LIGNES, livraison: "L2" });
    assert.equal(cree.erreur, false, cree.texte);
    const c = lireCommande(etat, "CO-2026-00012");
    // 12,40 × 0,96 × 0,97 = 11,54688, arrondi à 11,55 ; les gants, prix net, restent à 2,35.
    assert.deepEqual(
      c.lignes.map((l) => [l.prix_net_ht_euros, l.remise_pourcent, l.montant_ht_euros]),
      [
        [11.55, 6.88, 115.5],
        [2.35, 0, 56.4],
      ],
    );
    assert.deepEqual(
      [c.port_ht_euros, c.total_ht_euros, c.total_tva_euros, c.total_ttc_euros],
      [15, 186.9, 37.38, 224.28],
    );
    assert.equal(c.statut, "brouillon");
    assert.equal(c.livraison.code, "L2");
  });

  it("applique le forfait express, et le franco à partir de 300 € HT", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    await appeler(client, "creer_commande", {
      client: "c-0101",
      lignes: DEUX_LIGNES,
      livraison: "L1",
      mode: "express",
    });
    assert.equal(lireCommande(etat, "CO-2026-00012").total_ttc_euros, 236.28);
    await appeler(client, "creer_commande", {
      client: "c-0101",
      lignes: [{ reference: "VIS-01483", quantite: 30 }],
      livraison: "L1",
    });
    const franco = lireCommande(etat, "CO-2026-00013");
    assert.deepEqual([franco.port_ht_euros, franco.total_ht_euros, franco.total_ttc_euros], [0, 377.4, 452.88]);
  });

  it("refuse une adresse hors de la fiche et une quantité hors du conditionnement", async () => {
    const client = await clientPour(etatDeTest(), "manon.rey");
    const adresse = await appeler(client, "creer_commande", { client: "c-0101", lignes: DEUX_LIGNES, livraison: "L7" });
    assert.deepEqual(adresse, { texte: "adresse L7 absente de la fiche de c-0101 (adresses : L1, L2)", erreur: true });
    const multiple = await appeler(client, "creer_commande", {
      client: "c-0101",
      lignes: [{ reference: "GAN-00310", quantite: 10 }],
      livraison: "L1",
    });
    assert.equal(multiple.erreur, true);
    assert.match(multiple.texte, /se vend par 12/u);
  });

  it("valide une commande dans l'encours et réserve son stock", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    await appeler(client, "creer_commande", { client: "c-0101", lignes: DEUX_LIGNES, livraison: "L1" });
    const validee = await appeler(client, "valider_commande", { numero: "CO-2026-00012" });
    assert.equal(validee.texte, "Commande CO-2026-00012 validée : 224,28 € TTC, stock réservé.");
    const fiche = await appeler(client, "consulter_article", { reference: "VIS-01482" });
    assert.match(fiche.texte, /120 en rayon, 10 réservées, 110 disponibles/u);
  });

  it("refuse un manque de stock sans livraison partielle, et ne change rien", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    await appeler(client, "creer_commande", {
      client: "c-0101",
      lignes: [
        { reference: "PLB-02210", quantite: 25 },
        { reference: "VIS-01482", quantite: 10 },
      ],
      livraison: "L1",
    });
    const refus = await appeler(client, "valider_commande", { numero: "CO-2026-00012" });
    assert.deepEqual(refus, {
      texte: "stock insuffisant, rien n'est validé : PLB-02210 demandé 25, disponible 10",
      erreur: true,
    });
    assert.equal(lireCommande(etat, "CO-2026-00012").statut, "brouillon");
  });

  it("livre le disponible et met le reste en reliquat, sans perdre le port de la commande entière", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    await appeler(client, "creer_commande", {
      client: "c-0101",
      lignes: [
        { reference: "PLB-02210", quantite: 25 },
        { reference: "VIS-01482", quantite: 10 },
      ],
      livraison: "L1",
    });
    const partielle = await appeler(client, "valider_commande", { numero: "CO-2026-00012", livraison_partielle: true });
    assert.match(partielle.texte, /le reliquat CO-2026-00013 attend le réassort/u);
    const gardee = lireCommande(etat, "CO-2026-00012");
    const reliquat = lireCommande(etat, "CO-2026-00013");
    assert.equal(gardee.statut, "validee");
    assert.deepEqual(
      gardee.lignes.map((l) => [l.reference, l.quantite]),
      [
        ["PLB-02210", 10],
        ["VIS-01482", 10],
      ],
    );
    // 4,85 × 0,96 = 4,656, arrondi à 4,66 ; 10 × 4,66 + 115,50 = 162,10, plus le port de 15 €.
    assert.equal(gardee.total_ht_euros, 177.1);
    assert.deepEqual(
      [reliquat.statut, reliquat.reliquat_de, reliquat.port_ht_euros, reliquat.lignes.map((l) => l.quantite)],
      ["en_attente_reassort", "CO-2026-00012", 0, [15]],
    );
  });

  it("met en attente une commande qui dépasse l'encours, puis la débloque", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    await appeler(client, "creer_commande", {
      client: "c-0103",
      lignes: [{ reference: "VIS-01483", quantite: 30 }],
      livraison: "L1",
    });
    const attente = await appeler(client, "valider_commande", { numero: "CO-2026-00012" });
    assert.equal(
      attente.texte,
      "Commande CO-2026-00012 en attente de déblocage : encours 120,00 € et commande 471,60 € TTC pour une limite de 500,00 €.",
    );
    assert.equal(lireCommande(etat, "CO-2026-00012").statut, "en_attente_deblocage");
    const debloquee = await appeler(client, "debloquer_commande", {
      numero: "CO-2026-00012",
      motif: "règlement reçu le 3 juillet",
    });
    assert.equal(debloquee.erreur, false, debloquee.texte);
    const c = lireCommande(etat, "CO-2026-00012");
    assert.equal(c.statut, "validee");
    assert.deepEqual(c.historique.at(-1), {
      date: "2026-07-06T08:00:00+02:00",
      par: "manon.rey",
      action: "debloquee",
      detail: "règlement reçu le 3 juillet",
    });
  });

  it("met en attente toute commande d'un client bloqué", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    await appeler(client, "creer_commande", { client: "c-0102", lignes: DEUX_LIGNES, livraison: "L1" });
    const attente = await appeler(client, "valider_commande", { numero: "CO-2026-00012" });
    assert.match(attente.texte, /en attente de déblocage : le client c-0102 est bloqué \(contentieux/u);
    assert.equal(lireCommande(etat, "CO-2026-00012").motif_attente, "client bloqué : contentieux, factures de mars");
  });

  it("accorde un prix sur un brouillon, pas sur une commande validée", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    await appeler(client, "creer_commande", { client: "c-0101", lignes: DEUX_LIGNES, livraison: "L1" });
    await appeler(client, "accorder_prix", {
      numero: "CO-2026-00012",
      reference: "VIS-01482",
      prix_net_ht_euros: 9.8,
      motif: "accord écrit de Bruno Castaing",
    });
    const c = lireCommande(etat, "CO-2026-00012");
    assert.deepEqual(
      [c.lignes[0].prix_net_ht_euros, c.lignes[0].prix_derogatoire, c.lignes[0].montant_ht_euros, c.total_ht_euros],
      [9.8, true, 98, 169.4],
    );
    await appeler(client, "valider_commande", { numero: "CO-2026-00012" });
    const refus = await appeler(client, "accorder_prix", {
      numero: "CO-2026-00012",
      reference: "VIS-01482",
      prix_net_ht_euros: 9,
      motif: "?",
    });
    assert.equal(refus.erreur, true);
  });

  it("livre à une adresse ponctuelle", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    await appeler(client, "creer_commande", { client: "c-0101", lignes: DEUX_LIGNES, livraison: "L1" });
    await appeler(client, "livrer_a_une_adresse_ponctuelle", {
      numero: "CO-2026-00012",
      adresse: "Chantier des Ormes, 36999 Vaumoreau-sur-Indre (FICTIF)",
      motif: "demande de Paul Ferrand, vérifiée par appel",
    });
    assert.deepEqual(lireCommande(etat, "CO-2026-00012").livraison, {
      code: null,
      adresse: "Chantier des Ormes, 36999 Vaumoreau-sur-Indre (FICTIF)",
    });
  });
});

describe("ventes, retours et blocage", () => {
  it("remet en stock les articles revendables, pas ceux du rebut, sans dépasser le livré", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    const retour = await appeler(client, "enregistrer_retour", {
      livraison: "BL-2026-00020",
      lignes: [
        { reference: "VIS-01482", quantite: 5, etat: "revendable" },
        { reference: "GAN-00310", quantite: 12, etat: "rebut" },
      ],
      motif: "retour accepté par le service après-vente",
    });
    assert.equal(retour.erreur, false, retour.texte);
    const stocks = lireCatalogue(etat).articles.map((a) => [a.reference, a.stock_physique]);
    assert.deepEqual(stocks.slice(0, 3), [
      ["VIS-01482", 125],
      ["VIS-01483", 500],
      ["GAN-00310", 240],
    ]);
    const trop = await appeler(client, "enregistrer_retour", {
      livraison: "BL-2026-00020",
      lignes: [{ reference: "VIS-01482", quantite: 16, etat: "revendable" }],
      motif: "second retour",
    });
    assert.deepEqual(trop, {
      texte: "VIS-01482 : 20 livrées, 21 reviendraient en tout ; rien n'est enregistré",
      erreur: true,
    });
  });

  it("bloque un client, et la fiche reste conforme à son contrat", async () => {
    const etat = etatDeTest();
    const client = await clientPour(etat, "manon.rey");
    const bloque = await appeler(client, "bloquer_client", { client: "c-0101", motif: "mise en demeure du 6 juillet" });
    assert.equal(bloque.texte, "Client c-0101 bloqué : mise en demeure du 6 juillet.");
    const fiche: unknown = parse(
      readFileSync(path.join(etat, "dossiers", "clients", "c-0101", "fiche_client.yaml"), "utf-8"),
    );
    assert.deepEqual(ecartsContrat("fiche_client_negoce", fiche), []);
    assert.match(
      (await appeler(client, "consulter_client", { client: "c-0101" })).texte,
      /Statut : bloqué \(mise en demeure/u,
    );
    assert.equal((await appeler(client, "bloquer_client", { client: "c-0101", motif: "encore" })).erreur, true);
  });
});

describe("ventes, droits", () => {
  it("ouvre la consultation à l'entrepôt, mais pas la saisie", async () => {
    const client = await clientPour(etatDeTest(), "gilles.poirier");
    assert.equal((await appeler(client, "consulter_client", { client: "c-0101" })).erreur, false);
    const saisie = await appeler(client, "creer_commande", { client: "c-0101", lignes: DEUX_LIGNES, livraison: "L1" });
    assert.deepEqual(saisie, { texte: "Gilles Poirier n'a pas le droit de saisir dans les ventes", erreur: true });
  });

  it("ferme tout à une personne sans droit sur les ventes", async () => {
    const client = await clientPour(etatDeTest(), "dylan.moreau");
    const refus = await appeler(client, "chercher_articles", { texte: "vis" });
    assert.deepEqual(refus, { texte: "accès refusé aux ventes pour Dylan Moreau", erreur: true });
  });
});

describe("ventes, lancement réel en stdio", () => {
  it("répond en MCP quand on le lance comme un programme", async () => {
    const client = new Client({ name: "test", version: "0" });
    await client.connect(
      new StdioClientTransport({
        command: process.execPath,
        args: [PRINCIPAL, "--etat", etatDeTest(), "--pour", "manon.rey"],
        stderr: "ignore",
      }),
    );
    const commande = await appeler(client, "consulter_commande", { numero: "CO-2026-00011" });
    assert.match(commande.texte, /^Commande CO-2026-00011 \| client c-0101 \| livrée/u);
    await client.close();
  });
});
