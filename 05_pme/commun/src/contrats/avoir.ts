// Généré depuis 01_contrats/avoir.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Un avoir émis sur une facture client par le service facturation de la PME : un remboursement ou un geste commercial. Données fictives.
 */
export interface Avoir {
  /**
   * Par exemple AV-2026-0001.
   */
  numero: string;
  client: string;
  facture: string;
  /**
   * Heure simulée de la PME, au format RFC 3339 avec le décalage horaire.
   */
  date: string;
  montant_ttc_euros: number;
  motif: string;
  /**
   * Identifiant de la personne servie, dans l'organigramme.
   */
  emis_par: string;
}
