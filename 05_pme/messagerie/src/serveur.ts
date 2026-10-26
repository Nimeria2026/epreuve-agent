import { copyFileSync, existsSync, mkdirSync, statSync } from "node:fs";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { resoudreDansRacine } from "@poa/commun/chemins";
import type { Courriel, PieceJointe } from "@poa/commun/contrats/courriel";
import {
  boitesExistantes,
  courrielsDe,
  type DossierBoite,
  dossierBoite,
  ecrireCourriel,
  lireCourriel,
  prochainEnvoi,
} from "@poa/commun/courriels";
import { accesDossiers } from "@poa/commun/dossiers";
import { boitesDe, chargerPersonne } from "@poa/commun/droits";
import { ErreurOutil } from "@poa/commun/erreurs";
import { parametresSociete } from "@poa/commun/societe";
import { z } from "zod";
import { faireRepondre } from "./correspondants.ts";

/** Clé du _meta MCP qui marque un appel de l'accès en lecture seule d'EASE (MARQUE_LECTURE_SEULE). */
export const MARQUE_LECTURE_SEULE = "poa/lecture_seule";

/** Où se trouve l'état de la PME, et pour qui l'agent travaille. */
export interface OptionsMessagerie {
  readonly etat: string;
  readonly pour: string;
}

const ADRESSE = /^[a-z0-9._-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.example$/;
const IDENTIFIANT = /^m-[a-z0-9]+(-[a-z0-9]+)*$/;
const NOM_FICHIER = /^[^/\\]+$/;

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

function nonVide(adresses: readonly string[]): [string, ...string[]] {
  const [premiere, ...suivantes] = adresses;
  if (premiere === undefined) {
    throw new ErreurOutil("il faut au moins un destinataire");
  }
  return [premiere, ...suivantes];
}

function expediteur(courriel: Courriel): string {
  return courriel.de.nom === null ? courriel.de.adresse : `${courriel.de.nom} <${courriel.de.adresse}>`;
}

function enTete(courriel: Courriel): string {
  const pieces = courriel.pieces_jointes.map((p) => `${p.nom} (${p.taille_octets} octets)`).join(", ");
  const lignes = [
    `Identifiant : ${courriel.identifiant}`,
    `De : ${expediteur(courriel)}`,
    `À : ${courriel.a.join(", ")}`,
    `Cc : ${courriel.cc.join(", ") || "(aucun)"}`,
    `Date : ${courriel.date}`,
    `Objet : ${courriel.objet}`,
    `Pièces jointes : ${pieces || "(aucune)"}`,
  ];
  if (courriel.transfere_de !== null) {
    lignes.push(`Transfert de : ${courriel.transfere_de}`);
  }
  if (courriel.en_reponse_a !== null) {
    lignes.push(`En réponse à : ${courriel.en_reponse_a}`);
  }
  return lignes.join("\n");
}

interface Brouillon {
  readonly a: readonly string[];
  readonly cc: readonly string[];
  readonly objet: string;
  readonly corps: string;
  readonly pieces: readonly { readonly nom: string; readonly source: string }[];
  readonly enReponseA?: string;
  readonly transfereDe?: string;
}

/**
 * Serveur MCP de la messagerie de la PME. Il ne garde rien en mémoire : chaque boîte est un
 * dossier de <etat>/messagerie/boites/, et chaque courriel un fichier JSON conforme au contrat
 * courriel. La personne servie n'ouvre que sa boîte et les boîtes partagées qu'elle gère.
 * Un courriel envoyé est rangé dans « envoyes » de la boîte d'envoi, et déposé dans la boîte de
 * réception de chaque destinataire de Calorelle ; vers l'extérieur, rien ne part réellement, mais
 * un correspondant simulé peut répondre (correspondants.ts).
 */
export function creerServeurMessagerie(options: OptionsMessagerie): McpServer {
  const { etat } = options;
  const personne = chargerPersonne(etat, options.pour);
  const boites = boitesDe(etat, personne);
  const dossiers = accesDossiers(etat, personne);
  const messagerie = path.join(etat, "messagerie");
  /** La société servie (entreprise/societe.yaml, ADR 0006) : un envoi vers son domaine reste interne. */
  const societe = parametresSociete(etat);
  const domaineInterne = `@${societe.domaine}`;

  // Une adresse qui n'existe pas n'est pas « non ouverte » : le dire tel quel évite de lancer
  // l'agent sur une fausse piste de droits (premier essai sur Qwen, 2026-10-05).
  function boiteAutorisee(boite: string | undefined): string {
    const adresse = boite ?? boites[0];
    if (adresse === undefined) {
      throw new ErreurOutil(`aucune boîte ouverte à ${personne.nom}`);
    }
    if (!boitesExistantes(etat).includes(adresse)) {
      throw new ErreurOutil(`boîte inconnue : ${adresse}`);
    }
    if (!boites.includes(adresse)) {
      throw new ErreurOutil(`boîte non ouverte à ${personne.nom} : ${adresse}`);
    }
    return adresse;
  }

  function trouver(boite: string, identifiant: string): { courriel: Courriel; chemin: string; dossier: DossierBoite } {
    if (!IDENTIFIANT.test(identifiant)) {
      throw new ErreurOutil(`identifiant de courriel invalide : ${identifiant}`);
    }
    for (const dossier of ["reception", "envoyes"] as const) {
      const chemin = path.join(dossierBoite(etat, boite, dossier), `${identifiant}.json`);
      if (existsSync(chemin)) {
        return { courriel: lireCourriel(chemin), chemin, dossier };
      }
    }
    throw new ErreurOutil(`courriel introuvable dans ${boite} : ${identifiant}`);
  }

  function verifierAdresses(adresses: readonly string[]): void {
    const internes = new Set(boitesExistantes(etat));
    for (const adresse of adresses) {
      if (!ADRESSE.test(adresse)) {
        throw new ErreurOutil(`adresse refusée : ${adresse} (seules les adresses en .example existent ici)`);
      }
      if (adresse.endsWith(domaineInterne) && !internes.has(adresse)) {
        throw new ErreurOutil(`adresse inconnue chez ${societe.nom} : ${adresse}`);
      }
    }
  }

  function piecesDe(courriel: Courriel): { nom: string; source: string }[] {
    return courriel.pieces_jointes.map((piece) => ({
      nom: piece.nom,
      source: resoudreDansRacine(messagerie, piece.fichier),
    }));
  }

  function expedier(boite: string, brouillon: Brouillon): Courriel {
    const a = nonVide(brouillon.a);
    verifierAdresses([...a, ...brouillon.cc]);
    const { identifiant, date } = prochainEnvoi(etat);
    // Deux pièces de même nom, les pièces d'identité de deux candidats par exemple, ne s'écrasent
    // pas : la seconde est rangée sous « 2_<nom> », la suivante sous « 3_<nom> », et le
    // destinataire voit les deux sous leur nom (contrat courriel : pas de sous-dossier).
    const ranges = new Set<string>();
    const pieces: PieceJointe[] = brouillon.pieces.map(({ nom, source }) => {
      let range = nom;
      for (let n = 2; ranges.has(range); n += 1) {
        range = `${n}_${nom}`;
      }
      ranges.add(range);
      const fichier = `pieces/${identifiant}/${range}`;
      const cible = path.join(messagerie, fichier);
      mkdirSync(path.dirname(cible), { recursive: true });
      copyFileSync(source, cible);
      return { nom, fichier, taille_octets: statSync(cible).size };
    });
    const courriel: Courriel = {
      identifiant,
      de: { nom: personne.nom, adresse: boite },
      a,
      cc: [...brouillon.cc],
      objet: brouillon.objet,
      date,
      corps: brouillon.corps,
      pieces_jointes: pieces,
      lu: true,
      en_reponse_a: brouillon.enReponseA ?? null,
      transfere_de: brouillon.transfereDe ?? null,
    };
    ecrireCourriel(path.join(dossierBoite(etat, boite, "envoyes"), `${identifiant}.json`), courriel);
    for (const destinataire of new Set([...a, ...brouillon.cc])) {
      if (destinataire.endsWith(domaineInterne)) {
        const chemin = path.join(dossierBoite(etat, destinataire, "reception"), `${identifiant}.json`);
        ecrireCourriel(chemin, { ...courriel, lu: false });
      }
    }
    faireRepondre(etat, courriel, boite);
    return courriel;
  }

  const serveur = new McpServer({ name: "pme-messagerie", version: "0.1.0" });
  const boiteFacultative = z
    .string()
    .optional()
    .describe("adresse de la boîte ; par défaut, celle de la personne servie");
  const adresses = z.array(z.string());

  serveur.registerTool(
    "lister_boites",
    {
      title: "Lister les boîtes",
      annotations: { readOnlyHint: true },
      description: "Liste les boîtes que la personne servie peut ouvrir : la sienne, puis les boîtes partagées.",
    },
    () => avecRefus(() => boites.join("\n")),
  );

  serveur.registerTool(
    "lister_courriels",
    {
      title: "Lister les courriels",
      annotations: { readOnlyHint: true },
      description:
        "Liste les courriels d'une boîte, du plus ancien au plus récent : identifiant, date, expéditeur, objet, lu ou non.",
      inputSchema: {
        boite: boiteFacultative,
        dossier: z.enum(["reception", "envoyes"]).default("reception"),
        non_lus_seulement: z.boolean().default(false),
      },
    },
    ({ boite, dossier, non_lus_seulement }) =>
      avecRefus(() => {
        const courriels = courrielsDe(etat, boiteAutorisee(boite), dossier).filter((c) => !non_lus_seulement || !c.lu);
        const lignes = courriels.map((c) =>
          [
            c.identifiant,
            c.date,
            expediteur(c),
            c.objet,
            c.lu ? "lu" : "non lu",
            `${c.pieces_jointes.length} pièce(s) jointe(s)`,
          ].join(" | "),
        );
        return lignes.join("\n") || "(aucun courriel)";
      }),
  );

  serveur.registerTool(
    "lire_courriel",
    {
      title: "Lire un courriel",
      // Le courriel est marqué lu : un indicateur de lecture, pas une action de l'entreprise. Le
      // service le déclare donc en lecture seule (relu par personne, dans auteur_relecteur). Un
      // appel de l'accès en lecture seule d'EASE, marqué poa/lecture_seule, ne le marque pas : le
      // relecteur regarde sans rien changer (JOURNAL, entrée 95).
      annotations: { readOnlyHint: true },
      description: "Renvoie un courriel complet et le marque comme lu.",
      inputSchema: { boite: boiteFacultative, identifiant: z.string() },
    },
    ({ boite, identifiant }, extra) =>
      avecRefus(() => {
        const { courriel, chemin, dossier } = trouver(boiteAutorisee(boite), identifiant);
        const regardSeul = extra._meta?.[MARQUE_LECTURE_SEULE] === true;
        if (dossier === "reception" && !courriel.lu && !regardSeul) {
          ecrireCourriel(chemin, { ...courriel, lu: true });
        }
        return `${enTete(courriel)}\n\n${courriel.corps}`;
      }),
  );

  serveur.registerTool(
    "transferer",
    {
      title: "Transférer un courriel",
      annotations: { readOnlyHint: false },
      description: "Transfère un courriel, pièces jointes comprises, avec un commentaire facultatif.",
      inputSchema: {
        boite: boiteFacultative,
        identifiant: z.string(),
        a: adresses.describe("destinataires"),
        cc: adresses.default([]).describe("destinataires en copie"),
        commentaire: z.string().default(""),
      },
    },
    ({ boite, identifiant, a, cc, commentaire }) =>
      avecRefus(() => {
        const adresse = boiteAutorisee(boite);
        const { courriel } = trouver(adresse, identifiant);
        const corps =
          `${commentaire}\n\n----- Message transféré -----\n${enTete(courriel)}\n\n${courriel.corps}`.trimStart();
        const envoye = expedier(adresse, {
          a,
          cc,
          objet: `TR: ${courriel.objet}`,
          corps,
          pieces: piecesDe(courriel),
          transfereDe: courriel.identifiant,
        });
        return `Transféré : ${envoye.identifiant}`;
      }),
  );

  serveur.registerTool(
    "repondre",
    {
      title: "Répondre à un courriel",
      annotations: { readOnlyHint: false },
      description: "Répond à l'expéditeur d'un courriel, sans pièce jointe.",
      inputSchema: { boite: boiteFacultative, identifiant: z.string(), texte: z.string() },
    },
    ({ boite, identifiant, texte }) =>
      avecRefus(() => {
        const adresse = boiteAutorisee(boite);
        const { courriel } = trouver(adresse, identifiant);
        const objet = courriel.objet.startsWith("RE: ") ? courriel.objet : `RE: ${courriel.objet}`;
        const corps = `${texte}\n\n----- Message d'origine -----\n${enTete(courriel)}\n\n${courriel.corps}`;
        const envoye = expedier(adresse, {
          a: [courriel.de.adresse],
          cc: [],
          objet,
          corps,
          pieces: [],
          enReponseA: courriel.identifiant,
        });
        return `Réponse envoyée : ${envoye.identifiant}`;
      }),
  );

  serveur.registerTool(
    "envoyer",
    {
      title: "Envoyer un courriel",
      annotations: { readOnlyHint: false },
      description: "Envoie un nouveau courriel ; les pièces jointes sont prises dans les dossiers partagés.",
      inputSchema: {
        boite: boiteFacultative,
        a: adresses.describe("destinataires"),
        cc: adresses.default([]).describe("destinataires en copie"),
        objet: z.string(),
        texte: z.string(),
        pieces_jointes: z.array(z.string()).default([]).describe("chemins de documents dans les dossiers partagés"),
      },
    },
    ({ boite, a, cc, objet, texte, pieces_jointes }) =>
      avecRefus(() => {
        const adresse = boiteAutorisee(boite);
        const pieces = pieces_jointes.map((relatif) => {
          const source = dossiers.chemin(relatif);
          if (!existsSync(source) || !statSync(source).isFile()) {
            throw new ErreurOutil(`document introuvable : ${relatif}`);
          }
          return { nom: path.basename(source), source };
        });
        const envoye = expedier(adresse, { a, cc, objet, corps: texte, pieces });
        return `Envoyé : ${envoye.identifiant}`;
      }),
  );

  serveur.registerTool(
    "enregistrer_piece_jointe",
    {
      title: "Enregistrer une pièce jointe",
      annotations: { readOnlyHint: false },
      description:
        "Enregistre une pièce jointe d'un courriel dans un dossier partagé, sous son nom ou sous un nouveau nom.",
      inputSchema: {
        boite: boiteFacultative,
        identifiant: z.string(),
        piece: z.string().describe("nom de la pièce jointe, tel qu'affiché dans le courriel"),
        dossier: z.string().describe("dossier partagé d'arrivée ; créé au besoin"),
        nom_fichier: z.string().optional().describe("nouveau nom du fichier ; par défaut, celui de la pièce"),
      },
    },
    ({ boite, identifiant, piece, dossier, nom_fichier }) =>
      avecRefus(() => {
        const { courriel } = trouver(boiteAutorisee(boite), identifiant);
        const jointe = piecesDe(courriel).find((p) => p.nom === piece);
        if (jointe === undefined) {
          throw new ErreurOutil(`pièce jointe introuvable dans ${identifiant} : ${piece}`);
        }
        const nom = nom_fichier ?? jointe.nom;
        if (!NOM_FICHIER.test(nom) || nom === "." || nom === "..") {
          throw new ErreurOutil(`nom de fichier invalide : ${nom}`);
        }
        const repertoire = dossiers.chemin(dossier);
        const cible = dossiers.chemin(path.join(dossiers.relatif(repertoire), nom));
        if (existsSync(cible)) {
          throw new ErreurOutil(`un fichier existe déjà : ${dossiers.relatif(cible)}`);
        }
        mkdirSync(repertoire, { recursive: true });
        copyFileSync(jointe.source, cible);
        return dossiers.relatif(cible);
      }),
  );

  return serveur;
}
