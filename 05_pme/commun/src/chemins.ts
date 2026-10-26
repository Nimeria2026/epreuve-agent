import { existsSync, realpathSync } from "node:fs";
import path from "node:path";
import { ErreurOutil } from "./erreurs.ts";

/**
 * Résout un chemin donné par un agent, relatif à une racine, sans jamais en sortir :
 * chemins absolus, remontées par « .. » et liens vers l'extérieur sont refusés.
 */
export function resoudreDansRacine(racine: string, relatif: string): string {
  if (relatif.includes("\0")) {
    throw new ErreurOutil("chemin invalide");
  }
  if (path.isAbsolute(relatif)) {
    throw new ErreurOutil(`chemin absolu refusé : ${relatif}`);
  }
  const base = realpathSync(racine);
  const absolu = path.resolve(base, relatif);
  const reel = existsSync(absolu) ? realpathSync(absolu) : absolu;
  for (const candidat of [absolu, reel]) {
    if (candidat !== base && !candidat.startsWith(base + path.sep)) {
      throw new ErreurOutil(`chemin hors des dossiers partagés : ${relatif}`);
    }
  }
  return absolu;
}

/** Chemin relatif à la racine, avec des « / », tel que l'agent le voit. */
export function relatifA(racine: string, absolu: string): string {
  return path.relative(realpathSync(racine), absolu).split(path.sep).join("/");
}

/** Premier dossier d'un chemin relatif (« administration » pour « administration/factures »). */
export function premierDossier(relatif: string): string {
  return relatif.split("/").filter((partie) => partie !== "" && partie !== ".")[0] ?? "";
}
