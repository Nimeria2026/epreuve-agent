// Généré depuis 01_contrats/fiche_client_negoce.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * La fiche d'un client de Négovelle, rangée dans dossiers/clients/<code>/fiche_client.yaml : ses contacts et ses adresses déclarés, ses conditions, son statut ; lue par le service de ventes, qui n'y écrit que le statut. Données fictives.
 */
export interface FicheClientNegoce {
  /**
   * Code du client, celui de sa fiche.
   */
  code: string;
  nom: string;
  type: "artisan" | "entreprise" | "pme" | "collectivite";
  /**
   * Le siège ; le service de facturation la lit aussi.
   */
  adresse: string;
  /**
   * Le numéro à rappeler pour vérifier une demande.
   */
  telephone: string;
  secteur: "nord" | "sud" | "est" | "ouest";
  /**
   * Identifiant d'une personne de l'organigramme.
   */
  commercial: string;
  /**
   * Identifiant d'une personne de l'organigramme.
   */
  administration_des_ventes: string;
  /**
   * Les contacts déclarés : les seuls dont une commande ou une demande se reçoit.
   *
   * @minItems 1
   */
  contacts: [
    {
      nom: string;
      fonction: string;
      courriel: string;
    },
    ...{
      nom: string;
      fonction: string;
      courriel: string;
    }[]
  ];
  /**
   * @minItems 1
   */
  adresses_livraison: [
    {
      code: string;
      libelle: string;
      adresse: string;
    },
    ...{
      code: string;
      libelle: string;
      adresse: string;
    }[]
  ];
  categorie_remise: "A" | "B" | "C";
  delai_paiement: "comptant" | "30_jours_date_de_facture" | "60_jours_date_de_facture";
  client_depuis: string;
  limite_encours_euros: number;
  livraisons_partielles: boolean;
  substitution_acceptee: boolean;
  statut: "ouvert" | "bloque";
  motif_blocage: string | null;
}
