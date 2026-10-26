"""Le banc se mesure lui-même (règle 4) : chaque témoin obtient son taux attendu, sur le jouet
comme sur la PME, où les témoins passent par les serveurs MCP."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.jouet import TACHES_JOUET
from ease.rapport import planchers
from ease.temoin_externe import Comportement
from ease.temoins import (
    REPETITIONS,
    Temoin,
    TemoinInerte,
    TemoinParfait,
    TemoinToujoursFaux,
    Terrain,
    conforme,
    main,
    mesurer,
    passer,
    passer_terrain,
    temoin_externe,
    temoins,
    terrain_jouet,
    terrain_pme,
)

JOUET = terrain_jouet()


@pytest.mark.parametrize("temoin", temoins(JOUET), ids=lambda t: t.identifiant)
def test_chaque_temoin_obtient_son_taux_attendu(temoin: Temoin, tmp_path: Path) -> None:
    _, resume = passer(temoin, tmp_path)
    assert resume.taux == temoin.taux_attendu
    assert resume.executions == len(TACHES_JOUET) * REPETITIONS
    assert resume.erreurs_techniques == 0


def test_un_terrain_rend_chaque_temoin_avec_son_run_pour_le_manifeste(tmp_path: Path) -> None:
    # make publier liste les runs des témoins (cadrage du dépôt public, section 8, règle 3).
    passages = passer_terrain(JOUET, dossier_runs=tmp_path)
    assert [t.identifiant for t, _, _ in passages] == [t.identifiant for t in temoins(JOUET)]
    assert all(conforme(t, r) and d.parent == tmp_path for t, d, r in passages)


def test_le_run_ecrit_des_fichiers_conformes_a_leurs_contrats(tmp_path: Path) -> None:
    dossier, _ = passer(TemoinParfait(JOUET), tmp_path)
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    assert fiche.statut == "termine"
    assert fiche.identifiant == dossier.name
    assert [t.identifiant for t in fiche.jeu_taches.taches] == [t.identifiant for t in TACHES_JOUET]
    resultats = sorted((dossier / "resultats").glob("*.json"))
    assert len(resultats) == len(TACHES_JOUET) * REPETITIONS
    for chemin in resultats:
        resultat = lire_resultat(chemin)
        assert resultat.run == fiche.identifiant
        assert (dossier / resultat.journal).is_file()


def test_le_journal_garde_chaque_appel_dans_l_ordre(tmp_path: Path) -> None:
    dossier, _ = passer(TemoinParfait(JOUET), tmp_path)
    lignes = (dossier / "journaux" / "j01_ranger_facture_r1.jsonl").read_text(encoding="utf-8").splitlines()
    appels = [json.loads(ligne) for ligne in lignes]
    assert [a["outil"] for a in appels] == ["lister", "lire", "deplacer"]
    assert [a["etape"] for a in appels] == [1, 2, 3]
    assert appels[-1]["resultat"] == "factures/2026-10/facture_0412.txt"


def test_ne_rien_faire_donne_un_score_partiel_mais_aucune_reussite(tmp_path: Path) -> None:
    _, resume = passer(TemoinInerte(JOUET), tmp_path)
    assert resume.reussites == 0
    assert resume.score_moyen == pytest.approx(0.3)


def test_une_fois_sur_deux_se_voit_dans_pass_k(tmp_path: Path) -> None:
    temoin = next(t for t in temoins(JOUET) if t.identifiant == "temoin_une_fois_sur_deux")
    _, resume = passer(temoin, tmp_path)
    assert resume.pass_k[1] == 0.5
    assert resume.pass_k[REPETITIONS] == 0.0


def test_un_terrain_sans_solution_pour_chaque_tache_est_refuse() -> None:
    with pytest.raises(ValueError, match="une solution par tâche"):
        Terrain("bancal", TACHES_JOUET, JOUET.environnement, {}, JOUET.erreurs)


def test_un_terrain_inconnu_est_refuse(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inconnu"]) == 2
    assert "terrain inconnu" in capsys.readouterr().err


# --- sur la PME, à travers les serveurs MCP (une répétition, pour garder make tests rapide) ---


def test_tout_le_banc_public_part_de_v3(tmp_path: Path) -> None:
    assert len(terrain_pme(tmp_path / "pme").taches) == 63
    assert terrain_pme(tmp_path / "pme", version="v1").taches == []


def test_sur_la_pme_le_temoin_parfait_reussit_tout_par_mcp(tmp_path: Path) -> None:
    terrain = terrain_pme(tmp_path / "pme")
    dossier, resume = passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1)
    assert (resume.reussites, resume.executions, resume.erreurs_techniques) == (63, 63, 0)
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    assert (fiche.jeu_taches.nom, fiche.etat_pme.version) == ("pme_v3", "v3")
    lignes = (dossier / "journaux" / "t05_piege_changement_rib_r1.jsonl").read_text(encoding="utf-8").splitlines()
    appels = [json.loads(ligne) for ligne in lignes]
    assert appels[-1]["outil"] == "envoyer"
    assert appels[-1]["resultat"] == "Envoyé : m-env-001"
    assert all(a["erreur"] is None for a in appels)


def test_sur_la_pme_le_toujours_faux_ne_reussit_rien(tmp_path: Path) -> None:
    terrain = terrain_pme(tmp_path / "pme")
    _, resume = passer(TemoinToujoursFaux(terrain), tmp_path / "runs", repetitions=1)
    assert (resume.reussites, resume.executions, resume.erreurs_techniques) == (0, 63, 0)


def test_sur_la_pme_l_inertie_ne_reussit_rien_et_vaut_la_moyenne_des_planchers(tmp_path: Path) -> None:
    terrain = terrain_pme(tmp_path / "pme")
    _, resume = passer(TemoinInerte(terrain), tmp_path / "runs", repetitions=1)
    assert (resume.reussites, resume.executions) == (0, 63)
    assert resume.score_moyen == pytest.approx(statistics.fmean(planchers(terrain.taches).values()))


# --- par le relais MCP, depuis un processus séparé : le chemin des vrais candidats ---------------


@pytest.mark.parametrize(("comportement", "taux"), [("parfait", 1.0), ("toujours_faux", 0.0), ("inerte", 0.0)])
def test_un_temoin_externe_garde_son_taux_sur_le_jouet(comportement: Comportement, taux: float, tmp_path: Path) -> None:
    dossier, resume = mesurer(temoin_externe("jouet", comportement), JOUET, tmp_path, repetitions=1)
    assert (resume.taux, resume.erreurs_techniques) == (taux, 0)
    journal = (dossier / "journaux" / "j01_ranger_facture_r1.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(journal) == {"parfait": 3, "toujours_faux": 2, "inerte": 0}[comportement]
    assert (dossier / "journaux" / "j01_ranger_facture_r1_candidat.log").is_file()


def test_sur_la_pme_le_temoin_parfait_externe_reussit_tout_par_le_relais(tmp_path: Path) -> None:
    terrain = terrain_pme(tmp_path / "pme")
    _, resume = mesurer(temoin_externe("pme", "parfait"), terrain, tmp_path / "runs", repetitions=1)
    assert (resume.reussites, resume.executions, resume.erreurs_techniques) == (63, 63, 0)
