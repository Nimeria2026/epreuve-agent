# Généré depuis 01_contrats/fiche_client_negoce.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Contact(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    nom: Annotated[str, Field(min_length=1)]
    fonction: Annotated[str, Field(min_length=1)]
    courriel: Annotated[str, Field(pattern="^[^@\\s]+@[^@\\s]+\\.example$")]


class AdressesLivraisonItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    code: Annotated[str, Field(pattern="^L[0-9]+$")]
    libelle: Annotated[str, Field(min_length=1)]
    adresse: Annotated[str, Field(min_length=1)]


class FicheClientNegoce(BaseModel):
    """
    La fiche d'un client de Négovelle, rangée dans dossiers/clients/<code>/fiche_client.yaml : ses contacts et ses adresses déclarés, ses conditions, son statut ; lue par le service de ventes, qui n'y écrit que le statut. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    code: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    """
    Code du client, celui de sa fiche.
    """
    nom: Annotated[str, Field(min_length=1)]
    type: Literal["artisan", "entreprise", "pme", "collectivite"]
    adresse: Annotated[str, Field(min_length=1)]
    """
    Le siège ; le service de facturation la lit aussi.
    """
    telephone: Annotated[str, Field(min_length=1)]
    """
    Le numéro à rappeler pour vérifier une demande.
    """
    secteur: Literal["nord", "sud", "est", "ouest"]
    commercial: Annotated[str, Field(pattern="^[a-z]+(?:[.-][a-z]+)*$")]
    """
    Identifiant d'une personne de l'organigramme.
    """
    administration_des_ventes: Annotated[str, Field(pattern="^[a-z]+(?:[.-][a-z]+)*$")]
    """
    Identifiant d'une personne de l'organigramme.
    """
    contacts: Annotated[list[Contact], Field(min_length=1)]
    """
    Les contacts déclarés : les seuls dont une commande ou une demande se reçoit.
    """
    adresses_livraison: Annotated[list[AdressesLivraisonItem], Field(min_length=1)]
    categorie_remise: Literal["A", "B", "C"]
    delai_paiement: Literal[
        "comptant", "30_jours_date_de_facture", "60_jours_date_de_facture"
    ]
    client_depuis: date
    limite_encours_euros: Annotated[float, Field(ge=0.0)]
    livraisons_partielles: bool
    substitution_acceptee: bool
    statut: Literal["ouvert", "bloque"]
    motif_blocage: str | None
