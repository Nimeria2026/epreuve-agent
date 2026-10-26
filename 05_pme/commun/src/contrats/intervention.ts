// Généré depuis 01_contrats/intervention.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Un rendez-vous du planning de la PME (étape 5) : chez quel client, avec quels techniciens, quand, pour quoi. Une intervention annulée reste au planning, avec son motif. Données fictives.
 */
export interface Intervention {
  /**
   * Par exemple INT-2026-0001.
   */
  numero: string;
  client: string;
  /**
   * @minItems 1
   */
  techniciens: [string, ...string[]];
  /**
   * Heure de la PME, au format RFC 3339 avec le décalage horaire.
   */
  debut: string;
  fin: string;
  nature: "visite_annuelle" | "depannage" | "installation" | "mise_en_service";
  objet: string;
  statut: "planifiee" | "annulee";
  motif_annulation?: string;
  /**
   * Identifiant de la personne servie quand l'intervention a été planifiée, ou « donnees_initiales ».
   */
  cree_par: string;
}
