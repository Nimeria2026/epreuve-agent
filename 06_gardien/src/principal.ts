#!/usr/bin/env node
// Lance le gardien en stdio, entre EASE et les serveurs de la PME :
// poa-gardien --etat <dossier> --pour <personne> --services messagerie,dossiers --regles <fichier>
//             [--journal <fichier jsonl>] [--tache <identifiant>] [--validation refuser|accepter]
//             [--python <interpréteur>]
// --python : le Python de l'environnement du dépôt, qui lance les services écrits en Python (EKE).
// La sortie standard porte le protocole MCP ; les messages vont sur la sortie d'erreur.
import { parseArgs } from "node:util";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { brancherEnStdio, creerPasserelle, type Validation } from "./passerelle.ts";
import { creerContexte, lireRegles } from "./regles.ts";

const { values } = parseArgs({
  options: {
    etat: { type: "string" },
    pour: { type: "string" },
    services: { type: "string" },
    regles: { type: "string" },
    journal: { type: "string" },
    tache: { type: "string" },
    validation: { type: "string" },
    python: { type: "string" },
  },
});
const { etat, pour, services, regles: cheminRegles } = values;
const validation = values.validation ?? "refuser";
if (
  etat === undefined ||
  pour === undefined ||
  services === undefined ||
  cheminRegles === undefined ||
  (validation !== "refuser" && validation !== "accepter")
) {
  console.error(
    "usage : poa-gardien --etat <dossier> --pour <personne> --services <s1,s2> --regles <fichier> " +
      "[--journal <fichier>] [--tache <identifiant>] [--validation refuser|accepter] [--python <interpréteur>]",
  );
  process.exit(2);
}
const regles = lireRegles(cheminRegles);
const { serveur } = await creerPasserelle(
  {
    etat,
    pour,
    tache: values.tache ?? "",
    regles,
    contexte: creerContexte(etat, pour, regles),
    journal: values.journal ?? null,
    validation: validation as Validation,
  },
  services.split(",").filter((s) => s !== ""),
  brancherEnStdio(etat, pour, values.python ?? null),
);
await serveur.connect(new StdioServerTransport());
console.error(`poa-gardien prêt, règles ${regles.version}, pour ${pour}`);
