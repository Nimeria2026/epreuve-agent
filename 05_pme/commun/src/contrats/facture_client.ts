// Généré depuis 01_contrats/facture_client.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Une facture de Calorelle à un client, telle que le service facturation de la PME la garde. Données fictives.
 */
export interface FactureClient {
  /**
   * Par exemple FC-2026-0412.
   */
  numero: string;
  /**
   * Code du client, celui de sa fiche.
   */
  client: string;
  date: string;
  objet: string;
  montant_ttc_euros: number;
  payee: boolean;
}
