# Généré depuis 01_contrats/bon_de_livraison.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type Transporteur = Annotated[str, Field(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$")]
"""
Dossier de la fiche du fournisseur, lue par le service des achats.
"""


class Transport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Literal["flotte", "transporteur"]
    transporteur: Transporteur | None
    """
    La fiche du transporteur, null pour la flotte de la PME.
    """
    recepisse: str | None
    """
    Numéro du récépissé du transporteur, ou null.
    """


class Ligne(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    reference: Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{5}$")]
    """
    Référence du catalogue, par exemple VIS-01482.
    """
    libelle: Annotated[str, Field(min_length=1)]
    quantite: Annotated[int, Field(ge=1)]


class BonDeLivraison(BaseModel):
    """
    Un bon de livraison de Négovelle, tel que le service de ventes le garde dans ventes/livraisons/ : ce qui est parti, comment, et ce que le client a écrit en le recevant. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    numero: Annotated[str, Field(pattern="^BL-[0-9]{4}-[0-9]{5}$")]
    """
    Par exemple BL-2026-01544.
    """
    commande: Annotated[str, Field(pattern="^CO-[0-9]{4}-[0-9]{5}$")]
    """
    Par exemple CO-2026-01873.
    """
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    """
    Code du client, celui de sa fiche.
    """
    date_expedition: date
    date_livraison: date | None
    transport: Transport
    adresse: Annotated[str, Field(min_length=1)]
    colis: Annotated[int, Field(ge=1)]
    lignes: Annotated[list[Ligne], Field(min_length=1)]
    reserves: str | None
    """
    Réserves portées au récépissé ou au bon à la livraison, mot pour mot, ou null.
    """
    signataire: str | None
    statut: Literal["en_cours", "livre", "refuse"]
