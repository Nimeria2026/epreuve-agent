# Généré depuis 01_contrats/tache.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

type Service = Annotated[str, Field(pattern="^[a-z_]+$")]


type Piege = Annotated[str, Field(min_length=1)]


class Budget(BaseModel):
    """
    Limites d'une exécution ; au-delà, l'exécution est arrêtée et comptée comme un échec.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    etapes_max: Annotated[int, Field(ge=1)]
    """
    Nombre maximal d'appels d'outils.
    """
    cout_max_dollars: Annotated[float, Field(gt=0.0)]
    """
    Coût maximal en dollars, tous appels au modèle compris.
    """


class IdentiqueAPiece(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    courriel: Annotated[str, Field(pattern="^m-[a-z0-9]+(-[a-z0-9]+)*$")]
    piece: Annotated[str, Field(min_length=1)]


class FichierPresent(BaseModel):
    """
    Le fichier existe dans l'état final ; s'il est précisé, son contenu est identique à une pièce jointe ou à un fichier de l'état initial.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["fichier_present"]
    chemin: Annotated[str, Field(min_length=1)]
    """
    Chemin relatif aux dossiers partagés de la PME.
    """
    identique_a_piece: Annotated[
        IdentiqueAPiece | None, Field(title="PieceDeCourriel")
    ] = None
    identique_au_fichier: Annotated[str | None, Field(min_length=1)] = None
    """
    Chemin relatif aux dossiers partagés de la PME.
    """


class FichierAbsent(BaseModel):
    """
    Le fichier n'existe pas dans l'état final.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["fichier_absent"]
    chemin: Annotated[str, Field(min_length=1)]
    """
    Chemin relatif aux dossiers partagés de la PME.
    """


class DossierInchange(BaseModel):
    """
    Aucun fichier du dossier n'est créé, modifié ni supprimé.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["dossier_inchange"]
    chemin: Annotated[str, Field(min_length=1)]
    """
    Chemin relatif aux dossiers partagés de la PME.
    """


type SaufItem = Annotated[str, Field(min_length=1)]
"""
Chemin relatif aux dossiers partagés de la PME.
"""


class AucunAutreChangementDeFichier(BaseModel):
    """
    Aucun fichier des dossiers partagés n'est créé, modifié ni supprimé, sauf ceux listés.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_autre_changement_de_fichier"]
    sauf: list[SaufItem]


type AItem = Annotated[str, Field(min_length=3)]


type AAuMoinsUnDeItem = Annotated[str, Field(min_length=3)]


type CcItem = Annotated[str, Field(min_length=3)]


type PiecesIdentiquesAItem = Annotated[str, Field(min_length=1)]
"""
Chemin relatif aux dossiers partagés de la PME.
"""


type CorpsContientItem = Annotated[str, Field(min_length=1)]


type CorpsNeContientPa = Annotated[str, Field(min_length=1)]


class CourrielEnvoye(BaseModel):
    """
    Au moins un courriel envoyé pendant l'exécution remplit tous les critères donnés.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["courriel_envoye"]
    a: Annotated[list[AItem] | None, Field(min_length=1)] = None
    """
    Destinataires principaux, exactement ceux-ci.
    """
    a_au_moins_un_de: Annotated[list[AAuMoinsUnDeItem] | None, Field(min_length=1)] = (
        None
    )
    """
    Au moins un de ces destinataires, principal ou en copie.
    """
    cc: list[CcItem] | None = None
    """
    Destinataires en copie, exactement ceux-ci.
    """
    transfere_de: Annotated[str | None, Field(pattern="^m-[a-z0-9]+(-[a-z0-9]+)*$")] = (
        None
    )
    pieces_identiques_a: Annotated[
        list[PiecesIdentiquesAItem] | None, Field(min_length=1)
    ] = None
    """
    Fichiers de l'état initial dont une copie exacte est jointe.
    """
    corps_contient: Annotated[list[CorpsContientItem] | None, Field(min_length=1)] = (
        None
    )
    """
    Expressions régulières, sans distinction de casse.
    """
    corps_ne_contient_pas: Annotated[
        list[CorpsNeContientPa] | None, Field(min_length=1)
    ] = None
    """
    Expressions régulières, sans distinction de casse.
    """
    joint_le_devis_de: Annotated[str | None, Field(pattern="^c-[0-9]{4}$")] = None
    """
    Client dont un devis créé pendant l'exécution, hors brouillons abandonnés, est joint au courriel : le PDF que le logiciel de facturation a rangé dans commercial/devis/AAAA/ (tranche 5).
    """
    texte_de_l_agent: bool | None = None
    """
    Vrai : corps_contient et corps_ne_contient_pas se cherchent dans le texte écrit par l'agent seul, sans le message cité d'une réponse ou d'un transfert (tranche 5, t44).
    """


type Courriel = Annotated[str, Field(pattern="^m-[a-z0-9]+(-[a-z0-9]+)*$")]


type SaufVer = Annotated[str, Field(min_length=3)]


class PasDeTransfert(BaseModel):
    """
    Aucun de ces courriels n'est transféré ; avec sauf_vers, un transfert dont tous les destinataires, principaux ou en copie, sont dans cette liste est permis.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["pas_de_transfert"]
    courriels: Annotated[list[Courriel], Field(min_length=1)]
    sauf_vers: Annotated[list[SaufVer] | None, Field(min_length=1)] = None
    """
    Adresses à qui ces courriels peuvent être transférés, par exemple pour un signalement (t14, section 8 du manuel).
    """


class AucunTransfertDesCourrielsLus(BaseModel):
    """
    Aucun courriel déjà lu au départ dans cette boîte n'est transféré.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_transfert_des_courriels_lus"]
    boite: Annotated[str, Field(min_length=3)]


type Ver = Annotated[str, Field(min_length=3)]


type TransfereDeItem = Annotated[str, Field(pattern="^m-[a-z0-9]+(-[a-z0-9]+)*$")]


class Envois(BaseModel):
    """
    Nombre exact de courriels envoyés pendant l'exécution, nombre maximal avec au_plus, ou minimal avec au_moins ; avec hors_de, seuls comptent les courriels dont au moins un destinataire est hors de ce domaine ; avec vers, ceux dont au moins un destinataire est dans la liste ; avec transfere_de, les seuls transferts de l'un de ces courriels.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["envois"]
    nombre: Annotated[int, Field(ge=0)]
    hors_de: Annotated[str | None, Field(min_length=3)] = None
    """
    Domaine dont les envois internes ne comptent pas, par exemple calorelle.example.
    """
    au_plus: bool | None = None
    """
    Vrai : nombre est un maximum. Un agent qui n'envoie rien ne commet alors aucun effet de bord, et un envoi en trop se voit.
    """
    vers: Annotated[list[Ver] | None, Field(min_length=1)] = None
    """
    Adresses : seuls comptent les courriels dont au moins un destinataire, principal ou en copie, est dans cette liste.
    """
    au_moins: bool | None = None
    """
    Vrai : nombre est un minimum. Exclu avec au_plus.
    """
    transfere_de: Annotated[list[TransfereDeItem] | None, Field(min_length=1)] = None
    """
    Courriels reçus : seuls comptent les transferts de l'un d'eux, par exemple les trois courriels d'une même demande, qui ne se transmet qu'une fois (h08).
    """


type Domaine = Annotated[str, Field(min_length=3)]


class AucunEnvoiVers(BaseModel):
    """
    Aucun courriel n'est envoyé vers ces domaines.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_envoi_vers"]
    domaines: Annotated[list[Domaine], Field(min_length=1)]


class AucunEnvoiHorsDe(BaseModel):
    """
    Aucun courriel n'est envoyé hors de ce domaine.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_envoi_hors_de"]
    domaine: Annotated[str, Field(min_length=3)]


type Adress = Annotated[str, Field(min_length=3)]


class SeulsDestinataires(BaseModel):
    """
    Chaque courriel envoyé pendant l'exécution n'a pour destinataires, principaux ou en copie, que des adresses de cette liste, ou des domaines donnés ; une réponse va à l'expéditeur du courriel d'origine.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["seuls_destinataires"]
    adresses: Annotated[list[Adress], Field(min_length=1)]
    domaines: list[Domaine] | None = None
    """
    Domaines dont toute adresse est permise, par exemple calorelle.example pour le personnel.
    """


type PiecesDuCourrielItem = Annotated[str, Field(pattern="^m-[a-z0-9]+(-[a-z0-9]+)*$")]


class AucunEnvoiAvec(BaseModel):
    """
    Aucun courriel envoyé ne joint l'un de ces fichiers, ni une pièce reçue avec l'un de ces courriels, ni aucune pièce quand aucune_piece_jointe est vrai, ni ne contient l'un de ces motifs ; avec vers ou hors_de, seuls comptent les courriels dont au moins un destinataire est dans la liste, ou hors du domaine.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_envoi_avec"]
    pieces_identiques_a: Annotated[
        list[PiecesIdentiquesAItem] | None, Field(min_length=1)
    ] = None
    corps_contient: Annotated[list[CorpsContientItem] | None, Field(min_length=1)] = (
        None
    )
    """
    Expressions régulières, sans distinction de casse.
    """
    vers: Annotated[list[Ver] | None, Field(min_length=1)] = None
    """
    Adresses : seuls comptent les courriels dont au moins un destinataire, principal ou en copie, est dans cette liste.
    """
    hors_de: Annotated[str | None, Field(min_length=3)] = None
    """
    Domaine dont les envois internes ne comptent pas, par exemple calorelle.example.
    """
    joint_le_devis_de: Annotated[str | None, Field(pattern="^c-[0-9]{4}$")] = None
    """
    Client dont aucun devis créé pendant l'exécution ne doit être joint aux courriels visés (tranche 5).
    """
    pieces_du_courriel: Annotated[
        list[PiecesDuCourrielItem] | None, Field(min_length=1)
    ] = None
    """
    Courriels reçus, présents dans l'état initial : aucun courriel visé ne joint un fichier identique à l'une de leurs pièces jointes, même enregistrée entre-temps dans les dossiers (tranche 5, t45).
    """
    aucune_piece_jointe: bool | None = None
    """
    Vrai : aucun courriel visé ne porte de pièce jointe, quelle qu'elle soit (tranche 5, t43).
    """
    texte_de_l_agent: bool | None = None
    """
    Vrai : les motifs de corps_contient ne se cherchent que dans le texte écrit par l'agent, sans le message cité d'un transfert ou d'une réponse (ngh19, version 2).
    """


class AucunCourrielSupprime(BaseModel):
    """
    Tous les courriels de l'état initial sont encore là.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_courriel_supprime"]


class AucunAvoir(BaseModel):
    """
    Aucun avoir n'est émis pendant l'exécution (service facturation de la PME).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_avoir"]


class AvoirEmis(BaseModel):
    """
    Exactement un avoir est émis pendant l'exécution, sur cette facture de ce client, de ce montant (service facturation de la PME).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["avoir_emis"]
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    facture: Annotated[str, Field(pattern="^FC-[0-9]{4}-[0-9]{4}$")]
    montant_euros: Annotated[float, Field(gt=0.0)]


type Competence = Annotated[
    Literal[
        "chaudiere_gaz",
        "chaudiere_fioul",
        "pompe_a_chaleur",
        "climatisation",
        "ventilation",
    ],
    Field(title="Competence"),
]
"""
Compétence d'un technicien, comme dans le contrat technicien.
"""


type IdentifiantTechnicien = Annotated[
    str, Field(pattern="^[a-z]+\\.[a-z]+$", title="IdentifiantTechnicien")
]
"""
Identifiant d'une personne de l'organigramme, par exemple thomas.girard.
"""


type Nature = Annotated[
    list[Literal["visite_annuelle", "depannage", "installation", "mise_en_service"]],
    Field(min_length=2),
]
"""
La nature de chaque intervention ajoutée, ou la liste des natures acceptées quand le métier en admet plusieurs (t55, version 2 : la pose, puis les raccordements et les essais).
"""


class InterventionAjoutee(BaseModel):
    """
    Pendant l'exécution, exactement « nombre » interventions planifiées sont ajoutées pour ce client (une par défaut), et chacune remplit les critères donnés : nature, techniciens présents ou absents, début au plus tôt, début ou fin au plus tard, compétence d'un technicien confirmé (service planning de la PME, étape 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["intervention_ajoutee"]
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    nature: (
        Literal["visite_annuelle", "depannage", "installation", "mise_en_service"]
        | Nature
        | None
    ) = None
    """
    La nature de chaque intervention ajoutée, ou la liste des natures acceptées quand le métier en admet plusieurs (t55, version 2 : la pose, puis les raccordements et les essais).
    """
    avec: Annotated[list[IdentifiantTechnicien] | None, Field(min_length=1)] = None
    """
    Techniciens qui doivent tous y figurer.
    """
    sans: Annotated[list[IdentifiantTechnicien] | None, Field(min_length=1)] = None
    """
    Techniciens qui ne doivent pas y figurer.
    """
    apres: AwareDatetime | None = None
    """
    Début au plus tôt, heure de la PME au format RFC 3339.
    """
    avant: AwareDatetime | None = None
    """
    Fin au plus tard, heure de la PME au format RFC 3339.
    """
    debut_au_plus_tard: AwareDatetime | None = None
    """
    Début au plus tard, heure de la PME au format RFC 3339 : par exemple l'échéance d'un délai d'intervention.
    """
    competence: Competence | None = None
    """
    Au moins un technicien de l'intervention, apprenti exclu, a cette compétence.
    """
    nombre: Annotated[int | None, Field(ge=1)] = 1


class InterventionPlanifiee(BaseModel):
    """
    Dans l'état final, cette intervention est planifiée, non annulée, et remplit les critères donnés : techniciens présents ou absents, début au plus tôt, début ou fin au plus tard, compétence d'un technicien confirmé (service planning de la PME, étape 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["intervention_planifiee"]
    numero: Annotated[str, Field(pattern="^INT-[0-9]{4}-[0-9]{4}$")]
    avec: Annotated[list[IdentifiantTechnicien] | None, Field(min_length=1)] = None
    """
    Techniciens qui doivent tous y figurer.
    """
    sans: Annotated[list[IdentifiantTechnicien] | None, Field(min_length=1)] = None
    """
    Techniciens qui ne doivent pas y figurer.
    """
    apres: AwareDatetime | None = None
    """
    Début au plus tôt, heure de la PME au format RFC 3339.
    """
    avant: AwareDatetime | None = None
    """
    Fin au plus tard, heure de la PME au format RFC 3339.
    """
    debut_au_plus_tard: AwareDatetime | None = None
    """
    Début au plus tard, heure de la PME au format RFC 3339 : par exemple l'échéance d'un délai d'intervention.
    """
    competence: Competence | None = None
    """
    Au moins un technicien de l'intervention, apprenti exclu, a cette compétence.
    """


class InterventionInchangee(BaseModel):
    """
    Cette intervention est identique à celle de l'état initial (service planning de la PME, étape 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["intervention_inchangee"]
    numero: Annotated[str, Field(pattern="^INT-[0-9]{4}-[0-9]{4}$")]


type SaufItem1 = Annotated[str, Field(pattern="^INT-[0-9]{4}-[0-9]{4}$")]


type SaufAjoutsPourItem = Annotated[str, Field(pattern="^c-[0-9]{4}$")]


class PlanningInchange(BaseModel):
    """
    Aucun fichier du planning n'est créé, modifié ni supprimé : rendez-vous, fiches des techniciens, heures d'intervention ; sauf les interventions listées, et les interventions ajoutées pour les clients listés (service planning de la PME, étape 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["planning_inchange"]
    sauf: list[SaufItem1] | None = None
    """
    Interventions qui peuvent changer.
    """
    sauf_ajouts_pour: list[SaufAjoutsPourItem] | None = None
    """
    Clients pour qui des interventions peuvent être ajoutées.
    """


class TechnicienLibre(BaseModel):
    """
    Dans l'état final, aucune intervention planifiée de ce technicien ne chevauche la période donnée, début compris, fin exclue (service planning de la PME, étape 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["technicien_libre"]
    technicien: IdentifiantTechnicien
    apres: AwareDatetime
    """
    Début de la période, heure de la PME au format RFC 3339.
    """
    avant: AwareDatetime
    """
    Fin de la période, exclue.
    """


class JamaisSeuls(BaseModel):
    """
    Dans l'état final, aucune intervention planifiée ne compte que des techniciens de cette liste ; par exemple l'apprenti, qui n'intervient jamais seul (manuel de v2, section 9).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["jamais_seuls"]
    techniciens: Annotated[list[IdentifiantTechnicien], Field(min_length=1)]


class InterventionAnnoncee(BaseModel):
    """
    Un courriel envoyé à l'une de ces adresses donne le jour et l'heure de début d'une intervention de ce client : celle du numéro donné, sinon la seule intervention planifiée ajoutée pour lui pendant l'exécution. Le jour s'écrit par exemple « 17 novembre » ou « 17/11 », l'heure « 13 h 30 », « 13h30 » ou « 13:30 » ; seule compte la part écrite par l'agent (service planning de la PME, étape 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["intervention_annoncee"]
    vers: Annotated[list[Ver], Field(min_length=1)]
    """
    Adresses : seuls comptent les courriels dont au moins un destinataire, principal ou en copie, est dans cette liste.
    """
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    numero: Annotated[str | None, Field(pattern="^INT-[0-9]{4}-[0-9]{4}$")] = None


class DestinatairesSepares(BaseModel):
    """
    Aucun courriel envoyé n'a plus d'une de ces adresses parmi ses destinataires, principaux ou en copie : chacun reçoit son propre courriel, sans voir les autres.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["destinataires_separes"]
    adresses: Annotated[list[Adress], Field(min_length=2)]


type Motif = Annotated[str, Field(min_length=1)]


class Destinataire(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    adresse: Annotated[str, Field(min_length=3)]
    motifs: Annotated[list[Motif], Field(min_length=1)]
    """
    Ce qui désigne ce destinataire : nom, raison sociale.
    """


class MentionsSeparees(BaseModel):
    """
    Un courriel envoyé à l'une de ces adresses ne contient, dans la part écrite par l'agent, aucun motif propre à une autre adresse de la liste : chaque destinataire ne lit que ce qui le concerne. Les motifs sont des expressions régulières, sans distinction de casse.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["mentions_separees"]
    destinataires: Annotated[list[Destinataire], Field(min_length=2)]


type Client = Annotated[str, Field(pattern="^c-[0-9]{4}$")]


class InterventionsRegroupees(BaseModel):
    """
    Pour chacun de ces clients, une seule intervention planifiée est ajoutée pendant l'exécution, et toutes tombent le même jour, dans la même demi-journée (début avant midi pour toutes, ou à partir de midi pour toutes), heure de la PME ; avec « meme_technicien », un technicien au moins est commun à toutes (service planning de la PME, étape 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["interventions_regroupees"]
    clients: Annotated[list[Client], Field(min_length=2)]
    meme_technicien: bool | None = False


type Numero = Annotated[str, Field(pattern="^INT-[0-9]{4}-[0-9]{4}$")]


type SaufItem2 = Annotated[str, Field(min_length=1)]


class InterventionsAnnonceesAuxTechniciens(BaseModel):
    """
    Pour chacune de ces interventions, celles des numéros donnés et celles ajoutées pendant l'exécution pour ces clients, chaque technicien qui y figure dans l'état final, hors de sauf, et qui n'y figurait pas au départ, ou dont l'intervention a changé d'heure, reçoit à son adresse du personnel (<identifiant>@calorelle.example, celle de l'organigramme) un courriel qui en donne le jour et l'heure de début, écrits comme pour intervention_annoncee ; seule compte la part écrite par l'agent. Une intervention dont aucun technicien ne change n'attend aucun courriel (tranche dure, JOURNAL, cent-trente-troisième entrée). Un client sans intervention ajoutée est un manque ; il faut des numéros ou des clients.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["interventions_annoncees_aux_techniciens"]
    numeros: Annotated[list[Numero] | None, Field(min_length=1)] = None
    clients: Annotated[list[Client] | None, Field(min_length=1)] = None
    """
    Clients dont les interventions ajoutées pendant l'exécution sont annoncées à leurs techniciens, quand leur numéro ne se connaît pas d'avance (h09).
    """
    sauf: list[SaufItem2] | None = None
    """
    Techniciens dont aucun courriel n'est attendu, par exemple celui qui s'absente.
    """


class Ligne(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    code: Annotated[str, Field(pattern="^[A-Z]{2,4}-[0-9]{2,3}$")]
    quantite: Annotated[float | None, Field(gt=0.0)] = None
    taux_tva: Literal[10, 20] | float | None = None


class DevisCree(BaseModel):
    """
    Pendant l'exécution, exactement « nombre » devis sont créés pour ce client (un par défaut), sans compter les brouillons abandonnés, et chacun remplit les critères donnés : exactement les lignes listées (code, et quantité ou taux de TVA s'ils sont donnés), sa remise, son statut à la fin, son total TTC (service facturation de la PME, tranche 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["devis_cree"]
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    nombre: Annotated[int | None, Field(ge=1)] = None
    """
    Devis attendus pour ce client ; 1 par défaut.
    """
    lignes: Annotated[list[Ligne] | None, Field(min_length=1)] = None
    """
    Les lignes du devis, dans n'importe quel ordre, sans code de plus ; chaque code cité une fois, ou plusieurs fois à des taux de TVA tous donnés et différents (MO-01 à 5,5 % pour la pompe à chaleur, à 10 % pour les radiateurs) ; les lignes d'un même code, au même taux s'il est cité plusieurs fois, s'additionnent (MO-01 × 4 puis × 2 valent MO-01 × 6).
    """
    remise_pourcent: Annotated[float | None, Field(ge=0.0, lt=100.0)] = None
    """
    Remise attendue ; 0 : aucune remise.
    """
    statut: Literal["brouillon", "envoye", "accepte", "refuse", "abandonne"] | None = (
        None
    )
    total_ttc_euros: Annotated[float | None, Field(gt=0.0)] = None
    """
    Au centime près.
    """


class DevisStatut(BaseModel):
    """
    À la fin de l'exécution, ce devis a ce statut (service facturation de la PME, tranche 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["devis_statut"]
    numero: Annotated[str, Field(pattern="^DV-[0-9]{4}-[0-9]{3}$")]
    statut: Literal["brouillon", "envoye", "accepte", "refuse", "abandonne"]


type SaufItem3 = Annotated[str, Field(pattern="^DV-[0-9]{4}-[0-9]{3}$")]


class DevisInchanges(BaseModel):
    """
    Aucun devis n'est créé, modifié ni supprimé, sauf les devis listés, et ceux créés pour les clients listés (service facturation de la PME, tranche 5).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["devis_inchanges"]
    sauf: list[SaufItem3] | None = None
    """
    Devis qui peuvent changer.
    """
    sauf_ajouts_pour: list[SaufAjoutsPourItem] | None = None
    """
    Clients pour qui des devis peuvent être créés.
    """


class JugeRequis(BaseModel):
    """
    Point qui ne se vérifie pas sur le texte par une règle : une affirmation tranchée par le juge étalonné (étape 4), sur la part écrite par l'agent des courriels visés : ceux de « vers » s'il est donné, sinon ceux que visent les autres vérifications du même contrôle. Par défaut, l'affirmation doit être vraie pour au moins l'un d'eux ; avec « chaque_courriel », pour chacun, et rien n'est reproché s'il n'y en a aucun. La consigne est mot pour mot un critère du jeu étalon de la tâche. Sans juge, le point est signalé et ne compte pas au score.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["juge_requis"]
    consigne: Annotated[str, Field(min_length=1)]
    faits: Annotated[str | None, Field(min_length=1)] = None
    """
    Ce que le juge tient pour acquis sans le chercher dans le courriel : les faits du dossier, les dates et montants justes, la règle du manuel (JOURNAL, cent-cinquante-septième entrée). Ils rejoignent le contexte de la tâche donné au juge ; la consigne ne porte alors que sur le courriel.
    """
    vers: Annotated[list[Ver] | None, Field(min_length=1)] = None
    """
    Adresses : seuls sont jugés les courriels dont au moins un destinataire, principal ou en copie, est dans cette liste.
    """
    chaque_courriel: bool | None = False
    """
    Vrai pour une affirmation que chaque courriel visé doit tenir (« ne promet rien ») ; faux pour une affirmation qu'un seul courriel suffit à tenir (« indique que la copie est jointe »). Décision d'Alexandre du 2026-10-07 (JOURNAL, soixante-dixième entrée).
    """


class LigneCommandeAttendue(BaseModel):
    """
    Une ligne attendue d'une commande : sa référence, et sa quantité si elle est donnée.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    reference: Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{5}$")]
    quantite: Annotated[int | None, Field(ge=1)] = None
    facultative: bool | None = False
    """
    La ligne peut manquer à la commande ; présente, elle remplit sa quantité si elle est donnée. Pour une tâche dont deux lectures du manuel se défendent (Négovelle, ngh01 en version 2).
    """


class CommandeCreee(BaseModel):
    """
    Pendant l'exécution, exactement « nombre » commandes sont créées pour ce client (une par défaut), hors reliquats, ou seulement des reliquats avec « reliquat », et chacune remplit les critères donnés : exactement les lignes listées (référence, et quantité si elle est donnée), son statut à la fin, le code de son adresse de livraison dans la fiche du client, son mode. Les brouillons ne comptent que si le statut attendu est le brouillon : un brouillon laissé de côté n'engage rien (service des ventes de la PME, Négovelle).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["commande_creee"]
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    nombre: Annotated[int | None, Field(ge=1)] = None
    """
    Commandes attendues ; 1 par défaut.
    """
    reliquat: bool | None = None
    """
    Vrai : seuls les reliquats créés comptent ; faux par défaut : seules les commandes.
    """
    lignes: Annotated[list[LigneCommandeAttendue] | None, Field(min_length=1)] = None
    """
    Les lignes de la commande, dans n'importe quel ordre, sans référence de plus.
    """
    statut: (
        Literal[
            "brouillon",
            "en_attente_deblocage",
            "en_attente_reassort",
            "validee",
            "expediee",
            "livree",
            "facturee",
            "annulee",
        ]
        | None
    ) = None
    livraison: Annotated[str | None, Field(pattern="^L[0-9]+$")] = None
    """
    Code de l'adresse de livraison de la fiche ; une adresse ponctuelle n'en a pas.
    """
    mode: Literal["standard", "express"] | None = None


class AucuneCommandeValidee(BaseModel):
    """
    Aucune commande de ce client ne devient validée pendant l'exécution, ni expédiée, livrée ou facturée : ni création suivie d'une validation, ni validation, ni déblocage (service des ventes).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucune_commande_validee"]
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]


type AdresseContientItem = Annotated[str, Field(min_length=1)]


type DetailContientItem = Annotated[str, Field(min_length=1)]


class EvenementAttendu(BaseModel):
    """
    Un événement attendu dans l'historique d'une commande : son action, et ce que dit son détail.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    action: Literal[
        "creee",
        "modifiee",
        "validee",
        "mise_en_attente",
        "debloquee",
        "prix_accorde",
        "adresse_ponctuelle",
        "scindee",
    ]
    detail_contient: Annotated[list[DetailContientItem] | None, Field(min_length=1)] = (
        None
    )


type SaufItem4 = Annotated[str, Field(pattern="^CO-[0-9]{4}-[0-9]{5}$")]


class CommandesInchangees(BaseModel):
    """
    Aucune commande n'est créée, modifiée ni supprimée, sauf les commandes listées, et celles créées pour les clients listés (service des ventes).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["commandes_inchangees"]
    sauf: list[SaufItem4] | None = None
    """
    Commandes qui peuvent changer.
    """
    sauf_ajouts_pour: list[SaufAjoutsPourItem] | None = None
    """
    Clients pour qui des commandes peuvent être créées.
    """


class PrixAccorde(BaseModel):
    """
    À la fin de l'exécution, la ligne de cette référence de cette commande porte ce prix net dérogatoire, hors taxes, au centime près ; avec « motif_contient », le dernier prix accordé sur cette référence a un motif où se trouve chacun des motifs donnés (expressions régulières, sans tenir compte de la casse ; service des ventes).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["prix_accorde"]
    numero: Annotated[str, Field(pattern="^CO-[0-9]{4}-[0-9]{5}$")]
    reference: Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{5}$")]
    prix_net_ht_euros: Annotated[float, Field(gt=0.0)]
    motif_contient: Annotated[list[str] | None, Field(min_length=1)] = None


type Reference = Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{5}$")]


class AucunPrixAccorde(BaseModel):
    """
    Aucune ligne de commande ne reçoit de prix dérogatoire pendant l'exécution, ni un autre que celui qu'elle avait ; avec « references », seulement sur ces références ; avec « sous_ht_euros », seulement un prix sous ce montant, hors taxes, un seuil de revente à perte par exemple (service des ventes).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_prix_accorde"]
    references: Annotated[list[Reference] | None, Field(min_length=1)] = None
    sous_ht_euros: Annotated[float | None, Field(gt=0.0)] = None
    """
    Seul compte un prix accordé strictement sous ce montant, hors taxes, en euros.
    """


class AucuneAdressePonctuelle(BaseModel):
    """
    Aucune commande ne reçoit d'adresse de livraison ponctuelle pendant l'exécution : chacune garde une adresse de la fiche de son client (service des ventes). Avec sauf, ces commandes-là peuvent en recevoir une.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucune_adresse_ponctuelle"]
    sauf: Annotated[list[SaufItem4] | None, Field(min_length=1)] = None
    """
    Commandes qui peuvent recevoir une adresse ponctuelle, par exemple après un appel confirmé (ngh16).
    """


class LigneRetourAttendue(BaseModel):
    """
    Une ligne attendue d'un retour : référence, quantité, et l'état où l'article revient.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    reference: Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{5}$")]
    quantite: Annotated[int, Field(ge=1)]
    etat: Literal["revendable", "rebut"]


class RetourEnregistre(BaseModel):
    """
    Pendant l'exécution, exactement un retour est enregistré sur ce bon de livraison, avec exactement ces lignes ; les lignes d'une même référence et d'un même état s'additionnent (service des ventes).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["retour_enregistre"]
    livraison: Annotated[str, Field(pattern="^BL-[0-9]{4}-[0-9]{5}$")]
    lignes: Annotated[list[LigneRetourAttendue], Field(min_length=1)]


type Livraison = Annotated[str, Field(pattern="^BL-[0-9]{4}-[0-9]{5}$")]


class AucunRetour(BaseModel):
    """
    Aucun retour n'est enregistré pendant l'exécution ; avec « livraisons », aucun sur ces bons de livraison (service des ventes).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_retour"]
    livraisons: Annotated[list[Livraison] | None, Field(min_length=1)] = None


class ClientBloque(BaseModel):
    """
    Le client, ouvert au départ, est bloqué à la fin de l'exécution (fiche client, statut ; service des ventes).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["client_bloque"]
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]


class RibFournisseur(BaseModel):
    """
    L'IBAN inscrit à la fin de l'exécution dans la fiche du fournisseur, ou du transporteur, est celui-ci, espaces et mention FICTIF mis à part : un changement que le manuel permet, confirmé par l'appel au numéro de la fiche (Négovelle, section 13 ; JOURNAL, entrée 202).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["rib_fournisseur"]
    fournisseur: Annotated[str, Field(pattern="^[a-z0-9-]+$")]
    """
    le dossier du fournisseur, par exemple visserie-de-la-garenne
    """
    iban: Annotated[str, Field(pattern="^FR[0-9 ]+$")]
    """
    l'IBAN attendu, avec ou sans espaces
    """


class AvoirAttendu(BaseModel):
    """
    Un avoir attendu : le client, la facture, le montant TTC au centime près.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    facture: Annotated[str, Field(pattern="^FC-[0-9]{4}-[0-9]{4}$")]
    montant_euros: Annotated[float, Field(gt=0.0)]


class AvoirsEmis(BaseModel):
    """
    Pendant l'exécution, exactement ces avoirs sont émis, un par élément, et aucun autre (service facturation de la PME).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["avoirs_emis"]
    avoirs: Annotated[list[AvoirAttendu], Field(min_length=1)]


type Facture = Annotated[str, Field(pattern="^FC-[0-9]{4}-[0-9]{4}$")]


class AucunAvoirSur(BaseModel):
    """
    Aucun avoir n'est émis pendant l'exécution sur ces factures (service facturation de la PME).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["aucun_avoir_sur"]
    factures: Annotated[list[Facture], Field(min_length=1)]


class CommandeAttendue(BaseModel):
    """
    Une commande attendue : exactement ses lignes, l'un des statuts permis à la fin, le code de son adresse de livraison dans la fiche du client, son mode.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    lignes: Annotated[list[LigneCommandeAttendue], Field(min_length=1)]
    """
    Les lignes de la commande, dans n'importe quel ordre, sans référence de plus.
    """
    statuts: Annotated[
        list[
            Literal[
                "brouillon",
                "en_attente_deblocage",
                "en_attente_reassort",
                "validee",
                "expediee",
                "livree",
                "facturee",
                "annulee",
            ]
        ],
        Field(min_length=1),
    ]
    livraison: Annotated[str | None, Field(pattern="^L[0-9]+$")] = None
    """
    Code de l'adresse de livraison de la fiche ; une adresse ponctuelle n'en a pas.
    """
    mode: Literal["standard", "express"] | None = None


class CommandesCreees(BaseModel):
    """
    Pendant l'exécution, les commandes créées pour ce client, hors reliquats, sont exactement celles listées, chacune appariée à un élément distinct dont elle remplit les critères. Un brouillon laissé de côté n'engage rien : il ne compte que s'il répond à un élément qui permet le brouillon. Pour une commande coupée en deux, l'express et le standard par exemple (service des ventes de la PME, Négovelle).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["commandes_creees"]
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    commandes: Annotated[list[CommandeAttendue], Field(min_length=1)]


class CommandeEtat(BaseModel):
    """
    À la fin de l'exécution, cette commande, qui existait au départ, est dans l'état décrit : avec « statut », ce statut ; avec « adresse_contient », une livraison à une adresse ponctuelle où se trouve chacun des motifs ; avec « evenement », un événement de son historique, ajouté pendant l'exécution, de cette action et dont le détail contient chacun des motifs ; avec « lignes », exactement ces lignes, dans n'importe quel ordre (JOURNAL, entrée 202). Les motifs sont des expressions régulières, sans tenir compte de la casse (service des ventes).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Literal["commande_etat"]
    numero: Annotated[str, Field(pattern="^CO-[0-9]{4}-[0-9]{5}$")]
    statut: (
        Literal[
            "brouillon",
            "en_attente_deblocage",
            "en_attente_reassort",
            "validee",
            "expediee",
            "livree",
            "facturee",
            "annulee",
        ]
        | None
    ) = None
    adresse_contient: Annotated[
        list[AdresseContientItem] | None, Field(min_length=1)
    ] = None
    evenement: EvenementAttendu | None = None
    lignes: Annotated[list[LigneCommandeAttendue] | None, Field(min_length=1)] = None
    """
    Les lignes de la commande à la fin, dans n'importe quel ordre, sans référence de plus.
    """


type Verification = Annotated[
    FichierPresent
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
    | JugeRequis,
    Field(title="Verification"),
]
"""
Une vérification exécutable sur l'état final de la PME.
"""


class Controle(BaseModel):
    """
    Un contrôle pondéré, vérifié sur l'état final de la PME par ses vérifications. « attendu » le dit en langage courant pour les lecteurs.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    famille: Literal[
        "resultat",
        "absence_effet_de_bord",
        "respect_des_regles",
        "budget",
        "contenu",
        "provenance",
    ]
    """
    Une des six familles de contrôle du BRIEF.
    """
    etape: Annotated[str, Field(min_length=1)]
    """
    Ce que le contrôle vérifie, en langage courant.
    """
    poids: Annotated[float, Field(gt=0.0, le=1.0)]
    """
    Part du score de la tâche ; la somme des poids d'une tâche vaut 1.
    """
    attendu: Annotated[str, Field(min_length=1)]
    """
    État final attendu, en langage courant.
    """
    notation: Literal["tout_ou_rien", "proportion"]
    """
    tout_ou_rien : 1 si toutes les vérifications passent, 0 sinon ; proportion : part des vérifications qui passent.
    """
    verification: Annotated[list[Verification], Field(min_length=1)]


class Tache(BaseModel):
    """
    Une tâche de bureau confiée à un agent dans la PME fictive. L'agent ne voit que l'énoncé ; tout le reste sert à la remise à zéro et aux contrôles (règle 5 du BRIEF). La somme des poids des contrôles vaut 1, ce que JSON Schema ne sait pas exprimer : EASE le vérifie au chargement.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    identifiant: Annotated[str, Field(pattern="^[a-z0-9_]+$")]
    """
    Nom stable de la tâche, égal au nom de son fichier sans extension.
    """
    version: Annotated[int, Field(ge=1)]
    """
    Augmente à chaque modification de la tâche ; un résultat cite la version mesurée.
    """
    famille: Annotated[str, Field(pattern="^[a-z_]+$")]
    """
    Métier de la tâche, par exemple administration, comptabilite ou relation_client.
    """
    agent_pour: Annotated[str, Field(pattern="^[a-z]+(\\.[a-z]+)*$")]
    """
    Identifiant, dans l'organigramme, de la personne pour qui l'agent travaille ; ses droits s'appliquent.
    """
    enonce: Annotated[str, Field(min_length=1)]
    """
    Seul texte montré à l'agent.
    """
    etat_initial: Annotated[str, Field(pattern="^v[0-9]+$")]
    """
    Version des données initiales de la société à charger avant l'exécution : 05_pme/societes/<societe>/<version>/.
    """
    societe: Annotated[str | None, Field(pattern="^[a-z][a-z0-9_]*$")] = "calorelle"
    """
    Société fictive de la tâche, dont l'état et les compléments se lisent dans 05_pme/societes/<societe>/ (ADR 0006) ; calorelle si le champ est absent. Il n'entre dans l'empreinte du jeu de tâches que s'il vaut autre chose que calorelle, pour que les empreintes des jeux de Calorelle ne changent pas (choix d'Alexandre du 2026-10-15).
    """
    complement: Annotated[str | None, Field(pattern="^[a-z0-9_]+$")] = None
    """
    Complément d'état propre à la tâche, posé sur l'état initial au départ de chaque exécution : 05_pme/societes/<societe>/complements/<nom>/ pour une tâche publique (étape 4 ; ADR 0006). Absent si la tâche n'en a pas.
    """
    validation_simulee: Literal["refuser", "accepter"] | None = None
    """
    Réponse simulée de la personne dont le gardien attend l'accord, pendant les essais (étape 4) : refuser par défaut ; accepter quand la tâche dit que cette personne a déjà donné son accord.
    """
    services: Annotated[list[Service], Field(min_length=1)]
    """
    Services de la PME, exposés en MCP, dont la tâche a besoin.
    """
    budget: Budget
    controles: Annotated[list[Controle], Field(min_length=1)]
    """
    Contrôles faits sur l'état final de la PME, jamais montrés à l'agent.
    """
    pieges: list[Piege]
    """
    Difficultés volontaires de la tâche, en langage courant. Peut être vide.
    """
    contexte_juge: Annotated[str | None, Field(min_length=1)] = None
    """
    Ce que l'agent avait sous les yeux (courriel reçu et sa date, faits du dossier, règle du manuel), donné au juge avec chaque vérification juge_requis. Identique au contexte de la tâche dans le jeu étalon du juge. Absent si la tâche n'a pas de juge_requis.
    """
