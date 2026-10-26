// Généré depuis 01_contrats/commande.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Une commande d'un client de Négovelle, telle que le service de ventes la garde dans ventes/commandes/ : ses lignes chiffrées, sa livraison, ses totaux, son statut et son historique. Données fictives.
 */
export interface Commande {
  /**
   * Par exemple CO-2026-01873.
   */
  numero: string;
  /**
   * Code du client, celui de sa fiche.
   */
  client: string;
  /**
   * Référence du bon de commande du client, ou null.
   */
  reference_client: string | null;
  cree_le: string;
  /**
   * Identifiant d'une personne de l'organigramme.
   */
  cree_par: string;
  mode: "standard" | "express";
  /**
   * Où livrer : une adresse de la fiche, ou une adresse ponctuelle.
   */
  livraison: {
    /**
     * Code de l'adresse dans la fiche du client, null pour une adresse ponctuelle.
     */
    code: string | null;
    adresse: string;
  };
  /**
   * @minItems 1
   */
  lignes: [LigneCommande, ...LigneCommande[]];
  port_ht_euros: number;
  total_ht_euros: number;
  total_tva_euros: number;
  total_ttc_euros: number;
  statut:
    | "brouillon"
    | "en_attente_deblocage"
    | "en_attente_reassort"
    | "validee"
    | "expediee"
    | "livree"
    | "facturee"
    | "annulee";
  /**
   * Pourquoi une commande attend un déblocage, ou null.
   */
  motif_attente: string | null;
  /**
   * La commande dont celle-ci est le reliquat, ou null.
   */
  reliquat_de: string | null;
  /**
   * Items: Par exemple BL-2026-01544.
   */
  livraisons: string[];
  facture: string | null;
  historique: Evenement[];
}
export interface LigneCommande {
  /**
   * Référence du catalogue, par exemple VIS-01482.
   */
  reference: string;
  libelle: string;
  quantite: number;
  prix_tarif_ht_euros: number;
  /**
   * Remise de la catégorie du client puis du barème, composées ; 0 pour un prix net ou un prix dérogatoire.
   */
  remise_pourcent: number;
  /**
   * Prix unitaire après remise, au centime, calculé par le service ou accordé.
   */
  prix_net_ht_euros: number;
  /**
   * Vrai si le prix a été accordé par accorder_prix.
   */
  prix_derogatoire: boolean;
  /**
   * En pour cent.
   */
  taux_tva: 5.5 | 10 | 20;
  montant_ht_euros: number;
}
export interface Evenement {
  date: string;
  /**
   * Identifiant d'une personne de l'organigramme.
   */
  par: string;
  action:
    | "creee"
    | "modifiee"
    | "validee"
    | "mise_en_attente"
    | "debloquee"
    | "prix_accorde"
    | "adresse_ponctuelle"
    | "scindee"
    | "expediee"
    | "livree"
    | "facturee"
    | "annulee";
  detail: string;
}
