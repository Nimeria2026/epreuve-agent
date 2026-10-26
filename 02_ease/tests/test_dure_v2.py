"""La tranche longue de la v2 de Calorelle (cadrage du 2026-10-22 ; JOURNAL, entrées 250 et 256) :
h13 et suivantes, des tâches de deux à quatre heures de grille, gardées dans main sans entrer dans
la v1. Ces tests vérifient qu'elles restent justes jusqu'à la v2, et qu'aucun jeu de la v1 ne les
lit."""

from __future__ import annotations

from pathlib import Path

import pytest
from ease.chargement import racine_depot
from ease.classement import ecarts_classement, lire_classement
from ease.contrats.tache import Tache
from ease.gravite import ecarts, lire_gravite
from ease.solutions_dure import SOLUTIONS_DURE
from ease.taches import (
    budget_etapes_v2,
    coherence_pme,
    dossier_du_jeu,
    dossier_dure,
    dossier_dure_v2,
    lire_taches,
    taches_du_jeu,
    taches_dure,
    taches_dure_v2,
)
from ease.temoins import TERRAINS, ce_que_le_temoin_n_a_pas_vu, passer, temoins, terrain_dure_v2

TACHES = {t.identifiant: t for t in taches_dure_v2()}
PUBLIC = racine_depot() / "07_taches" / "public"
CLASSEMENT = lire_classement(dossier_dure_v2() / "classement.yaml")


def test_la_tranche_v2_reste_hors_de_la_v1() -> None:
    assert [i[:3] for i in TACHES] == [f"h{n}" for n in range(13, 21)]
    assert dossier_du_jeu("dure_v2") == dossier_dure_v2() == dossier_dure() / "v2"
    assert taches_du_jeu("dure_v2") == list(TACHES.values())
    assert "dure_v2" in TERRAINS
    # la v1 : la tranche dure h01 à h12 et le socle t01 à t63, sans aucune tâche de la v2
    assert [t.identifiant[:3] for t in taches_dure()] == [f"h{n:02d}" for n in range(1, 13)]
    v1 = {t.identifiant for t in [*taches_dure(), *lire_taches(PUBLIC)]}
    assert not set(TACHES) & v1
    assert not set(TACHES) & set(lire_classement(dossier_dure() / "classement.yaml").taches)
    assert not set(TACHES) & set(lire_gravite(PUBLIC, dossier_dure()).graves)


@pytest.mark.parametrize("tache", list(TACHES.values()), ids=lambda t: t.identifiant[:3])
def test_chaque_tache_tient_a_la_pme_et_a_la_regle_du_budget(tache: Tache, tmp_path: Path) -> None:
    # la règle de la v2 : celle du témoin, relevée au rythme de DeepSeek par minute de grille (C6)
    duree = CLASSEMENT.taches[tache.identifiant].duree_estimee
    assert duree is not None
    assert coherence_pme(tache) == []
    assert tache.budget.etapes_max == budget_etapes_v2(len(SOLUTIONS_DURE[tache.identifiant]), duree.secondes)
    assert ce_que_le_temoin_n_a_pas_vu(tache, SOLUTIONS_DURE[tache.identifiant], tmp_path / "pme") == []


def test_le_classement_et_la_gravite_de_la_tranche_v2_tiennent() -> None:
    assert ecarts_classement(lire_classement(dossier_dure_v2() / "classement.yaml"), list(TACHES.values())) == []
    gravite = lire_gravite(PUBLIC, dossier_dure_v2())
    tranche = type(gravite)(
        gravite.version, gravite.categories, {k: v for k, v in gravite.graves.items() if k in TACHES}
    )
    assert set(tranche.graves) == {"h16_la_boite_de_patrick", "h20_la_fin_d_annee_de_karim"}
    assert ecarts(tranche, list(TACHES.values())) == []


@pytest.mark.parametrize("rang", range(4), ids=["parfait", "toujours_faux", "une_fois_sur_deux", "inerte"])
def test_les_temoins_sont_conformes_sur_la_tranche_v2(rang: int, tmp_path: Path) -> None:
    temoin = temoins(terrain_dure_v2(tmp_path / "pme"))[rang]
    _, resume = passer(temoin, tmp_path / "runs", repetitions=2)
    assert resume.erreurs_techniques == 0
    assert resume.taux == temoin.taux_attendu
