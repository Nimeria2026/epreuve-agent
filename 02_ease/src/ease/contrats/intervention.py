# Généré depuis 01_contrats/intervention.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

type Technicien = Annotated[str, Field(pattern="^[a-z]+\\.[a-z]+$")]


class Intervention(BaseModel):
    """
    Un rendez-vous du planning de la PME (étape 5) : chez quel client, avec quels techniciens, quand, pour quoi. Une intervention annulée reste au planning, avec son motif. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    numero: Annotated[str, Field(pattern="^INT-[0-9]{4}-[0-9]{4}$")]
    """
    Par exemple INT-2026-0001.
    """
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    techniciens: Annotated[list[Technicien], Field(min_length=1)]
    debut: AwareDatetime
    """
    Heure de la PME, au format RFC 3339 avec le décalage horaire.
    """
    fin: AwareDatetime
    nature: Literal["visite_annuelle", "depannage", "installation", "mise_en_service"]
    objet: Annotated[str, Field(min_length=1)]
    statut: Literal["planifiee", "annulee"]
    motif_annulation: Annotated[str | None, Field(min_length=1)] = None
    cree_par: Annotated[str, Field(min_length=1)]
    """
    Identifiant de la personne servie quand l'intervention a été planifiée, ou « donnees_initiales ».
    """
