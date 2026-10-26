import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { parse } from "yaml";
import type { ParametresSociete } from "./contrats/parametres_societe.ts";
import { ecartsContrat } from "./validation.ts";

/**
 * Les paramètres d'un état sans entreprise/societe.yaml : ceux de Calorelle, dont les états n'ont
 * pas ce fichier (ADR 0006). EASE garde les mêmes valeurs (PARAMETRES_CALORELLE, ease.chargement).
 */
export const PARAMETRES_CALORELLE: ParametresSociete = {
  nom: "Calorelle",
  domaine: "calorelle.example",
  dossier_fiches_fournisseurs: "administration/fournisseurs",
};

/** Les paramètres de la société d'un état, contrôlés par leur contrat ; ceux de Calorelle si le fichier manque. */
export function parametresSociete(etat: string): ParametresSociete {
  const chemin = path.join(etat, "entreprise", "societe.yaml");
  if (!existsSync(chemin)) {
    return PARAMETRES_CALORELLE;
  }
  const donnees: unknown = parse(readFileSync(chemin, "utf-8"));
  const ecarts = ecartsContrat("parametres_societe", donnees);
  if (ecarts.length > 0) {
    throw new Error(`paramètres de société mal formés : ${chemin} (${ecarts.join(" ; ")})`);
  }
  return donnees as ParametresSociete;
}
