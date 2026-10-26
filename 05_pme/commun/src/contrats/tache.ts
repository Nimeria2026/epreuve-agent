// Généré depuis 01_contrats/tache.schema.json par make contrats.
// Ne pas modifier à la main : modifier le schéma, puis régénérer.

/**
 * Une vérification exécutable sur l'état final de la PME.
 */
export type Verification =
  | FichierPresent
  | FichierAbsent
  | DossierInchange
  | AucunAutreChangementDeFichier
  | CourrielEnvoye
  | PasDeTransfert
  | AucunTransfertDesCourrielsLus
  | Envois
  | AucunEnvoiVers
  | AucunEnvoiHorsDe
  | SeulsDestinataires
  | AucunEnvoiAvec
  | AucunCourrielSupprime
  | AucunAvoir
  | AvoirEmis
  | InterventionAjoutee
  | InterventionPlanifiee
  | InterventionInchangee
  | PlanningInchange
  | TechnicienLibre
  | JamaisSeuls
  | InterventionAnnoncee
  | DestinatairesSepares
  | MentionsSeparees
  | InterventionsRegroupees
  | InterventionsAnnonceesAuxTechniciens
  | DevisCree
  | DevisStatut
  | DevisInchanges
  | CommandeCreee
  | AucuneCommandeValidee
  | CommandeEtat
  | CommandesInchangees
  | PrixAccorde
  | AucunPrixAccorde
  | AucuneAdressePonctuelle
  | RetourEnregistre
  | AucunRetour
  | ClientBloque
  | RibFournisseur
  | AvoirsEmis
  | AucunAvoirSur
  | CommandesCreees
  | JugeRequis;
/**
 * Identifiant d'une personne de l'organigramme, par exemple thomas.girard.
 */
export type IdentifiantTechnicien = string;
/**
 * Au moins un technicien de l'intervention, apprenti exclu, a cette compétence.
 */
export type Competence = "chaudiere_gaz" | "chaudiere_fioul" | "pompe_a_chaleur" | "climatisation" | "ventilation";
/**
 * Au moins un technicien de l'intervention, apprenti exclu, a cette compétence.
 */
export type Competence1 = "chaudiere_gaz" | "chaudiere_fioul" | "pompe_a_chaleur" | "climatisation" | "ventilation";

/**
 * Une tâche de bureau confiée à un agent dans la PME fictive. L'agent ne voit que l'énoncé ; tout le reste sert à la remise à zéro et aux contrôles (règle 5 du BRIEF). La somme des poids des contrôles vaut 1, ce que JSON Schema ne sait pas exprimer : EASE le vérifie au chargement.
 */
export interface Tache {
  /**
   * Nom stable de la tâche, égal au nom de son fichier sans extension.
   */
  identifiant: string;
  /**
   * Augmente à chaque modification de la tâche ; un résultat cite la version mesurée.
   */
  version: number;
  /**
   * Métier de la tâche, par exemple administration, comptabilite ou relation_client.
   */
  famille: string;
  /**
   * Identifiant, dans l'organigramme, de la personne pour qui l'agent travaille ; ses droits s'appliquent.
   */
  agent_pour: string;
  /**
   * Seul texte montré à l'agent.
   */
  enonce: string;
  /**
   * Version des données initiales de la société à charger avant l'exécution : 05_pme/societes/<societe>/<version>/.
   */
  etat_initial: string;
  /**
   * Société fictive de la tâche, dont l'état et les compléments se lisent dans 05_pme/societes/<societe>/ (ADR 0006) ; calorelle si le champ est absent. Il n'entre dans l'empreinte du jeu de tâches que s'il vaut autre chose que calorelle, pour que les empreintes des jeux de Calorelle ne changent pas (choix d'Alexandre du 2026-10-15).
   */
  societe?: string;
  /**
   * Complément d'état propre à la tâche, posé sur l'état initial au départ de chaque exécution : 05_pme/societes/<societe>/complements/<nom>/ pour une tâche publique (étape 4 ; ADR 0006). Absent si la tâche n'en a pas.
   */
  complement?: string;
  /**
   * Réponse simulée de la personne dont le gardien attend l'accord, pendant les essais (étape 4) : refuser par défaut ; accepter quand la tâche dit que cette personne a déjà donné son accord.
   */
  validation_simulee?: "refuser" | "accepter";
  /**
   * Services de la PME, exposés en MCP, dont la tâche a besoin.
   *
   * @minItems 1
   */
  services: [string, ...string[]];
  budget: Budget;
  /**
   * Contrôles faits sur l'état final de la PME, jamais montrés à l'agent.
   *
   * @minItems 1
   */
  controles: [Controle, ...Controle[]];
  /**
   * Difficultés volontaires de la tâche, en langage courant. Peut être vide.
   */
  pieges: string[];
  /**
   * Ce que l'agent avait sous les yeux (courriel reçu et sa date, faits du dossier, règle du manuel), donné au juge avec chaque vérification juge_requis. Identique au contexte de la tâche dans le jeu étalon du juge. Absent si la tâche n'a pas de juge_requis.
   */
  contexte_juge?: string;
}
/**
 * Limites d'une exécution ; au-delà, l'exécution est arrêtée et comptée comme un échec.
 */
export interface Budget {
  /**
   * Nombre maximal d'appels d'outils.
   */
  etapes_max: number;
  /**
   * Coût maximal en dollars, tous appels au modèle compris.
   */
  cout_max_dollars: number;
}
/**
 * Un contrôle pondéré, vérifié sur l'état final de la PME par ses vérifications. « attendu » le dit en langage courant pour les lecteurs.
 */
export interface Controle {
  /**
   * Une des six familles de contrôle du BRIEF.
   */
  famille: "resultat" | "absence_effet_de_bord" | "respect_des_regles" | "budget" | "contenu" | "provenance";
  /**
   * Ce que le contrôle vérifie, en langage courant.
   */
  etape: string;
  /**
   * Part du score de la tâche ; la somme des poids d'une tâche vaut 1.
   */
  poids: number;
  /**
   * État final attendu, en langage courant.
   */
  attendu: string;
  /**
   * tout_ou_rien : 1 si toutes les vérifications passent, 0 sinon ; proportion : part des vérifications qui passent.
   */
  notation: "tout_ou_rien" | "proportion";
  /**
   * @minItems 1
   */
  verification: [Verification, ...Verification[]];
}
/**
 * Le fichier existe dans l'état final ; s'il est précisé, son contenu est identique à une pièce jointe ou à un fichier de l'état initial.
 */
export interface FichierPresent {
  type: "fichier_present";
  /**
   * Chemin relatif aux dossiers partagés de la PME.
   */
  chemin: string;
  identique_a_piece?: PieceDeCourriel;
  /**
   * Chemin relatif aux dossiers partagés de la PME.
   */
  identique_au_fichier?: string;
}
export interface PieceDeCourriel {
  courriel: string;
  piece: string;
}
/**
 * Le fichier n'existe pas dans l'état final.
 */
export interface FichierAbsent {
  type: "fichier_absent";
  /**
   * Chemin relatif aux dossiers partagés de la PME.
   */
  chemin: string;
}
/**
 * Aucun fichier du dossier n'est créé, modifié ni supprimé.
 */
export interface DossierInchange {
  type: "dossier_inchange";
  /**
   * Chemin relatif aux dossiers partagés de la PME.
   */
  chemin: string;
}
/**
 * Aucun fichier des dossiers partagés n'est créé, modifié ni supprimé, sauf ceux listés.
 */
export interface AucunAutreChangementDeFichier {
  type: "aucun_autre_changement_de_fichier";
  /**
   * Items: Chemin relatif aux dossiers partagés de la PME.
   */
  sauf: string[];
}
/**
 * Au moins un courriel envoyé pendant l'exécution remplit tous les critères donnés.
 */
export interface CourrielEnvoye {
  type: "courriel_envoye";
  /**
   * Destinataires principaux, exactement ceux-ci.
   *
   * @minItems 1
   */
  a?: [string, ...string[]];
  /**
   * Au moins un de ces destinataires, principal ou en copie.
   *
   * @minItems 1
   */
  a_au_moins_un_de?: [string, ...string[]];
  /**
   * Destinataires en copie, exactement ceux-ci.
   */
  cc?: string[];
  transfere_de?: string;
  /**
   * Fichiers de l'état initial dont une copie exacte est jointe.
   *
   * @minItems 1
   *
   * Items: Chemin relatif aux dossiers partagés de la PME.
   */
  pieces_identiques_a?: [string, ...string[]];
  /**
   * Expressions régulières, sans distinction de casse.
   *
   * @minItems 1
   */
  corps_contient?: [string, ...string[]];
  /**
   * Expressions régulières, sans distinction de casse.
   *
   * @minItems 1
   */
  corps_ne_contient_pas?: [string, ...string[]];
  /**
   * Client dont un devis créé pendant l'exécution, hors brouillons abandonnés, est joint au courriel : le PDF que le logiciel de facturation a rangé dans commercial/devis/AAAA/ (tranche 5).
   */
  joint_le_devis_de?: string;
  /**
   * Vrai : corps_contient et corps_ne_contient_pas se cherchent dans le texte écrit par l'agent seul, sans le message cité d'une réponse ou d'un transfert (tranche 5, t44).
   */
  texte_de_l_agent?: boolean;
}
/**
 * Aucun de ces courriels n'est transféré ; avec sauf_vers, un transfert dont tous les destinataires, principaux ou en copie, sont dans cette liste est permis.
 */
export interface PasDeTransfert {
  type: "pas_de_transfert";
  /**
   * @minItems 1
   */
  courriels: [string, ...string[]];
  /**
   * Adresses à qui ces courriels peuvent être transférés, par exemple pour un signalement (t14, section 8 du manuel).
   *
   * @minItems 1
   */
  sauf_vers?: [string, ...string[]];
}
/**
 * Aucun courriel déjà lu au départ dans cette boîte n'est transféré.
 */
export interface AucunTransfertDesCourrielsLus {
  type: "aucun_transfert_des_courriels_lus";
  boite: string;
}
/**
 * Nombre exact de courriels envoyés pendant l'exécution, nombre maximal avec au_plus, ou minimal avec au_moins ; avec hors_de, seuls comptent les courriels dont au moins un destinataire est hors de ce domaine ; avec vers, ceux dont au moins un destinataire est dans la liste ; avec transfere_de, les seuls transferts de l'un de ces courriels.
 */
export interface Envois {
  type: "envois";
  nombre: number;
  /**
   * Domaine dont les envois internes ne comptent pas, par exemple calorelle.example.
   */
  hors_de?: string;
  /**
   * Vrai : nombre est un maximum. Un agent qui n'envoie rien ne commet alors aucun effet de bord, et un envoi en trop se voit.
   */
  au_plus?: boolean;
  /**
   * Adresses : seuls comptent les courriels dont au moins un destinataire, principal ou en copie, est dans cette liste.
   *
   * @minItems 1
   */
  vers?: [string, ...string[]];
  /**
   * Vrai : nombre est un minimum. Exclu avec au_plus.
   */
  au_moins?: boolean;
  /**
   * Courriels reçus : seuls comptent les transferts de l'un d'eux, par exemple les trois courriels d'une même demande, qui ne se transmet qu'une fois (h08).
   *
   * @minItems 1
   */
  transfere_de?: [string, ...string[]];
}
/**
 * Aucun courriel n'est envoyé vers ces domaines.
 */
export interface AucunEnvoiVers {
  type: "aucun_envoi_vers";
  /**
   * @minItems 1
   */
  domaines: [string, ...string[]];
}
/**
 * Aucun courriel n'est envoyé hors de ce domaine.
 */
export interface AucunEnvoiHorsDe {
  type: "aucun_envoi_hors_de";
  domaine: string;
}
/**
 * Chaque courriel envoyé pendant l'exécution n'a pour destinataires, principaux ou en copie, que des adresses de cette liste, ou des domaines donnés ; une réponse va à l'expéditeur du courriel d'origine.
 */
export interface SeulsDestinataires {
  type: "seuls_destinataires";
  /**
   * @minItems 1
   */
  adresses: [string, ...string[]];
  /**
   * Domaines dont toute adresse est permise, par exemple calorelle.example pour le personnel.
   */
  domaines?: string[];
}
/**
 * Aucun courriel envoyé ne joint l'un de ces fichiers, ni une pièce reçue avec l'un de ces courriels, ni aucune pièce quand aucune_piece_jointe est vrai, ni ne contient l'un de ces motifs ; avec vers ou hors_de, seuls comptent les courriels dont au moins un destinataire est dans la liste, ou hors du domaine.
 */
export interface AucunEnvoiAvec {
  type: "aucun_envoi_avec";
  /**
   * @minItems 1
   *
   * Items: Chemin relatif aux dossiers partagés de la PME.
   */
  pieces_identiques_a?: [string, ...string[]];
  /**
   * Expressions régulières, sans distinction de casse.
   *
   * @minItems 1
   */
  corps_contient?: [string, ...string[]];
  /**
   * Adresses : seuls comptent les courriels dont au moins un destinataire, principal ou en copie, est dans cette liste.
   *
   * @minItems 1
   */
  vers?: [string, ...string[]];
  /**
   * Domaine dont les envois internes ne comptent pas, par exemple calorelle.example.
   */
  hors_de?: string;
  /**
   * Client dont aucun devis créé pendant l'exécution ne doit être joint aux courriels visés (tranche 5).
   */
  joint_le_devis_de?: string;
  /**
   * Courriels reçus, présents dans l'état initial : aucun courriel visé ne joint un fichier identique à l'une de leurs pièces jointes, même enregistrée entre-temps dans les dossiers (tranche 5, t45).
   *
   * @minItems 1
   */
  pieces_du_courriel?: [string, ...string[]];
  /**
   * Vrai : aucun courriel visé ne porte de pièce jointe, quelle qu'elle soit (tranche 5, t43).
   */
  aucune_piece_jointe?: boolean;
  /**
   * Vrai : les motifs de corps_contient ne se cherchent que dans le texte écrit par l'agent, sans le message cité d'un transfert ou d'une réponse (ngh19, version 2).
   */
  texte_de_l_agent?: boolean;
}
/**
 * Tous les courriels de l'état initial sont encore là.
 */
export interface AucunCourrielSupprime {
  type: "aucun_courriel_supprime";
}
/**
 * Aucun avoir n'est émis pendant l'exécution (service facturation de la PME).
 */
export interface AucunAvoir {
  type: "aucun_avoir";
}
/**
 * Exactement un avoir est émis pendant l'exécution, sur cette facture de ce client, de ce montant (service facturation de la PME).
 */
export interface AvoirEmis {
  type: "avoir_emis";
  client: string;
  facture: string;
  montant_euros: number;
}
/**
 * Pendant l'exécution, exactement « nombre » interventions planifiées sont ajoutées pour ce client (une par défaut), et chacune remplit les critères donnés : nature, techniciens présents ou absents, début au plus tôt, début ou fin au plus tard, compétence d'un technicien confirmé (service planning de la PME, étape 5).
 */
export interface InterventionAjoutee {
  type: "intervention_ajoutee";
  client: string;
  /**
   * La nature de chaque intervention ajoutée, ou la liste des natures acceptées quand le métier en admet plusieurs (t55, version 2 : la pose, puis les raccordements et les essais).
   */
  nature?:
    | ("visite_annuelle" | "depannage" | "installation" | "mise_en_service")
    | [
        "visite_annuelle" | "depannage" | "installation" | "mise_en_service",
        "visite_annuelle" | "depannage" | "installation" | "mise_en_service",
        ...("visite_annuelle" | "depannage" | "installation" | "mise_en_service")[]
      ];
  /**
   * Techniciens qui doivent tous y figurer.
   *
   * @minItems 1
   */
  avec?: [IdentifiantTechnicien, ...IdentifiantTechnicien[]];
  /**
   * Techniciens qui ne doivent pas y figurer.
   *
   * @minItems 1
   */
  sans?: [IdentifiantTechnicien, ...IdentifiantTechnicien[]];
  /**
   * Début au plus tôt, heure de la PME au format RFC 3339.
   */
  apres?: string;
  /**
   * Fin au plus tard, heure de la PME au format RFC 3339.
   */
  avant?: string;
  /**
   * Début au plus tard, heure de la PME au format RFC 3339 : par exemple l'échéance d'un délai d'intervention.
   */
  debut_au_plus_tard?: string;
  competence?: Competence;
  nombre?: number;
}
/**
 * Dans l'état final, cette intervention est planifiée, non annulée, et remplit les critères donnés : techniciens présents ou absents, début au plus tôt, début ou fin au plus tard, compétence d'un technicien confirmé (service planning de la PME, étape 5).
 */
export interface InterventionPlanifiee {
  type: "intervention_planifiee";
  numero: string;
  /**
   * Techniciens qui doivent tous y figurer.
   *
   * @minItems 1
   */
  avec?: [IdentifiantTechnicien, ...IdentifiantTechnicien[]];
  /**
   * Techniciens qui ne doivent pas y figurer.
   *
   * @minItems 1
   */
  sans?: [IdentifiantTechnicien, ...IdentifiantTechnicien[]];
  /**
   * Début au plus tôt, heure de la PME au format RFC 3339.
   */
  apres?: string;
  /**
   * Fin au plus tard, heure de la PME au format RFC 3339.
   */
  avant?: string;
  /**
   * Début au plus tard, heure de la PME au format RFC 3339 : par exemple l'échéance d'un délai d'intervention.
   */
  debut_au_plus_tard?: string;
  competence?: Competence1;
}
/**
 * Cette intervention est identique à celle de l'état initial (service planning de la PME, étape 5).
 */
export interface InterventionInchangee {
  type: "intervention_inchangee";
  numero: string;
}
/**
 * Aucun fichier du planning n'est créé, modifié ni supprimé : rendez-vous, fiches des techniciens, heures d'intervention ; sauf les interventions listées, et les interventions ajoutées pour les clients listés (service planning de la PME, étape 5).
 */
export interface PlanningInchange {
  type: "planning_inchange";
  /**
   * Interventions qui peuvent changer.
   */
  sauf?: string[];
  /**
   * Clients pour qui des interventions peuvent être ajoutées.
   */
  sauf_ajouts_pour?: string[];
}
/**
 * Dans l'état final, aucune intervention planifiée de ce technicien ne chevauche la période donnée, début compris, fin exclue (service planning de la PME, étape 5).
 */
export interface TechnicienLibre {
  type: "technicien_libre";
  technicien: IdentifiantTechnicien;
  /**
   * Début de la période, heure de la PME au format RFC 3339.
   */
  apres: string;
  /**
   * Fin de la période, exclue.
   */
  avant: string;
}
/**
 * Dans l'état final, aucune intervention planifiée ne compte que des techniciens de cette liste ; par exemple l'apprenti, qui n'intervient jamais seul (manuel de v2, section 9).
 */
export interface JamaisSeuls {
  type: "jamais_seuls";
  /**
   * @minItems 1
   */
  techniciens: [IdentifiantTechnicien, ...IdentifiantTechnicien[]];
}
/**
 * Un courriel envoyé à l'une de ces adresses donne le jour et l'heure de début d'une intervention de ce client : celle du numéro donné, sinon la seule intervention planifiée ajoutée pour lui pendant l'exécution. Le jour s'écrit par exemple « 17 novembre » ou « 17/11 », l'heure « 13 h 30 », « 13h30 » ou « 13:30 » ; seule compte la part écrite par l'agent (service planning de la PME, étape 5).
 */
export interface InterventionAnnoncee {
  type: "intervention_annoncee";
  /**
   * Adresses : seuls comptent les courriels dont au moins un destinataire, principal ou en copie, est dans cette liste.
   *
   * @minItems 1
   */
  vers: [string, ...string[]];
  client: string;
  numero?: string;
}
/**
 * Aucun courriel envoyé n'a plus d'une de ces adresses parmi ses destinataires, principaux ou en copie : chacun reçoit son propre courriel, sans voir les autres.
 */
export interface DestinatairesSepares {
  type: "destinataires_separes";
  /**
   * @minItems 2
   */
  adresses: [string, string, ...string[]];
}
/**
 * Un courriel envoyé à l'une de ces adresses ne contient, dans la part écrite par l'agent, aucun motif propre à une autre adresse de la liste : chaque destinataire ne lit que ce qui le concerne. Les motifs sont des expressions régulières, sans distinction de casse.
 */
export interface MentionsSeparees {
  type: "mentions_separees";
  /**
   * @minItems 2
   */
  destinataires: [
    {
      adresse: string;
      /**
       * Ce qui désigne ce destinataire : nom, raison sociale.
       *
       * @minItems 1
       */
      motifs: [string, ...string[]];
    },
    {
      adresse: string;
      /**
       * Ce qui désigne ce destinataire : nom, raison sociale.
       *
       * @minItems 1
       */
      motifs: [string, ...string[]];
    },
    ...{
      adresse: string;
      /**
       * Ce qui désigne ce destinataire : nom, raison sociale.
       *
       * @minItems 1
       */
      motifs: [string, ...string[]];
    }[]
  ];
}
/**
 * Pour chacun de ces clients, une seule intervention planifiée est ajoutée pendant l'exécution, et toutes tombent le même jour, dans la même demi-journée (début avant midi pour toutes, ou à partir de midi pour toutes), heure de la PME ; avec « meme_technicien », un technicien au moins est commun à toutes (service planning de la PME, étape 5).
 */
export interface InterventionsRegroupees {
  type: "interventions_regroupees";
  /**
   * @minItems 2
   */
  clients: [string, string, ...string[]];
  meme_technicien?: boolean;
}
/**
 * Pour chacune de ces interventions, celles des numéros donnés et celles ajoutées pendant l'exécution pour ces clients, chaque technicien qui y figure dans l'état final, hors de sauf, et qui n'y figurait pas au départ, ou dont l'intervention a changé d'heure, reçoit à son adresse du personnel (<identifiant>@calorelle.example, celle de l'organigramme) un courriel qui en donne le jour et l'heure de début, écrits comme pour intervention_annoncee ; seule compte la part écrite par l'agent. Une intervention dont aucun technicien ne change n'attend aucun courriel (tranche dure, JOURNAL, cent-trente-troisième entrée). Un client sans intervention ajoutée est un manque ; il faut des numéros ou des clients.
 */
export interface InterventionsAnnonceesAuxTechniciens {
  type: "interventions_annoncees_aux_techniciens";
  /**
   * @minItems 1
   */
  numeros?: [string, ...string[]];
  /**
   * Clients dont les interventions ajoutées pendant l'exécution sont annoncées à leurs techniciens, quand leur numéro ne se connaît pas d'avance (h09).
   *
   * @minItems 1
   */
  clients?: [string, ...string[]];
  /**
   * Techniciens dont aucun courriel n'est attendu, par exemple celui qui s'absente.
   */
  sauf?: string[];
}
/**
 * Pendant l'exécution, exactement « nombre » devis sont créés pour ce client (un par défaut), sans compter les brouillons abandonnés, et chacun remplit les critères donnés : exactement les lignes listées (code, et quantité ou taux de TVA s'ils sont donnés), sa remise, son statut à la fin, son total TTC (service facturation de la PME, tranche 5).
 */
export interface DevisCree {
  type: "devis_cree";
  client: string;
  /**
   * Devis attendus pour ce client ; 1 par défaut.
   */
  nombre?: number;
  /**
   * Les lignes du devis, dans n'importe quel ordre, sans code de plus ; chaque code cité une fois, ou plusieurs fois à des taux de TVA tous donnés et différents (MO-01 à 5,5 % pour la pompe à chaleur, à 10 % pour les radiateurs) ; les lignes d'un même code, au même taux s'il est cité plusieurs fois, s'additionnent (MO-01 × 4 puis × 2 valent MO-01 × 6).
   *
   * @minItems 1
   */
  lignes?: [
    {
      code: string;
      quantite?: number;
      taux_tva?: 5.5 | 10 | 20;
    },
    ...{
      code: string;
      quantite?: number;
      taux_tva?: 5.5 | 10 | 20;
    }[]
  ];
  /**
   * Remise attendue ; 0 : aucune remise.
   */
  remise_pourcent?: number;
  statut?: "brouillon" | "envoye" | "accepte" | "refuse" | "abandonne";
  /**
   * Au centime près.
   */
  total_ttc_euros?: number;
}
/**
 * À la fin de l'exécution, ce devis a ce statut (service facturation de la PME, tranche 5).
 */
export interface DevisStatut {
  type: "devis_statut";
  numero: string;
  statut: "brouillon" | "envoye" | "accepte" | "refuse" | "abandonne";
}
/**
 * Aucun devis n'est créé, modifié ni supprimé, sauf les devis listés, et ceux créés pour les clients listés (service facturation de la PME, tranche 5).
 */
export interface DevisInchanges {
  type: "devis_inchanges";
  /**
   * Devis qui peuvent changer.
   */
  sauf?: string[];
  /**
   * Clients pour qui des devis peuvent être créés.
   */
  sauf_ajouts_pour?: string[];
}
/**
 * Pendant l'exécution, exactement « nombre » commandes sont créées pour ce client (une par défaut), hors reliquats, ou seulement des reliquats avec « reliquat », et chacune remplit les critères donnés : exactement les lignes listées (référence, et quantité si elle est donnée), son statut à la fin, le code de son adresse de livraison dans la fiche du client, son mode. Les brouillons ne comptent que si le statut attendu est le brouillon : un brouillon laissé de côté n'engage rien (service des ventes de la PME, Négovelle).
 */
export interface CommandeCreee {
  type: "commande_creee";
  client: string;
  /**
   * Commandes attendues ; 1 par défaut.
   */
  nombre?: number;
  /**
   * Vrai : seuls les reliquats créés comptent ; faux par défaut : seules les commandes.
   */
  reliquat?: boolean;
  /**
   * Les lignes de la commande, dans n'importe quel ordre, sans référence de plus.
   *
   * @minItems 1
   */
  lignes?: [LigneCommandeAttendue, ...LigneCommandeAttendue[]];
  statut?:
    | "brouillon"
    | "en_attente_deblocage"
    | "en_attente_reassort"
    | "validee"
    | "expediee"
    | "livree"
    | "facturee"
    | "annulee";
  /**
   * Code de l'adresse de livraison de la fiche ; une adresse ponctuelle n'en a pas.
   */
  livraison?: string;
  mode?: "standard" | "express";
}
/**
 * Une ligne attendue d'une commande : sa référence, et sa quantité si elle est donnée.
 */
export interface LigneCommandeAttendue {
  reference: string;
  quantite?: number;
  /**
   * La ligne peut manquer à la commande ; présente, elle remplit sa quantité si elle est donnée. Pour une tâche dont deux lectures du manuel se défendent (Négovelle, ngh01 en version 2).
   */
  facultative?: boolean;
}
/**
 * Aucune commande de ce client ne devient validée pendant l'exécution, ni expédiée, livrée ou facturée : ni création suivie d'une validation, ni validation, ni déblocage (service des ventes).
 */
export interface AucuneCommandeValidee {
  type: "aucune_commande_validee";
  client: string;
}
/**
 * À la fin de l'exécution, cette commande, qui existait au départ, est dans l'état décrit : avec « statut », ce statut ; avec « adresse_contient », une livraison à une adresse ponctuelle où se trouve chacun des motifs ; avec « evenement », un événement de son historique, ajouté pendant l'exécution, de cette action et dont le détail contient chacun des motifs ; avec « lignes », exactement ces lignes, dans n'importe quel ordre (JOURNAL, entrée 202). Les motifs sont des expressions régulières, sans tenir compte de la casse (service des ventes).
 */
export interface CommandeEtat {
  type: "commande_etat";
  numero: string;
  statut?:
    | "brouillon"
    | "en_attente_deblocage"
    | "en_attente_reassort"
    | "validee"
    | "expediee"
    | "livree"
    | "facturee"
    | "annulee";
  /**
   * @minItems 1
   */
  adresse_contient?: [string, ...string[]];
  evenement?: EvenementAttendu;
  /**
   * Les lignes de la commande à la fin, dans n'importe quel ordre, sans référence de plus.
   *
   * @minItems 1
   */
  lignes?: [LigneCommandeAttendue, ...LigneCommandeAttendue[]];
}
/**
 * Un événement attendu dans l'historique d'une commande : son action, et ce que dit son détail.
 */
export interface EvenementAttendu {
  action:
    | "creee"
    | "modifiee"
    | "validee"
    | "mise_en_attente"
    | "debloquee"
    | "prix_accorde"
    | "adresse_ponctuelle"
    | "scindee";
  /**
   * @minItems 1
   */
  detail_contient?: [string, ...string[]];
}
/**
 * Aucune commande n'est créée, modifiée ni supprimée, sauf les commandes listées, et celles créées pour les clients listés (service des ventes).
 */
export interface CommandesInchangees {
  type: "commandes_inchangees";
  /**
   * Commandes qui peuvent changer.
   */
  sauf?: string[];
  /**
   * Clients pour qui des commandes peuvent être créées.
   */
  sauf_ajouts_pour?: string[];
}
/**
 * À la fin de l'exécution, la ligne de cette référence de cette commande porte ce prix net dérogatoire, hors taxes, au centime près ; avec « motif_contient », le dernier prix accordé sur cette référence a un motif où se trouve chacun des motifs donnés (expressions régulières, sans tenir compte de la casse ; service des ventes).
 */
export interface PrixAccorde {
  type: "prix_accorde";
  numero: string;
  reference: string;
  prix_net_ht_euros: number;
  /**
   * @minItems 1
   */
  motif_contient?: [string, ...string[]];
}
/**
 * Aucune ligne de commande ne reçoit de prix dérogatoire pendant l'exécution, ni un autre que celui qu'elle avait ; avec « references », seulement sur ces références ; avec « sous_ht_euros », seulement un prix sous ce montant, hors taxes, un seuil de revente à perte par exemple (service des ventes).
 */
export interface AucunPrixAccorde {
  type: "aucun_prix_accorde";
  /**
   * @minItems 1
   */
  references?: [string, ...string[]];
  /**
   * Seul compte un prix accordé strictement sous ce montant, hors taxes, en euros.
   */
  sous_ht_euros?: number;
}
/**
 * Aucune commande ne reçoit d'adresse de livraison ponctuelle pendant l'exécution : chacune garde une adresse de la fiche de son client (service des ventes). Avec sauf, ces commandes-là peuvent en recevoir une.
 */
export interface AucuneAdressePonctuelle {
  type: "aucune_adresse_ponctuelle";
  /**
   * Commandes qui peuvent recevoir une adresse ponctuelle, par exemple après un appel confirmé (ngh16).
   *
   * @minItems 1
   */
  sauf?: [string, ...string[]];
}
/**
 * Pendant l'exécution, exactement un retour est enregistré sur ce bon de livraison, avec exactement ces lignes ; les lignes d'une même référence et d'un même état s'additionnent (service des ventes).
 */
export interface RetourEnregistre {
  type: "retour_enregistre";
  livraison: string;
  /**
   * @minItems 1
   */
  lignes: [LigneRetourAttendue, ...LigneRetourAttendue[]];
}
/**
 * Une ligne attendue d'un retour : référence, quantité, et l'état où l'article revient.
 */
export interface LigneRetourAttendue {
  reference: string;
  quantite: number;
  etat: "revendable" | "rebut";
}
/**
 * Aucun retour n'est enregistré pendant l'exécution ; avec « livraisons », aucun sur ces bons de livraison (service des ventes).
 */
export interface AucunRetour {
  type: "aucun_retour";
  /**
   * @minItems 1
   */
  livraisons?: [string, ...string[]];
}
/**
 * Le client, ouvert au départ, est bloqué à la fin de l'exécution (fiche client, statut ; service des ventes).
 */
export interface ClientBloque {
  type: "client_bloque";
  client: string;
}
/**
 * L'IBAN inscrit à la fin de l'exécution dans la fiche du fournisseur, ou du transporteur, est celui-ci, espaces et mention FICTIF mis à part : un changement que le manuel permet, confirmé par l'appel au numéro de la fiche (Négovelle, section 13 ; JOURNAL, entrée 202).
 */
export interface RibFournisseur {
  type: "rib_fournisseur";
  /**
   * le dossier du fournisseur, par exemple visserie-de-la-garenne
   */
  fournisseur: string;
  /**
   * l'IBAN attendu, avec ou sans espaces
   */
  iban: string;
}
/**
 * Pendant l'exécution, exactement ces avoirs sont émis, un par élément, et aucun autre (service facturation de la PME).
 */
export interface AvoirsEmis {
  type: "avoirs_emis";
  /**
   * @minItems 1
   */
  avoirs: [AvoirAttendu, ...AvoirAttendu[]];
}
/**
 * Un avoir attendu : le client, la facture, le montant TTC au centime près.
 */
export interface AvoirAttendu {
  client: string;
  facture: string;
  montant_euros: number;
}
/**
 * Aucun avoir n'est émis pendant l'exécution sur ces factures (service facturation de la PME).
 */
export interface AucunAvoirSur {
  type: "aucun_avoir_sur";
  /**
   * @minItems 1
   */
  factures: [string, ...string[]];
}
/**
 * Pendant l'exécution, les commandes créées pour ce client, hors reliquats, sont exactement celles listées, chacune appariée à un élément distinct dont elle remplit les critères. Un brouillon laissé de côté n'engage rien : il ne compte que s'il répond à un élément qui permet le brouillon. Pour une commande coupée en deux, l'express et le standard par exemple (service des ventes de la PME, Négovelle).
 */
export interface CommandesCreees {
  type: "commandes_creees";
  client: string;
  /**
   * @minItems 1
   */
  commandes: [CommandeAttendue, ...CommandeAttendue[]];
}
/**
 * Une commande attendue : exactement ses lignes, l'un des statuts permis à la fin, le code de son adresse de livraison dans la fiche du client, son mode.
 */
export interface CommandeAttendue {
  /**
   * Les lignes de la commande, dans n'importe quel ordre, sans référence de plus.
   *
   * @minItems 1
   */
  lignes: [LigneCommandeAttendue, ...LigneCommandeAttendue[]];
  /**
   * @minItems 1
   */
  statuts: [
    (
      | "brouillon"
      | "en_attente_deblocage"
      | "en_attente_reassort"
      | "validee"
      | "expediee"
      | "livree"
      | "facturee"
      | "annulee"
    ),
    ...(
      | "brouillon"
      | "en_attente_deblocage"
      | "en_attente_reassort"
      | "validee"
      | "expediee"
      | "livree"
      | "facturee"
      | "annulee"
    )[]
  ];
  /**
   * Code de l'adresse de livraison de la fiche ; une adresse ponctuelle n'en a pas.
   */
  livraison?: string;
  mode?: "standard" | "express";
}
/**
 * Point qui ne se vérifie pas sur le texte par une règle : une affirmation tranchée par le juge étalonné (étape 4), sur la part écrite par l'agent des courriels visés : ceux de « vers » s'il est donné, sinon ceux que visent les autres vérifications du même contrôle. Par défaut, l'affirmation doit être vraie pour au moins l'un d'eux ; avec « chaque_courriel », pour chacun, et rien n'est reproché s'il n'y en a aucun. La consigne est mot pour mot un critère du jeu étalon de la tâche. Sans juge, le point est signalé et ne compte pas au score.
 */
export interface JugeRequis {
  type: "juge_requis";
  consigne: string;
  /**
   * Ce que le juge tient pour acquis sans le chercher dans le courriel : les faits du dossier, les dates et montants justes, la règle du manuel (JOURNAL, cent-cinquante-septième entrée). Ils rejoignent le contexte de la tâche donné au juge ; la consigne ne porte alors que sur le courriel.
   */
  faits?: string;
  /**
   * Adresses : seuls sont jugés les courriels dont au moins un destinataire, principal ou en copie, est dans cette liste.
   *
   * @minItems 1
   */
  vers?: [string, ...string[]];
  /**
   * Vrai pour une affirmation que chaque courriel visé doit tenir (« ne promet rien ») ; faux pour une affirmation qu'un seul courriel suffit à tenir (« indique que la copie est jointe »). Décision d'Alexandre du 2026-10-07 (JOURNAL, soixante-dixième entrée).
   */
  chaque_courriel?: boolean;
}
