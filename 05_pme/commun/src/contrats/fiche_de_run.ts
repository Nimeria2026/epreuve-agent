// Généré depuis 01_contrats/fiche_de_run.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Date de début du run en UTC, puis un nom ; c'est aussi le nom du dossier du run.
 */
export type IdentifiantRun = string;
/**
 * Date et heure en UTC, au format RFC 3339 (par exemple 2026-11-03T14:00:00Z).
 */
export type HorodatageUTC = string;
/**
 * Valeur inconnue ; le rapport la montre comme telle.
 */
export type Inconnu = "?";
/**
 * Empreinte sha256, préfixée par « sha256: ».
 */
export type Empreinte = string;

/**
 * Une campagne de mesure : un candidat passé sur un jeu de tâches, chaque tâche répétée k fois. Elle permet de rejouer le run (règle 1 du BRIEF). « ? » signifie inconnu, et le rapport le montre ; null signifie sans objet. EASE vérifie au chargement ce que le schéma ne sait pas exprimer : statut et fin cohérents, dates en UTC, date de l'identifiant.
 */
export interface FicheDeRun {
  identifiant: IdentifiantRun;
  debut_utc: HorodatageUTC;
  fin_utc: HorodatageUTC | null;
  statut: "en_cours" | "termine" | "interrompu";
  raison_interruption: string | null;
  code: Code;
  candidat: ReferenceCandidat;
  configuration: Configuration;
  /**
   * Empreinte des prompts ; null pour un candidat sans prompt.
   */
  empreinte_prompts: Empreinte | Inconnu | null;
  jeu_taches: JeuDeTaches;
  etat_pme: EtatPME;
  regles_gardien: ReglesGardien | null;
  /**
   * Nombre de répétitions de chaque tâche.
   */
  repetitions: number;
  machine: Machine | null;
  /**
   * Le juge qui a tranché les vérifications juge_requis ; null : aucun juge. Absent des runs d'avant le juge (étape 4).
   */
  juge?: JugeDuRun | null;
  /**
   * Le banc public sur lequel le candidat a été mesuré, hors de la PME (étape 7) ; null ou absent : un run de la PME. etat_pme porte alors la version et l'empreinte des données du banc.
   */
  banc_public?: BancPublic | null;
}
/**
 * Version du code qui a produit le run.
 */
export interface Code {
  /**
   * Commit git complet.
   */
  commit: string;
  /**
   * Vrai si le dépôt avait des modifications non commitées : le run n'est alors pas rejouable à l'identique.
   */
  modifications_non_commitees: boolean;
}
/**
 * Fiche candidat utilisée pour ce run.
 */
export interface ReferenceCandidat {
  identifiant: string;
  version: string;
}
/**
 * Configuration exacte du candidat pendant ce run.
 */
export interface Configuration {
  /**
   * Modèles appelés ; liste vide pour un témoin qui n'appelle aucun modèle.
   */
  modeles: Modele[];
}
/**
 * Un modèle appelé pendant le run.
 */
export interface Modele {
  /**
   * Rôle du modèle dans l'orchestration, par exemple agent ou superviseur.
   */
  role: string;
  /**
   * Nom du modèle demandé.
   */
  nom: string;
  /**
   * Fournisseur de l'API, ou local.
   */
  fournisseur: string;
  version_renvoyee: string | Inconnu;
  /**
   * Réglages d'appel : température, nombre maximal de jetons, effort de raisonnement.
   */
  parametres: {
    [k: string]: number | string | boolean | null;
  };
  tarif: Tarif | null;
}
/**
 * Prix appliqués au calcul du coût, recopiés avec leur source pour qu'un coût publié se recalcule sans dépendre des prix du jour.
 */
export interface Tarif {
  entree_dollars_par_million: number;
  entree_en_cache_dollars_par_million: number | Inconnu;
  sortie_dollars_par_million: number;
  /**
   * Adresse ou nom de la source des prix.
   */
  source: string;
  /**
   * Date du relevé des prix.
   */
  releve_le: string;
}
/**
 * Jeu de tâches identifié par la liste de ses tâches, leurs versions et une empreinte.
 */
export interface JeuDeTaches {
  /**
   * Nom du jeu, par exemple public.
   */
  nom: string;
  /**
   * @minItems 1
   */
  taches: [TacheDuJeu, ...TacheDuJeu[]];
  empreinte: Empreinte;
}
/**
 * Une tâche du jeu, avec la version mesurée et, si elle en a un, l'empreinte de son complément d'état.
 */
export interface TacheDuJeu {
  identifiant: string;
  version: number;
  /**
   * Empreinte du complément d'état propre à la tâche (étape 4) ; null ou absent si elle n'en a pas.
   */
  empreinte_complement?: Empreinte | null;
}
/**
 * État initial de la PME chargé avant chaque exécution.
 */
export interface EtatPME {
  version: string;
  empreinte: Empreinte;
  /**
   * Société fictive de l'état (ADR 0006) ; null : terrain qui n'est pas une société (tau2). Absent des fiches écrites avant la seconde société, toutes de Calorelle.
   */
  societe?: string | null;
}
/**
 * Version des règles du gardien (étape 4).
 */
export interface ReglesGardien {
  version: string;
  empreinte: Empreinte;
}
/**
 * Machine qui sert un modèle local. Chaque champ vaut « ? » si inconnu.
 */
export interface Machine {
  systeme: string;
  processeur: string;
  carte_graphique: string;
  /**
   * Logiciel qui sert le modèle et sa version, par exemple vLLM.
   */
  service_modele: string;
}
/**
 * Le juge étalonné d'EASE (étape 4) : son modèle, la version de sa grille, et le nombre d'avis qu'il rend au plus quand le premier ne dit pas vrai.
 */
export interface JugeDuRun {
  modele: string;
  grille: string;
  /**
   * Avis au plus quand le premier ne dit pas vrai, faux ou illisible, la majorité tranchant (JOURNAL, 161e et 168e entrées) ; absent, un seul avis, comme dans les runs d'avant le 2026-10-15 au soir.
   */
  avis?: number;
}
/**
 * Un banc public d'agents construit par d'autres (ADR 0004), servi à EASE par MCP : ce qu'il faut pour rejouer le run et le comparer aux scores publiés.
 */
export interface BancPublic {
  /**
   * Nom du banc, par exemple tau2_bench.
   */
  nom: string;
  /**
   * Version du paquet du banc installée par uv.lock, par exemple 1.0.1.
   */
  version: string;
  /**
   * Domaine du banc, par exemple airline.
   */
  domaine: string;
  /**
   * Jeu de tâches du domaine, par exemple verified.
   */
  jeu: string;
  simulateur: SimulateurDuRun;
}
/**
 * Celui qui joue le client face à l'agent : un modèle, payé à part du candidat, ou un utilisateur sans modèle (écrit d'avance, rejoué).
 */
export interface SimulateurDuRun {
  /**
   * Nom du modèle au format de litellm, par exemple openrouter/google/gemini-2.5-flash ; ecrit_d_avance ou rejoue:<agent> sans modèle.
   */
  modele: string;
  /**
   * null sans modèle.
   */
  fournisseur: string | null;
  /**
   * Réglages envoyés au modèle à chaque appel, tels quels.
   */
  parametres: {
    [k: string]: unknown;
  };
  /**
   * null sans modèle.
   */
  tarif: Tarif | null;
  /**
   * Jetons du simulateur sur tout le run, lus dans les réponses de son API ; null sans modèle ou tant que le run n'est pas fini.
   */
  jetons: JetonsSimulateur | null;
  /**
   * Coût du simulateur sur tout le run, calculé par EASE avec le tarif ; null sans modèle ou tant que le run n'est pas fini.
   */
  cout_dollars: number | Inconnu | null;
  /**
   * Coût annoncé par le fournisseur dans ses réponses, s'il en annonce un ; « ? » s'il manque à une réponse ; null sans modèle ou tant que le run n'est pas fini.
   */
  cout_annonce_dollars: number | Inconnu | null;
}
/**
 * Jetons consommés par le simulateur d'utilisateur ; la réflexion compte en sortie, et dont_reflexion en donne la part.
 */
export interface JetonsSimulateur {
  entree: number | Inconnu;
  entree_en_cache: number | Inconnu;
  sortie: number | Inconnu;
  /**
   * Jetons de réflexion compris dans la sortie, tels que l'API les donne (completion_tokens_details.reasoning_tokens) ; « ? » s'ils manquent à une réponse.
   */
  dont_reflexion: number | Inconnu;
}
