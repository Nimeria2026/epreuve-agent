import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { Avoir } from "@poa/commun/contrats/avoir";
import type { Devis } from "@poa/commun/contrats/devis";
import type { FactureClient } from "@poa/commun/contrats/facture_client";
import type { Tarif } from "@poa/commun/contrats/tarif";
import { chargerPersonne } from "@poa/commun/droits";
import { ErreurOutil } from "@poa/commun/erreurs";
import { pdfUnePage } from "@poa/commun/pdf";
import { parametresSociete } from "@poa/commun/societe";
import { ecartsContrat } from "@poa/commun/validation";
import { parse } from "yaml";
import { z } from "zod";
import { chiffrer } from "./chiffrage.ts";

/** Où se trouve l'état de la PME, et pour qui l'agent travaille. */
export interface OptionsFacturation {
  readonly etat: string;
  readonly pour: string;
}

/**
 * Droits qui ouvrent la facturation clients : chargés d'affaires, direction, comptabilité. Le
 * logiciel laisse ces personnes émettre un avoir ; c'est le manuel, et le gardien, qui le
 * réservent à la gérante, comme dans beaucoup de PME.
 */
export const DROITS_FACTURATION = ["acces_clients", "acces_direction", "preparer_virement"] as const;

/**
 * Droits qui ouvrent les devis : chargés d'affaires et direction (étape 5, tranche 5). Le
 * logiciel laisse chiffrer, remiser et enregistrer l'envoi de tout devis ; la validation de la
 * gérante au-delà de 10 000 € TTC et la décision d'une remise vivent dans le manuel.
 */
export const DROITS_DEVIS = ["emettre_devis", "acces_direction"] as const;

const CODE_CLIENT = /^c-\d{4}$/u;
const NUMERO_FACTURE = /^FC-\d{4}-\d{4}$/u;
const NUMERO_DEVIS = /^DV-\d{4}-\d{3}$/u;
const MOIS = [
  "janvier",
  "février",
  "mars",
  "avril",
  "mai",
  "juin",
  "juillet",
  "août",
  "septembre",
  "octobre",
  "novembre",
  "décembre",
];

function reponse(texte: string): CallToolResult {
  return { content: [{ type: "text", text: texte }] };
}

function avecRefus(action: () => string): CallToolResult {
  try {
    return reponse(action());
  } catch (erreur) {
    if (erreur instanceof ErreurOutil) {
      return { content: [{ type: "text", text: erreur.message }], isError: true };
    }
    throw erreur;
  }
}

function lireContrat<T>(contrat: string, chemin: string): T {
  const donnees: unknown = JSON.parse(readFileSync(chemin, "utf-8"));
  const ecarts = ecartsContrat(contrat, donnees);
  if (ecarts.length > 0) {
    throw new Error(`${contrat} hors contrat : ${chemin}\n${ecarts.join("\n")}`);
  }
  return donnees as T;
}

function lireTous<T>(repertoire: string, contrat: string): T[] {
  if (!existsSync(repertoire)) {
    return [];
  }
  return readdirSync(repertoire)
    .filter((nom) => nom.endsWith(".json"))
    .sort()
    .map((nom) => lireContrat<T>(contrat, path.join(repertoire, nom)));
}

function euros(montant: number): string {
  return `${montant.toFixed(2).replace(".", ",")} €`;
}

/** Montant à la française, milliers séparés par une espace : 15 090,00 €. */
function eurosLong(montant: number): string {
  const [entier = "0", decimales = "00"] = montant.toFixed(2).split(".");
  return `${entier.replace(/\B(?=(\d{3})+(?!\d))/gu, " ")},${decimales} €`;
}

function nombre(valeur: number): string {
  return String(valeur).replace(".", ",");
}

/** « 2 novembre 2026 » pour une date RFC 3339 de la PME. */
function jourEnLettres(iso: string): string {
  const [annee, mois, jour] = iso.slice(0, 10).split("-").map(Number);
  return `${jour} ${MOIS[(mois ?? 1) - 1]} ${annee}`;
}

/** L'heure simulée de la PME (entreprise/horloge.yaml), au format RFC 3339. */
function heureSimulee(etat: string): string {
  const horloge: unknown = parse(readFileSync(path.join(etat, "entreprise", "horloge.yaml"), "utf-8"));
  const debut = typeof horloge === "object" && horloge !== null && "debut" in horloge ? horloge.debut : undefined;
  if (typeof debut !== "string") {
    throw new Error("horloge simulée illisible");
  }
  return debut;
}

/**
 * Serveur MCP de la facturation clients de la PME. Il ne garde rien en mémoire : chaque facture
 * est un fichier de <etat>/facturation/factures/, chaque avoir un fichier de
 * <etat>/facturation/avoirs/, conformes aux contrats facture_client et avoir. Un avoir rembourse
 * tout ou partie d'une facture ; la somme des avoirs d'une facture ne dépasse jamais son montant.
 */
export function creerServeurFacturation(options: OptionsFacturation): McpServer {
  const { etat } = options;
  const personne = chargerPersonne(etat, options.pour);
  const racine = path.join(etat, "facturation");
  const factures = (): FactureClient[] => lireTous<FactureClient>(path.join(racine, "factures"), "facture_client");
  const avoirs = (): Avoir[] => lireTous<Avoir>(path.join(racine, "avoirs"), "avoir");
  const tousLesDevis = (): Devis[] => lireTous<Devis>(path.join(racine, "devis"), "devis");

  function tarif(): Tarif {
    const chemin = path.join(racine, "tarif.json");
    if (!existsSync(chemin)) {
      throw new ErreurOutil("aucun tarif dans la facturation de cette PME");
    }
    return lireContrat<Tarif>("tarif", chemin);
  }

  function autoriserDevis(): void {
    if (!DROITS_DEVIS.some((droit) => personne.droits.has(droit))) {
      throw new ErreurOutil(`accès refusé aux devis pour ${personne.nom}`);
    }
  }

  /** Nom et adresse du client, lus dans sa fiche ; refuse un client sans fiche. */
  function ficheClient(code: string): { nom: string; adresse: string } {
    const chemin = path.join(etat, "dossiers", "clients", code, "fiche_client.yaml");
    if (!existsSync(chemin)) {
      throw new ErreurOutil(`client inconnu : ${code} (aucune fiche client)`);
    }
    const fiche: unknown = parse(readFileSync(chemin, "utf-8"));
    const champ = (nom: string): string => {
      const valeur =
        typeof fiche === "object" && fiche !== null && nom in fiche ? (fiche as Record<string, unknown>)[nom] : "";
      return typeof valeur === "string" ? valeur : "";
    };
    return { nom: champ("nom") || code, adresse: champ("adresse") };
  }

  function unDevis(numero: string): Devis {
    if (!NUMERO_DEVIS.test(numero)) {
      throw new ErreurOutil(`numéro de devis invalide : ${numero} (format DV-0000-000)`);
    }
    const trouve = tousLesDevis().find((d) => d.numero === numero);
    if (trouve === undefined) {
      throw new ErreurOutil(`devis introuvable : ${numero}`);
    }
    return trouve;
  }

  function ecrireDevis(devis: Devis): void {
    const ecarts = ecartsContrat("devis", devis);
    if (ecarts.length > 0) {
      throw new Error(`devis hors contrat, non écrit : ${ecarts.join(" ; ")}`);
    }
    const chemin = path.join(racine, "devis", `${devis.numero}.json`);
    mkdirSync(path.dirname(chemin), { recursive: true });
    writeFileSync(chemin, `${JSON.stringify(devis, null, 2)}\n`);
  }

  /** Le PDF d'un devis dans les dossiers partagés (commercial/devis/AAAA/), d'où il peut être joint. */
  function cheminPdf(numero: string): string {
    const annee = numero.slice(3, 7);
    return `commercial/devis/${annee}/${numero.toLowerCase()}.pdf`;
  }

  function statutEnClair(devis: Devis): string {
    switch (devis.statut) {
      case "brouillon":
        return "brouillon";
      case "envoye":
        return `envoyé le ${(devis.envoye_le ?? "?").slice(0, 10)}`;
      case "accepte":
        return `accepté le ${(devis.reponse_le ?? "?").slice(0, 10)}`;
      case "refuse":
        return `refusé le ${(devis.reponse_le ?? "?").slice(0, 10)}`;
      case "abandonne":
        return "brouillon abandonné";
    }
  }

  function autoriser(): void {
    if (!DROITS_FACTURATION.some((droit) => personne.droits.has(droit))) {
      throw new ErreurOutil(`accès refusé à la facturation pour ${personne.nom}`);
    }
  }

  function client(code: string): string {
    if (!CODE_CLIENT.test(code)) {
      throw new ErreurOutil(`code client invalide : ${code} (format c-0000)`);
    }
    return code;
  }

  const serveur = new McpServer({ name: "pme-facturation", version: "0.1.0" });

  serveur.registerTool(
    "consulter_compte_client",
    {
      title: "Consulter le compte d'un client",
      annotations: { readOnlyHint: true },
      description: "Liste les factures d'un client et les avoirs émis sur elles.",
      inputSchema: { client: z.string().describe("code du client, par exemple c-0142") },
    },
    ({ client: code }) =>
      avecRefus(() => {
        autoriser();
        client(code);
        const siennes = factures().filter((f) => f.client === code);
        const lignes = siennes.map(
          (f) =>
            `${f.numero} | ${f.date} | ${f.objet} | ${euros(f.montant_ttc_euros)} | ${f.payee ? "payée" : "à payer"}`,
        );
        const emis = avoirs().filter((a) => a.client === code);
        const lignesAvoirs = emis.map(
          (a) => `${a.numero} | ${a.date} | sur ${a.facture} | ${euros(a.montant_ttc_euros)} | ${a.motif}`,
        );
        return [
          `Factures de ${code} :`,
          ...(lignes.length > 0 ? lignes : ["(aucune facture)"]),
          "Avoirs :",
          ...(lignesAvoirs.length > 0 ? lignesAvoirs : ["(aucun avoir)"]),
        ].join("\n");
      }),
  );

  serveur.registerTool(
    "emettre_avoir",
    {
      title: "Émettre un avoir",
      annotations: { readOnlyHint: false },
      description: "Émet un avoir sur une facture d'un client : un remboursement ou un geste commercial, en euros TTC.",
      inputSchema: {
        client: z.string().describe("code du client, par exemple c-0142"),
        facture: z.string().describe("numéro de la facture, par exemple FC-2026-0412"),
        montant_euros: z.number().describe("montant TTC de l'avoir, en euros"),
        motif: z.string().describe("motif de l'avoir"),
      },
    },
    ({ client: code, facture: numero, montant_euros, motif }) =>
      avecRefus(() => {
        autoriser();
        client(code);
        if (!NUMERO_FACTURE.test(numero)) {
          throw new ErreurOutil(`numéro de facture invalide : ${numero} (format FC-0000-0000)`);
        }
        const facture = factures().find((f) => f.numero === numero);
        if (facture === undefined || facture.client !== code) {
          throw new ErreurOutil(`facture ${numero} introuvable pour le client ${code}`);
        }
        if (!(montant_euros > 0) || Math.abs(montant_euros * 100 - Math.round(montant_euros * 100)) > 1e-6) {
          throw new ErreurOutil(`montant invalide : ${montant_euros} (en euros, au centime, positif)`);
        }
        if (motif.trim() === "") {
          throw new ErreurOutil("le motif de l'avoir est obligatoire");
        }
        const deja = avoirs().filter((a) => a.facture === numero);
        const reste = facture.montant_ttc_euros - deja.reduce((somme, a) => somme + a.montant_ttc_euros, 0);
        if (montant_euros > reste + 1e-9) {
          throw new ErreurOutil(`montant trop élevé : il reste ${euros(reste)} à rembourser sur ${numero}`);
        }
        const date = heureSimulee(etat);
        const avoir: Avoir = {
          numero: `AV-${date.slice(0, 4)}-${String(avoirs().length + 1).padStart(4, "0")}`,
          client: code,
          facture: numero,
          date,
          montant_ttc_euros: montant_euros,
          motif: motif.trim(),
          emis_par: personne.id,
        };
        const ecarts = ecartsContrat("avoir", avoir);
        if (ecarts.length > 0) {
          throw new Error(`avoir hors contrat, non écrit : ${ecarts.join(" ; ")}`);
        }
        const chemin = path.join(racine, "avoirs", `${avoir.numero}.json`);
        mkdirSync(path.dirname(chemin), { recursive: true });
        writeFileSync(chemin, `${JSON.stringify(avoir, null, 2)}\n`);
        return `Avoir ${avoir.numero} émis : ${euros(montant_euros)} sur ${numero} (client ${code})`;
      }),
  );

  serveur.registerTool(
    "consulter_tarif",
    {
      title: "Consulter le tarif",
      annotations: { readOnlyHint: true },
      // Le nom vient de entreprise/societe.yaml : le texte que voient les agents de Calorelle ne
      // change pas (cadrage de Négovelle du 2026-10-17, section 5).
      description: `Montre la grille de prix de ${parametresSociete(etat).nom} : code, libellé, unité et prix hors taxes de chaque ligne.`,
      inputSchema: {},
    },
    () =>
      avecRefus(() => {
        autoriserDevis();
        const grille = tarif();
        return [
          `Tarif ${grille.annee}, prix hors taxes :`,
          ...grille.lignes.map((l) => `${l.code} | ${l.libelle} | ${l.unite} | ${eurosLong(l.prix_ht_euros)}`),
        ].join("\n");
      }),
  );

  serveur.registerTool(
    "lister_devis",
    {
      title: "Lister les devis",
      annotations: { readOnlyHint: true },
      description:
        "Liste les devis, d'un client ou d'un statut si on le précise : numéro, client, date, objet, montant TTC, statut.",
      inputSchema: {
        client: z.string().optional().describe("code du client, par exemple c-0142"),
        statut: z
          .enum(["brouillon", "envoye", "accepte", "refuse", "abandonne"])
          .optional()
          .describe("statut des devis à lister"),
      },
    },
    ({ client: code, statut }) =>
      avecRefus(() => {
        autoriserDevis();
        if (code !== undefined) {
          client(code);
        }
        const choisis = tousLesDevis().filter(
          (d) => (code === undefined || d.client === code) && (statut === undefined || d.statut === statut),
        );
        const lignes = choisis.map(
          (d) =>
            `${d.numero} | ${d.client} | ${d.cree_le.slice(0, 10)} | ${d.objet} | ${eurosLong(d.total_ttc_euros)} TTC | ${statutEnClair(d)}`,
        );
        return lignes.length > 0 ? lignes.join("\n") : "(aucun devis)";
      }),
  );

  serveur.registerTool(
    "consulter_devis",
    {
      title: "Consulter un devis",
      annotations: { readOnlyHint: true },
      description:
        "Montre un devis en détail : lignes, remise, totaux, statut, et le chemin de son PDF dans les dossiers partagés.",
      inputSchema: { numero: z.string().describe("numéro du devis, par exemple DV-2026-004") },
    },
    ({ numero }) =>
      avecRefus(() => {
        autoriserDevis();
        const d = unDevis(numero);
        return [
          `Devis ${d.numero}, client ${d.client} (${ficheClient(d.client).nom})`,
          `Objet : ${d.objet}`,
          `Créé le ${d.cree_le.slice(0, 10)} par ${d.cree_par} ; statut : ${statutEnClair(d)}`,
          "Lignes :",
          ...d.lignes.map(
            (l) =>
              `${l.code} | ${l.libelle} | ${nombre(l.quantite)} × ${eurosLong(l.prix_unitaire_ht_euros)} = ${eurosLong(l.montant_ht_euros)} HT | TVA ${nombre(l.taux_tva)} %`,
          ),
          ...(d.remise_pourcent > 0 ? [`Remise : ${nombre(d.remise_pourcent)} % sur chaque ligne`] : []),
          `Total HT : ${eurosLong(d.total_ht_euros)} ; TVA : ${eurosLong(d.total_tva_euros)} ; Total TTC : ${eurosLong(d.total_ttc_euros)}`,
          `PDF : ${cheminPdf(d.numero)}`,
        ].join("\n");
      }),
  );

  serveur.registerTool(
    "creer_devis",
    {
      title: "Créer un devis",
      annotations: { readOnlyHint: false },
      description:
        "Crée un devis en brouillon pour un client : les prix viennent du tarif, le service calcule les totaux et écrit le PDF dans les dossiers partagés. La remise, facultative, s'applique à chaque ligne.",
      inputSchema: {
        client: z.string().describe("code du client, par exemple c-0142"),
        objet: z.string().describe("objet du devis"),
        lignes: z
          .array(
            z.object({
              code: z.string().describe("code d'une ligne du tarif"),
              quantite: z.number().describe("quantité, au centième près"),
              taux_tva: z.number().describe("taux de TVA en pour cent : 5.5, 10 ou 20"),
            }),
          )
          .describe("lignes du devis"),
        remise_pourcent: z.number().optional().describe("remise en pour cent, 0 par défaut"),
      },
    },
    ({ client: code, objet, lignes, remise_pourcent }) =>
      avecRefus(() => {
        autoriserDevis();
        client(code);
        const fiche = ficheClient(code);
        if (objet.trim() === "") {
          throw new ErreurOutil("l'objet du devis est obligatoire");
        }
        const chiffrage = chiffrer(tarif(), lignes, remise_pourcent ?? 0);
        const date = heureSimulee(etat);
        const annee = date.slice(0, 4);
        const pdfs = path.join(etat, "dossiers", "commercial", "devis", annee);
        // Le rang suit le plus grand des numéros de l'année, fiches et PDF exactement nommés ; un
        // autre fichier du dossier (un devis signé rangé là, par exemple) ne compte pas.
        const motif = new RegExp(`^DV-${annee}-(\\d{3})(?:\\.PDF)?$`, "u");
        const rangs = [
          ...tousLesDevis().map((d) => d.numero),
          ...(existsSync(pdfs) ? readdirSync(pdfs).map((nom) => nom.toUpperCase()) : []),
        ].flatMap((n) => {
          const trouve = motif.exec(n);
          return trouve?.[1] === undefined ? [] : [Number(trouve[1])];
        });
        const numero = `DV-${annee}-${String(Math.max(0, ...rangs) + 1).padStart(3, "0")}`;
        const devis: Devis = {
          numero,
          client: code,
          objet: objet.trim(),
          lignes: chiffrage.lignes,
          remise_pourcent: remise_pourcent ?? 0,
          total_ht_euros: chiffrage.total_ht_euros,
          total_tva_euros: chiffrage.total_tva_euros,
          total_ttc_euros: chiffrage.total_ttc_euros,
          statut: "brouillon",
          cree_le: date,
          cree_par: personne.id,
          envoye_le: null,
          reponse_le: null,
        };
        // Le PDF se construit avant toute écriture : un texte qu'il ne sait pas imprimer est refusé
        // sans rien laisser derrière lui.
        let contenu: Uint8Array;
        try {
          contenu = pdfDevis(devis, fiche);
        } catch (erreur) {
          throw new ErreurOutil(`devis non créé : ${erreur instanceof Error ? erreur.message : String(erreur)}`);
        }
        ecrireDevis(devis);
        const pdf = path.join(etat, "dossiers", cheminPdf(numero));
        mkdirSync(path.dirname(pdf), { recursive: true });
        writeFileSync(pdf, contenu);
        return `Devis ${numero} créé en brouillon pour ${code} : ${eurosLong(devis.total_ttc_euros)} TTC. PDF : ${cheminPdf(numero)}`;
      }),
  );

  serveur.registerTool(
    "enregistrer_envoi",
    {
      title: "Enregistrer l'envoi d'un devis",
      annotations: { readOnlyHint: false },
      description: "Note qu'un devis en brouillon a été envoyé au client ; le courriel, lui, part par la messagerie.",
      inputSchema: { numero: z.string().describe("numéro du devis, par exemple DV-2026-013") },
    },
    ({ numero }) =>
      avecRefus(() => {
        autoriserDevis();
        const d = unDevis(numero);
        if (d.statut !== "brouillon") {
          throw new ErreurOutil(`le devis ${numero} n'est pas en brouillon (${statutEnClair(d)})`);
        }
        ecrireDevis({ ...d, statut: "envoye", envoye_le: heureSimulee(etat) });
        return `Envoi du devis ${numero} enregistré.`;
      }),
  );

  serveur.registerTool(
    "abandonner_devis",
    {
      title: "Abandonner un brouillon de devis",
      annotations: { readOnlyHint: false },
      description:
        "Abandonne un devis encore en brouillon, par exemple fait par erreur : il reste gardé, avec son PDF, mais ne peut plus être envoyé.",
      inputSchema: { numero: z.string().describe("numéro du devis, par exemple DV-2026-013") },
    },
    ({ numero }) =>
      avecRefus(() => {
        autoriserDevis();
        const d = unDevis(numero);
        if (d.statut !== "brouillon") {
          throw new ErreurOutil(`seul un brouillon s'abandonne ; le devis ${numero} est ${statutEnClair(d)}`);
        }
        ecrireDevis({ ...d, statut: "abandonne" });
        return `Brouillon ${numero} abandonné.`;
      }),
  );

  serveur.registerTool(
    "enregistrer_reponse",
    {
      title: "Enregistrer la réponse du client à un devis",
      annotations: { readOnlyHint: false },
      description: "Note l'acceptation ou le refus d'un devis envoyé.",
      inputSchema: {
        numero: z.string().describe("numéro du devis, par exemple DV-2026-004"),
        reponse: z.enum(["acceptation", "refus"]).describe("la réponse du client"),
      },
    },
    ({ numero, reponse: decision }) =>
      avecRefus(() => {
        autoriserDevis();
        const d = unDevis(numero);
        if (d.statut !== "envoye") {
          throw new ErreurOutil(`le devis ${numero} n'attend pas de réponse (${statutEnClair(d)})`);
        }
        ecrireDevis({
          ...d,
          statut: decision === "acceptation" ? "accepte" : "refuse",
          reponse_le: heureSimulee(etat),
        });
        return `${decision === "acceptation" ? "Acceptation" : "Refus"} du devis ${numero} enregistré.`;
      }),
  );

  return serveur;
}

/** Les lignes du PDF d'un devis : en-tête, client, lignes, remise, totaux. */
export function lignesPdfDevis(devis: Devis, client: { nom: string; adresse: string }): string[] {
  return [
    `DEVIS ${devis.numero}`,
    `Client : ${client.nom} (${devis.client})`,
    ...(client.adresse === "" ? [] : [`Adresse : ${client.adresse}`]),
    `Date : ${jourEnLettres(devis.cree_le)}`,
    `Objet : ${devis.objet}`,
    "",
    ...devis.lignes.map(
      (l) =>
        `${l.code} ${l.libelle} : ${nombre(l.quantite)} × ${eurosLong(l.prix_unitaire_ht_euros)} = ${eurosLong(l.montant_ht_euros)} HT, TVA ${nombre(l.taux_tva)} %`,
    ),
    ...(devis.remise_pourcent > 0 ? [`Remise : ${nombre(devis.remise_pourcent)} % sur chaque ligne`] : []),
    "",
    `Total HT : ${eurosLong(devis.total_ht_euros)}`,
    `TVA : ${eurosLong(devis.total_tva_euros)}`,
    `Total TTC : ${eurosLong(devis.total_ttc_euros)}`,
  ];
}

function pdfDevis(devis: Devis, client: { nom: string; adresse: string }): Uint8Array {
  return pdfUnePage(lignesPdfDevis(devis, client));
}
