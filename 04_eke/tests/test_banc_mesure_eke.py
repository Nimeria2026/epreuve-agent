"""Les scores de la mesure sur le banc public et leurs marges ; la translittération et la
validation d'entrée de la métrique portée.

Les marges se vérifient sur des cas dont la réponse se connaît sans bootstrap : toutes les pages
pareilles (intervalle réduit à un point), écart nul entre deux lectures identiques.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from eke.banc_public import translitteration
from eke.banc_public.html_markdown import EntreeRefusee, balise_veritable, convertir, decoder_entites, valider
from eke.banc_public.jeu import Page
from eke.banc_public.mesure import (
    Resultat,
    bootstrap_ecart_pages,
    bootstrap_pages,
    ecarts,
    evaluer_page,
    quantile,
    scores,
)


def _resultats(reussites: dict[str, list[bool]], categorie: str = "tiny_text") -> list[Resultat]:
    return [
        Resultat(page, f"{page}-{i}", "present", categorie, reussi)
        for page, liste in reussites.items()
        for i, reussi in enumerate(liste)
    ]


def test_quantile_par_interpolation() -> None:
    assert quantile([0.0, 1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    assert quantile([0.0, 10.0], 0.25) == 2.5


def test_le_bootstrap_tire_des_pages_et_reste_reproductible() -> None:
    pages = [[True, True, False], [False], [True] * 5, [False, False]]
    assert bootstrap_pages(pages, tirages=500) == bootstrap_pages(pages, tirages=500)
    bas, haut = bootstrap_pages(pages, tirages=2000)
    assert 0.0 <= bas < 7 / 11 < haut <= 1.0
    assert bootstrap_pages([[True, False]] * 30, tirages=200) == (0.5, 0.5)


def test_un_score_par_categorie_publiee_puis_toutes_et_la_base() -> None:
    resultats = _resultats({"a": [True, False], "b": [True]}) + _resultats({"c": [False]}, "graphics")
    resultats += [Resultat("a", "a-b", "baseline", "baseline", True)]
    lignes = {s.categorie: s for s in scores(resultats)}
    assert list(lignes)[-2:] == ["toutes", "baseline"]
    assert (lignes["tiny_text"].tests, lignes["tiny_text"].reussis, lignes["tiny_text"].pages) == (3, 2, 2)
    assert lignes["toutes"].tests == 4 and lignes["toutes"].reussis == 2
    assert lignes["baseline"].score == 1.0


def test_l_ecart_apparie_de_deux_lectures_identiques_est_nul() -> None:
    a = {"p1": [True, False], "p2": [True]}
    assert bootstrap_ecart_pages(a, a, tirages=300) == (0.0, 0.0)
    b = {"p1": [True, True], "p2": [True]}
    bas, haut = bootstrap_ecart_pages(a, b, tirages=300)
    assert 0.0 <= bas <= haut <= 1.0
    with pytest.raises(ValueError, match="mêmes tests"):
        bootstrap_ecart_pages(a, {"p1": [True]}, tirages=10)


def test_les_ecarts_portent_sur_les_memes_tests() -> None:
    premiere = _resultats({"a": [False, False], "b": [True]})
    seconde = _resultats({"a": [True, False], "b": [True]})
    lignes = {e.categorie: e for e in ecarts(premiere, seconde)}
    assert lignes["tiny_text"].ecart == pytest.approx(1 / 3)
    assert lignes["toutes"].ecart == pytest.approx(1 / 3)


def test_chaque_test_de_la_page_porte_aussi_un_test_de_base() -> None:
    page = Page(
        "tiny_text1",
        "p",
        Path("p.pdf"),
        (
            {"id": "t0", "type": "present", "text": "budget", "category": "tiny_text"},
            {"id": "t1", "type": "table", "cell": "1", "category": "long_table2"},
        ),
    )
    resultats = evaluer_page(page, "Le budget est voté.")
    assert [(r.test, r.categorie, r.reussi) for r in resultats] == [
        ("t0", "tiny_text", True),
        ("t0-baseline", "baseline", True),
        ("t1", "long_table", False),
        ("t1-baseline", "baseline", True),
    ]


def test_translitteration_regle_et_exceptions() -> None:
    assert translitteration.translitterer("Élève à l’œuvre : 25 °C, 3 €") == "Eleve a l'oeuvre : 25 degC, 3 EUR"
    assert translitteration.translitterer_caractere("") == ""
    assert translitteration.translitterer_caractere("≠") == "≠"
    assert translitteration.non_verifies("é漢") == {"漢"}
    assert set(translitteration.EXCEPTIONS) <= translitteration.VERIFIES


def test_validation_d_entree_comme_html_to_markdown() -> None:
    valider("texte\x02avec une marque de coupure, assez long pour rester sous trente pour cent")
    for refuse in ("a\x00b", "%PDF-1.7", "\x01\x02\x03abc"):
        with pytest.raises(EntreeRefusee):
            convertir(refuse)


def test_automate_des_entites() -> None:
    assert decoder_entites("R&D &amp; S&amp;P") == "R&D &amp; S&P"
    assert decoder_entites("&lt;&#233;&#x41;&#+66;") == "<éAB"
    assert decoder_entites("&lesg; &#55296; &#x110000;") == "⋚ &#55296; &#x110000;"


def test_seule_une_vraie_balise_sort_du_portage_exact() -> None:
    assert not balise_veritable("x < 5 et y <= 6, R&D <5 %")
    assert balise_veritable("le ministre <b 's tra")
    assert balise_veritable("Paris<br>Lyon")
