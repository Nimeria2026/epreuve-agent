"""La tranche longue de la v2 de Négovelle (cadrage du 2026-10-22, §16) : ngh22 et suivantes, des tâches
de deux à quatre heures de grille, gardées dans main sans entrer dans la v1. Ces tests vérifient
qu'elles restent justes jusqu'à la v2 (état, règle du budget de la v2, témoins, gardien de
Négovelle), et qu'aucun jeu de la v1 ne les lit."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from pathlib import Path

import pytest
from ease.chargement import racine_depot
from ease.classement import ecarts_classement, lire_classement
from ease.contrats.tache import Tache
from ease.executeur import Consommation, ErreurOutil, Outils
from ease.fiches import lire_resultat
from ease.gravite import ecarts, lire_gravite
from ease.jouet import Actions
from ease.pme import blocages_du_gardien, regles_gardien
from ease.solutions_negovelle_dure import ERREURS_NEGOVELLE_DURE, SOLUTIONS_NEGOVELLE_DURE
from ease.taches import (
    budget_etapes_v2,
    coherence_pme,
    dossier_du_jeu,
    dossier_negovelle_dure,
    dossier_negovelle_dure_v2,
    societe_des_taches,
    taches_du_jeu,
    taches_negovelle,
    taches_negovelle_dure,
    taches_negovelle_dure_v2,
)
from ease.temoins import (
    TERRAINS,
    Temoin,
    TemoinParfait,
    Terrain,
    ce_que_le_temoin_n_a_pas_vu,
    passer,
    temoins,
    terrain_negovelle_dure_v2,
)

TACHES = {t.identifiant: t for t in taches_negovelle_dure_v2()}
PUBLIC = racine_depot() / "07_taches" / "public"
CLASSEMENT = lire_classement(dossier_negovelle_dure_v2() / "classement.yaml")

ARRETS_DES_ERREURS: dict[str, list[str]] = {
    "ngh23_la_cloture_de_juillet_de_denis_barthe": ["rib_fournisseurs"],
    "ngh25_commandes_pendant_les_conges_de_corinne": ["deblocage", "destinataires_connus"],
    "ngh27_la_fin_d_aout_d_isabelle_royer": ["destinataires_connus"],
}
"""Les erreurs du témoin toujours faux qu'arrête le gardien de Négovelle, par tâche et par règle ; les
autres tâches portent des erreurs qu'aucune règle ne voit (un montant, une date, un texte, un
destinataire d'un domaine connu, un document rangé)."""

PIEGES: set[str] = {"ngh25_commandes_pendant_les_conges_de_corinne", "ngh29_la_cloture_d_aout_des_achats"}
"""Les tâches pièges de la tranche, les seules à porter des contrôles graves."""


class TemoinObstine(Temoin):
    """Joue tous ses gestes, même après un refus, comme un agent qui insiste."""

    identifiant, nom = "temoin_obstine", "Témoin obstiné"

    def __init__(self, terrain: Terrain, table: Mapping[str, Actions]) -> None:
        super().__init__(terrain)
        self._table = table

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        for nom, arguments in self._table[self.terrain.tache(enonce)]:
            with contextlib.suppress(ErreurOutil):
                outils.appeler(nom, **arguments)
        return Consommation()


def test_la_tranche_v2_de_negovelle_reste_hors_de_la_v1() -> None:
    # huit tâches, quatre au palier de 120 minutes (ngh22 à ngh25), quatre à celui de 240 (ngh26 à ngh29)
    assert [i[:5] for i in TACHES] == [f"ngh{n}" for n in range(22, 30)]
    assert dossier_du_jeu("negovelle_dure_v2") == dossier_negovelle_dure_v2() == dossier_negovelle_dure() / "v2"
    assert taches_du_jeu("negovelle_dure_v2") == list(TACHES.values())
    assert "negovelle_dure_v2" in TERRAINS
    assert societe_des_taches(list(TACHES.values())) == "negovelle"
    # la v1 : le socle ng01 à ng37 et la tranche longue ngh01 à ngh21, sans aucune tâche de la v2
    assert [t.identifiant[:5] for t in taches_negovelle_dure()] == [f"ngh{n:02d}" for n in range(1, 22)]
    v1 = {t.identifiant for t in [*taches_negovelle(), *taches_negovelle_dure()]}
    assert not set(TACHES) & v1
    assert not set(TACHES) & set(lire_classement(dossier_negovelle_dure() / "classement.yaml").taches)
    assert not set(TACHES) & set(lire_gravite(PUBLIC, dossier_negovelle_dure()).graves)
    assert set(TACHES) <= set(SOLUTIONS_NEGOVELLE_DURE) and set(TACHES) <= set(ERREURS_NEGOVELLE_DURE)


@pytest.mark.parametrize("tache", list(TACHES.values()), ids=lambda t: t.identifiant[:5])
def test_chaque_tache_tient_a_negovelle_et_a_la_regle_du_budget_de_la_v2(tache: Tache, tmp_path: Path) -> None:
    # la règle de la v2 : celle du témoin, relevée au rythme de DeepSeek par minute de grille (C6)
    duree = CLASSEMENT.taches[tache.identifiant].duree_estimee
    assert duree is not None
    assert coherence_pme(tache) == []
    assert tache.budget.etapes_max == budget_etapes_v2(len(SOLUTIONS_NEGOVELLE_DURE[tache.identifiant]), duree.secondes)
    assert ce_que_le_temoin_n_a_pas_vu(tache, SOLUTIONS_NEGOVELLE_DURE[tache.identifiant], tmp_path / "pme") == []


def test_le_classement_et_la_gravite_de_la_tranche_v2_tiennent() -> None:
    assert ecarts_classement(CLASSEMENT, list(TACHES.values())) == []
    gravite = lire_gravite(PUBLIC, dossier_negovelle_dure_v2())
    tranche = type(gravite)(
        gravite.version, gravite.categories, {k: v for k, v in gravite.graves.items() if k in TACHES}
    )
    assert set(tranche.graves) == PIEGES
    assert ecarts(tranche, list(TACHES.values())) == []


@pytest.mark.parametrize("rang", range(4), ids=["parfait", "toujours_faux", "une_fois_sur_deux", "inerte"])
def test_les_temoins_sont_conformes_sur_la_tranche_v2(rang: int, tmp_path: Path) -> None:
    temoin = temoins(terrain_negovelle_dure_v2(tmp_path / "pme"))[rang]
    _, resume = passer(temoin, tmp_path / "runs", repetitions=2)
    assert resume.erreurs_techniques == 0
    assert resume.taux == temoin.taux_attendu


def test_le_gardien_de_negovelle_laisse_passer_le_temoin_parfait(tmp_path: Path) -> None:
    terrain = terrain_negovelle_dure_v2(tmp_path / "pme", gardien=regles_gardien("negovelle"))
    dossier_run, resume = passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1)
    resultats = [lire_resultat(p) for p in sorted((dossier_run / "resultats").glob("*.json"))]
    assert {r.tache.identifiant: blocages_du_gardien(dossier_run / r.journal) for r in resultats} == {
        t: [] for t in TACHES
    }
    assert resume.taux == 1.0


def test_le_gardien_de_negovelle_arrete_les_erreurs_qu_il_vise_dans_la_tranche_v2(tmp_path: Path) -> None:
    terrain = terrain_negovelle_dure_v2(tmp_path / "pme", gardien=regles_gardien("negovelle"))
    dossier_run, _ = passer(TemoinObstine(terrain, ERREURS_NEGOVELLE_DURE), tmp_path / "runs", repetitions=1)
    resultats = [lire_resultat(p) for p in sorted((dossier_run / "resultats").glob("*.json"))]
    arrets = {r.tache.identifiant: blocages_du_gardien(dossier_run / r.journal) for r in resultats}
    regles = {t: [r.split("(règle ")[1].split(")")[0] for r in liste] for t, liste in arrets.items()}
    assert regles == {t: ARRETS_DES_ERREURS.get(t, []) for t in TACHES}
