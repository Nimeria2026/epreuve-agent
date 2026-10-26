// Généré depuis 01_contrats/parametres_societe.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Paramètres d'une société fictive pour les services communs de la PME (ADR 0006), lus dans entreprise/societe.yaml de son état. Un état sans ce fichier est celui de Calorelle : nom Calorelle, domaine calorelle.example, fiches fournisseurs dans administration/fournisseurs, valeurs que gardent les services et EASE quand le fichier manque.
 */
export interface ParametresSociete {
  /**
   * Nom de la société, par exemple Domivelle.
   */
  nom: string;
  /**
   * Domaine des adresses du personnel et des boîtes partagées, toujours en .example (RFC 2606) : un courriel vers ce domaine reste dans la société.
   */
  domaine: string;
  /**
   * Dossier, relatif aux dossiers partagés, des fiches que lit et modifie le service des achats : <dossier>/<fournisseur>/fiche_fournisseur.yaml.
   */
  dossier_fiches_fournisseurs: string;
}
