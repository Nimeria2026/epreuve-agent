// Généré depuis 01_contrats/catalogue.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Le catalogue d'une PME de négoce (Négovelle, cadrage du 2026-10-17), tel que le service de ventes le garde dans ventes/catalogue.json : chaque article, son prix, ce qu'il coûte, son stock. Données fictives.
 */
export interface Catalogue {
  annee_tarif: number;
  /**
   * Les conditions générales de vente que le logiciel applique à chaque commande.
   */
  conditions: {
    /**
     * Remise en pour cent de chaque catégorie de client, sur le prix du tarif.
     */
    remises_categories: {
      A: number;
      B: number;
      C: number;
    };
    /**
     * Port d'une commande standard sous le franco.
     */
    port_standard_ht_euros: number;
    /**
     * Montant des lignes, hors taxes, à partir duquel une commande standard part sans port.
     */
    franco_a_partir_de_ht_euros: number;
    /**
     * Port d'une commande express, quel que soit son montant.
     */
    forfait_express_ht_euros: number;
    /**
     * En pour cent.
     */
    taux_tva_port: 5.5 | 10 | 20;
  };
  /**
   * @minItems 1
   */
  articles: [Article, ...Article[]];
}
export interface Article {
  /**
   * Référence du catalogue, par exemple VIS-01482.
   */
  reference: string;
  libelle: string;
  /**
   * Une des familles du catalogue, par exemple visserie.
   */
  famille: string;
  /**
   * Unité de vente, par exemple boîte de 100.
   */
  unite: string;
  /**
   * Une commande en demande un multiple.
   */
  conditionnement: number;
  /**
   * Prix du tarif général, avant toute remise.
   */
  prix_vente_ht_euros: number;
  /**
   * Vrai pour un article qui ne prend aucune remise.
   */
  prix_net: boolean;
  /**
   * Remises par quantité commandée sur une ligne, seuils croissants ; la plus haute atteinte s'applique.
   */
  bareme_quantite: {
    a_partir_de: number;
    remise_pourcent: number;
  }[];
  /**
   * En pour cent.
   */
  taux_tva: 5.5 | 10 | 20;
  /**
   * Ce que l'article coûte : de quoi calculer le seuil de revente à perte.
   */
  achat: {
    /**
     * Dossier de la fiche du fournisseur, lue par le service des achats.
     */
    fournisseur: string;
    /**
     * Prix unitaire net de la dernière facture d'achat.
     */
    prix_net_facture_ht_euros: number;
    /**
     * Autres avantages financiers du fournisseur, en pour cent du prix unitaire net.
     */
    avantages_financiers_pourcent: number;
    /**
     * Part du transport d'achat, par unité.
     */
    transport_unitaire_ht_euros: number;
  };
  /**
   * Unités en rayon ; le réservé se calcule sur les commandes validées.
   */
  stock_physique: number;
  point_de_commande: number;
  quantite_reassort: number;
  /**
   * Réassort commandé au fournisseur, ou null.
   */
  reassort: {
    quantite: number;
    date_prevue: string;
  } | null;
  statut: "courant" | "fin_de_serie" | "dereference";
  /**
   * Articles qui peuvent le remplacer, avec l'accord du client.
   *
   * Items: Référence du catalogue, par exemple VIS-01482.
   */
  substituts: string[];
}
