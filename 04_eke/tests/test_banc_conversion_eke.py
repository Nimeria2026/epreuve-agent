"""Le Markdown simple d'EKE pour le banc public, et le chargement des pages et des tests du jeu.

Les PDF viennent de `fabrique_pdf` : deux colonnes de texte suivi, écrites colonne après colonne
dans le flux du PDF, comme le font les logiciels de mise en page. PDFium les rend dans cet ordre,
et `lire_document` aussi depuis la seizième entrée du journal de l'étape 6 ; les lignes visuelles
d'EKE, que garde `extraire_valeurs`, lisent la page d'une traite, d'une colonne à l'autre.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eke.banc_public.conversion import (
    VARIANTES,
    chemin_sortie,
    convertir_jeu,
    lire_sortie,
    markdown_flux,
    markdown_lignes,
    markdown_pdfium,
)
from eke.banc_public.jeu import categorie_publiee, charger
from eke.lecture import lire, sortie_lignes
from eke.pdfium import lire_pages
from fabrique_pdf import PageDeTest, Texte, fabriquer_pdf


def _deux_colonnes() -> bytes:
    gauche = ["Le conseil municipal", "a voté le budget", "de la commune."]
    droite = ["La séance est levée", "à vingt heures", "et quart."]
    textes = [Texte(56, 760 - 14 * i, ligne) for i, ligne in enumerate(gauche)]
    textes += [Texte(320, 760 - 14 * i, ligne) for i, ligne in enumerate(droite)]
    return fabriquer_pdf([PageDeTest(textes), PageDeTest([Texte(56, 760, "Seconde page.")])])


def test_les_lignes_d_eke_traversent_les_colonnes() -> None:
    assert markdown_lignes(_deux_colonnes()) == (
        "Le conseil municipal La séance est levée\n"
        "a voté le budget à vingt heures\n"
        "de la commune. et quart.\n\n"
        "Seconde page."
    )


def test_pdfium_garde_l_ordre_du_flux() -> None:
    texte = markdown_pdfium(_deux_colonnes())
    assert texte.split("\n\n") == [
        "Le conseil municipal\na voté le budget\nde la commune.\nLa séance est levée\nà vingt heures\net quart.",
        "Seconde page.",
    ]


def test_le_flux_d_eke_garde_les_colonnes() -> None:
    assert markdown_flux(_deux_colonnes()) == (
        "Le conseil municipal\na voté le budget\nde la commune.\nLa séance est levée\nà vingt heures\net quart.\n\n"
        "Seconde page."
    )


def test_lire_document_suit_les_colonnes() -> None:
    lignes = sortie_lignes(lire("deux_colonnes.pdf", _deux_colonnes()))["lignes"]
    assert [ligne["texte"] for ligne in lignes][:4] == [
        "Le conseil municipal",
        "a voté le budget",
        "de la commune.",
        "La séance est levée",
    ]


def test_le_flux_recolle_deux_objets_d_une_meme_ligne() -> None:
    page = PageDeTest(
        [Texte(56, 760, "Total"), Texte(87, 760, "TTC :"), Texte(300, 760, "189,90 €"), Texte(56, 740, "fin")]
    )
    assert markdown_flux(fabriquer_pdf([page])) == "Total TTC : 189,90 €\nfin"


def test_le_trait_d_union_de_coupure_se_lit_comme_il_est_trace() -> None:
    page = PageDeTest(
        [
            Texte(56, 760, "un exam-"),
            Texte(56, 746, "ple de coupure"),
            Texte(56, 720, "mot\u00ad"),
            Texte(56, 706, "suite"),
            Texte(56, 680, "pas-de-coupure ici"),
        ]
    )
    donnees = fabriquer_pdf([page])
    texte = "".join(c.texte for c in lire_pages(donnees)[0].caracteres)
    assert "\x02" not in texte
    assert texte.count("-") == 4
    assert markdown_lignes(donnees).split("\n") == ["un exam-", "ple de coupure", "mot-", "suite", "pas-de-coupure ici"]


@pytest.mark.parametrize("variante", sorted(VARIANTES))
def test_un_fichier_illisible_rend_un_texte_vide(variante: str) -> None:
    assert VARIANTES[variante](b"pas un PDF") == ""
    assert VARIANTES[variante](b"%PDF-1.4 tronque") == ""


def _jeu(racine: Path) -> None:
    page = racine / "pdfs" / "multi_column3" / "page à deux colonnes"
    page.mkdir(parents=True)
    (page / "page à deux colonnes.pdf").write_bytes(_deux_colonnes())
    (page / "metadata.json").write_text(json.dumps({"pdf": "page à deux colonnes.pdf", "page": 0}))
    tests = [
        {"pdf": "p.pdf", "page": 0, "id": "t0", "type": "present", "text": "budget", "category": "multicolumn",
         "first_n": None, "tags": ["x"], "max_diffs": 0},
        {"pdf": "p.pdf", "page": 0, "id": "t1", "type": "table", "cell": "1", "category": "long_table2"},
    ]  # fmt: skip
    (page / "tests.jsonl").write_text("\n".join(json.dumps(t) for t in tests) + "\n\n")
    (racine / "pdfs" / "vide").mkdir()


def test_le_jeu_se_charge_comme_le_banc_le_charge(tmp_path: Path) -> None:
    _jeu(tmp_path)
    pages = charger(tmp_path)
    assert [p.identifiant for p in pages] == ["multi_column3/page à deux colonnes"]
    premier, second = pages[0].tests
    assert premier["pdf_name"] == "page à deux colonnes.pdf"
    assert "first_n" not in premier and "tags" not in premier
    assert premier["pdf"] == "p.pdf"
    assert categorie_publiee(str(second["category"])) == "long_table"


def test_deux_pdf_dans_une_page_arretent_le_chargement(tmp_path: Path) -> None:
    _jeu(tmp_path)
    (tmp_path / "pdfs" / "multi_column3" / "page à deux colonnes" / "autre.pdf").write_bytes(b"%PDF-")
    with pytest.raises(ValueError, match="2 PDF"):
        charger(tmp_path)


def test_la_conversion_ecrit_une_sortie_utf8_par_page(tmp_path: Path) -> None:
    _jeu(tmp_path)
    pages = charger(tmp_path)
    durees = convertir_jeu(pages, "pdfium", tmp_path / "sorties", dire=lambda _: None)
    assert set(durees) == {"multi_column3/page à deux colonnes"}
    assert chemin_sortie(tmp_path / "sorties", "pdfium", pages[0]).name == "page à deux colonnes.md"
    assert lire_sortie(tmp_path / "sorties", "pdfium", pages[0]) == markdown_pdfium(pages[0].pdf.read_bytes())
