# Généré depuis 01_contrats/tarif.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Ligne(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    code: Annotated[str, Field(pattern="^[A-Z]{2,4}-[0-9]{2,3}$")]
    """
    Par exemple CHA-01.
    """
    libelle: Annotated[str, Field(min_length=1)]
    unite: Literal["unité", "heure", "forfait", "mètre"]
    prix_ht_euros: Annotated[float, Field(gt=0.0)]
    """
    Prix hors taxes d'une unité, au centime.
    """


class Tarif(BaseModel):
    """
    La grille de prix de Calorelle, que le service facturation de la PME lit pour chiffrer un devis (étape 5, tranche 5). Prix hors taxes, fictifs.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    annee: Annotated[int, Field(ge=2020)]
    """
    Année du tarif.
    """
    lignes: Annotated[list[Ligne], Field(min_length=1)]
