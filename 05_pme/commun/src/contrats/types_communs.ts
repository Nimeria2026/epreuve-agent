// Généré depuis 01_contrats/types_communs.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Le catalogue du socle commun (07_taches/public/types_communs.yaml ; JOURNAL, cent-cinquante-quatrième entrée ; 00_docs/sources/2026-10-15_cadrage_socle_commun.md) : les types de tâches que toute entreprise rencontre, écrits une fois. Chaque société en a au moins une instance, écrite avec ses données et mesurée chez elle ; une tâche dit son type dans son classement (type_commun), et le catalogue ne liste pas les tâches.
 */
export interface TypesCommuns {
  /**
   * Version du catalogue, augmentée à chaque type ajouté, retiré ou redéfini.
   */
  version: number;
  /**
   * Un type par nom.
   */
  types: {
    [k: string]: TypeCommun;
  };
}
export interface TypeCommun {
  /**
   * Le type en quelques mots.
   */
  titre: string;
  /**
   * Ce que la tâche met devant l'agent.
   */
  piege: string;
  /**
   * La règle que le manuel de toute société porte sous une forme ou une autre.
   */
  regle: string;
  /**
   * Les catégories de contrôle grave de ses instances (gravite.yaml) ; vide pour un type sans contrôle grave.
   */
  gravite: string[];
  /**
   * Les risques de l'OWASP que le type illustre, pour lire les résultats dans une grille publique (JOURNAL, cent-cinquante-sixième entrée) : Top 10 for LLM Applications 2025 (LLM01:2025 à LLM10:2025) et Top 10 for Agentic Applications 2026 (ASI01 à ASI10). Absent pour un type sans risque de sécurité.
   *
   * @minItems 1
   */
  owasp?: [string, ...string[]];
}
