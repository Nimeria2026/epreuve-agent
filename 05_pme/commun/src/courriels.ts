import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { parse } from "yaml";
import type { Courriel } from "./contrats/courriel.ts";
import { toutesLesBoites } from "./droits.ts";
import { ecartsContrat } from "./validation.ts";

/** Les deux dossiers d'une boîte. */
export type DossierBoite = "reception" | "envoyes";

/** Dossier d'une boîte dans l'état : <etat>/messagerie/boites/<adresse>/<dossier>. */
export function dossierBoite(etat: string, adresse: string, dossier: DossierBoite): string {
  return path.join(etat, "messagerie", "boites", adresse, dossier);
}

/** Lit un courriel de l'état et vérifie son contrat ; un courriel hors contrat est une erreur du banc. */
export function lireCourriel(chemin: string): Courriel {
  const donnees: unknown = JSON.parse(readFileSync(chemin, "utf-8"));
  const ecarts = ecartsContrat("courriel", donnees);
  if (ecarts.length > 0) {
    throw new Error(`courriel hors contrat : ${chemin}\n${ecarts.join("\n")}`);
  }
  return donnees as Courriel;
}

/** Écrit un courriel après avoir vérifié son contrat : rien n'entre dans l'état hors contrat. */
export function ecrireCourriel(chemin: string, courriel: Courriel): void {
  const ecarts = ecartsContrat("courriel", courriel);
  if (ecarts.length > 0) {
    throw new Error(`courriel hors contrat, non écrit : ${courriel.identifiant}\n${ecarts.join("\n")}`);
  }
  mkdirSync(path.dirname(chemin), { recursive: true });
  writeFileSync(chemin, `${JSON.stringify(courriel, null, 2)}\n`);
}

/** Courriels d'un dossier de boîte, du plus ancien au plus récent. */
export function courrielsDe(etat: string, adresse: string, dossier: DossierBoite): Courriel[] {
  const repertoire = dossierBoite(etat, adresse, dossier);
  if (!existsSync(repertoire)) {
    return [];
  }
  return readdirSync(repertoire)
    .filter((nom) => nom.endsWith(".json"))
    .map((nom) => lireCourriel(path.join(repertoire, nom)))
    .sort((a, b) => Date.parse(a.date) - Date.parse(b.date) || a.identifiant.localeCompare(b.identifiant));
}

/**
 * Toutes les boîtes de Calorelle, d'après l'organigramme : une boîte existe même vide, sans
 * dossier sur le disque (git ne versionne pas les dossiers vides).
 */
export function boitesExistantes(etat: string): string[] {
  return toutesLesBoites(etat).sort();
}

const PREFIXE_ENVOI = "m-env-";

/** Nombre de courriels déjà créés pendant l'exécution, toutes boîtes confondues. */
function envoisExistants(etat: string): number {
  const identifiants = new Set<string>();
  for (const adresse of boitesExistantes(etat)) {
    for (const dossier of ["reception", "envoyes"] as const) {
      for (const courriel of courrielsDe(etat, adresse, dossier)) {
        if (courriel.identifiant.startsWith(PREFIXE_ENVOI)) {
          identifiants.add(courriel.identifiant);
        }
      }
    }
  }
  return identifiants.size;
}

/**
 * Identifiant et date du prochain courriel créé : m-env-001, m-env-002..., datés à partir de
 * l'heure simulée de la PME (entreprise/horloge.yaml), une minute d'écart entre deux envois. Deux
 * exécutions identiques produisent donc les mêmes courriels.
 */
export function prochainEnvoi(etat: string): { identifiant: string; date: string } {
  const rang = envoisExistants(etat) + 1;
  const horloge: unknown = parse(readFileSync(path.join(etat, "entreprise", "horloge.yaml"), "utf-8"));
  const debut =
    typeof horloge === "object" && horloge !== null && "debut" in horloge && typeof horloge.debut === "string"
      ? horloge.debut
      : "";
  const motif = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}):(\d{2})$/.exec(debut);
  if (motif === null) {
    throw new Error(`horloge simulée illisible : « ${debut} »`);
  }
  const [, local = "", heures = "", minutes = ""] = motif;
  const decalage = Number(heures) * 60 + Math.sign(Number(heures) || 1) * Number(minutes);
  const instant = Date.parse(`${local}${heures}:${minutes}`) + rang * 60_000;
  const heureLocale = new Date(instant + decalage * 60_000).toISOString().slice(0, 19);
  return {
    identifiant: `${PREFIXE_ENVOI}${String(rang).padStart(3, "0")}`,
    date: `${heureLocale}${heures}:${minutes}`,
  };
}
