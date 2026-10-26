# Généré depuis 01_contrats/commande.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

type Code = Annotated[str, Field(pattern="^L[0-9]+$")]
"""
Code de l'adresse dans la fiche du client, null pour une adresse ponctuelle.
"""


class Livraison(BaseModel):
    """
    Où livrer : une adresse de la fiche, ou une adresse ponctuelle.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    code: Code | None
    """
    Code de l'adresse dans la fiche du client, null pour une adresse ponctuelle.
    """
    adresse: Annotated[str, Field(min_length=1)]


type ReliquatDe = Annotated[str, Field(pattern="^CO-[0-9]{4}-[0-9]{5}$")]
"""
Par exemple CO-2026-01873.
"""


type Livraison1 = Annotated[str, Field(pattern="^BL-[0-9]{4}-[0-9]{5}$")]
"""
Par exemple BL-2026-01544.
"""


type Facture = Annotated[str, Field(pattern="^FC-[0-9]{4}-[0-9]{4}$")]
"""
Par exemple FC-2026-0412.
"""


class LigneCommande(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    reference: Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{5}$")]
    """
    Référence du catalogue, par exemple VIS-01482.
    """
    libelle: Annotated[str, Field(min_length=1)]
    quantite: Annotated[int, Field(ge=1)]
    prix_tarif_ht_euros: Annotated[float, Field(gt=0.0)]
    remise_pourcent: Annotated[float, Field(ge=0.0, lt=100.0)]
    """
    Remise de la catégorie du client puis du barème, composées ; 0 pour un prix net ou un prix dérogatoire.
    """
    prix_net_ht_euros: Annotated[float, Field(gt=0.0)]
    """
    Prix unitaire après remise, au centime, calculé par le service ou accordé.
    """
    prix_derogatoire: bool
    """
    Vrai si le prix a été accordé par accorder_prix.
    """
    taux_tva: Literal[10, 20] | float
    """
    En pour cent.
    """
    montant_ht_euros: Annotated[float, Field(ge=0.0)]


class Evenement(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    date: AwareDatetime
    par: Annotated[str, Field(pattern="^[a-z]+(?:[.-][a-z]+)*$")]
    """
    Identifiant d'une personne de l'organigramme.
    """
    action: Literal[
        "creee",
        "modifiee",
        "validee",
        "mise_en_attente",
        "debloquee",
        "prix_accorde",
        "adresse_ponctuelle",
        "scindee",
        "expediee",
        "livree",
        "facturee",
        "annulee",
    ]
    detail: str


class Commande(BaseModel):
    """
    Une commande d'un client de Négovelle, telle que le service de ventes la garde dans ventes/commandes/ : ses lignes chiffrées, sa livraison, ses totaux, son statut et son historique. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    numero: Annotated[str, Field(pattern="^CO-[0-9]{4}-[0-9]{5}$")]
    """
    Par exemple CO-2026-01873.
    """
    client: Annotated[str, Field(pattern="^c-[0-9]{4}$")]
    """
    Code du client, celui de sa fiche.
    """
    reference_client: str | None
    """
    Référence du bon de commande du client, ou null.
    """
    cree_le: AwareDatetime
    cree_par: Annotated[str, Field(pattern="^[a-z]+(?:[.-][a-z]+)*$")]
    """
    Identifiant d'une personne de l'organigramme.
    """
    mode: Literal["standard", "express"]
    livraison: Livraison
    """
    Où livrer : une adresse de la fiche, ou une adresse ponctuelle.
    """
    lignes: Annotated[list[LigneCommande], Field(min_length=1)]
    port_ht_euros: Annotated[float, Field(ge=0.0)]
    total_ht_euros: Annotated[float, Field(ge=0.0)]
    total_tva_euros: Annotated[float, Field(ge=0.0)]
    total_ttc_euros: Annotated[float, Field(ge=0.0)]
    statut: Literal[
        "brouillon",
        "en_attente_deblocage",
        "en_attente_reassort",
        "validee",
        "expediee",
        "livree",
        "facturee",
        "annulee",
    ]
    motif_attente: str | None
    """
    Pourquoi une commande attend un déblocage, ou null.
    """
    reliquat_de: ReliquatDe | None
    """
    La commande dont celle-ci est le reliquat, ou null.
    """
    livraisons: list[Livraison1]
    facture: Facture | None
    historique: list[Evenement]
