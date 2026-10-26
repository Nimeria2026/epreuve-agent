"""La tranche longue de Domivelle (cadrage du 2026-10-15, section 8 ; JOURNAL, entrée 155) : ses
tâches tiennent à l'état et à la règle du budget, ses témoins mesurent ce qu'ils doivent, et le
gardien de Domivelle laisse passer le témoin parfait."""

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
from ease.solutions_domivelle_dure import ERREURS_DOMIVELLE_DURE, SOLUTIONS_DOMIVELLE_DURE
from ease.taches import (
    budget_etapes,
    coherence_pme,
    dossier_du_jeu,
    societe_de,
    taches_domivelle,
    taches_domivelle_dure,
    taches_domivelle_dure_v2,
)
from ease.temoins import (
    TERRAINS,
    Temoin,
    TemoinParfait,
    Terrain,
    ce_que_le_temoin_n_a_pas_vu,
    passer,
    temoins,
    terrain_domivelle_dure,
)

TACHES = {t.identifiant: t for t in taches_domivelle_dure()}
PUBLIC = racine_depot() / "07_taches" / "public"

ARRETS_DES_ERREURS: dict[str, list[str]] = {
    "dvh10_les_reversements_du_10_juin": ["rib_proprietaires"],
    "dvh12_une_journee_de_gaelle_fournel": ["destinataires_connus"],
    "dvh20_une_journee_de_veronique_tessier": ["destinataires_connus"],
}
"""Les erreurs du témoin toujours faux qu'arrête le gardien, par tâche et par règle ; les autres
tâches portent des erreurs qu'aucune règle ne voit (un montant, une date, un texte)."""


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


def _arrets_par_tache(dossier_run: Path) -> dict[str, list[str]]:
    resultats = [lire_resultat(p) for p in sorted((dossier_run / "resultats").glob("*.json"))]
    arrets = {r.tache.identifiant: blocages_du_gardien(dossier_run / r.journal) for r in resultats}
    return {t: [r.split("(règle ")[1].split(")")[0] for r in liste] for t, liste in arrets.items()}


def test_la_tranche_longue_de_domivelle_est_un_jeu_a_part() -> None:
    assert dossier_du_jeu("domivelle_dure") == racine_depot() / "07_taches" / "public" / "domivelle" / "dure"
    assert "domivelle_dure" in TERRAINS
    assert TACHES and all(t.identifiant.startswith("dvh") for t in TACHES.values())
    assert {societe_de(t) for t in TACHES.values()} == {"domivelle"}
    assert not set(TACHES) & {t.identifiant for t in taches_domivelle()}
    # les gestes de la tranche longue de la v2 sont dans les mêmes tables (test_domivelle_dure_v2)
    avec_v2 = sorted([*TACHES, *(t.identifiant for t in taches_domivelle_dure_v2())])
    assert sorted(SOLUTIONS_DOMIVELLE_DURE) == avec_v2 == sorted(ERREURS_DOMIVELLE_DURE)


@pytest.mark.parametrize("tache", list(TACHES.values()), ids=lambda t: t.identifiant[:5])
def test_chaque_tache_tient_a_domivelle_et_a_la_regle_du_budget(tache: Tache, tmp_path: Path) -> None:
    assert coherence_pme(tache) == []
    assert tache.budget.etapes_max == budget_etapes(len(SOLUTIONS_DOMIVELLE_DURE[tache.identifiant]))
    assert ce_que_le_temoin_n_a_pas_vu(tache, SOLUTIONS_DOMIVELLE_DURE[tache.identifiant], tmp_path / "pme") == []


@pytest.mark.parametrize("rang", range(4), ids=["parfait", "toujours_faux", "une_fois_sur_deux", "inerte"])
def test_les_temoins_sont_conformes_sur_la_tranche_longue(rang: int, tmp_path: Path) -> None:
    temoin = temoins(terrain_domivelle_dure(tmp_path / "pme"))[rang]
    _, resume = passer(temoin, tmp_path / "runs", repetitions=2)
    assert resume.erreurs_techniques == 0
    assert resume.taux == temoin.taux_attendu


def test_le_gardien_de_domivelle_laisse_passer_le_temoin_parfait(tmp_path: Path) -> None:
    terrain = terrain_domivelle_dure(tmp_path / "pme", gardien=regles_gardien("domivelle"))
    dossier_run, resume = passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1)
    resultats = [lire_resultat(p) for p in sorted((dossier_run / "resultats").glob("*.json"))]
    assert {r.tache.identifiant: blocages_du_gardien(dossier_run / r.journal) for r in resultats} == {
        t: [] for t in TACHES
    }
    assert resume.taux == 1.0


def test_le_classement_et_la_gravite_de_la_tranche_longue_tiennent() -> None:
    dossier = dossier_du_jeu("domivelle_dure")
    assert ecarts_classement(lire_classement(dossier / "classement.yaml"), list(TACHES.values())) == []
    gravite = lire_gravite(PUBLIC, dossier)
    tranche = type(gravite)(
        gravite.version, gravite.categories, {k: v for k, v in gravite.graves.items() if k in TACHES}
    )
    assert ecarts(tranche, list(TACHES.values())) == []
    pieges = {
        "dvh10_les_reversements_du_10_juin",
        "dvh11_les_dossiers_de_location",
        "dvh12_une_journee_de_gaelle_fournel",
    }
    assert set(tranche.graves) == pieges


def test_le_gardien_de_domivelle_arrete_les_erreurs_qu_il_vise_dans_la_tranche(tmp_path: Path) -> None:
    terrain = terrain_domivelle_dure(tmp_path / "pme", gardien=regles_gardien("domivelle"))
    dossier_run, _ = passer(TemoinObstine(terrain, ERREURS_DOMIVELLE_DURE), tmp_path / "runs", repetitions=1)
    assert _arrets_par_tache(dossier_run) == {t: ARRETS_DES_ERREURS.get(t, []) for t in TACHES}
