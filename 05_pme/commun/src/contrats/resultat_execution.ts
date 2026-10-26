// Généré depuis 01_contrats/resultat_execution.schema.json par make contrats.
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
 * Un passage du candidat sur une tâche, pour une répétition. « ? » signifie inconnu, et le rapport le montre ; null signifie sans objet. Une erreur technique (API en panne, coupure) n'est pas un échec de l'agent : l'exécution est relancée et le rapport compte ces erreurs. EASE vérifie au chargement le score recalculé, la réussite et la cohérence avec la tâche.
 */
export interface ResultatExecution {
  run: IdentifiantRun;
  tache: ReferenceTache;
  repetition: number;
  debut_utc: HorodatageUTC;
  fin_utc: HorodatageUTC;
  /**
   * Fin normale, budget dépassé, erreur technique sans rapport avec l'agent, contexte du modèle dépassé ou délai dépassé : ces deux derniers sont des échecs de l'agent, comptés dans le taux chacun sous son arrêt (cadrage du 2026-10-14, choix T3 ; cadrage du générateur des images, choix D1).
   */
  arret: "termine" | "budget_etapes" | "budget_cout" | "erreur_technique" | "contexte_depasse" | "delai_depasse";
  detail_arret: string | null;
  /**
   * @minItems 1
   */
  controles: [ResultatControle, ...ResultatControle[]];
  /**
   * Somme des scores pondérés par les poids.
   */
  score: number;
  /**
   * Vrai si l'exécution s'est terminée normalement et que chaque contrôle a son score plein.
   */
  reussie: boolean;
  /**
   * Nombre d'appels d'outils.
   */
  etapes: number;
  jetons: Jetons;
  cout_dollars: number | Inconnu;
  /**
   * Énergie électrique de la carte graphique qui sert un modèle local pendant l'exécution, en wattheures, relevée par nvidia-smi. La machine entière consomme davantage : c'est un minimum. « ? » si le relevé a manqué ; null pour un candidat sans modèle local.
   */
  energie_wh: number | Inconnu | null;
  duree_secondes: number;
  /**
   * Poste humain seulement : durée chronométrée par le poste, de « Commencer » à « J'ai fini », en secondes, reprise de sa sortie ; duree_secondes compte en plus l'attente avant « Commencer ». null pour un agent ; absente des résultats écrits avant le 2026-10-13.
   */
  duree_chronometree_secondes?: number | null;
  /**
   * Chemin du journal des actions, relatif au dossier du run.
   */
  journal: string;
}
/**
 * Tâche exécutée, avec sa version.
 */
export interface ReferenceTache {
  identifiant: string;
  version: number;
}
/**
 * Score d'un contrôle de la tâche ; famille et poids sont recopiés de la tâche.
 */
export interface ResultatControle {
  /**
   * Rang du contrôle dans la tâche, à partir de 1.
   */
  numero: number;
  famille: "resultat" | "absence_effet_de_bord" | "respect_des_regles" | "budget" | "contenu" | "provenance";
  poids: number;
  /**
   * De 0 à 1 ; une valeur intermédiaire est un crédit partiel.
   */
  score: number;
  detail: string | null;
}
/**
 * Jetons consommés. L'entrée compte aussi la part servie depuis le cache.
 */
export interface Jetons {
  entree: number | Inconnu;
  entree_en_cache: number | Inconnu;
  sortie: number | Inconnu;
}
