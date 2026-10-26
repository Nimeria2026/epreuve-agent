import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { Courriel } from "@poa/commun/contrats/courriel";
import { boitesExistantes, courrielsDe, dossierBoite, ecrireCourriel } from "@poa/commun/courriels";
import { parametresSociete } from "@poa/commun/societe";
import { parse } from "yaml";

/**
 * Correspondants simulés (étape 4, JOURNAL, soixantième entrée) : une personne extérieure dont
 * les réponses sont écrites d'avance, dans <etat>/messagerie/correspondants/<adresse>.yaml :
 *
 *   nom: Martine Rousseau
 *   reponses:
 *     - corps: texte de sa première réponse
 *     - corps: texte de la deuxième
 *
 * La n-ième réponse arrive après le n-ième courriel que Calorelle lui envoie : dans la boîte qui
 * a envoyé, non lue, en réponse à ce courriel, datée trente secondes après lui. Elle ne dépend pas
 * de ce que l'agent a écrit : deux exécutions qui envoient autant de courriels reçoivent les mêmes
 * réponses. Une fois les réponses épuisées, le correspondant se tait.
 */
export interface Correspondant {
  readonly adresse: string;
  readonly nom: string;
  readonly reponses: readonly string[];
}

const PREFIXE_ENVOI = "m-env-";
const PREFIXE_REPONSE = "m-rep-";

function estObjet(valeur: unknown): valeur is Record<string, unknown> {
  return typeof valeur === "object" && valeur !== null && !Array.isArray(valeur);
}

/** Le correspondant simulé de cette adresse, ou null ; un fichier mal formé est une erreur du banc. */
export function lireCorrespondant(etat: string, adresse: string): Correspondant | null {
  const chemin = path.join(etat, "messagerie", "correspondants", `${adresse}.yaml`);
  if (!existsSync(chemin)) {
    return null;
  }
  const donnees: unknown = parse(readFileSync(chemin, "utf-8"));
  const cles = estObjet(donnees) ? Object.keys(donnees).sort().join(",") : "";
  if (!estObjet(donnees) || cles !== "nom,reponses" || typeof donnees.nom !== "string" || donnees.nom === "") {
    throw new Error(`correspondant mal formé : ${chemin} (nom et reponses attendus, rien d'autre)`);
  }
  const reponses = Array.isArray(donnees.reponses) ? donnees.reponses : [];
  const textes = reponses.map((reponse: unknown, rang: number) => {
    if (!estObjet(reponse) || Object.keys(reponse).join(",") !== "corps" || typeof reponse.corps !== "string") {
      throw new Error(`correspondant mal formé : ${chemin}, réponse ${rang + 1} (corps attendu, rien d'autre)`);
    }
    return reponse.corps.trimEnd();
  });
  if (textes.length === 0) {
    throw new Error(`correspondant sans réponse : ${chemin}`);
  }
  return { adresse, nom: donnees.nom, reponses: textes };
}

/** Courriels de la société créés pendant l'exécution vers cette adresse, en destinataire ou en copie. */
function envoisVers(etat: string, adresse: string): number {
  const identifiants = new Set<string>();
  for (const boite of boitesExistantes(etat)) {
    for (const courriel of courrielsDe(etat, boite, "envoyes")) {
      if (courriel.identifiant.startsWith(PREFIXE_ENVOI) && [...courriel.a, ...courriel.cc].includes(adresse)) {
        identifiants.add(courriel.identifiant);
      }
    }
  }
  return identifiants.size;
}

/** Réponses de correspondants déjà arrivées, toutes boîtes confondues. */
function reponsesArrivees(etat: string): number {
  const identifiants = new Set<string>();
  for (const boite of boitesExistantes(etat)) {
    for (const courriel of courrielsDe(etat, boite, "reception")) {
      if (courriel.identifiant.startsWith(PREFIXE_REPONSE)) {
        identifiants.add(courriel.identifiant);
      }
    }
  }
  return identifiants.size;
}

/** La même heure, trente secondes plus tard, avec le même décalage horaire. */
function trenteSecondesApres(date: string): string {
  const motif = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2})$/u.exec(date);
  if (motif === null) {
    throw new Error(`date de courriel illisible : « ${date} »`);
  }
  const [, local = "", decalage = ""] = motif;
  const instant = Date.parse(`${local}Z`) + 30_000;
  return `${new Date(instant).toISOString().slice(0, 19)}${decalage}`;
}

/**
 * Après un envoi de la société, dépose la réponse écrite d'avance de chaque correspondant simulé
 * parmi les destinataires, s'il lui en reste une. Rend les courriels déposés.
 */
export function faireRepondre(etat: string, envoye: Courriel, boite: string): Courriel[] {
  const deposes: Courriel[] = [];
  for (const adresse of new Set([...envoye.a, ...envoye.cc])) {
    if (adresse.endsWith(`@${parametresSociete(etat).domaine}`)) {
      continue;
    }
    const correspondant = lireCorrespondant(etat, adresse);
    const corps = correspondant?.reponses[envoisVers(etat, adresse) - 1];
    if (correspondant === null || corps === undefined) {
      continue;
    }
    const identifiant = `${PREFIXE_REPONSE}${String(reponsesArrivees(etat) + 1).padStart(3, "0")}`;
    const courriel: Courriel = {
      identifiant,
      de: { nom: correspondant.nom, adresse },
      a: [boite],
      cc: [],
      objet: envoye.objet.startsWith("RE: ") ? envoye.objet : `RE: ${envoye.objet}`,
      date: trenteSecondesApres(envoye.date),
      corps,
      pieces_jointes: [],
      lu: false,
      en_reponse_a: envoye.identifiant,
      transfere_de: null,
    };
    ecrireCourriel(path.join(dossierBoite(etat, boite, "reception"), `${identifiant}.json`), courriel);
    deposes.push(courriel);
  }
  return deposes;
}
