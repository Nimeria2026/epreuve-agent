// Généré depuis 01_contrats/lecture_document.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Ce qu'EKE, l'outil documentaire de la PME, rend d'un document PDF (étape 6) : le document lu, puis selon l'outil appelé ses lignes, ses valeurs ou les citations d'un texte cherché. Chaque texte rendu porte sa provenance : la page et la zone d'où il vient. Zones en points PDF (1/72 de pouce), origine en haut à gauche de la page telle qu'elle s'affiche, y vers le bas.
 */
export interface LectureDocument {
  document: Document;
  /**
   * Ce qui a lu le document, pour rejouer une lecture (règle 1 du BRIEF).
   */
  lecteur: {
    /**
     * Version d'EKE.
     */
    version: string;
    /**
     * Bibliothèque de lecture des PDF et sa version, par exemple « pypdfium2 5.14.0 ».
     */
    moteur: string;
  };
  /**
   * Outil lire_document : le texte du document dans l'ordre de lecture du PDF, une colonne de texte après l'autre. Une ligne est un morceau de texte d'une seule ligne visuelle, sans grand blanc : la ligne d'un courrier, la cellule d'un tableau.
   */
  lignes?: Citation[];
  /**
   * Outil extraire_valeurs : les paires étiquette-valeur trouvées, dans l'ordre des lignes.
   */
  valeurs?: Valeur[];
  /**
   * Outil citer : le texte cherché, tel que donné.
   */
  recherche?: string;
  /**
   * Outil citer : chaque endroit où le texte cherché apparaît ; vide s'il n'apparaît nulle part.
   */
  citations?: Citation[];
}
export interface Document {
  /**
   * Chemin du document dans les dossiers partagés de la PME, avec des « / ».
   */
  chemin: string;
  /**
   * Empreinte sha256 du fichier lu, préfixée par « sha256: ».
   */
  empreinte: string;
  /**
   * @minItems 1
   */
  pages: [Page, ...Page[]];
}
export interface Page {
  /**
   * Numéro de la page, à partir de 1.
   */
  numero: number;
  /**
   * En points, page telle qu'elle s'affiche (une page tournée d'un quart de tour échange largeur et hauteur).
   */
  largeur: number;
  /**
   * En points, page telle qu'elle s'affiche.
   */
  hauteur: number;
}
/**
 * Un texte du document et sa provenance.
 */
export interface Citation {
  /**
   * Le texte exact, tel qu'il se lit dans le document.
   */
  texte: string;
  page: number;
  zone: Zone;
}
/**
 * Rectangle en points, origine en haut à gauche de la page affichée, y vers le bas : x0 ≤ x1 et y0 ≤ y1.
 */
export interface Zone {
  /**
   * Bord gauche.
   */
  x0: number;
  /**
   * Bord haut.
   */
  y0: number;
  /**
   * Bord droit.
   */
  x1: number;
  /**
   * Bord bas.
   */
  y1: number;
}
export interface Valeur {
  /**
   * L'étiquette telle qu'elle est écrite, par exemple « Total TTC ».
   */
  etiquette: string;
  /**
   * Ce que la valeur est. « iban » se reconnaît à sa forme ; la clé de contrôle n'est pas vérifiée.
   */
  type: "montant" | "date" | "iban" | "pourcentage" | "texte";
  /**
   * La valeur normalisée : montant en décimal à point et deux décimales (« 512.40 »), date AAAA-MM-JJ, IBAN sans espaces, pourcentage en décimal à point (« 5.5 »), texte tel qu'écrit.
   */
  valeur: string;
  /**
   * « EUR » pour un montant, « % » pour un pourcentage ; null sinon.
   */
  unite: string | null;
  citation: Citation1;
}
/**
 * Un texte du document et sa provenance.
 */
export interface Citation1 {
  /**
   * Le texte exact, tel qu'il se lit dans le document.
   */
  texte: string;
  page: number;
  zone: Zone;
}
