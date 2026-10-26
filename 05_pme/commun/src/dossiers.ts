import path from "node:path";
import { premierDossier, relatifA, resoudreDansRacine } from "./chemins.ts";
import { chargerAccesDossiers, type Personne, peutOuvrir } from "./droits.ts";
import { ErreurOutil } from "./erreurs.ts";

/** Accès d'une personne aux dossiers partagés de l'état de la PME. */
export interface AccesDossiers {
  /** Racine des dossiers partagés : <etat>/dossiers. */
  readonly racine: string;
  /** Vrai si la personne peut ouvrir ce dossier de premier niveau. */
  ouvre(dossierRacine: string): boolean;
  /** Chemin absolu d'un chemin donné par l'agent, après contrôle du confinement et des droits. */
  chemin(relatif: string): string;
  /** Chemin tel que l'agent le voit, relatif aux dossiers partagés. */
  relatif(absolu: string): string;
}

export function accesDossiers(etat: string, personne: Personne): AccesDossiers {
  const racine = path.join(etat, "dossiers");
  const acces = chargerAccesDossiers(etat);
  const ouvre = (dossierRacine: string): boolean => peutOuvrir(acces, personne, dossierRacine);
  return {
    racine,
    ouvre,
    chemin(relatif: string): string {
      const absolu = resoudreDansRacine(racine, relatif);
      const dossier = premierDossier(relatifA(racine, absolu));
      if (dossier !== "" && !ouvre(dossier)) {
        throw new ErreurOutil(`accès refusé à ${dossier}/ pour ${personne.nom}`);
      }
      return absolu;
    },
    relatif: (absolu: string): string => relatifA(racine, absolu),
  };
}
