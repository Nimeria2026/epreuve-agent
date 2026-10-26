// Généré depuis 01_contrats/classement.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Difficulté d'une tâche, liste fermée (cadrage de l'horizon de temps, §6) : calcul, un montant, un taux ou un nombre à calculer ; dates_et_echeances, une date, un délai ou un créneau à trouver ou à calculer ; volume, au moins trois éléments à traiter ; regle_peu_visible, une règle du manuel facile à manquer ; document, une information décisive à lire dans une pièce jointe ou un document autre que le manuel ; piege, une demande qui pousse à enfreindre le manuel. « plusieurs services » se calcule depuis la tâche.
 */
export type Etiquette = "calcul" | "dates_et_echeances" | "volume" | "regle_peu_visible" | "document" | "piege";
/**
 * Code d'une personne du poste humain.
 */
export type CodePersonne = string;

/**
 * Classement des tâches d'un jeu (07_taches/public/classement.yaml ; les tâches cachées ont le leur dans 07_taches/prive/) : ce qui ne se calcule pas depuis la tâche. Les étiquettes de difficulté servent à lire les échecs, jamais à noter ; la fiche ROME de France Travail ancre la tâche dans un métier réel ; les sections du manuel dont la tâche se sert s'écrivent à la main ; les durées humaines mesurées viennent des runs du poste humain, versées par un script (make classement VERSER=1), et la durée estimée par la grille se calcule depuis un run du témoin parfait (make classement ESTIMER=1), jamais à la main. Le métier, les services, le contrôle grave et les étapes du témoin parfait se calculent depuis la tâche et ne s'écrivent pas ici (JOURNAL, entrées 121 et 125).
 */
export interface Classement {
  /**
   * Version du fichier, augmentée à chaque changement de sa forme.
   */
  version: number;
  /**
   * Les personnes du poste humain, par leur code (p1, p2), jamais par leur nom.
   */
  personnes: {
    [k: string]: Personne;
  };
  /**
   * Une fiche par tâche, sous son identifiant.
   */
  taches: {
    [k: string]: FicheClassement;
  };
}
export interface Personne {
  /**
   * Vrai pour une personne qui a vu les tâches avant de les faire, par exemple en les concevant : ses durées sont plus courtes que celles d'un nouvel employé.
   */
  connait_les_taches: boolean;
}
export interface FicheClassement {
  /**
   * Version de la tâche classée ; une version plus récente demande de relire la fiche.
   */
  version_tache: number;
  etiquettes: Etiquette[];
  /**
   * Le type du socle commun dont la tâche est une instance, par son nom dans 07_taches/public/types_communs.yaml (JOURNAL, cent-cinquante-quatrième entrée) ; absent pour une tâche du métier. Écrit à la main.
   */
  type_commun?: string;
  /**
   * La fonction de la PME que la tâche exerce, pour le benchmark par branche (cadrage du 2026-10-20, choix B1) : une des six fonctions de la carte du banc du 2026-10-07. Écrite à la main ; absente pour une tâche hors du benchmark (tranches longues).
   */
  branche?:
    | "accueil_et_courrier"
    | "relation_client"
    | "comptabilite_et_fournisseurs"
    | "commercial_et_devis"
    | "planning_et_interventions"
    | "personnel_et_rh";
  rome: FicheRome;
  /**
   * Les sections du manuel dont la tâche se sert, par leur numéro dans le manuel de la tâche (un complément peut le changer) ; la grille ne compte qu'elles. Listées par Claude, relues par Alexandre (JOURNAL, cent-vingt-cinquième entrée).
   */
  sections_manuel: number[];
  /**
   * Les essais réussis au poste humain, toutes versions de la tâche confondues.
   */
  durees: DureeHumaine[];
  duree_estimee?: DureeEstimee;
}
/**
 * La fiche du ROME de France Travail que la tâche illustre ; on cite son code et son intitulé, jamais son texte.
 */
export interface FicheRome {
  code: string;
  intitule: string;
}
/**
 * Un essai réussi au poste humain : la durée chronométrée de « Commencer » à « J'ai fini », le run et la répétition d'où elle vient, et la version de la tâche faite.
 */
export interface DureeHumaine {
  personne: CodePersonne;
  secondes: number;
  run: string;
  repetition: number;
  version_tache: number;
}
/**
 * La durée d'une tâche estimée par la grille (cadrage de l'horizon de temps, suite du 2026-10-14) : le temps d'un employé du métier qui sait déjà quoi faire, sur le chemin du témoin parfait ; une borne basse, jamais une durée mesurée. Ses quatre parts, en secondes, font son total.
 */
export interface DureeEstimee {
  /**
   * La durée estimée, somme des quatre parts.
   */
  secondes: number;
  /**
   * Version de la grille qui l'a calculée ; une autre version demande de la refaire.
   */
  grille: string;
  /**
   * Version de la tâche estimée.
   */
  version_tache: number;
  /**
   * Le run du témoin parfait d'où vient le chemin.
   */
  run: string;
  /**
   * Courriels, documents et sections du manuel lus pour comprendre.
   */
  lire: number;
  /**
   * Listes et tableaux balayés pour trouver une ligne.
   */
  chercher: number;
  /**
   * Textes libres écrits : corps, objet, commentaire, motif.
   */
  ecrire: number;
  /**
   * Gestes : ouvrir, remplir, valider, au modèle KLM.
   */
  agir: number;
}
