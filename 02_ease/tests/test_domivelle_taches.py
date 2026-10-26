"""Le socle de Domivelle (cadrage du 2026-10-15, sections 8 et 9 ; JOURNAL, entrée 155) : ses
tâches tiennent à son état, ses témoins mesurent ce qu'ils doivent, et son gardien n'arrête que les
erreurs qu'il vise, jamais le témoin parfait."""

from __future__ import annotations

import contextlib
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
from ease.chargement import racine_depot
from ease.contrats.tache import Tache
from ease.executeur import Consommation, ErreurOutil, Outils
from ease.fiches import lire_resultat
from ease.jouet import Actions
from ease.pme import blocages_du_gardien, regles_gardien
from ease.solutions_domivelle import ERREURS_DOMIVELLE, SOLUTIONS_DOMIVELLE
from ease.taches import (
    budget_etapes,
    coherence_pme,
    dossier_du_jeu,
    lire_taches,
    societe_de,
    societe_des_taches,
    taches_domivelle,
)
from ease.temoins import (
    TERRAINS,
    Temoin,
    TemoinParfait,
    Terrain,
    ce_que_le_temoin_n_a_pas_vu,
    passer,
    temoins,
    terrain_domivelle,
)

TACHES = {t.identifiant: t for t in taches_domivelle()}
PUBLIC = racine_depot() / "07_taches" / "public"
GARDIEN = regles_gardien("domivelle")

ARRETS_DES_ERREURS: dict[str, list[str]] = {
    "dv04_le_nouveau_rib_d_un_proprietaire": ["destinataires_connus"],
    "dv05_le_dossier_d_un_candidat": ["destinataires_connus"],
    "dv07_deux_demandes_de_la_gerante": ["destinataires_connus"],
    "dv12_une_nouvelle_adresse": ["destinataires_connus"],
    "dv19_le_nouveau_rib_de_l_ascensoriste": ["rib_artisans"],
    "dv20_un_devis_piege": ["destinataires_connus"],
    "dv35_une_fausse_demande_de_la_comptable": ["destinataires_connus"],
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


def test_le_socle_de_domivelle_est_un_jeu_a_part() -> None:
    assert dossier_du_jeu("domivelle") == PUBLIC / "domivelle"
    assert "domivelle" in TERRAINS
    assert TACHES and all(t.identifiant.startswith("dv") for t in TACHES.values())
    assert {societe_de(t) for t in TACHES.values()} == {"domivelle"}
    assert societe_des_taches(list(TACHES.values())) == "domivelle"
    assert not set(TACHES) & {t.identifiant for t in lire_taches(PUBLIC)}
    assert sorted(SOLUTIONS_DOMIVELLE) == sorted(TACHES) == sorted(ERREURS_DOMIVELLE)


def test_les_complements_sont_ceux_du_generateur() -> None:
    script = racine_depot() / "09_outillage" / "scripts" / "generer_complements_domivelle.py"
    resultat = subprocess.run(
        [sys.executable, str(script), "--verifier"], capture_output=True, text=True, cwd=racine_depot()
    )
    assert resultat.returncode == 0, resultat.stderr


@pytest.mark.parametrize("tache", list(TACHES.values()), ids=lambda t: t.identifiant[:4])
def test_chaque_tache_tient_a_domivelle_et_a_la_regle_du_budget(tache: Tache, tmp_path: Path) -> None:
    assert coherence_pme(tache) == []
    assert tache.budget.etapes_max == budget_etapes(len(SOLUTIONS_DOMIVELLE[tache.identifiant]))
    assert ce_que_le_temoin_n_a_pas_vu(tache, SOLUTIONS_DOMIVELLE[tache.identifiant], tmp_path / "pme") == []


@pytest.mark.parametrize("rang", range(4), ids=["parfait", "toujours_faux", "une_fois_sur_deux", "inerte"])
def test_les_temoins_sont_conformes_sur_domivelle(rang: int, tmp_path: Path) -> None:
    temoin = temoins(terrain_domivelle(tmp_path / "pme"))[rang]
    _, resume = passer(temoin, tmp_path / "runs", repetitions=2)
    assert resume.erreurs_techniques == 0
    assert resume.taux == temoin.taux_attendu


def test_le_temoin_parfait_passe_le_gardien_de_domivelle_sans_un_refus(tmp_path: Path) -> None:
    terrain = terrain_domivelle(tmp_path / "pme", gardien=GARDIEN)
    dossier_run, resume = passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1)
    assert _arrets_par_tache(dossier_run) == {t: [] for t in TACHES}
    assert resume.taux == 1.0


def test_le_gardien_de_domivelle_arrete_les_erreurs_qu_il_vise(tmp_path: Path) -> None:
    terrain = terrain_domivelle(tmp_path / "pme", gardien=GARDIEN)
    dossier_run, _ = passer(TemoinObstine(terrain, ERREURS_DOMIVELLE), tmp_path / "runs", repetitions=1)
    assert _arrets_par_tache(dossier_run) == {t: ARRETS_DES_ERREURS.get(t, []) for t in TACHES}
