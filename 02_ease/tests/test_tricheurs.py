"""Témoins tricheurs, étape 4 : chaque tâche visée doit faire échouer chaque triche.

Le 2026-10-06, les six triches passaient toutes (JOURNAL, quarante-troisième entrée). t03 en
version 4 fait tomber « copie_a_tous » ; t01 en version 4 et t02 en version 5 font tomber
« spam_interne » (décision d'Alexandre, quarante-quatrième entrée). Les trois « bourrage »
ne tombent que par le juge (entrées quarante-huit à cinquante-et-une), rejoué ici depuis les
verdicts enregistrés par make verdicts-temoins, sans appel à l'API. Tant que ce fichier
n'existe pas, elles restent marquées « échec attendu », de façon stricte.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ease.fiches import lire_resultat
from ease.solutions_pme import TRICHEURS_PME
from ease.temoins import (
    VERDICTS_TEMOINS,
    TemoinParfait,
    TemoinToujoursFaux,
    juge_rejoue,
    passer,
    terrain_pme,
    tricheur_pme,
)

JUGE = "attend les verdicts du juge sur les témoins : make verdicts-temoins"
SANS_VERDICTS = not VERDICTS_TEMOINS.is_file()

FUITES = (
    {
        ("bourrage", "t02_envoyer_copie_contrat"): JUGE,
        ("bourrage", "t04_date_prochain_entretien"): JUGE,
        ("bourrage", "t05_piege_changement_rib"): JUGE,
    }
    if SANS_VERDICTS
    else {}
)

CAS = [
    pytest.param(
        triche,
        tache,
        id=f"{triche}-{tache[:3]}",
        marks=[pytest.mark.xfail(strict=True, reason=FUITES[(triche, tache)])] if (triche, tache) in FUITES else [],
    )
    for triche, table in TRICHEURS_PME.items()
    for tache in table
]

_reussites: dict[str, dict[str, bool]] = {}


def _reussites_de(triche: str, dossier: Path) -> dict[str, bool]:
    """Une exécution de chaque tâche visée par la triche, jouée une seule fois par session de tests."""
    if triche not in _reussites:
        temoin = tricheur_pme(triche, dossier / "pme")
        dossier_run, _ = passer(temoin, dossier / "runs", repetitions=1, juge=juge_rejoue())
        resultats = [lire_resultat(p) for p in (dossier_run / "resultats").glob("*.json")]
        _reussites[triche] = {r.tache.identifiant: r.reussie for r in resultats}
    return _reussites[triche]


@pytest.mark.parametrize(("triche", "tache"), CAS)
def test_chaque_triche_echoue(triche: str, tache: str, tmp_path_factory: pytest.TempPathFactory) -> None:
    reussites = _reussites_de(triche, tmp_path_factory.mktemp(triche))
    assert reussites[tache] is False


@pytest.mark.skipif(SANS_VERDICTS, reason=JUGE)
def test_avec_le_juge_le_parfait_reussit_tout_et_le_toujours_faux_rien(tmp_path: Path) -> None:
    terrain = terrain_pme(tmp_path / "pme")
    _, parfait = passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1, juge=juge_rejoue())
    _, faux = passer(TemoinToujoursFaux(terrain), tmp_path / "runs", repetitions=1, juge=juge_rejoue())
    assert (parfait.taux, faux.taux) == (1.0, 0.0)
