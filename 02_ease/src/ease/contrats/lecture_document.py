# Généré depuis 01_contrats/lecture_document.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Lecteur(BaseModel):
    """
    Ce qui a lu le document, pour rejouer une lecture (règle 1 du BRIEF).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Annotated[str, Field(min_length=1)]
    """
    Version d'EKE.
    """
    moteur: Annotated[str, Field(min_length=1)]
    """
    Bibliothèque de lecture des PDF et sa version, par exemple « pypdfium2 5.14.0 ».
    """


class Page(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    numero: Annotated[int, Field(ge=1)]
    """
    Numéro de la page, à partir de 1.
    """
    largeur: Annotated[float, Field(gt=0.0)]
    """
    En points, page telle qu'elle s'affiche (une page tournée d'un quart de tour échange largeur et hauteur).
    """
    hauteur: Annotated[float, Field(gt=0.0)]
    """
    En points, page telle qu'elle s'affiche.
    """


class Zone(BaseModel):
    """
    Rectangle en points, origine en haut à gauche de la page affichée, y vers le bas : x0 ≤ x1 et y0 ≤ y1.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    x0: float
    """
    Bord gauche.
    """
    y0: float
    """
    Bord haut.
    """
    x1: float
    """
    Bord droit.
    """
    y1: float
    """
    Bord bas.
    """


class Citation(BaseModel):
    """
    Un texte du document et sa provenance.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    texte: Annotated[str, Field(min_length=1)]
    """
    Le texte exact, tel qu'il se lit dans le document.
    """
    page: Annotated[int, Field(ge=1)]
    zone: Zone


class Valeur(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    etiquette: Annotated[str, Field(min_length=1)]
    """
    L'étiquette telle qu'elle est écrite, par exemple « Total TTC ».
    """
    type: Literal["montant", "date", "iban", "pourcentage", "texte"]
    """
    Ce que la valeur est. « iban » se reconnaît à sa forme ; la clé de contrôle n'est pas vérifiée.
    """
    valeur: Annotated[str, Field(min_length=1)]
    """
    La valeur normalisée : montant en décimal à point et deux décimales (« 512.40 »), date AAAA-MM-JJ, IBAN sans espaces, pourcentage en décimal à point (« 5.5 »), texte tel qu'écrit.
    """
    unite: str | None
    """
    « EUR » pour un montant, « % » pour un pourcentage ; null sinon.
    """
    citation: Citation
    """
    Le texte d'où vient la valeur, sans l'étiquette, et sa provenance.
    """


class Document(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    chemin: Annotated[str, Field(min_length=1)]
    """
    Chemin du document dans les dossiers partagés de la PME, avec des « / ».
    """
    empreinte: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    """
    Empreinte sha256 du fichier lu, préfixée par « sha256: ».
    """
    pages: Annotated[list[Page], Field(min_length=1)]


class LectureDocument(BaseModel):
    """
    Ce qu'EKE, l'outil documentaire de la PME, rend d'un document PDF (étape 6) : le document lu, puis selon l'outil appelé ses lignes, ses valeurs ou les citations d'un texte cherché. Chaque texte rendu porte sa provenance : la page et la zone d'où il vient. Zones en points PDF (1/72 de pouce), origine en haut à gauche de la page telle qu'elle s'affiche, y vers le bas.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    document: Document
    lecteur: Lecteur
    """
    Ce qui a lu le document, pour rejouer une lecture (règle 1 du BRIEF).
    """
    lignes: list[Citation] | None = None
    """
    Outil lire_document : le texte du document dans l'ordre de lecture du PDF, une colonne de texte après l'autre. Une ligne est un morceau de texte d'une seule ligne visuelle, sans grand blanc : la ligne d'un courrier, la cellule d'un tableau.
    """
    valeurs: list[Valeur] | None = None
    """
    Outil extraire_valeurs : les paires étiquette-valeur trouvées, dans l'ordre des lignes.
    """
    recherche: Annotated[str | None, Field(min_length=1)] = None
    """
    Outil citer : le texte cherché, tel que donné.
    """
    citations: list[Citation] | None = None
    """
    Outil citer : chaque endroit où le texte cherché apparaît ; vide s'il n'apparaît nulle part.
    """
