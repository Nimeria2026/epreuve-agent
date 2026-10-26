"""Les zones contre l'image de la page : ce qu'un lecteur voit est dans une zone d'EKE.

PDFium rend la page comme un lecteur l'affiche, rotation comprise. Chaque pixel d'encre doit
tomber dans la zone d'un morceau, et chaque zone doit contenir de l'encre : une zone décalée,
retournée ou mise à la mauvaise échelle échoue ici, quelle que soit la façon dont elle a été
calculée.
"""

from __future__ import annotations

import pytest
from eke.contrat import racine_depot
from eke.geometrie import Zone
from eke.mise_en_page import morceaux_de_page
from eke.pdfium import Image, lire_pages, rendre_en_gris
from fabrique_pdf import PageDeTest, Texte, fabriquer_pdf

ECHELLE = 2
MARGE = 2
"""Pixels de tolérance autour d'une zone : l'anticrénelage déborde d'un pixel."""
ENCRE = bytes(1 if gris < 160 else 0 for gris in range(256))
"""Table qui marque 1 un pixel assez sombre pour être de l'encre, 0 sinon."""
DOSSIERS = racine_depot() / "05_pme" / "societes" / "calorelle" / "v3" / "dossiers"
PME = [
    "administration/factures_fournisseurs/2026-10/thermopieces-loire_f-2026-1151.pdf",
    "commercial/devis/2026/dv-2026-004.pdf",
    "clients/c-0088/contrats/contrat_entretien_c-0088.pdf",
    "administration/fournisseurs/garage-bessiere/rib_garage-bessiere.pdf",
]


def _encre_hors_zones(image: Image, zones: list[Zone]) -> list[tuple[int, int]]:
    """Les pixels d'encre qu'aucune zone ne couvre, et un pixel de chaque zone vide d'encre."""
    boites = [
        (
            max(0, int(z.x0 * ECHELLE) - MARGE),
            max(0, int(z.y0 * ECHELLE) - MARGE),
            min(image.largeur, int(z.x1 * ECHELLE) + MARGE + 1),
            min(image.hauteur, int(z.y1 * ECHELLE) + MARGE + 1),
        )
        for z in zones
    ]
    fautes: list[tuple[int, int]] = []
    encrees = [False] * len(boites)
    for y in range(image.hauteur):
        rangee = image.pixels[y * image.pas : y * image.pas + image.largeur].translate(ENCRE)
        couvertes = sorted((g, d, rang) for rang, (g, h, d, b) in enumerate(boites) if h <= y < b)
        debut = 0
        for gauche, droite, rang in couvertes:
            hors = rangee.find(1, debut, gauche)
            if hors != -1:
                fautes.append((hors, y))
            encrees[rang] = encrees[rang] or rangee.find(1, gauche, droite) != -1
            debut = max(debut, droite)
        hors = rangee.find(1, debut)
        if hors != -1:
            fautes.append((hors, y))
    fautes += [(g, h) for (g, h, _, _), encree in zip(boites, encrees, strict=True) if not encree]
    return fautes


def _verifier(donnees: bytes) -> None:
    for page in lire_pages(donnees):
        zones = [m.zone for ligne in morceaux_de_page(page) for m in ligne]
        image = rendre_en_gris(donnees, page.numero, ECHELLE)
        assert (image.largeur, image.hauteur) == (round(page.largeur * ECHELLE), round(page.hauteur * ECHELLE))
        assert zones
        assert _encre_hors_zones(image, zones) == []


@pytest.mark.parametrize("chemin", PME)
def test_l_encre_des_pdf_de_la_pme_est_dans_les_zones(chemin: str) -> None:
    _verifier((DOSSIERS / chemin).read_bytes())


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_l_encre_d_une_page_tournee_est_dans_les_zones(rotation: int) -> None:
    largeur, hauteur = (595, 842) if rotation in (0, 180) else (842, 595)
    textes = [
        Texte(56, hauteur - 60, "FACTURE", taille=18, police="F2", creneau=-120),
        Texte(largeur - 200, hauteur - 60, "N° FA-2026-0042", taille=10),
        Texte(56, hauteur - 140, "Total TTC"),
        Texte(largeur - 120, hauteur - 140, "189,90 €"),
        Texte(56, 40, "Échéance : 1er décembre 2026", taille=8),
    ]
    # Une feuille à la française dans le PDF (595 × 842), affichée à l'italienne si elle tourne
    # d'un quart de tour.
    page = PageDeTest(textes, mediabox=(30, 40, 625, 882), rotation=rotation)
    _verifier(fabriquer_pdf([page]))


def test_une_zone_decalee_serait_prise() -> None:
    """Le test se mesure lui-même : décaler les zones de 10 points fait apparaître des fautes."""
    donnees = (DOSSIERS / PME[0]).read_bytes()
    page = lire_pages(donnees)[0]
    zones = [
        Zone(m.zone.x0 + 10, m.zone.y0, m.zone.x1 + 10, m.zone.y1) for ligne in morceaux_de_page(page) for m in ligne
    ]
    assert _encre_hors_zones(rendre_en_gris(donnees, 1, ECHELLE), zones) != []
