// Généré depuis 01_contrats/devis.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Un devis de Calorelle à un client, tel que le service facturation de la PME le garde (étape 5, tranche 5) : ses lignes prises au tarif, sa remise, ses totaux calculés par le service, son statut. Données fictives.
 */
export interface Devis {
  /**
   * Par exemple DV-2026-013.
   */
  numero: string;
  /**
   * Code du client, celui de sa fiche.
   */
  client: string;
  objet: string;
  /**
   * @minItems 1
   */
  lignes: [
    {
      /**
       * Code de la ligne du tarif.
       */
      code: string;
      libelle: string;
      /**
       * Au centième près.
       */
      quantite: number;
      /**
       * Pris au tarif par le service.
       */
      prix_unitaire_ht_euros: number;
      /**
       * En pour cent, choisi par la personne qui chiffre le devis.
       */
      taux_tva: 5.5 | 10 | 20;
      /**
       * Quantité fois prix unitaire, arrondi au centime, avant remise.
       */
      montant_ht_euros: number;
    },
    ...{
      /**
       * Code de la ligne du tarif.
       */
      code: string;
      libelle: string;
      /**
       * Au centième près.
       */
      quantite: number;
      /**
       * Pris au tarif par le service.
       */
      prix_unitaire_ht_euros: number;
      /**
       * En pour cent, choisi par la personne qui chiffre le devis.
       */
      taux_tva: 5.5 | 10 | 20;
      /**
       * Quantité fois prix unitaire, arrondi au centime, avant remise.
       */
      montant_ht_euros: number;
    }[]
  ];
  /**
   * Remise sur chaque ligne, en pour cent ; 0 sans remise.
   */
  remise_pourcent: number;
  /**
   * Après remise.
   */
  total_ht_euros: number;
  total_tva_euros: number;
  total_ttc_euros: number;
  /**
   * Un brouillon abandonné reste gardé : on ne supprime aucun document.
   */
  statut: "brouillon" | "envoye" | "accepte" | "refuse" | "abandonne";
  /**
   * Heure de la PME, au format RFC 3339 avec le décalage horaire.
   */
  cree_le: string;
  /**
   * Identifiant de la personne servie quand le devis a été créé.
   */
  cree_par: string;
  /**
   * Quand l'envoi a été enregistré ; null pour un brouillon.
   */
  envoye_le: string | null;
  /**
   * Quand l'acceptation ou le refus a été enregistré ; null sinon.
   */
  reponse_le: string | null;
}
