// Point d'entrée du poste humain, lancé par EASE comme un candidat externe (candidat_externe.py) :
//
//   node 05_pme/interface_web/src/principal.ts --mcp <adresse> --mcp-lecture <adresse>
//     --enonce <fichier> --sortie <fichier>
//
// Il sert la page sur 127.0.0.1, port 30200 par défaut (variable POA_POSTE_HUMAIN_PORT), le temps
// d'un essai, puis s'arrête une fois sa sortie écrite.

import { readFileSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { Pme } from "./pme.ts";
import { creerPoste } from "./serveur.ts";

const PORT_PAR_DEFAUT = 30200;
const HOTE = "127.0.0.1";

async function connecter(adresse: string): Promise<Client> {
  const client = new Client({ name: "poste-humain", version: "0.1.0" });
  await client.connect(new StreamableHTTPClientTransport(new URL(adresse)));
  return client;
}

async function principal(): Promise<void> {
  const { values } = parseArgs({
    options: {
      mcp: { type: "string" },
      "mcp-lecture": { type: "string" },
      enonce: { type: "string" },
      sortie: { type: "string" },
    },
  });
  if (values.mcp === undefined || values.enonce === undefined || values.sortie === undefined) {
    throw new Error("arguments attendus : --mcp, --enonce et --sortie, plus --mcp-lecture");
  }
  const fichierSortie = values.sortie;
  const actions = await connecter(values.mcp);
  const lecture = values["mcp-lecture"] === undefined ? null : await connecter(values["mcp-lecture"]);
  const port = Number(process.env.POA_POSTE_HUMAIN_PORT ?? PORT_PAR_DEFAUT);
  const serveur = creerPoste({
    pme: new Pme(actions, lecture),
    enonce: readFileSync(values.enonce, "utf-8"),
    ecrireSortie: (sortie) => writeFileSync(fichierSortie, `${JSON.stringify(sortie)}\n`, "utf-8"),
    quitter: () => {
      serveur.closeAllConnections();
      serveur.close(() => process.exit(0));
    },
  });
  serveur.on("error", (erreur) => {
    console.error(`Poste humain : le port ${port} ne s'ouvre pas : ${erreur.message}`);
    process.exit(1);
  });
  serveur.listen(port, HOTE, () => {
    console.log(`Poste humain prêt : http://${HOTE}:${port}`);
  });
}

principal().catch((erreur: unknown) => {
  console.error(`Poste humain : ${erreur instanceof Error ? erreur.message : String(erreur)}`);
  process.exit(1);
});
