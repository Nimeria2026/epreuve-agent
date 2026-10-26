"""Chaque contrôle des tâches est-il testé sur au moins une réponse juste et une fausse ?

    uv run --all-packages python 09_outillage/scripts/couverture_controles.py    # make couverture

Lance les tests d'EASE en notant, pour chaque contrôle de chaque tâche, les scores qu'il a
rendus. Un contrôle qui n'a jamais rendu 1, ou jamais moins de 1, n'est pas couvert. Code de
sortie 1 s'il en manque. Premier passage le 2026-10-06 (JOURNAL, cinquante-septième entrée) ; le jeu
« documents » de l'étape 6 y entre le 2026-10-10.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

RACINE = Path(__file__).resolve().parents[2]


class Releve:
    """Greffon pytest : enveloppe ease.verification.noter et garde les scores par contrôle."""

    def __init__(self) -> None:
        self.scores: defaultdict[str, set[float]] = defaultdict(set)

    def pytest_configure(self, config: pytest.Config) -> None:
        del config
        import ease.verification as verification

        noter = verification.noter

        def noter_et_relever(controle: Any, ctx: Any) -> tuple[float, str | None]:
            score, detail = noter(controle, ctx)
            self.scores[controle.model_dump_json()].add(score)
            return score, detail

        verification.noter = noter_et_relever


def main() -> int:
    releve = Releve()
    code = pytest.main(["-q", "-p", "no:cacheprovider", str(RACINE / "02_ease" / "tests")], plugins=[releve])
    if code != 0:
        print("Les tests échouent : couverture non mesurée.", file=sys.stderr)
        return 2
    from ease.taches import lire_taches, taches_documents, taches_dure

    manques = 0
    for tache in [*lire_taches(RACINE / "07_taches" / "public"), *taches_documents(RACINE), *taches_dure(RACINE)]:
        for numero, controle in enumerate(tache.controles, start=1):
            vus = releve.scores.get(controle.model_dump_json(), set())
            couvert = 1.0 in vus and any(s < 1.0 for s in vus)
            manques += not couvert
            etat = "couvert" if couvert else "NON COUVERT"
            print(f"{etat:12} {tache.identifiant} contrôle {numero} : {controle.etape}")
    print(f"\n{manques} contrôle(s) sans réponse juste et fausse testées.")
    return 1 if manques else 0


if __name__ == "__main__":
    sys.exit(main())
