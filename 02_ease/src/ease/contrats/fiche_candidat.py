# Généré depuis 01_contrats/fiche_candidat.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

type Inconnu = Literal["?"]
"""
Valeur inconnue ; le rapport la montre comme telle.
"""


class ModeleCandidat(BaseModel):
    """
    Un modèle utilisé par le candidat.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    nom: Annotated[str, Field(min_length=1)]
    fournisseur: Annotated[str, Field(min_length=1)]


class ConditionsUtilisation(BaseModel):
    """
    Conditions d'utilisation lues avant toute publication nommée (clause DeWitt, BRIEF §3).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    url: AnyUrl
    lues_le: date
    publication_permise: Literal["oui", "non", "?"]
    """
    Les conditions permettent-elles de publier des résultats nommés ?
    """


class FicheCandidat(BaseModel):
    """
    Le système mesuré. Un candidat qui n'est pas classable (témoin, humain, non évaluable, publication non permise ou non vérifiée) n'apparaît jamais dans un classement. « ? » signifie inconnu, et le rapport le montre ; null signifie sans objet.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    identifiant: Annotated[str, Field(pattern="^[a-z0-9_]+$")]
    nom: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    origine: Literal["fait_main", "pret_a_l_emploi", "temoin", "humain"]
    """
    fait_main : orchestration du projet ; pret_a_l_emploi : produit d'un éditeur ; temoin : comportement connu d'avance, pour vérifier le banc ; humain : une personne au poste humain, pour mesurer la durée humaine des tâches (JOURNAL, cent-vingt-et-unième entrée).
    """
    division: Literal["a_modele_egal", "systeme_complet"] | None
    """
    Division de classement ; null pour un témoin ou un humain, jamais classés.
    """
    branchement: Literal["mcp", "interface", "aucun"]
    """
    mcp : mesurable ; interface : mesurable en partie ; aucun : non évaluable.
    """
    editeur: Annotated[str, Field(min_length=1)]
    url: AnyUrl | Inconnu | None
    modeles: list[ModeleCandidat] | Inconnu
    cout_mesurable: bool
    """
    Vrai si le coût par tâche se mesure (jetons et prix connus).
    """
    conditions_utilisation: ConditionsUtilisation | None
    """
    Obligatoires pour un produit prêt à l'emploi ; null pour un candidat fait main ou un témoin.
    """
