# Généré depuis 01_contrats/catalogue.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RemisesCategories(BaseModel):
    """
    Remise en pour cent de chaque catégorie de client, sur le prix du tarif.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    A: Annotated[float, Field(ge=0.0, lt=100.0)]
    B: Annotated[float, Field(ge=0.0, lt=100.0)]
    C: Annotated[float, Field(ge=0.0, lt=100.0)]


class Conditions(BaseModel):
    """
    Les conditions générales de vente que le logiciel applique à chaque commande.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    remises_categories: RemisesCategories
    """
    Remise en pour cent de chaque catégorie de client, sur le prix du tarif.
    """
    port_standard_ht_euros: Annotated[float, Field(ge=0.0)]
    """
    Port d'une commande standard sous le franco.
    """
    franco_a_partir_de_ht_euros: Annotated[float, Field(ge=0.0)]
    """
    Montant des lignes, hors taxes, à partir duquel une commande standard part sans port.
    """
    forfait_express_ht_euros: Annotated[float, Field(ge=0.0)]
    """
    Port d'une commande express, quel que soit son montant.
    """
    taux_tva_port: Literal[10, 20] | float
    """
    En pour cent.
    """


class BaremeQuantiteItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    a_partir_de: Annotated[int, Field(ge=2)]
    remise_pourcent: Annotated[float, Field(gt=0.0, lt=100.0)]


class Achat(BaseModel):
    """
    Ce que l'article coûte : de quoi calculer le seuil de revente à perte.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    fournisseur: Annotated[str, Field(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    """
    Dossier de la fiche du fournisseur, lue par le service des achats.
    """
    prix_net_facture_ht_euros: Annotated[float, Field(gt=0.0)]
    """
    Prix unitaire net de la dernière facture d'achat.
    """
    avantages_financiers_pourcent: Annotated[float, Field(ge=0.0, lt=100.0)]
    """
    Autres avantages financiers du fournisseur, en pour cent du prix unitaire net.
    """
    transport_unitaire_ht_euros: Annotated[float, Field(ge=0.0)]
    """
    Part du transport d'achat, par unité.
    """


class Reassort(BaseModel):
    """
    Réassort commandé au fournisseur, ou null.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    quantite: Annotated[int, Field(ge=1)]
    date_prevue: date


type Substitut = Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{5}$")]
"""
Référence du catalogue, par exemple VIS-01482.
"""


class Article(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    reference: Annotated[str, Field(pattern="^[A-Z]{3}-[0-9]{5}$")]
    """
    Référence du catalogue, par exemple VIS-01482.
    """
    libelle: Annotated[str, Field(min_length=1)]
    famille: Annotated[str, Field(pattern="^[a-z_]+$")]
    """
    Une des familles du catalogue, par exemple visserie.
    """
    unite: Annotated[str, Field(min_length=1)]
    """
    Unité de vente, par exemple boîte de 100.
    """
    conditionnement: Annotated[int, Field(ge=1)]
    """
    Une commande en demande un multiple.
    """
    prix_vente_ht_euros: Annotated[float, Field(gt=0.0)]
    """
    Prix du tarif général, avant toute remise.
    """
    prix_net: bool
    """
    Vrai pour un article qui ne prend aucune remise.
    """
    bareme_quantite: list[BaremeQuantiteItem]
    """
    Remises par quantité commandée sur une ligne, seuils croissants ; la plus haute atteinte s'applique.
    """
    taux_tva: Literal[10, 20] | float
    """
    En pour cent.
    """
    achat: Achat
    """
    Ce que l'article coûte : de quoi calculer le seuil de revente à perte.
    """
    stock_physique: Annotated[int, Field(ge=0)]
    """
    Unités en rayon ; le réservé se calcule sur les commandes validées.
    """
    point_de_commande: Annotated[int, Field(ge=0)]
    quantite_reassort: Annotated[int, Field(ge=0)]
    reassort: Reassort | None
    """
    Réassort commandé au fournisseur, ou null.
    """
    statut: Literal["courant", "fin_de_serie", "dereference"]
    substituts: list[Substitut]
    """
    Articles qui peuvent le remplacer, avec l'accord du client.
    """


class Catalogue(BaseModel):
    """
    Le catalogue d'une PME de négoce (Négovelle, cadrage du 2026-10-17), tel que le service de ventes le garde dans ventes/catalogue.json : chaque article, son prix, ce qu'il coûte, son stock. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    annee_tarif: Annotated[int, Field(ge=2000)]
    conditions: Conditions
    """
    Les conditions générales de vente que le logiciel applique à chaque commande.
    """
    articles: Annotated[list[Article], Field(min_length=1)]
