# Généré depuis 01_contrats/avoir.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Avoir(BaseModel):
    """
    Un avoir émis sur une facture client par le service facturation de la PME : un remboursement ou un geste commercial. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    numero: Annotated[str, Field(pattern="^AV-[0-9]{4}-[0-9]{4}$")]
    """
    Par exemple AV-2026-0001.
    """
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    facture: Annotated[str, Field(pattern="^FC-[0-9]{4}-[0-9]{4}$")]
    date: AwareDatetime
    """
    Heure simulée de la PME, au format RFC 3339 avec le décalage horaire.
    """
    montant_ttc_euros: Annotated[float, Field(gt=0.0)]
    motif: Annotated[str, Field(min_length=1)]
    emis_par: Annotated[str, Field(min_length=1)]
    """
    Identifiant de la personne servie, dans l'organigramme.
    """
