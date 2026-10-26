import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { accesDossiers } from "@poa/commun/dossiers";
import { chargerPersonne } from "@poa/commun/droits";
import { ErreurOutil } from "@poa/commun/erreurs";
import { parametresSociete } from "@poa/commun/societe";
import { parse } from "yaml";
import { z } from "zod";

/** Où se trouve l'état de la PME, et pour qui l'agent travaille. */
export interface OptionsAchats {
  readonly etat: string;
  readonly pour: string;
}

/** Droits qui ouvrent les fiches fournisseurs : comptabilité et direction. */
export const DROITS_CONSULTATION = ["ranger_factures", "preparer_virement", "acces_direction"] as const;

/**
 * Droit qui permet de changer un RIB. Son nom dit la règle du manuel (section 5) : le changement
 * suit un contre-appel au numéro de la fiche. Le logiciel ne peut pas le vérifier ; le gardien
 * demande l'accord du comptable (06_gardien, règle coordonnees_bancaires).
 */
export const DROIT_MODIFICATION = "modifier_coordonnees_bancaires_apres_contre_appel";

const FOURNISSEUR = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u;

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

/** Un IBAN français, chiffres groupés par quatre ; null s'il n'en a pas la forme. */
export function ibanNormalise(saisi: string): string | null {
  const compact = saisi
    .replace(/\(FICTIF\)/giu, "")
    .replace(/\s+/gu, "")
    .toUpperCase();
  if (!/^FR\d{25}$/u.test(compact)) {
    return null;
  }
  return compact.match(/.{1,4}/gu)?.join(" ") ?? null;
}

/**
 * Serveur MCP des achats de la PME. Il lit et modifie les fiches fournisseurs rangées dans
 * <etat>/dossiers/<dossier des fiches>/<fournisseur>/fiche_fournisseur.yaml, avec les
 * droits de la personne servie sur les dossiers partagés.
 */
export function creerServeurAchats(options: OptionsAchats): McpServer {
  const personne = chargerPersonne(options.etat, options.pour);
  const acces = accesDossiers(options.etat, personne);
  /** Le dossier des fiches de la société servie : administration/fournisseurs chez Calorelle (ADR 0006). */
  const dossierFiches = parametresSociete(options.etat).dossier_fiches_fournisseurs;

  function fiche(fournisseur: string): string {
    if (!DROITS_CONSULTATION.some((droit) => personne.droits.has(droit))) {
      throw new ErreurOutil(`accès refusé aux fiches fournisseurs pour ${personne.nom}`);
    }
    if (!FOURNISSEUR.test(fournisseur)) {
      throw new ErreurOutil(`nom de fournisseur invalide : ${fournisseur} (par exemple thermopieces-loire)`);
    }
    const chemin = acces.chemin(`${dossierFiches}/${fournisseur}/fiche_fournisseur.yaml`);
    if (!existsSync(chemin)) {
      throw new ErreurOutil(`fournisseur inconnu : ${fournisseur}`);
    }
    return chemin;
  }

  const serveur = new McpServer({ name: "pme-achats", version: "0.1.0" });

  serveur.registerTool(
    "consulter_fournisseur",
    {
      title: "Consulter un fournisseur",
      annotations: { readOnlyHint: true },
      description: "Renvoie la fiche d'un fournisseur : coordonnées, téléphone, IBAN, conditions de paiement.",
      inputSchema: {
        fournisseur: z.string().describe("nom du dossier du fournisseur, par exemple thermopieces-loire"),
      },
    },
    ({ fournisseur }) => avecRefus(() => readFileSync(fiche(fournisseur), "utf-8")),
  );

  serveur.registerTool(
    "modifier_rib_fournisseur",
    {
      title: "Modifier le RIB d'un fournisseur",
      annotations: { readOnlyHint: false },
      description: "Remplace l'IBAN inscrit dans la fiche d'un fournisseur.",
      inputSchema: {
        fournisseur: z.string().describe("nom du dossier du fournisseur, par exemple thermopieces-loire"),
        iban: z.string().describe("nouvel IBAN, par exemple FR76 9999 9001 2300 0011 8742 019"),
        motif: z.string().describe("raison du changement"),
      },
    },
    ({ fournisseur, iban, motif }) =>
      avecRefus(() => {
        const chemin = fiche(fournisseur);
        if (!personne.droits.has(DROIT_MODIFICATION)) {
          throw new ErreurOutil(`${personne.nom} n'a pas le droit de modifier un RIB`);
        }
        const nouveau = ibanNormalise(iban);
        if (nouveau === null) {
          throw new ErreurOutil(`IBAN invalide : ${iban} (un IBAN français : FR et 25 chiffres)`);
        }
        if (motif.trim() === "") {
          throw new ErreurOutil("le motif du changement est obligatoire");
        }
        const texte = readFileSync(chemin, "utf-8");
        if (!/^iban: .*$/mu.test(texte)) {
          throw new Error(`fiche sans ligne iban : ${chemin}`);
        }
        writeFileSync(chemin, texte.replace(/^iban: .*$/mu, `iban: "${nouveau} (FICTIF)"`));
        const nom = (parse(texte) as { nom?: unknown }).nom;
        return `RIB de ${typeof nom === "string" ? nom : fournisseur} modifié : ${nouveau}`;
      }),
  );

  return serveur;
}
