import { readFileSync } from "node:fs";
import path from "node:path";
import { parse } from "yaml";

/** Une personne de l'organigramme, pour qui un agent peut travailler. */
export interface Personne {
  readonly id: string;
  readonly nom: string;
  readonly courriel: string;
  readonly droits: ReadonlySet<string>;
}

function lireYaml(chemin: string): unknown {
  return parse(readFileSync(chemin, "utf-8"));
}

function estObjet(valeur: unknown): valeur is Record<string, unknown> {
  return typeof valeur === "object" && valeur !== null && !Array.isArray(valeur);
}

function listeDeTextes(valeur: unknown): string[] {
  return Array.isArray(valeur) ? valeur.filter((v): v is string => typeof v === "string") : [];
}

/** Charge une personne depuis entreprise/organigramme.yaml de l'état de la PME. */
export function chargerPersonne(etat: string, id: string): Personne {
  const organigramme = lireYaml(path.join(etat, "entreprise", "organigramme.yaml"));
  const personnes = estObjet(organigramme) && Array.isArray(organigramme.personnes) ? organigramme.personnes : [];
  for (const personne of personnes) {
    if (estObjet(personne) && personne.id === id) {
      return {
        id,
        nom: typeof personne.nom === "string" ? personne.nom : id,
        courriel: typeof personne.courriel === "string" ? personne.courriel : "",
        droits: new Set(listeDeTextes(personne.droits)),
      };
    }
  }
  throw new Error(`personne inconnue dans l'organigramme : ${id}`);
}

/** Droits requis pour chaque dossier de premier niveau (entreprise/acces_dossiers.yaml). */
export function chargerAccesDossiers(etat: string): ReadonlyMap<string, ReadonlySet<string>> {
  const contenu = lireYaml(path.join(etat, "entreprise", "acces_dossiers.yaml"));
  const acces = new Map<string, ReadonlySet<string>>();
  if (estObjet(contenu)) {
    for (const [dossier, droits] of Object.entries(contenu)) {
      acces.set(dossier, new Set(listeDeTextes(droits)));
    }
  }
  return acces;
}

/** Mot réservé de acces_dossiers.yaml : le dossier est ouvert à toute personne de l'organigramme. */
export const TOUT_LE_PERSONNEL = "tous";

/** Vrai si la personne a au moins un des droits requis par ce dossier ; fermé par défaut. */
export function peutOuvrir(
  acces: ReadonlyMap<string, ReadonlySet<string>>,
  personne: Personne,
  dossierRacine: string,
): boolean {
  const requis = acces.get(dossierRacine);
  if (requis === undefined) {
    return false;
  }
  return requis.has(TOUT_LE_PERSONNEL) || [...requis].some((droit) => personne.droits.has(droit));
}

/** Toutes les boîtes de Calorelle : celle de chaque personne, puis les boîtes partagées. */
export function toutesLesBoites(etat: string): string[] {
  const organigramme = lireYaml(path.join(etat, "entreprise", "organigramme.yaml"));
  if (!estObjet(organigramme)) {
    return [];
  }
  const personnes = Array.isArray(organigramme.personnes) ? organigramme.personnes : [];
  const individuelles = personnes.flatMap((p) => (estObjet(p) && typeof p.courriel === "string" ? [p.courriel] : []));
  const partagees = estObjet(organigramme.boites_partagees) ? Object.keys(organigramme.boites_partagees) : [];
  return [...individuelles, ...partagees];
}

/** Boîtes que la personne peut ouvrir : la sienne, puis les boîtes partagées qu'elle gère. */
export function boitesDe(etat: string, personne: Personne): string[] {
  const organigramme = lireYaml(path.join(etat, "entreprise", "organigramme.yaml"));
  const partagees =
    estObjet(organigramme) && estObjet(organigramme.boites_partagees) ? organigramme.boites_partagees : {};
  const gerees = Object.entries(partagees)
    .filter(([, regle]) => estObjet(regle) && regle.gere_par === personne.id)
    .map(([adresse]) => adresse);
  return [personne.courriel, ...gerees.sort()].filter((adresse) => adresse !== "");
}
