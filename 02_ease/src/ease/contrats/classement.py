# Généré depuis 01_contrats/classement.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type IdentifiantTache = Annotated[str, Field(pattern="^[a-z0-9_]+$")]
"""
Identifiant d'une tâche, celui de son fichier.
"""


type CodePersonne = Annotated[str, Field(pattern="^p[0-9]+$")]
"""
Code d'une personne du poste humain.
"""


class Personne(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    connait_les_taches: bool
    """
    Vrai pour une personne qui a vu les tâches avant de les faire, par exemple en les concevant : ses durées sont plus courtes que celles d'un nouvel employé.
    """


type Etiquette = Literal[
    "calcul", "dates_et_echeances", "volume", "regle_peu_visible", "document", "piege"
]
"""
Difficulté d'une tâche, liste fermée (cadrage de l'horizon de temps, §6) : calcul, un montant, un taux ou un nombre à calculer ; dates_et_echeances, une date, un délai ou un créneau à trouver ou à calculer ; volume, au moins trois éléments à traiter ; regle_peu_visible, une règle du manuel facile à manquer ; document, une information décisive à lire dans une pièce jointe ou un document autre que le manuel ; piege, une demande qui pousse à enfreindre le manuel. « plusieurs services » se calcule depuis la tâche.
"""


class FicheRome(BaseModel):
    """
    La fiche du ROME de France Travail que la tâche illustre ; on cite son code et son intitulé, jamais son texte.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    code: Annotated[str, Field(pattern="^[A-N][0-9]{4}$")]
    intitule: Annotated[str, Field(min_length=1)]


class DureeHumaine(BaseModel):
    """
    Un essai réussi au poste humain : la durée chronométrée de « Commencer » à « J'ai fini », le run et la répétition d'où elle vient, et la version de la tâche faite.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    personne: CodePersonne
    secondes: Annotated[float, Field(gt=0.0)]
    run: Annotated[str, Field(pattern="^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9_]+$")]
    repetition: Annotated[int, Field(ge=1)]
    version_tache: Annotated[int, Field(ge=1)]


type SectionsManuelItem = Annotated[int, Field(ge=1)]


class DureeEstimee(BaseModel):
    """
    La durée d'une tâche estimée par la grille (cadrage de l'horizon de temps, suite du 2026-10-14) : le temps d'un employé du métier qui sait déjà quoi faire, sur le chemin du témoin parfait ; une borne basse, jamais une durée mesurée. Ses quatre parts, en secondes, font son total.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    secondes: Annotated[float, Field(ge=0.0)]
    """
    La durée estimée, somme des quatre parts.
    """
    grille: Annotated[str, Field(min_length=1)]
    """
    Version de la grille qui l'a calculée ; une autre version demande de la refaire.
    """
    version_tache: Annotated[int, Field(ge=1)]
    """
    Version de la tâche estimée.
    """
    run: Annotated[str, Field(pattern="^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9_]+$")]
    """
    Le run du témoin parfait d'où vient le chemin.
    """
    lire: Annotated[float, Field(ge=0.0)]
    """
    Courriels, documents et sections du manuel lus pour comprendre.
    """
    chercher: Annotated[float, Field(ge=0.0)]
    """
    Listes et tableaux balayés pour trouver une ligne.
    """
    ecrire: Annotated[float, Field(ge=0.0)]
    """
    Textes libres écrits : corps, objet, commentaire, motif.
    """
    agir: Annotated[float, Field(ge=0.0)]
    """
    Gestes : ouvrir, remplir, valider, au modèle KLM.
    """


class FicheClassement(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    version_tache: Annotated[int, Field(ge=1)]
    """
    Version de la tâche classée ; une version plus récente demande de relire la fiche.
    """
    etiquettes: list[Etiquette]
    type_commun: Annotated[str | None, Field(pattern="^[a-z][a-z_]*[a-z]$")] = None
    """
    Le type du socle commun dont la tâche est une instance, par son nom dans 07_taches/public/types_communs.yaml (JOURNAL, cent-cinquante-quatrième entrée) ; absent pour une tâche du métier. Écrit à la main.
    """
    branche: (
        Literal[
            "accueil_et_courrier",
            "relation_client",
            "comptabilite_et_fournisseurs",
            "commercial_et_devis",
            "planning_et_interventions",
            "personnel_et_rh",
        ]
        | None
    ) = None
    """
    La fonction de la PME que la tâche exerce, pour le benchmark par branche (cadrage du 2026-10-20, choix B1) : une des six fonctions de la carte du banc du 2026-10-07. Écrite à la main ; absente pour une tâche hors du benchmark (tranches longues).
    """
    rome: FicheRome
    sections_manuel: list[SectionsManuelItem]
    """
    Les sections du manuel dont la tâche se sert, par leur numéro dans le manuel de la tâche (un complément peut le changer) ; la grille ne compte qu'elles. Listées par Claude, relues par Alexandre (JOURNAL, cent-vingt-cinquième entrée).
    """
    durees: list[DureeHumaine]
    """
    Les essais réussis au poste humain, toutes versions de la tâche confondues.
    """
    duree_estimee: DureeEstimee | None = None


class Classement(BaseModel):
    """
    Classement des tâches d'un jeu (07_taches/public/classement.yaml ; les tâches cachées ont le leur dans 07_taches/prive/) : ce qui ne se calcule pas depuis la tâche. Les étiquettes de difficulté servent à lire les échecs, jamais à noter ; la fiche ROME de France Travail ancre la tâche dans un métier réel ; les sections du manuel dont la tâche se sert s'écrivent à la main ; les durées humaines mesurées viennent des runs du poste humain, versées par un script (make classement VERSER=1), et la durée estimée par la grille se calcule depuis un run du témoin parfait (make classement ESTIMER=1), jamais à la main. Le métier, les services, le contrôle grave et les étapes du témoin parfait se calculent depuis la tâche et ne s'écrivent pas ici (JOURNAL, entrées 121 et 125).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Annotated[int, Field(ge=1)]
    """
    Version du fichier, augmentée à chaque changement de sa forme.
    """
    personnes: dict[CodePersonne, Personne]
    """
    Les personnes du poste humain, par leur code (p1, p2), jamais par leur nom.
    """
    taches: dict[IdentifiantTache, FicheClassement]
    """
    Une fiche par tâche, sous son identifiant.
    """
