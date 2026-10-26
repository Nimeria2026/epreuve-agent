"""Des caractères d'une page aux morceaux de ligne, chacun avec la zone de chaque caractère.

Générique : rien ici ne connaît Calorelle ni un type de document. Trois étapes :

1. Suivre les caractères dans l'ordre de PDFium. Ses fins de ligne, ajoutées ou non, coupent ;
   ses espaces, ajoutées ou non, séparent les mots.
2. Couper encore là où le texte saute : changement de ligne visuelle, retour en arrière, ou grand
   blanc (une colonne de tableau, une valeur alignée à droite).
3. Rassembler les morceaux d'une même ligne visuelle, de gauche à droite, et recoller ceux que
   seul un petit blanc sépare (deux objets texte du PDF sur la même ligne).

Les seuils se comptent en hauteur de ligne, pas en points : ils valent pour toute taille de
police. Une page en deux colonnes de texte suivi se lit ligne visuelle par ligne visuelle ; c'est
une limite connue, que le banc public de documents mesurera (journal de l'étape 6).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from eke.geometrie import Zone, union
from eke.pdfium import PageLue

SEUIL_MOT = 0.15
"""Blanc, en hauteur de ligne, au-delà duquel deux morceaux recollés sont séparés d'une espace."""
SEUIL_COLONNE = 1.5
"""Blanc, en hauteur de ligne, au-delà duquel le texte change de colonne : deux morceaux."""
MEME_LIGNE = 0.5
"""Part de la plus petite hauteur que deux zones doivent partager pour être sur la même ligne."""
FINS_DE_LIGNE = frozenset("\r\n  ")


@dataclass(frozen=True)
class Morceau:
    """Un texte d'une seule ligne visuelle, sans grand blanc, et la zone de chacun de ses caractères.

    `zones[i]` est la zone de `texte[i]`, ou None pour une espace ou un caractère sans étendue (un
    accent combiné) : il ne marque rien qui se mesure, il ne compte pas dans la zone d'une citation.
    """

    page: int
    texte: str
    zones: tuple[Zone | None, ...]

    @property
    def zone(self) -> Zone:
        return self.zone_de(0, len(self.texte))

    def zone_de(self, debut: int, fin: int) -> Zone:
        """La zone du texte[debut:fin] ; refuse un passage fait seulement d'espaces."""
        return union(z for z in self.zones[debut:fin] if z is not None)

    @property
    def hauteur(self) -> float:
        return median(z.hauteur for z in self.zones if z is not None)


@dataclass
class _EnCours:
    page: int
    texte: list[str]
    zones: list[Zone | None]

    def derniere(self) -> Zone:
        return next(z for z in reversed(self.zones) if z is not None)

    def fige(self) -> Morceau:
        while self.texte and self.texte[-1].isspace():
            self.texte.pop()
            self.zones.pop()
        return Morceau(self.page, "".join(self.texte), tuple(self.zones))


def _meme_ligne(a: Zone, b: Zone) -> bool:
    plus_petite = min(a.hauteur, b.hauteur)
    return plus_petite > 0 and a.chevauchement_vertical(b) >= MEME_LIGNE * plus_petite


def sur_la_meme_ligne(a: Morceau, b: Morceau) -> bool:
    """Vrai si les deux morceaux sont sur la même ligne visuelle."""
    return a.page == b.page and _meme_ligne(a.zone, b.zone)


def _suite(precedente: Zone, zone: Zone) -> bool:
    """Vrai si ce caractère continue le morceau : même ligne, ni retour en arrière, ni grand blanc."""
    if not _meme_ligne(precedente, zone):
        return False
    hauteur = max(precedente.hauteur, zone.hauteur)
    blanc = zone.x0 - precedente.x1
    return -hauteur <= blanc <= SEUIL_COLONNE * hauteur


def _morceaux_bruts(page: PageLue) -> list[Morceau]:
    """Étapes 1 et 2 : les morceaux dans l'ordre de PDFium.

    Entre deux caractères visibles, les blancs du PDF restent tels quels (une espace insécable
    reste insécable : le texte cité est exact) ; un blanc que PDFium déduit de la position du
    texte devient une espace simple.
    """
    morceaux: list[Morceau] = []
    courant: _EnCours | None = None
    blancs: list[str] = []
    blanc_ajoute = False

    def fermer() -> None:
        nonlocal courant
        if courant is not None and any(z is not None for z in courant.zones):
            morceaux.append(courant.fige())
        courant = None

    for caractere in page.caracteres:
        if caractere.texte in FINS_DE_LIGNE:
            fermer()
            blancs, blanc_ajoute = [], False
            continue
        if caractere.texte.isspace():
            if caractere.ajoute:
                blanc_ajoute = True
            else:
                blancs.append(caractere.texte)
            continue
        visible = caractere.zone.largeur > 0 and caractere.zone.hauteur > 0
        if visible and courant is not None and not _suite(courant.derniere(), caractere.zone):
            fermer()
        if courant is None:
            if visible:
                courant = _EnCours(page.numero, [], [])
        else:
            entre = blancs or ([" "] if blanc_ajoute else [])
            courant.texte.extend(entre)
            courant.zones.extend(None for _ in entre)
        blancs, blanc_ajoute = [], False
        if courant is not None:
            courant.texte.append(caractere.texte)
            courant.zones.append(caractere.zone if visible else None)
    fermer()
    return morceaux


def _recoller(gauche: Morceau, droite: Morceau) -> Morceau | None:
    """Étape 3 : un seul morceau si seul un petit blanc les sépare, None sinon."""
    hauteur = max(gauche.hauteur, droite.hauteur)
    blanc = droite.zone.x0 - gauche.zone.x1
    if not -0.5 * hauteur <= blanc <= SEUIL_COLONNE * hauteur:
        return None
    if blanc > SEUIL_MOT * hauteur:
        return Morceau(gauche.page, f"{gauche.texte} {droite.texte}", (*gauche.zones, None, *droite.zones))
    return Morceau(gauche.page, gauche.texte + droite.texte, gauche.zones + droite.zones)


def _lignes_visuelles(morceaux: Sequence[Morceau]) -> list[list[Morceau]]:
    """Les morceaux rangés par ligne visuelle, de haut en bas, chaque ligne de gauche à droite."""
    lignes: list[list[Morceau]] = []
    for morceau in sorted(morceaux, key=lambda m: m.zone.milieu_y):
        ligne = next((autre for autre in lignes if any(_meme_ligne(m.zone, morceau.zone) for m in autre)), None)
        if ligne is None:
            lignes.append([morceau])
        else:
            ligne.append(morceau)
    for ligne in lignes:
        ligne.sort(key=lambda m: m.zone.x0)
    lignes.sort(key=lambda ligne: min(m.zone.y0 for m in ligne))
    return lignes


def morceaux_du_flux(page: PageLue) -> list[Morceau]:
    """Les morceaux dans l'ordre où PDFium lit le flux du PDF, celui d'un texte suivi en colonnes ;
    deux morceaux qui se suivent sur la même ligne visuelle, séparés d'un petit blanc, sont
    recollés comme à l'étape 3."""
    morceaux: list[Morceau] = []
    for morceau in _morceaux_bruts(page):
        if morceaux and _meme_ligne(morceaux[-1].zone, morceau.zone):
            ensemble = _recoller(morceaux[-1], morceau)
            if ensemble is not None:
                morceaux[-1] = ensemble
                continue
        morceaux.append(morceau)
    return morceaux


def morceaux_de_page(page: PageLue) -> list[list[Morceau]]:
    """Les lignes visuelles de la page, chacune faite de ses morceaux de gauche à droite."""
    lignes: list[list[Morceau]] = []
    for ligne in _lignes_visuelles(_morceaux_bruts(page)):
        recollee: list[Morceau] = [ligne[0]]
        for morceau in ligne[1:]:
            ensemble = _recoller(recollee[-1], morceau)
            if ensemble is None:
                recollee.append(morceau)
            else:
                recollee[-1] = ensemble
        lignes.append(recollee)
    return lignes
