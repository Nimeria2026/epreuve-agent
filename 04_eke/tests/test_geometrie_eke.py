"""Le repère de la page affichée : EKE convertit comme PDFium, pour toute boîte et toute rotation."""

from __future__ import annotations

import pytest
from eke.geometrie import Repere, Zone, union, zone_de_points
from eke.pdfium import lire_pages, point_affiche
from fabrique_pdf import PageDeTest, Texte, fabriquer_pdf

ROTATIONS = (0, 90, 180, 270)
POINTS_PDF = [(40.0, 50.0), (600.0, 860.0), (150.0, 700.0), (333.3, 444.4), (41.5, 859.0)]


def _pages_tournees() -> bytes:
    """Une page par rotation, MediaBox et CropBox qui ne commencent pas en 0."""
    return fabriquer_pdf(
        [
            PageDeTest([Texte(20, 20, "Repère")], mediabox=(20, 30, 620, 880), cropbox=(40, 50, 600, 860), rotation=r)
            for r in ROTATIONS
        ]
    )


@pytest.mark.parametrize("rang", range(len(ROTATIONS)))
def test_eke_convertit_comme_pdfium(rang: int) -> None:
    donnees = _pages_tournees()
    page = lire_pages(donnees)[rang]
    assert page.repere.rotation == ROTATIONS[rang]
    for x, y in POINTS_PDF:
        attendu = point_affiche(donnees, page.numero, x, y)
        obtenu = page.repere.vers_affichage(x, y)
        assert obtenu == pytest.approx(attendu, abs=1.0), (x, y)


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_taille_affichee_et_aller_retour(rotation: int) -> None:
    repere = Repere(40, 50, 600, 860, rotation)
    assert (repere.largeur, repere.hauteur) == ((560, 810) if rotation in (0, 180) else (810, 560))
    for x, y in POINTS_PDF:
        assert repere.vers_pdf(*repere.vers_affichage(x, y)) == pytest.approx((x, y))
    coin_haut_gauche = repere.vers_pdf(0, 0)
    assert repere.vers_affichage(*coin_haut_gauche) == pytest.approx((0, 0))


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_une_zone_fait_l_aller_retour(rotation: int) -> None:
    repere = Repere(40, 50, 600, 860, rotation)
    zone = repere.zone_affichee(100, 200, 180, 212)
    assert zone.x0 <= zone.x1 and zone.y0 <= zone.y1
    assert repere.rectangle_pdf(zone) == pytest.approx((100, 200, 180, 212))


def test_repere_refuse_une_rotation_ou_une_boite_impossibles() -> None:
    with pytest.raises(ValueError, match="rotation"):
        Repere(0, 0, 595, 842, 45)
    with pytest.raises(ValueError, match="vide"):
        Repere(0, 0, 0, 842)


def test_zones() -> None:
    a, b = Zone(10, 10, 20, 20), Zone(15, 18, 30, 25)
    assert union([a, b]) == Zone(10, 10, 30, 25)
    assert a.chevauchement_vertical(b) == 2
    assert a.chevauchement_vertical(Zone(0, 30, 5, 40)) == 0
    assert union([a, b]).contient(a) and not a.contient(b)
    assert zone_de_points(5, 9, 1, 2) == Zone(1, 2, 5, 9)
    assert Zone(1.234, 2.345, 3.456, 4.567).en_contrat() == {"x0": 1.23, "y0": 2.35, "x1": 3.46, "y1": 4.57}
    with pytest.raises(ValueError):
        union([])
