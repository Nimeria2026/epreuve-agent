#!/usr/bin/env node
// Lance le serveur MCP de la facturation en stdio : pme-facturation --etat <dossier> --pour <personne>.
// La sortie standard porte le protocole MCP ; les messages vont sur la sortie d'erreur.
import { parseArgs } from "node:util";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { creerServeurFacturation } from "./serveur.ts";

const { values } = parseArgs({ options: { etat: { type: "string" }, pour: { type: "string" } } });
if (values.etat === undefined || values.pour === undefined) {
  console.error("usage : pme-facturation --etat <dossier de l'état de la PME> --pour <identifiant de la personne>");
  process.exit(2);
}
const serveur = creerServeurFacturation({ etat: values.etat, pour: values.pour });
await serveur.connect(new StdioServerTransport());
console.error(`pme-facturation prêt, pour ${values.pour}`);
