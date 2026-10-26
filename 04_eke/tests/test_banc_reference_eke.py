"""La métrique de fr-bench-pdf2md refaite dans EKE, contre le code original : 619 cas synthétiques
dont `cas_fr_bench_pdf2md.json` garde le résultat que leur donnent rapidfuzz 3.14.3,
html-to-markdown 2.20.0, unidecode 1.4.0 et `benchmark_tsts.py` (commit `ceab1548`).

Ces cas sont écrits par `original/cas_de_reference.py`, dans un environnement jetable hors du
dépôt (`original/README.md`) : aucun texte du jeu n'y entre. La comparaison sur les sorties réelles
d'EKE se fait par `original/verifier_contre_original.py`.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from eke.banc_public import flou
from eke.banc_public.html_markdown import EntreeRefusee, convertir
from eke.banc_public.metrique import correspondances, evaluer, normaliser, options_du_test

CAS = Path(__file__).parent / "cas_fr_bench_pdf2md.json"


@cache
def _cas() -> dict[str, Any]:
    return json.loads(CAS.read_text(encoding="utf-8"))


def _rubrique(nom: str) -> list[Any]:
    return list(_cas()[nom])


@pytest.mark.parametrize(("a", "b", "attendu"), _rubrique("partial_ratio"))
def test_partial_ratio_comme_rapidfuzz(a: str, b: str, attendu: float) -> None:
    assert flou.partial_ratio(a, b) == attendu


@pytest.mark.parametrize(("a", "b", "attendu"), _rubrique("ratio"))
def test_ratio_comme_rapidfuzz(a: str, b: str, attendu: float) -> None:
    assert flou.ratio(a, b) == attendu


@pytest.mark.parametrize(("a", "b", "attendu"), _rubrique("levenshtein"))
def test_levenshtein_comme_rapidfuzz(a: str, b: str, attendu: int) -> None:
    assert flou.levenshtein(a, b) == attendu


@pytest.mark.parametrize(("motif", "texte", "plafond", "debuts"), _rubrique("correspondances"))
def test_correspondances_comme_find_near_matches(motif: str, texte: str, plafond: int, debuts: list[int]) -> None:
    assert correspondances(motif, texte, plafond) == debuts


@pytest.mark.parametrize(("texte", "attendu"), _rubrique("convert_to_markdown"))
def test_convert_to_markdown_comme_l_original(texte: str, attendu: str | None) -> None:
    if attendu is None:
        with pytest.raises(EntreeRefusee):
            convertir(texte)
    else:
        assert convertir(texte) == attendu


@pytest.mark.parametrize(("options", "texte", "attendu"), _rubrique("normalise"))
def test_normalise_comme_l_original(options: dict[str, Any], texte: str, attendu: str) -> None:
    assert normaliser(options_du_test(options), texte) == attendu


@pytest.mark.parametrize("cas", _rubrique("tests"), ids=lambda c: f"{c['test']['id']}-{c['test']['type']}")
def test_chaque_test_du_banc_comme_l_original(cas: dict[str, Any]) -> None:
    assert evaluer(cas["test"], cas["contenu"]) is cas["reussi"]


def test_les_cas_couvrent_chaque_type_et_chaque_issue() -> None:
    vus = {(c["test"]["type"], c["reussi"]) for c in _rubrique("tests")}
    for sorte in ("present", "absent", "order", "table", "baseline"):
        assert (sorte, True) in vus
        assert (sorte, False) in vus
    assert any(len(a) > 64 and attendu not in (0, 100) for a, _, attendu in _rubrique("partial_ratio"))
