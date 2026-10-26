#!/usr/bin/env node
// Lance le serveur MCP du planning en stdio : pme-planning --etat <dossier> --pour <personne>.
// La sortie standard porte le protocole MCP ; les messages vont sur la sortie d'erreur.
import { parseArgs } from "node:util";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { creerServeurPlanning } from "./serveur.ts";

const { values } = parseArgs({ options: { etat: { type: "string" }, pour: { type: "string" } } });
if (values.etat === undefined || values.pour === undefined) {
  console.error("usage : pme-planning --etat <dossier de l'état de la PME> --pour <identifiant de la personne>");
  process.exit(2);
}
const serveur = creerServeurPlanning({ etat: values.etat, pour: values.pour });
await serveur.connect(new StdioServerTransport());
console.error(`pme-planning prêt, pour ${values.pour}`);
