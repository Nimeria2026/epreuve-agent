# Généré depuis 01_contrats/facture_client.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from datetime import date as date_aliased
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class FactureClient(BaseModel):
    """
    Une facture de Calorelle à un client, telle que le service facturation de la PME la garde. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    numero: Annotated[str, Field(pattern="^FC-[0-9]{4}-[0-9]{4}$")]
    """
    Par exemple FC-2026-0412.
    """
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    """
    Code du client, celui de sa fiche.
    """
    date: date_aliased
    objet: Annotated[str, Field(min_length=1)]
    montant_ttc_euros: Annotated[float, Field(gt=0.0)]
    payee: bool
