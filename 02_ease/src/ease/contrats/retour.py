# Généré depuis 01_contrats/retour.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Ligne(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    reference: Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{5}$")]
    """
    Référence du catalogue, par exemple VIS-01482.
    """
    quantite: Annotated[int, Field(ge=1)]
    etat: Literal["revendable", "rebut"]


class Retour(BaseModel):
    """
    Des articles revenus d'une livraison de Négovelle, enregistrés par le service de ventes dans ventes/retours/ : les revendables reviennent en stock. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    numero: Annotated[str, Field(pattern="^RT-[0-9]{4}-[0-9]{4}$")]
    """
    Par exemple RT-2026-0042.
    """
    livraison: Annotated[str, Field(pattern="^BL-[0-9]{4}-[0-9]{5}$")]
    """
    Par exemple BL-2026-01544.
    """
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    """
    Code du client, celui de sa fiche.
    """
    date: AwareDatetime
    lignes: Annotated[list[Ligne], Field(min_length=1)]
    motif: Annotated[str, Field(min_length=1)]
    enregistre_par: Annotated[str, Field(pattern="^[a-z]+(?:[.-][a-z]+)*$")]
    """
    Identifiant d'une personne de l'organigramme.
    """
