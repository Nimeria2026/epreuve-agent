// Généré depuis 01_contrats/bon_de_livraison.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Un bon de livraison de Négovelle, tel que le service de ventes le garde dans ventes/livraisons/ : ce qui est parti, comment, et ce que le client a écrit en le recevant. Données fictives.
 */
export interface BonDeLivraison {
  /**
   * Par exemple BL-2026-01544.
   */
  numero: string;
  /**
   * Par exemple CO-2026-01873.
   */
  commande: string;
  /**
   * Code du client, celui de sa fiche.
   */
  client: string;
  date_expedition: string;
  date_livraison: string | null;
  transport: {
    mode: "flotte" | "transporteur";
    /**
     * La fiche du transporteur, null pour la flotte de la PME.
     */
    transporteur: string | null;
    /**
     * Numéro du récépissé du transporteur, ou null.
     */
    recepisse: string | null;
  };
  adresse: string;
  colis: number;
  /**
   * @minItems 1
   */
  lignes: [
    {
      /**
       * Référence du catalogue, par exemple VIS-01482.
       */
      reference: string;
      libelle: string;
      quantite: number;
    },
    ...{
      /**
       * Référence du catalogue, par exemple VIS-01482.
       */
      reference: string;
      libelle: string;
      quantite: number;
    }[]
  ];
  /**
   * Réserves portées au récépissé ou au bon à la livraison, mot pour mot, ou null.
   */
  reserves: string | null;
  signataire: string | null;
  statut: "en_cours" | "livre" | "refuse";
}
