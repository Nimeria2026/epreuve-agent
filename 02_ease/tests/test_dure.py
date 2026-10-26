"""La tranche dure (cadrage du 2026-10-14 ; JOURNAL, entrées 130 et 131) : des tâches longues, faites
d'un vrai travail enchaîné, à part du socle des 45 tâches publiques."""

from __future__ import annotations

from pathlib import Path

import pytest
from ease.chargement import racine_depot
from ease.classement import ecarts_classement, lire_classement
from ease.contrats.tache import Tache
from ease.gravite import ecarts, lire_gravite
from ease.solutions_dure import ERREURS_DURE, SOLUTIONS_DURE
from ease.taches import budget_etapes, coherence_pme, dossier_dure, lire_taches, taches_dure, taches_dure_v2
from ease.temoins import ce_que_le_temoin_n_a_pas_vu, passer, temoins, terrain_dure

TACHES = {t.identifiant: t for t in taches_dure()}
PUBLIC = racine_depot() / "07_taches" / "public"


def test_la_tranche_est_a_part_du_socle_et_chaque_tache_a_son_temoin() -> None:
    assert TACHES and all(t.identifiant.startswith("h") for t in TACHES.values())
    assert not set(TACHES) & {t.identifiant for t in lire_taches(PUBLIC)}
    # les gestes de la tranche longue de la v2 sont dans le même module (test_dure_v2)
    avec_v2 = sorted([*TACHES, *(t.identifiant for t in taches_dure_v2())])
    assert sorted(SOLUTIONS_DURE) == avec_v2 == sorted(ERREURS_DURE)


@pytest.mark.parametrize("tache", list(TACHES.values()), ids=lambda t: t.identifiant[:3])
def test_chaque_tache_tient_a_la_pme_et_a_la_regle_du_budget(tache: Tache, tmp_path: Path) -> None:
    assert coherence_pme(tache) == []
    assert tache.budget.etapes_max == budget_etapes(len(SOLUTIONS_DURE[tache.identifiant]))
    assert ce_que_le_temoin_n_a_pas_vu(tache, SOLUTIONS_DURE[tache.identifiant], tmp_path / "pme") == []


def test_le_classement_et_la_gravite_de_la_tranche_tiennent() -> None:
    assert ecarts_classement(lire_classement(dossier_dure() / "classement.yaml"), list(TACHES.values())) == []
    gravite = lire_gravite(PUBLIC, dossier_dure())
    tranche = type(gravite)(
        gravite.version, gravite.categories, {k: v for k, v in gravite.graves.items() if k in TACHES}
    )
    assert ecarts(tranche, list(TACHES.values())) == []


@pytest.mark.parametrize("rang", range(4), ids=["parfait", "toujours_faux", "une_fois_sur_deux", "inerte"])
def test_les_temoins_sont_conformes_sur_la_tranche(rang: int, tmp_path: Path) -> None:
    temoin = temoins(terrain_dure(tmp_path / "pme"))[rang]
    _, resume = passer(temoin, tmp_path / "runs", repetitions=2)
    assert resume.erreurs_techniques == 0
    assert resume.taux == temoin.taux_attendu
