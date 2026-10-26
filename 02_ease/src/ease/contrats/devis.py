# Généré depuis 01_contrats/devis.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Ligne(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    code: Annotated[str, Field(pattern="^[A-Z]{2,4}-[0-9]{2,3}$")]
    """
    Code de la ligne du tarif.
    """
    libelle: Annotated[str, Field(min_length=1)]
    quantite: Annotated[float, Field(gt=0.0)]
    """
    Au centième près.
    """
    prix_unitaire_ht_euros: Annotated[float, Field(gt=0.0)]
    """
    Pris au tarif par le service.
    """
    taux_tva: Literal[10, 20] | float
    """
    En pour cent, choisi par la personne qui chiffre le devis.
    """
    montant_ht_euros: Annotated[float, Field(gt=0.0)]
    """
    Quantité fois prix unitaire, arrondi au centime, avant remise.
    """


class Devis(BaseModel):
    """
    Un devis de Calorelle à un client, tel que le service facturation de la PME le garde (étape 5, tranche 5) : ses lignes prises au tarif, sa remise, ses totaux calculés par le service, son statut. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    numero: Annotated[str, Field(pattern="^DV-[0-9]{4}-[0-9]{3}$")]
    """
    Par exemple DV-2026-013.
    """
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    """
    Code du client, celui de sa fiche.
    """
    objet: Annotated[str, Field(min_length=1)]
    lignes: Annotated[list[Ligne], Field(min_length=1)]
    remise_pourcent: Annotated[float, Field(ge=0.0, lt=100.0)]
    """
    Remise sur chaque ligne, en pour cent ; 0 sans remise.
    """
    total_ht_euros: Annotated[float, Field(gt=0.0)]
    """
    Après remise.
    """
    total_tva_euros: Annotated[float, Field(ge=0.0)]
    total_ttc_euros: Annotated[float, Field(gt=0.0)]
    statut: Literal["brouillon", "envoye", "accepte", "refuse", "abandonne"]
    """
    Un brouillon abandonné reste gardé : on ne supprime aucun document.
    """
    cree_le: AwareDatetime
    """
    Heure de la PME, au format RFC 3339 avec le décalage horaire.
    """
    cree_par: Annotated[str, Field(min_length=1)]
    """
    Identifiant de la personne servie quand le devis a été créé.
    """
    envoye_le: AwareDatetime | None
    """
    Quand l'envoi a été enregistré ; null pour un brouillon.
    """
    reponse_le: AwareDatetime | None
    """
    Quand l'acceptation ou le refus a été enregistré ; null sinon.
    """
