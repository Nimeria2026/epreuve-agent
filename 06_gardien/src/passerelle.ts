import { appendFileSync, existsSync } from "node:fs";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  CallToolRequestSchema,
  type CallToolResult,
  ListToolsRequestSchema,
  type Tool,
} from "@modelcontextprotocol/sdk/types.js";
import { chargerPersonne } from "@poa/commun/droits";
import { type Appel, type Contexte, type Decision, evaluer, type Regles } from "./regles.ts";

/** Réponse simulée d'une personne à qui le gardien demande son accord, pendant les essais. */
export type Validation = "accepter" | "refuser";

export interface Options {
  readonly etat: string;
  readonly pour: string;
  readonly tache: string;
  readonly regles: Regles;
  readonly contexte: Contexte;
  /** Journal JSONL du gardien, une ligne par appel ; null pour ne rien écrire. */
  readonly journal: string | null;
  readonly validation: Validation;
}

/** Ouvre un client MCP vers un service de la PME. */
export type Branchement = (service: string) => Promise<Client>;

/** Les services écrits en Python, et leur module : EKE, l'outil documentaire (étape 6). */
export const SERVICES_PYTHON: ReadonlyMap<string, string> = new Map([["eke", "eke"]]);

/** La commande d'un service : Node et son point d'entrée, ou le Python du dépôt et son module. */
export function commandeDuService(service: string, python: string | null): { command: string; args: string[] } {
  const module = SERVICES_PYTHON.get(service);
  if (module !== undefined) {
    if (python === null) {
      throw new Error(`le service ${service} est en Python : lancer le gardien avec --python`);
    }
    return { command: python, args: ["-m", module] };
  }
  const principal = new URL(`../../05_pme/${service}/src/principal.ts`, import.meta.url).pathname;
  if (!/^[a-z_]+$/u.test(service) || !existsSync(principal)) {
    throw new Error(`service inconnu de la PME : ${service}`);
  }
  return { command: process.execPath, args: [principal] };
}

/**
 * Lance le serveur d'un service de la PME en stdio, pour la même personne et le même état.
 * python : l'interpréteur de l'environnement du dépôt, pour les services en Python ; null sinon.
 */
export function brancherEnStdio(etat: string, pour: string, python: string | null = null): Branchement {
  return async (service) => {
    const { command, args } = commandeDuService(service, python);
    const client = new Client({ name: "poa-gardien", version: "0.1.0" });
    await client.connect(
      new StdioClientTransport({
        command,
        args: [...args, "--etat", etat, "--pour", pour],
        stderr: "inherit",
      }),
    );
    return client;
  };
}

export const PREFIXE_REFUS = "Bloqué par le gardien";

function refus(texte: string): CallToolResult {
  return { content: [{ type: "text", text: texte }], isError: true };
}

/**
 * La passerelle : un serveur MCP qui annonce les outils des services de la PME, juge chaque
 * appel avec les règles, écrit le journal, puis transmet l'appel permis au service.
 */
export async function creerPasserelle(
  options: Options,
  services: readonly string[],
  brancher: Branchement,
): Promise<{ serveur: Server; fermer: () => Promise<void> }> {
  // Chaque valideur doit être dans l'organigramme dès le départ, pas au premier appel visé.
  const valideurs = new Map<string, string>();
  for (const regle of options.regles.regles) {
    if (regle.valideur !== null) {
      valideurs.set(regle.valideur, chargerPersonne(options.etat, regle.valideur).nom);
    }
  }
  const clients: Client[] = [];
  const outils = new Map<string, { client: Client; outil: Tool }>();
  async function fermer(): Promise<void> {
    await Promise.allSettled(clients.map((client) => client.close()));
  }
  try {
    for (const service of services) {
      const client = await brancher(service);
      clients.push(client);
      for (const outil of (await client.listTools()).tools) {
        if (outils.has(outil.name)) {
          throw new Error(`deux services de la PME annoncent l'outil ${outil.name}`);
        }
        outils.set(outil.name, { client, outil });
      }
    }
  } catch (erreur) {
    await fermer();
    throw erreur;
  }

  /** Une ligne du journal : l'appel, la décision, et ce qui a suivi. */
  function noter(appel: Appel, champs: Decision | Record<string, unknown>): void {
    if (options.journal === null) {
      return;
    }
    const ligne = {
      le: new Date().toISOString(),
      tache: options.tache,
      pour: options.pour,
      regles: options.regles.version,
      outil: appel.outil,
      arguments: appel.arguments,
      ...champs,
    };
    appendFileSync(options.journal, `${JSON.stringify(ligne)}\n`);
  }

  const serveur = new Server({ name: "poa-gardien", version: "0.1.0" }, { capabilities: { tools: {} } });
  serveur.setRequestHandler(ListToolsRequestSchema, () => ({ tools: [...outils.values()].map((o) => o.outil) }));
  serveur.setRequestHandler(CallToolRequestSchema, async (requete): Promise<CallToolResult> => {
    const appel: Appel = { outil: requete.params.name, arguments: requete.params.arguments ?? {} };
    const cible = outils.get(appel.outil);
    if (cible === undefined) {
      noter(appel, { verdict: "inconnu" });
      return refus(`outil inconnu : ${appel.outil}`);
    }
    const decision = evaluer(appel, options.regles, options.contexte);
    if (decision.verdict === "bloque") {
      noter(appel, decision);
      return refus(`${PREFIXE_REFUS} (règle ${decision.regle}) : ${decision.raison}.`);
    }
    const simulee = decision.verdict === "validation" ? { reponse: options.validation, simulee: true } : {};
    if (decision.verdict === "validation" && options.validation === "refuser") {
      noter(appel, { ...decision, ...simulee });
      const valideur = valideurs.get(decision.valideur) ?? decision.valideur;
      return refus(
        `${PREFIXE_REFUS} (règle ${decision.regle}) : ${decision.raison} ; ${valideur} n'a pas donné son accord.`,
      );
    }
    try {
      // Le _meta de l'appel passe tel quel : il porte, par exemple, la marque de l'accès en lecture
      // seule d'EASE (poa/lecture_seule), que le service respecte.
      const meta = requete.params._meta;
      const resultat = (await cible.client.callTool({
        name: appel.outil,
        arguments: { ...appel.arguments },
        ...(meta === undefined ? {} : { _meta: meta }),
      })) as CallToolResult;
      noter(appel, { ...decision, ...simulee, erreur_pme: resultat.isError === true });
      return resultat;
    } catch (erreur) {
      noter(appel, { ...decision, ...simulee, erreur_pme: true });
      throw erreur;
    }
  });

  serveur.onclose = () => {
    void fermer();
  };
  return { serveur, fermer };
}
