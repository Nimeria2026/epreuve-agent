"""La mise en page sur des PDF qui ne ressemblent pas à ceux de Calorelle : colonnes, tailles,
crénage, objets texte dans le désordre, plusieurs pages, page tournée."""

from __future__ import annotations

from itertools import pairwise

import pytest
from eke.mise_en_page import Morceau, morceaux_de_page
from eke.pdfium import lire_pages
from fabrique_pdf import PageDeTest, Texte, fabriquer_pdf

LARGEUR_HELVETICA = {"T": 611, "o": 556, "t": 278, "a": 556, "l": 222}
"""Largeurs en millièmes de cadratin, métriques Adobe de Helvetica, pour placer un mot à la main."""


def _facture(rotation: int = 0) -> PageDeTest:
    """Une facture fictive en tableau : étiquettes à gauche, montants alignés à droite ; la feuille
    est à la française dans le PDF, affichée à l'italienne si elle tourne d'un quart de tour."""
    hauteur = 842 if rotation in (0, 180) else 595
    haut = hauteur - 60
    return PageDeTest(
        [
            Texte(56, haut, "FACTURE", taille=18, police="F2", creneau=-120),
            Texte(400, haut, "N° FA-2026-0042", taille=10),
            Texte(56, haut - 80, "Désignation", police="F2"),
            Texte(330, haut - 80, "Qté", police="F2"),
            Texte(480, haut - 80, "Montant HT", police="F2"),
            Texte(56, haut - 95, "Thermostat d'ambiance"),
            Texte(330, haut - 95, "2"),
            Texte(480, haut - 95, "180,00 €"),
            Texte(330, haut - 125, "Total HT"),
            Texte(480, haut - 125, "180,00 €"),
            Texte(330, haut - 140, "TVA 5,5 %"),
            Texte(480, haut - 140, "9,90 €"),
            Texte(330, haut - 155, "Total TTC :"),
            Texte(480, haut - 155, "189,90 €"),
            Texte(56, haut - 200, "Échéance : 1er décembre 2026", taille=9),
        ],
        rotation=rotation,
    )


FACTURE_ATTENDUE = [
    ["FACTURE", "N° FA-2026-0042"],
    ["Désignation", "Qté", "Montant HT"],
    ["Thermostat d'ambiance", "2", "180,00 €"],
    ["Total HT", "180,00 €"],
    ["TVA 5,5 %", "9,90 €"],
    ["Total TTC :", "189,90 €"],
    ["Échéance : 1er décembre 2026"],
]


def _textes(lignes: list[list[Morceau]]) -> list[list[str]]:
    return [[m.texte for m in ligne] for ligne in lignes]


def test_un_tableau_se_lit_ligne_par_ligne_et_colonne_par_colonne() -> None:
    page = lire_pages(fabriquer_pdf([_facture()]))[0]
    lignes = morceaux_de_page(page)
    assert _textes(lignes) == FACTURE_ATTENDUE
    for ligne in lignes:
        assert all(gauche.zone.x1 < droite.zone.x0 for gauche, droite in pairwise(ligne))
    assert all(haut[0].zone.y1 <= bas[0].zone.y0 for haut, bas in pairwise(lignes))


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_une_page_tournee_se_lit_comme_elle_s_affiche(rotation: int) -> None:
    """Le contenu tracé tourné, comme le font les logiciels pour une page à l'italienne."""
    droite = lire_pages(fabriquer_pdf([_facture(0)]))[0]
    tournee = lire_pages(fabriquer_pdf([_facture(rotation)]))[0]
    assert _textes(morceaux_de_page(tournee)) == FACTURE_ATTENDUE
    if rotation == 180:
        for a, b in zip(morceaux_de_page(droite), morceaux_de_page(tournee), strict=True):
            for m, n in zip(a, b, strict=True):
                assert n.zone.en_contrat() == pytest.approx(m.zone.en_contrat(), abs=0.05)


def test_une_boite_decalee_ne_change_rien() -> None:
    simple = lire_pages(fabriquer_pdf([_facture()]))[0]
    decalee = lire_pages(fabriquer_pdf([PageDeTest(_facture().textes, mediabox=(-100, 250, 495, 1092))]))[0]
    for a, b in zip(morceaux_de_page(simple), morceaux_de_page(decalee), strict=True):
        assert [m.texte for m in a] == [m.texte for m in b]
        for m, n in zip(a, b, strict=True):
            assert n.zone.en_contrat() == pytest.approx(m.zone.en_contrat(), abs=0.05)


def test_deux_objets_texte_sur_une_ligne_se_recollent_dans_l_ordre_de_lecture() -> None:
    """« Total » puis « TTC » tracés à l'envers, à une espace de distance : un seul morceau."""
    largeur_total = sum(LARGEUR_HELVETICA[c] for c in "Total") * 11 / 1000
    espace = 278 * 11 / 1000
    page = PageDeTest([Texte(56 + largeur_total + espace, 700, "TTC"), Texte(56, 700, "Total")])
    lignes = morceaux_de_page(lire_pages(fabriquer_pdf([page]))[0])
    assert _textes(lignes) == [["Total TTC"]]
    collees = PageDeTest([Texte(56 + largeur_total, 700, "TTC"), Texte(56, 700, "Total")])
    assert _textes(morceaux_de_page(lire_pages(fabriquer_pdf([collees]))[0])) == [["TotalTTC"]]


def test_plusieurs_pages_gardent_leur_numero() -> None:
    pages = [PageDeTest([Texte(56, 780, f"Page {n} sur 3"), Texte(56, 760, f"Article {n}.1")]) for n in (1, 2, 3)]
    for page in lire_pages(fabriquer_pdf(pages)):
        lignes = morceaux_de_page(page)
        assert _textes(lignes) == [[f"Page {page.numero} sur 3"], [f"Article {page.numero}.1"]]
        assert {m.page for ligne in lignes for m in ligne} == {page.numero}


def test_tailles_melees_sur_une_ligne_de_base() -> None:
    """Un mot en 18 points et un en 8 points, sur la même ligne de base : même ligne visuelle."""
    page = PageDeTest([Texte(56, 700, "Grand", taille=18), Texte(200, 700, "petit", taille=8)])
    assert _textes(morceaux_de_page(lire_pages(fabriquer_pdf([page]))[0])) == [["Grand", "petit"]]


def test_la_zone_d_un_passage_ignore_les_espaces() -> None:
    page = lire_pages(fabriquer_pdf([PageDeTest([Texte(56, 700, "Total TTC : 512,40 €")])]))[0]
    morceau = morceaux_de_page(page)[0][0]
    debut = morceau.texte.index("512")
    zone = morceau.zone_de(debut - 1, len(morceau.texte))
    assert zone == morceau.zone_de(debut, len(morceau.texte))
    assert morceau.zone.contient(zone)
    with pytest.raises(ValueError):
        morceau.zone_de(debut - 1, debut)


def test_une_page_sans_texte_ne_rend_rien() -> None:
    assert morceaux_de_page(lire_pages(fabriquer_pdf([PageDeTest([])]))[0]) == []
