// Généré depuis 01_contrats/sortie_candidat.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Valeur inconnue ; le rapport la montre comme telle.
 */
export type Inconnu = "?";

/**
 * Ce qu'un candidat lancé dans son propre processus rend à EASE pour une exécution : comment il s'est arrêté, ce qu'il a consommé, et les modèles que les API ont annoncés. Ses actions ne passent pas par ce fichier : EASE les voit dans le journal de son relais. Le candidat réécrit ce fichier après chaque appel de modèle, pour qu'un arrêt brutal laisse la consommation déjà faite. « ? » signifie inconnu.
 */
export interface SortieCandidat {
  /**
   * en_cours : fichier réécrit pendant l'exécution ; termine : l'agent a rendu la main ; tours_max : la boucle a atteint sa limite de tours ; erreur : panne côté candidat, détaillée dans detail ; contexte_depasse : le serveur du modèle a refusé une conversation plus longue que son contexte, détaillé dans detail ; delai_depasse : un appel au modèle a dépassé son délai, détaillé dans detail.
   */
  fin: "en_cours" | "termine" | "tours_max" | "erreur" | "contexte_depasse" | "delai_depasse";
  /**
   * Explication d'une fin autre que termine ; null sinon.
   */
  detail: string | null;
  /**
   * Nombre d'appels aux modèles pendant l'exécution, tous rôles confondus.
   */
  appels_modele: number;
  /**
   * Jetons consommés, par rôle de modèle (agent, superviseur) ; vide pour un candidat qui n'appelle aucun modèle.
   */
  consommation: {
    [k: string]: Jetons;
  };
  /**
   * Nom du modèle annoncé par l'API dans ses réponses, par rôle.
   */
  modeles_renvoyes: {
    [k: string]: string;
  };
  /**
   * Poste humain seulement : durée de l'essai chronométrée par le poste, de « Commencer » à « J'ai fini », en secondes. Absente pour un agent, dont EASE mesure seul la durée.
   */
  duree_chronometree_secondes?: number;
}
/**
 * Jetons consommés. L'entrée compte aussi la part servie depuis le cache.
 */
export interface Jetons {
  entree: number | Inconnu;
  entree_en_cache: number | Inconnu;
  sortie: number | Inconnu;
}
