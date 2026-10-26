"""Zones et repère de la page affichée : ce que vaut une coordonnée, quel que soit le PDF.

Un PDF place son texte dans l'espace de la page : origine en bas à gauche, y vers le haut, une
boîte (MediaBox, CropBox) qui ne commence pas forcément en 0, et une rotation d'un nombre de
quarts de tour que le lecteur applique à l'affichage. EKE rend ses zones dans le repère de la
page telle qu'elle s'affiche : en points, origine en haut à gauche, y vers le bas (contrat
`lecture_document`). Ce module fait le passage dans les deux sens ; il ne dépend d'aucune
bibliothèque de lecture.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

DECIMALES = 2
"""Précision des zones rendues : le centième de point, bien en dessous d'un pixel à 300 dpi."""


@dataclass(frozen=True)
class Zone:
    """Un rectangle, x0 ≤ x1 et y0 ≤ y1, dans le repère où il a été construit."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def largeur(self) -> float:
        return self.x1 - self.x0

    @property
    def hauteur(self) -> float:
        return self.y1 - self.y0

    @property
    def milieu_y(self) -> float:
        return (self.y0 + self.y1) / 2

    def chevauchement_vertical(self, autre: Zone) -> float:
        """Hauteur commune aux deux zones, 0 si elles ne se touchent pas."""
        return max(0.0, min(self.y1, autre.y1) - max(self.y0, autre.y0))

    def contient(self, autre: Zone, marge: float = 0.0) -> bool:
        return (
            self.x0 - marge <= autre.x0
            and self.y0 - marge <= autre.y0
            and autre.x1 <= self.x1 + marge
            and autre.y1 <= self.y1 + marge
        )

    def en_contrat(self) -> dict[str, float]:
        return {
            "x0": round(self.x0, DECIMALES),
            "y0": round(self.y0, DECIMALES),
            "x1": round(self.x1, DECIMALES),
            "y1": round(self.y1, DECIMALES),
        }


def zone_de_points(xa: float, ya: float, xb: float, yb: float) -> Zone:
    """La zone qui a ces deux coins opposés, dans n'importe quel ordre."""
    return Zone(min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb))


def union(zones: Iterable[Zone]) -> Zone:
    """La plus petite zone qui contient toutes celles données ; refuse une liste vide."""
    liste = list(zones)
    if not liste:
        raise ValueError("union d'aucune zone")
    return Zone(
        min(z.x0 for z in liste),
        min(z.y0 for z in liste),
        max(z.x1 for z in liste),
        max(z.y1 for z in liste),
    )


@dataclass(frozen=True)
class Repere:
    """Passage entre l'espace d'une page PDF et la page affichée.

    `boite` est la partie visible de la page dans l'espace PDF (gauche, bas, droite, haut) ;
    `rotation` est celle que le PDF demande à l'affichage, en degrés, sens des aiguilles d'une
    montre : 0, 90, 180 ou 270.
    """

    gauche: float
    bas: float
    droite: float
    haut: float
    rotation: int = 0

    def __post_init__(self) -> None:
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError(f"rotation non prévue : {self.rotation}")
        if self.droite <= self.gauche or self.haut <= self.bas:
            raise ValueError("boîte de page vide")

    @property
    def largeur(self) -> float:
        """Largeur de la page affichée."""
        cote = self.droite - self.gauche
        return cote if self.rotation in (0, 180) else self.haut - self.bas

    @property
    def hauteur(self) -> float:
        """Hauteur de la page affichée."""
        cote = self.haut - self.bas
        return cote if self.rotation in (0, 180) else self.droite - self.gauche

    def vers_affichage(self, x: float, y: float) -> tuple[float, float]:
        """Un point de l'espace PDF, dans le repère de la page affichée."""
        match self.rotation:
            case 0:
                return x - self.gauche, self.haut - y
            case 90:
                return y - self.bas, x - self.gauche
            case 180:
                return self.droite - x, y - self.bas
            case _:
                return self.haut - y, self.droite - x

    def vers_pdf(self, x: float, y: float) -> tuple[float, float]:
        """Un point de la page affichée, dans l'espace PDF : l'inverse de vers_affichage."""
        match self.rotation:
            case 0:
                return x + self.gauche, self.haut - y
            case 90:
                return y + self.gauche, x + self.bas
            case 180:
                return self.droite - x, y + self.bas
            case _:
                return self.droite - y, self.haut - x

    def zone_affichee(self, gauche: float, bas: float, droite: float, haut: float) -> Zone:
        """Un rectangle de l'espace PDF, dans le repère de la page affichée."""
        xa, ya = self.vers_affichage(gauche, bas)
        xb, yb = self.vers_affichage(droite, haut)
        return zone_de_points(xa, ya, xb, yb)

    def rectangle_pdf(self, zone: Zone) -> tuple[float, float, float, float]:
        """Une zone de la page affichée, en rectangle de l'espace PDF (gauche, bas, droite, haut)."""
        xa, ya = self.vers_pdf(zone.x0, zone.y0)
        xb, yb = self.vers_pdf(zone.x1, zone.y1)
        return min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)
