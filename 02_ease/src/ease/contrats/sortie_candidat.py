# Généré depuis 01_contrats/sortie_candidat.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypeAliasType

ModelesRenvoyesAdditionalProperty = TypeAliasType(
    "ModelesRenvoyesAdditionalProperty", Annotated[str, Field(min_length=1)]
)


type Inconnu = Literal["?"]
"""
Valeur inconnue ; le rapport la montre comme telle.
"""


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


class SortieCandidat(BaseModel):
    """
    Ce qu'un candidat lancé dans son propre processus rend à EASE pour une exécution : comment il s'est arrêté, ce qu'il a consommé, et les modèles que les API ont annoncés. Ses actions ne passent pas par ce fichier : EASE les voit dans le journal de son relais. Le candidat réécrit ce fichier après chaque appel de modèle, pour qu'un arrêt brutal laisse la consommation déjà faite. « ? » signifie inconnu.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    fin: Literal[
        "en_cours",
        "termine",
        "tours_max",
        "erreur",
        "contexte_depasse",
        "delai_depasse",
    ]
    """
    en_cours : fichier réécrit pendant l'exécution ; termine : l'agent a rendu la main ; tours_max : la boucle a atteint sa limite de tours ; erreur : panne côté candidat, détaillée dans detail ; contexte_depasse : le serveur du modèle a refusé une conversation plus longue que son contexte, détaillé dans detail ; delai_depasse : un appel au modèle a dépassé son délai, détaillé dans detail.
    """
    detail: str | None
    """
    Explication d'une fin autre que termine ; null sinon.
    """
    appels_modele: Annotated[int, Field(ge=0)]
    """
    Nombre d'appels aux modèles pendant l'exécution, tous rôles confondus.
    """
    consommation: dict[str, Jetons]
    """
    Jetons consommés, par rôle de modèle (agent, superviseur) ; vide pour un candidat qui n'appelle aucun modèle.
    """
    modeles_renvoyes: dict[str, ModelesRenvoyesAdditionalProperty]
    """
    Nom du modèle annoncé par l'API dans ses réponses, par rôle.
    """
    duree_chronometree_secondes: Annotated[float | None, Field(ge=0.0)] = None
    """
    Poste humain seulement : durée de l'essai chronométrée par le poste, de « Commencer » à « J'ai fini », en secondes. Absente pour un agent, dont EASE mesure seul la durée.
    """
