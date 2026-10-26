"""Lecture d'un journal d'exécution : étapes dans l'ordre, refus visibles, résultats coupés."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ease.journal import LIGNES_MAX, journaux, lire, main
from ease.temoins import TemoinInerte, TemoinParfait, passer, terrain_jouet


def _ecrire(chemin: Path, appels: list[dict[str, Any]]) -> Path:
    chemin.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in appels), encoding="utf-8")
    return chemin


def test_un_journal_de_run_se_lit_etape_par_etape(tmp_path: Path) -> None:
    dossier, _ = passer(TemoinParfait(terrain_jouet()), tmp_path, repetitions=1)
    lignes = lire(dossier / "journaux" / "j01_ranger_facture_r1.jsonl")
    assert lignes[1] == 'Étape 1  lister(dossier="arrivee")'
    assert 'Étape 3  deplacer(source="arrivee/facture_0412.txt", destination="factures/2026-10")' in lignes
    assert "  → factures/2026-10/facture_0412.txt" in lignes


def test_un_refus_se_voit_et_un_long_resultat_est_coupe(tmp_path: Path) -> None:
    long = "\n".join(f"ligne {n}" for n in range(LIGNES_MAX + 3))
    chemin = _ecrire(
        tmp_path / "t.jsonl",
        [
            {"etape": 1, "outil": "lire", "arguments": {"chemin": "rh"}, "resultat": None, "erreur": "dossier fermé"},
            {"etape": 2, "outil": "lire", "arguments": {"chemin": "a"}, "resultat": long, "erreur": None},
        ],
    )
    lignes = lire(chemin)
    assert "  refusé : dossier fermé" in lignes
    assert "    [3 lignes de plus, --complet pour tout voir]" in lignes
    assert f"    ligne {LIGNES_MAX + 2}" in lire(chemin, complet=True)


def test_un_agent_inerte_laisse_un_journal_vide_et_le_lecteur_le_dit(tmp_path: Path) -> None:
    dossier, _ = passer(TemoinInerte(terrain_jouet()), tmp_path, repetitions=1)
    assert "aucun appel d'outil : l'agent n'a rien fait" in lire(dossier / "journaux" / "j02_archiver_devis_r1.jsonl")


def test_un_dossier_de_run_et_un_motif_choisissent_les_journaux(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dossier, _ = passer(TemoinParfait(terrain_jouet()), tmp_path, repetitions=2)
    assert [p.name for p in journaux(dossier, "j02")] == ["j02_archiver_devis_r1.jsonl", "j02_archiver_devis_r2.jsonl"]
    assert main([str(dossier), "j01"]) == 0
    assert "== j01_ranger_facture_r1.jsonl" in capsys.readouterr().out
    assert main([str(dossier), "t99"]) == 2


def test_les_lectures_hors_budget_s_affichent_apres_leur_journal_sans_en_faire_un_autre(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journaux_run = tmp_path / "journaux"
    journaux_run.mkdir()
    principal: dict[str, Any] = {"etape": 1, "outil": "envoyer", "arguments": {}, "resultat": "Envoyé", "erreur": None}
    lecture = {
        "lecture": 1,
        "outil": "lire",
        "arguments": {"chemin": "commun/manuel.md"},
        "resultat": "Manuel",
        "erreur": None,
    }
    _ecrire(journaux_run / "t05_r1.jsonl", [principal])
    refus: dict[str, Any] = {
        "lecture": None,
        "outil": "envoyer",
        "arguments": {},
        "resultat": None,
        "erreur": "outil hors de l'accès",
    }
    _ecrire(journaux_run / "t05_r1_lectures.jsonl", [lecture, refus])
    assert journaux(tmp_path, "t05") == [journaux_run / "t05_r1.jsonl"]
    assert main([str(tmp_path), "t05"]) == 0
    sortie = capsys.readouterr().out
    assert "Étape 1  envoyer()" in sortie
    assert (
        "Lectures hors budget, par l'accès en lecture seule :\n== t05_r1_lectures.jsonl\n"
        'Lecture 1  lire(chemin="commun/manuel.md")' in sortie
    )
    assert "Lecture refusée  envoyer()\n  refusé : outil hors de l'accès" in sortie
