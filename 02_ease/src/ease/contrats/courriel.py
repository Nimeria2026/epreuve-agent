# Généré depuis 01_contrats/courriel.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

type EnReponseA = Annotated[str, Field(pattern="^m-[a-z0-9]+(-[a-z0-9]+)*$")]
"""
Courriel auquel celui-ci répond ; null sinon.
"""


type TransfereDe = Annotated[str, Field(pattern="^m-[a-z0-9]+(-[a-z0-9]+)*$")]
"""
Courriel que celui-ci transfère ; null sinon.
"""


type Adresse = Annotated[
    str, Field(pattern="^[a-z0-9._-]+@[a-z0-9-]+(\\.[a-z0-9-]+)*\\.example$")
]
"""
Adresse fictive : le domaine se termine toujours par .example (RFC 2606).
"""


type Nom = Annotated[str, Field(min_length=1)]


class Correspondant(BaseModel):
    """
    Expéditeur : nom affiché et adresse. Le nom affiché peut mentir, pas le domaine.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    nom: Nom | None
    adresse: Adresse


class PieceJointe(BaseModel):
    """
    Une pièce jointe, rangée dans messagerie/pieces/ de l'état de la PME.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    nom: Annotated[str, Field(pattern="^[^/\\\\]+$")]
    """
    Nom du fichier tel qu'il apparaît dans le courriel.
    """
    fichier: Annotated[
        str, Field(pattern="^pieces/m-[a-z0-9]+(-[a-z0-9]+)*/[^/\\\\]+$")
    ]
    """
    Chemin du fichier, relatif au dossier messagerie de l'état.
    """
    taille_octets: Annotated[int, Field(ge=0)]


class Courriel(BaseModel):
    """
    Un courriel de la messagerie de la PME fictive, tel que le serveur messagerie l'enregistre et qu'EASE le relit pour ses contrôles. Toutes les adresses sont fictives, en .example.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    identifiant: Annotated[str, Field(pattern="^m-[a-z0-9]+(-[a-z0-9]+)*$")]
    """
    Identifiant stable, cité par les tâches (par exemple m-cpt-001).
    """
    de: Correspondant
    a: Annotated[list[Adresse], Field(min_length=1)]
    cc: list[Adresse]
    objet: str
    date: AwareDatetime
    """
    Date et heure d'envoi au format RFC 3339, avec le décalage horaire (par exemple 2026-11-02T08:12:00+01:00).
    """
    corps: str
    pieces_jointes: list[PieceJointe]
    lu: bool
    en_reponse_a: EnReponseA | None
    """
    Courriel auquel celui-ci répond ; null sinon.
    """
    transfere_de: TransfereDe | None
    """
    Courriel que celui-ci transfère ; null sinon.
    """
