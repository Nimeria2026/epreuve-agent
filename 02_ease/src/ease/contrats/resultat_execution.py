# Généré depuis 01_contrats/resultat_execution.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

type DetailArret = Annotated[str, Field(min_length=1)]


type CoutDollars = Annotated[float, Field(ge=0.0)]


type EnergieWh = Annotated[float, Field(ge=0.0)]
"""
Énergie électrique de la carte graphique qui sert un modèle local pendant l'exécution, en wattheures, relevée par nvidia-smi. La machine entière consomme davantage : c'est un minimum. « ? » si le relevé a manqué ; null pour un candidat sans modèle local.
"""


type DureeChronometreeSecondes = Annotated[float, Field(ge=0.0)]
"""
Poste humain seulement : durée chronométrée par le poste, de « Commencer » à « J'ai fini », en secondes, reprise de sa sortie ; duree_secondes compte en plus l'attente avant « Commencer ». null pour un agent ; absente des résultats écrits avant le 2026-10-13.
"""


type Inconnu = Literal["?"]
"""
Valeur inconnue ; le rapport la montre comme telle.
"""


type HorodatageUTC = AwareDatetime
"""
Date et heure en UTC, au format RFC 3339 (par exemple 2026-11-03T14:00:00Z).
"""


type IdentifiantRun = Annotated[
    str, Field(pattern="^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9_]+$")
]
"""
Date de début du run en UTC, puis un nom ; c'est aussi le nom du dossier du run.
"""


class ReferenceTache(BaseModel):
    """
    Tâche exécutée, avec sa version.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    identifiant: Annotated[str, Field(pattern="^[a-z0-9_]+$")]
    version: Annotated[int, Field(ge=1)]


type Detail = Annotated[str, Field(min_length=1)]


class ResultatControle(BaseModel):
    """
    Score d'un contrôle de la tâche ; famille et poids sont recopiés de la tâche.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    numero: Annotated[int, Field(ge=1)]
    """
    Rang du contrôle dans la tâche, à partir de 1.
    """
    famille: Literal[
        "resultat",
        "absence_effet_de_bord",
        "respect_des_regles",
        "budget",
        "contenu",
        "provenance",
    ]
    poids: Annotated[float, Field(gt=0.0, le=1.0)]
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    """
    De 0 à 1 ; une valeur intermédiaire est un crédit partiel.
    """
    detail: Detail | None


type Entree = Annotated[int, Field(ge=0)]


type EntreeEnCache = Annotated[int, Field(ge=0)]


type Sortie = Annotated[int, Field(ge=0)]


class Jetons(BaseModel):
    """
    Jetons consommés. L'entrée compte aussi la part servie depuis le cache.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    entree: Entree | Inconnu
    entree_en_cache: EntreeEnCache | Inconnu
    sortie: Sortie | Inconnu


class ResultatExecution(BaseModel):
    """
    Un passage du candidat sur une tâche, pour une répétition. « ? » signifie inconnu, et le rapport le montre ; null signifie sans objet. Une erreur technique (API en panne, coupure) n'est pas un échec de l'agent : l'exécution est relancée et le rapport compte ces erreurs. EASE vérifie au chargement le score recalculé, la réussite et la cohérence avec la tâche.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    run: IdentifiantRun
    tache: ReferenceTache
    repetition: Annotated[int, Field(ge=1)]
    debut_utc: HorodatageUTC
    fin_utc: HorodatageUTC
    arret: Literal[
        "termine",
        "budget_etapes",
        "budget_cout",
        "erreur_technique",
        "contexte_depasse",
        "delai_depasse",
    ]
    """
    Fin normale, budget dépassé, erreur technique sans rapport avec l'agent, contexte du modèle dépassé ou délai dépassé : ces deux derniers sont des échecs de l'agent, comptés dans le taux chacun sous son arrêt (cadrage du 2026-10-14, choix T3 ; cadrage du générateur des images, choix D1).
    """
    detail_arret: DetailArret | None
    controles: Annotated[list[ResultatControle], Field(min_length=1)]
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    """
    Somme des scores pondérés par les poids.
    """
    reussie: bool
    """
    Vrai si l'exécution s'est terminée normalement et que chaque contrôle a son score plein.
    """
    etapes: Annotated[int, Field(ge=0)]
    """
    Nombre d'appels d'outils.
    """
    jetons: Jetons
    cout_dollars: CoutDollars | Inconnu
    energie_wh: EnergieWh | Inconnu | None
    """
    Énergie électrique de la carte graphique qui sert un modèle local pendant l'exécution, en wattheures, relevée par nvidia-smi. La machine entière consomme davantage : c'est un minimum. « ? » si le relevé a manqué ; null pour un candidat sans modèle local.
    """
    duree_secondes: Annotated[float, Field(ge=0.0)]
    duree_chronometree_secondes: DureeChronometreeSecondes | None = None
    """
    Poste humain seulement : durée chronométrée par le poste, de « Commencer » à « J'ai fini », en secondes, reprise de sa sortie ; duree_secondes compte en plus l'attente avant « Commencer ». null pour un agent ; absente des résultats écrits avant le 2026-10-13.
    """
    journal: Annotated[str, Field(pattern="^[A-Za-z0-9_][A-Za-z0-9_./-]*$")]
    """
    Chemin du journal des actions, relatif au dossier du run.
    """
