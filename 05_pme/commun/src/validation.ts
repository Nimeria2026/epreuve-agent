import { readFileSync } from "node:fs";
import type { ValidateFunction } from "ajv";
import { Ajv2020 } from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";

// ajv-formats est un module CommonJS : vu depuis un module ES, sa fonction est sous « default ».
const addFormats = addFormatsModule.default;

const DOSSIER_CONTRATS = new URL("../../../01_contrats/", import.meta.url);
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const validateurs = new Map<string, ValidateFunction>();

function validateur(contrat: string): ValidateFunction {
  let valider = validateurs.get(contrat);
  if (valider === undefined) {
    const schema: unknown = JSON.parse(readFileSync(new URL(`${contrat}.schema.json`, DOSSIER_CONTRATS), "utf-8"));
    valider = ajv.compile(schema as object);
    validateurs.set(contrat, valider);
  }
  return valider;
}

/** Écarts entre des données et le schéma d'un contrat de 01_contrats/ ; liste vide si conformes. */
export function ecartsContrat(contrat: string, donnees: unknown): string[] {
  const valider = validateur(contrat);
  if (valider(donnees)) {
    return [];
  }
  return (valider.errors ?? []).map((erreur) => `${erreur.instancePath || "(racine)"} : ${erreur.message ?? "?"}`);
}
