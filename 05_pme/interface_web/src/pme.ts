// Les outils de la PME vus par le poste humain, à travers le relais d'EASE.
//
// EASE donne deux adresses : celle des actions, où chaque appel compte une étape du budget de la
// tâche, et celle de l'accès en lecture seule, hors budget (02_ease/src/ease/relais.py). Le poste
// affiche par la seconde et agit par la première, comme l'agent agit. Une exception : lire un
// courriel le marque comme lu quand l'agent le lit ; le poste le lit donc par les actions, pour que
// l'état de la PME suive le même chemin (conception, §2).

import type { Client } from "@modelcontextprotocol/sdk/client/index.js";
import type { Schema } from "./formulaires.ts";

export interface Outil {
  readonly nom: string;
  readonly titre: string;
  readonly description: string;
  readonly schema: Schema;
  readonly lectureSeule: boolean;
}

export interface Reponse {
  readonly texte: string;
  readonly erreur: boolean;
}

/** Outils en lecture seule qui passent quand même par les actions, parce qu'ils changent un état. */
export const LUS_PAR_LES_ACTIONS: ReadonlySet<string> = new Set(["lire_courriel"]);

export interface Service {
  readonly cle: string;
  readonly nom: string;
  readonly outils: readonly string[];
}

/** Les services de la PME et leurs outils, dans l'ordre d'un poste de bureau ; le reste va dans « Autres ». */
export const SERVICES: readonly Service[] = [
  {
    cle: "messagerie",
    nom: "Messagerie",
    outils: [
      "lister_boites",
      "lister_courriels",
      "lire_courriel",
      "repondre",
      "transferer",
      "envoyer",
      "enregistrer_piece_jointe",
    ],
  },
  { cle: "dossiers", nom: "Dossiers", outils: ["lister", "lire", "deplacer", "copier"] },
  {
    cle: "planning",
    nom: "Planning",
    outils: [
      "lister_techniciens",
      "consulter_planning",
      "chercher_creneaux",
      "planifier_intervention",
      "deplacer_intervention",
      "annuler_intervention",
    ],
  },
  {
    cle: "facturation",
    nom: "Facturation",
    outils: [
      "consulter_compte_client",
      "consulter_tarif",
      "lister_devis",
      "consulter_devis",
      "creer_devis",
      "enregistrer_envoi",
      "enregistrer_reponse",
      "abandonner_devis",
      "emettre_avoir",
    ],
  },
  { cle: "achats", nom: "Achats", outils: ["consulter_fournisseur", "modifier_rib_fournisseur"] },
];

export const AUTRES: Service = { cle: "autres", nom: "Autres outils", outils: [] };

/**
 * Les titres que les services donnent à leurs outils. Le relais d'EASE ne transmet que le nom, la
 * description et le schéma ; un test vérifie que ces titres suivent ceux des services.
 */
export const TITRES: Readonly<Record<string, string>> = {
  lister_boites: "Lister les boîtes",
  lister_courriels: "Lister les courriels",
  lire_courriel: "Lire un courriel",
  transferer: "Transférer un courriel",
  repondre: "Répondre à un courriel",
  envoyer: "Envoyer un courriel",
  enregistrer_piece_jointe: "Enregistrer une pièce jointe",
  lister: "Lister un dossier",
  lire: "Lire un document",
  deplacer: "Déplacer un document",
  copier: "Copier un document",
  lister_techniciens: "Lister les techniciens",
  consulter_planning: "Consulter le planning",
  chercher_creneaux: "Chercher des créneaux libres",
  planifier_intervention: "Planifier une intervention",
  deplacer_intervention: "Déplacer une intervention",
  annuler_intervention: "Annuler une intervention",
  consulter_compte_client: "Consulter le compte d'un client",
  emettre_avoir: "Émettre un avoir",
  consulter_tarif: "Consulter le tarif",
  lister_devis: "Lister les devis",
  consulter_devis: "Consulter un devis",
  creer_devis: "Créer un devis",
  enregistrer_envoi: "Enregistrer l'envoi d'un devis",
  abandonner_devis: "Abandonner un brouillon de devis",
  enregistrer_reponse: "Enregistrer la réponse du client à un devis",
  consulter_fournisseur: "Consulter un fournisseur",
  modifier_rib_fournisseur: "Modifier le RIB d'un fournisseur",
};

/** Le service d'un outil, ou « Autres » pour un outil qu'aucun service ne nomme. */
export function serviceDe(nom: string): Service {
  return SERVICES.find((s) => s.outils.includes(nom)) ?? AUTRES;
}

function texteDe(contenu: unknown): string {
  if (!Array.isArray(contenu)) {
    return "";
  }
  return contenu
    .filter((c): c is { type: "text"; text: string } => typeof c === "object" && c !== null && c.type === "text")
    .map((c) => c.text)
    .join("\n");
}

/** La PME derrière le relais : la liste de ses outils, et l'appel de chacun par le bon accès. */
export class Pme {
  readonly #actions: Client;
  readonly #lecture: Client | null;
  #outils: readonly Outil[] | null = null;

  constructor(actions: Client, lecture: Client | null) {
    this.#actions = actions;
    this.#lecture = lecture;
  }

  async outils(): Promise<readonly Outil[]> {
    if (this.#outils === null) {
      const outils: Outil[] = [];
      let curseur: string | undefined;
      do {
        const page = await this.#actions.listTools(curseur === undefined ? {} : { cursor: curseur });
        for (const o of page.tools) {
          outils.push({
            nom: o.name,
            titre: o.title ?? TITRES[o.name] ?? o.name.replaceAll("_", " "),
            description: o.description ?? "",
            schema: o.inputSchema as Schema,
            lectureSeule: o.annotations?.readOnlyHint === true,
          });
        }
        curseur = page.nextCursor;
      } while (curseur !== undefined);
      this.#outils = outils;
    }
    return this.#outils;
  }

  async outil(nom: string): Promise<Outil | undefined> {
    return (await this.outils()).find((o) => o.nom === nom);
  }

  async appeler(nom: string, arguments_: Readonly<Record<string, unknown>>): Promise<Reponse> {
    const outil = await this.outil(nom);
    const parLecture = this.#lecture !== null && outil?.lectureSeule === true && !LUS_PAR_LES_ACTIONS.has(nom);
    const client = parLecture && this.#lecture !== null ? this.#lecture : this.#actions;
    try {
      const resultat = await client.callTool({ name: nom, arguments: { ...arguments_ } });
      return { texte: texteDe(resultat.content), erreur: resultat.isError === true };
    } catch (erreur) {
      return { texte: erreur instanceof Error ? erreur.message : String(erreur), erreur: true };
    }
  }
}
