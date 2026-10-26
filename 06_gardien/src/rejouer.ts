#!/usr/bin/env node
// Rejoue les appels d'outils des runs passés devant des règles du gardien, sans rien exécuter :
//   node 06_gardien/src/rejouer.ts [--regles <fichier>] [--runs <dossier>] [--tous] [--detail]
// Chaque appel d'un journal est jugé sur l'état initial du run, pour la personne de sa tâche.
// Sert à voir, avant tout run payant, ce que des règles auraient bloqué ; un appel visé dans
// une exécution réussie sans gardien est un blocage à tort probable, sauf si la validation simulée
// de la tâche l'accepte (src/rejeu.ts). Le résumé compte les appels visés par règle et par issue ;
// seuls les blocages à tort probables sont listés, tous les appels visés avec --detail. Les runs
// des témoins sont laissés de côté, sauf avec --tous. Limites : l'agent n'aurait pas agi pareil
// après un refus, et l'état est celui du départ (un courriel envoyé pendant le run n'y est pas).
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { parseArgs } from "node:util";
import { parse } from "yaml";
import { type Contexte, creerContexte, evaluer, lireRegles } from "./regles.ts";
import { classer, type Issue, LIBELLES } from "./rejeu.ts";

const RACINE = new URL("../../", import.meta.url).pathname;
/** La société des runs rejoués : Calorelle, la seule du banc avant la seconde (ADR 0006). */
const SOCIETE = "calorelle";
const { values } = parseArgs({
  options: {
    regles: { type: "string", default: path.join(RACINE, "06_gardien", "regles", "v2.yaml") },
    runs: { type: "string", default: path.join(RACINE, "99_local", "runs") },
    tous: { type: "boolean", default: false },
    detail: { type: "boolean", default: false },
  },
});
const regles = lireRegles(values.regles);

/**
 * Les dossiers des tâches publiques de Calorelle rejouées, et le motif de leurs fichiers : le socle et
 * la tranche dure (JOURNAL, entrée 176). Les tâches cachées n'y sont pas : leurs appels sont sautés.
 */
const JEUX: readonly [string, RegExp][] = [
  [path.join(RACINE, "07_taches", "public"), /^t\d+.*\.ya?ml$/u],
  [path.join(RACINE, "07_taches", "public", "dure"), /^h\d+.*\.ya?ml$/u],
];

/** Pour chaque tâche publique : la personne servie, et la réponse de sa validation simulée. */
function lireTaches(): Map<string, { pour: string; validation: "accepter" | "refuser" }> {
  const taches = new Map<string, { pour: string; validation: "accepter" | "refuser" }>();
  for (const [dossier, motif] of JEUX) {
    for (const nom of readdirSync(dossier).filter((n) => motif.test(n))) {
      const tache = parse(readFileSync(path.join(dossier, nom), "utf-8")) as {
        identifiant?: unknown;
        agent_pour?: unknown;
        validation_simulee?: unknown;
      };
      if (typeof tache.identifiant === "string" && typeof tache.agent_pour === "string") {
        const validation = tache.validation_simulee === "accepter" ? "accepter" : "refuser";
        taches.set(tache.identifiant, { pour: tache.agent_pour, validation });
      }
    }
  }
  return taches;
}

interface Fiche {
  candidat: { identifiant: string };
  etat_pme: { version: string; societe?: string | null };
  regles_gardien?: unknown;
}
interface Ligne {
  etape: number;
  outil: string;
  arguments: Record<string, unknown>;
}

const taches = lireTaches();
const contextes = new Map<string, Contexte>();
const compte = new Map<string, number>(); // « règle|issue » → appels visés
let runs = 0;
let executions = 0;
let appels = 0;

for (const run of existsSync(values.runs) ? readdirSync(values.runs).sort() : []) {
  const cheminFiche = path.join(values.runs, run, "fiche_de_run.json");
  if (!existsSync(cheminFiche)) {
    continue;
  }
  const fiche = JSON.parse(readFileSync(cheminFiche, "utf-8")) as Fiche;
  if (!values.tous && fiche.candidat.identifiant.startsWith("temoin")) {
    continue;
  }
  // Un run d'une autre société (Domivelle) ne se rejoue jamais devant les règles de Calorelle, et
  // ne compte pas parmi ses runs ; une fiche sans société est de Calorelle.
  if (typeof fiche.etat_pme.societe === "string" && fiche.etat_pme.societe !== SOCIETE) {
    continue;
  }
  const etat = path.join(RACINE, "05_pme", "societes", SOCIETE, fiche.etat_pme.version);
  const resultats = path.join(values.runs, run, "resultats");
  if (!existsSync(etat) || !existsSync(resultats)) {
    continue;
  }
  runs += 1;
  const avecGardien = fiche.regles_gardien !== undefined && fiche.regles_gardien !== null;
  for (const nom of readdirSync(resultats).sort()) {
    const resultat = JSON.parse(readFileSync(path.join(resultats, nom), "utf-8")) as {
      tache: { identifiant: string };
      reussie: boolean;
      journal: string;
    };
    const tache = taches.get(resultat.tache.identifiant);
    const journal = path.join(values.runs, run, resultat.journal);
    if (tache === undefined || !existsSync(journal)) {
      continue;
    }
    const pour = tache.pour;
    executions += 1;
    const cle = `${etat}|${pour}`;
    const contexte = contextes.get(cle) ?? creerContexte(etat, pour, regles);
    contextes.set(cle, contexte);
    for (const texte of readFileSync(journal, "utf-8")
      .split("\n")
      .filter((l) => l !== "")) {
      const ligne = JSON.parse(texte) as Ligne;
      appels += 1;
      const decision = evaluer({ outil: ligne.outil, arguments: ligne.arguments }, regles, contexte);
      if (decision.verdict === "autorise") {
        continue;
      }
      const issue = classer(decision.verdict, tache.validation, avecGardien, resultat.reussie);
      compte.set(`${decision.regle}|${issue}`, (compte.get(`${decision.regle}|${issue}`) ?? 0) + 1);
      if (values.detail || issue === "a_tort_probable") {
        console.log(`${run} ${path.basename(journal)}, étape ${ligne.etape} : ${LIBELLES[issue]}`);
        console.log(`  ${decision.verdict} par ${decision.regle} : ${ligne.outil} ${JSON.stringify(ligne.arguments)}`);
      }
    }
  }
}

const total = [...compte.values()].reduce((a, b) => a + b, 0);
console.log(`\nRègles ${regles.version} : ${runs} runs, ${executions} exécutions, ${appels} appels rejoués.`);
console.log(`Appels visés : ${total}.`);
const ordre: Issue[] = ["a_tort_probable", "faute_arretee", "refus_reel", "validation_acceptee"];
for (const issue of ordre) {
  const parRegle = [...compte]
    .filter(([cle]) => cle.endsWith(`|${issue}`))
    .map(([cle, n]) => `${cle.split("|")[0]} ${n}`);
  const n = [...compte].filter(([cle]) => cle.endsWith(`|${issue}`)).reduce((a, [, v]) => a + v, 0);
  console.log(`  ${LIBELLES[issue]} : ${n}${parRegle.length > 0 ? ` (${parRegle.join(", ")})` : ""}`);
}
if (!values.detail) {
  console.log("Détail de chaque appel visé : make rejouer-gardien DETAIL=1");
}
