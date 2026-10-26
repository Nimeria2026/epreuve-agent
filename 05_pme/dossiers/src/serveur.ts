import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, renameSync, statSync } from "node:fs";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { premierDossier } from "@poa/commun/chemins";
import { accesDossiers } from "@poa/commun/dossiers";
import { chargerPersonne } from "@poa/commun/droits";
import { ErreurOutil } from "@poa/commun/erreurs";
import { z } from "zod";

/** Où se trouve l'état de la PME, et pour qui l'agent travaille. */
export interface OptionsDossiers {
  readonly etat: string;
  readonly pour: string;
}

const LISIBLES = new Set([".txt", ".md", ".yaml", ".yml", ".json", ".csv"]);

function reponse(texte: string): CallToolResult {
  return { content: [{ type: "text", text: texte }] };
}

function refus(erreur: unknown): CallToolResult {
  if (erreur instanceof ErreurOutil) {
    return { content: [{ type: "text", text: erreur.message }], isError: true };
  }
  throw erreur;
}

/**
 * Serveur MCP des dossiers partagés de la PME. Il ne garde rien en mémoire : chaque appel lit et
 * écrit dans <etat>/dossiers/, que EASE remet à zéro avant chaque exécution et relit pour ses
 * contrôles. Les droits de la personne servie s'appliquent au dossier de premier niveau.
 */
export function creerServeurDossiers(options: OptionsDossiers): McpServer {
  const personne = chargerPersonne(options.etat, options.pour);
  const acces = accesDossiers(options.etat, personne);
  const { racine } = acces;
  const cheminAutorise = (relatif: string): string => acces.chemin(relatif);

  function fichierExistant(relatif: string): string {
    const absolu = cheminAutorise(relatif);
    if (!existsSync(absolu) || !statSync(absolu).isFile()) {
      throw new ErreurOutil(`fichier introuvable : ${relatif}`);
    }
    return absolu;
  }

  function arrivee(source: string, destination: string): string {
    const dossier = cheminAutorise(destination);
    const cible = path.join(dossier, path.basename(source));
    if (existsSync(cible)) {
      throw new ErreurOutil(`un fichier existe déjà : ${acces.relatif(cible)}`);
    }
    mkdirSync(dossier, { recursive: true });
    return cible;
  }

  const serveur = new McpServer({ name: "pme-dossiers", version: "0.1.0" });

  serveur.registerTool(
    "lister",
    {
      title: "Lister un dossier",
      annotations: { readOnlyHint: true },
      description:
        "Liste le contenu d'un dossier partagé : un élément par ligne, les dossiers finissent par « / ». " +
        "Sans dossier, liste les dossiers de premier niveau que la personne servie peut ouvrir.",
      inputSchema: { dossier: z.string().default("").describe("chemin du dossier, par exemple administration") },
    },
    ({ dossier }) => {
      try {
        if (premierDossier(dossier) === "") {
          const ouverts = readdirSync(racine, { withFileTypes: true })
            .filter((e) => e.isDirectory() && acces.ouvre(e.name))
            .map((e) => `${e.name}/`);
          return reponse(ouverts.sort().join("\n"));
        }
        const absolu = cheminAutorise(dossier);
        if (!existsSync(absolu) || !statSync(absolu).isDirectory()) {
          throw new ErreurOutil(`dossier introuvable : ${dossier}`);
        }
        const entrees = readdirSync(absolu, { withFileTypes: true }).map((e) =>
          e.isDirectory() ? `${e.name}/` : e.name,
        );
        return reponse(entrees.sort().join("\n"));
      } catch (erreur) {
        return refus(erreur);
      }
    },
  );

  serveur.registerTool(
    "lire",
    {
      title: "Lire un document",
      annotations: { readOnlyHint: true },
      description:
        "Renvoie le texte d'un document. Les PDF ne se lisent pas encore : leur taille seulement est donnée.",
      inputSchema: { chemin: z.string().describe("chemin du document") },
    },
    ({ chemin }) => {
      try {
        const absolu = fichierExistant(chemin);
        if (LISIBLES.has(path.extname(absolu).toLowerCase())) {
          return reponse(readFileSync(absolu, "utf-8"));
        }
        const taille = statSync(absolu).size;
        return reponse(
          `Document ${path.extname(absolu).slice(1).toUpperCase() || "binaire"} de ${taille} octets ; son contenu ne se lit pas avec cet outil.`,
        );
      } catch (erreur) {
        return refus(erreur);
      }
    },
  );

  serveur.registerTool(
    "deplacer",
    {
      title: "Déplacer un document",
      annotations: { readOnlyHint: false },
      description: "Déplace un document dans un dossier, sous le même nom ; le dossier est créé au besoin.",
      inputSchema: {
        source: z.string().describe("chemin du document"),
        destination: z.string().describe("chemin du dossier d'arrivée"),
      },
    },
    ({ source, destination }) => {
      try {
        const depart = fichierExistant(source);
        const cible = arrivee(depart, destination);
        renameSync(depart, cible);
        return reponse(acces.relatif(cible));
      } catch (erreur) {
        return refus(erreur);
      }
    },
  );

  serveur.registerTool(
    "copier",
    {
      title: "Copier un document",
      annotations: { readOnlyHint: false },
      description: "Copie un document dans un dossier, sous le même nom ; le dossier est créé au besoin.",
      inputSchema: {
        source: z.string().describe("chemin du document"),
        destination: z.string().describe("chemin du dossier d'arrivée"),
      },
    },
    ({ source, destination }) => {
      try {
        const depart = fichierExistant(source);
        const cible = arrivee(depart, destination);
        copyFileSync(depart, cible);
        return reponse(acces.relatif(cible));
      } catch (erreur) {
        return refus(erreur);
      }
    },
  );

  return serveur;
}
