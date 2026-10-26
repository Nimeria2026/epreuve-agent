#!/usr/bin/env node
// Lance le serveur MCP des achats en stdio : pme-achats --etat <dossier> --pour <personne>.
// La sortie standard porte le protocole MCP ; les messages vont sur la sortie d'erreur.
import { parseArgs } from "node:util";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { creerServeurAchats } from "./serveur.ts";

const { values } = parseArgs({ options: { etat: { type: "string" }, pour: { type: "string" } } });
if (values.etat === undefined || values.pour === undefined) {
  console.error("usage : pme-achats --etat <dossier de l'état de la PME> --pour <identifiant de la personne>");
  process.exit(2);
}
const serveur = creerServeurAchats({ etat: values.etat, pour: values.pour });
await serveur.connect(new StdioServerTransport());
console.error(`pme-achats prêt, pour ${values.pour}`);
