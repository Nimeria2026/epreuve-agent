// Généré depuis 01_contrats/retour.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Des articles revenus d'une livraison de Négovelle, enregistrés par le service de ventes dans ventes/retours/ : les revendables reviennent en stock. Données fictives.
 */
export interface Retour {
  /**
   * Par exemple RT-2026-0042.
   */
  numero: string;
  /**
   * Par exemple BL-2026-01544.
   */
  livraison: string;
  /**
   * Code du client, celui de sa fiche.
   */
  client: string;
  date: string;
  /**
   * @minItems 1
   */
  lignes: [
    {
      /**
       * Référence du catalogue, par exemple VIS-01482.
       */
      reference: string;
      quantite: number;
      etat: "revendable" | "rebut";
    },
    ...{
      /**
       * Référence du catalogue, par exemple VIS-01482.
       */
      reference: string;
      quantite: number;
      etat: "revendable" | "rebut";
    }[]
  ];
  motif: string;
  /**
   * Identifiant d'une personne de l'organigramme.
   */
  enregistre_par: string;
}
