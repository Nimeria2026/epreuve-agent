// Généré depuis 01_contrats/courriel.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Adresse fictive : le domaine se termine toujours par .example (RFC 2606).
 */
export type Adresse = string;

/**
 * Un courriel de la messagerie de la PME fictive, tel que le serveur messagerie l'enregistre et qu'EASE le relit pour ses contrôles. Toutes les adresses sont fictives, en .example.
 */
export interface Courriel {
  /**
   * Identifiant stable, cité par les tâches (par exemple m-cpt-001).
   */
  identifiant: string;
  de: Correspondant;
  /**
   * @minItems 1
   */
  a: [Adresse, ...Adresse[]];
  cc: Adresse[];
  objet: string;
  /**
   * Date et heure d'envoi au format RFC 3339, avec le décalage horaire (par exemple 2026-11-02T08:12:00+01:00).
   */
  date: string;
  corps: string;
  pieces_jointes: PieceJointe[];
  lu: boolean;
  /**
   * Courriel auquel celui-ci répond ; null sinon.
   */
  en_reponse_a: string | null;
  /**
   * Courriel que celui-ci transfère ; null sinon.
   */
  transfere_de: string | null;
}
/**
 * Expéditeur : nom affiché et adresse. Le nom affiché peut mentir, pas le domaine.
 */
export interface Correspondant {
  nom: string | null;
  adresse: Adresse;
}
/**
 * Une pièce jointe, rangée dans messagerie/pieces/ de l'état de la PME.
 */
export interface PieceJointe {
  /**
   * Nom du fichier tel qu'il apparaît dans le courriel.
   */
  nom: string;
  /**
   * Chemin du fichier, relatif au dossier messagerie de l'état.
   */
  fichier: string;
  taille_octets: number;
}
