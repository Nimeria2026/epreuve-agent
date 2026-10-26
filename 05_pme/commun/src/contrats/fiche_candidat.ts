// Généré depuis 01_contrats/fiche_candidat.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Valeur inconnue ; le rapport la montre comme telle.
 */
export type Inconnu = "?";

/**
 * Le système mesuré. Un candidat qui n'est pas classable (témoin, humain, non évaluable, publication non permise ou non vérifiée) n'apparaît jamais dans un classement. « ? » signifie inconnu, et le rapport le montre ; null signifie sans objet.
 */
export interface FicheCandidat {
  identifiant: string;
  nom: string;
  version: string;
  /**
   * fait_main : orchestration du projet ; pret_a_l_emploi : produit d'un éditeur ; temoin : comportement connu d'avance, pour vérifier le banc ; humain : une personne au poste humain, pour mesurer la durée humaine des tâches (JOURNAL, cent-vingt-et-unième entrée).
   */
  origine: "fait_main" | "pret_a_l_emploi" | "temoin" | "humain";
  /**
   * Division de classement ; null pour un témoin ou un humain, jamais classés.
   */
  division: ("a_modele_egal" | "systeme_complet") | null;
  /**
   * mcp : mesurable ; interface : mesurable en partie ; aucun : non évaluable.
   */
  branchement: "mcp" | "interface" | "aucun";
  editeur: string;
  url: string | Inconnu | null;
  modeles: ModeleCandidat[] | Inconnu;
  /**
   * Vrai si le coût par tâche se mesure (jetons et prix connus).
   */
  cout_mesurable: boolean;
  /**
   * Obligatoires pour un produit prêt à l'emploi ; null pour un candidat fait main ou un témoin.
   */
  conditions_utilisation: ConditionsUtilisation | null;
}
/**
 * Un modèle utilisé par le candidat.
 */
export interface ModeleCandidat {
  nom: string;
  fournisseur: string;
}
/**
 * Conditions d'utilisation lues avant toute publication nommée (clause DeWitt, BRIEF §3).
 */
export interface ConditionsUtilisation {
  url: string;
  lues_le: string;
  /**
   * Les conditions permettent-elles de publier des résultats nommés ?
   */
  publication_permise: "oui" | "non" | "?";
}
