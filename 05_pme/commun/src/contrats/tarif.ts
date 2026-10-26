// Généré depuis 01_contrats/tarif.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * La grille de prix de Calorelle, que le service facturation de la PME lit pour chiffrer un devis (étape 5, tranche 5). Prix hors taxes, fictifs.
 */
export interface Tarif {
  /**
   * Année du tarif.
   */
  annee: number;
  /**
   * @minItems 1
   */
  lignes: [
    {
      /**
       * Par exemple CHA-01.
       */
      code: string;
      libelle: string;
      unite: "unité" | "heure" | "forfait" | "mètre";
      /**
       * Prix hors taxes d'une unité, au centime.
       */
      prix_ht_euros: number;
    },
    ...{
      /**
       * Par exemple CHA-01.
       */
      code: string;
      libelle: string;
      unite: "unité" | "heure" | "forfait" | "mètre";
      /**
       * Prix hors taxes d'une unité, au centime.
       */
      prix_ht_euros: number;
    }[]
  ];
}
