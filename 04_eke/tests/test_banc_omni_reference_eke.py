"""La forme canonique et l'aplatissement d'OmniExtractBench refaits dans EKE, contre l'original :
`cas_omniextractbench.json` garde la clé que `canon_key` (omni-extract-bench 0.1.7) donne à 3 819
valeurs synthétiques et l'aplatissement de quatre vérités synthétiques.

Ces cas sont écrits par `original/omni/cas_de_reference.py`, dans un environnement jetable hors du
dépôt (`original/omni/README.md`) : aucun texte du jeu n'y entre. La comparaison sur les 620
documents se fait par `original/omni/verifier_contre_original.py`.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from eke.banc_public.omni.valeurs import cle
from eke.banc_public.omni.verite import valeurs_de_la_verite

CAS = Path(__file__).parent / "cas_omniextractbench.json"


@cache
def _cas() -> dict[str, Any]:
    return json.loads(CAS.read_text(encoding="utf-8"))


def _cles() -> list[Any]:
    return list(_cas()["cles"])


@pytest.mark.parametrize(("type_", "valeur", "attendue"), _cles())
def test_cle_comme_canon_key(type_: str, valeur: Any, attendue: str) -> None:
    assert type(valeur).__name__ == type_
    assert cle(valeur) == attendue


@pytest.mark.parametrize(("verite", "schema", "attendu"), list(_cas()["verites"]))
def test_aplatissement_comme_flatten(verite: Any, schema: dict[str, Any], attendu: list[Any]) -> None:
    obtenu = [[[list(etape) for etape in a], v] for a, v in valeurs_de_la_verite(verite, schema).items()]
    assert obtenu == attendu
