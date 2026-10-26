// Généré depuis 01_contrats/technicien.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

export type Competence = "chaudiere_gaz" | "chaudiere_fioul" | "pompe_a_chaleur" | "climatisation" | "ventilation";

/**
 * Un technicien de la PME vu par le service de planning (étape 5) : ses compétences, s'il est apprenti, ses périodes d'indisponibilité, sans motif. Une personne de l'organigramme. Données fictives.
 */
export interface Technicien {
  /**
   * Identifiant de la personne dans l'organigramme, par exemple thomas.girard.
   */
  id: string;
  nom: string;
  /**
   * @minItems 1
   */
  competences: [Competence, ...Competence[]];
  /**
   * Vrai pour un apprenti. Le logiciel le planifie comme les autres ; le manuel dit ce qu'il peut faire seul.
   */
  apprenti: boolean;
  /**
   * Périodes où le technicien ne peut pas être planifié, sans motif : congés, arrêts et formations restent au dossier RH.
   */
  indisponibilites: Periode[];
}
export interface Periode {
  debut: string;
  fin: string;
}
