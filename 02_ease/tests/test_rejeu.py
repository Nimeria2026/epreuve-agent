"""Le rejeu d'un run (ease.rejeu) : les gestes d'un témoin, relus dans les journaux de son run,
redonnent ses verdicts ; un contrôle changé depuis change le verdict, et le rejeu le dit. Sur le
jouet, sans serveur ni modèle."""

from __future__ import annotations

import json
from pathlib import Path

from ease.contrats.tache import Tache
from ease.fiches import lire_fiche_de_run
from ease.jouet import TACHES_JOUET, ClasseurJouet
from ease.rejeu import afficher, gestes_du_journal, main, rejouer, taches_rejouables
from ease.temoins import REPETITIONS, TemoinParfait, TemoinToujoursFaux, passer, terrain_jouet
from ease.verification import verifier

JOUET = terrain_jouet()
TOUTES = [(t, t.version) for t in TACHES_JOUET]


def test_seuls_les_appels_reussis_se_rejouent(tmp_path: Path) -> None:
    journal = tmp_path / "j01_r1.jsonl"
    lignes: list[dict[str, object]] = [
        {"etape": 1, "outil": "lister", "arguments": {"dossier": "arrivee"}, "resultat": [], "erreur": None},
        {"etape": 2, "outil": "deplacer", "arguments": {"source": "x"}, "resultat": None, "erreur": "introuvable"},
        {"etape": 3, "outil": "lire", "arguments": {"chemin": "a.txt"}, "resultat": "texte", "erreur": None},
    ]
    journal.write_text("\n".join(json.dumps(ligne) for ligne in lignes) + "\n", encoding="utf-8")
    assert gestes_du_journal(journal) == [("lister", {"dossier": "arrivee"}), ("lire", {"chemin": "a.txt"})]


def test_le_rejeu_redonne_les_verdicts_des_temoins(tmp_path: Path) -> None:
    for temoin in (TemoinParfait(JOUET), TemoinToujoursFaux(JOUET)):
        dossier, _ = passer(temoin, tmp_path / temoin.identifiant)
        lignes = rejouer(dossier, TOUTES, REPETITIONS, ClasseurJouet(), verifier, juge_appele=False)
        assert len(lignes) == len(TACHES_JOUET) * REPETITIONS
        assert all(ligne.reussie_apres == ligne.reussie_avant for ligne in lignes)
        assert all(ligne.score_apres == ligne.score_avant for ligne in lignes)
        assert not any(ligne.change or ligne.divergences for ligne in lignes)


def _plus_stricte(tache: Tache) -> Tache:
    """La tâche en version 2, dont le premier contrôle attend un fichier que personne ne crée."""
    premier = tache.controles[0]
    verification = premier.verification[0].model_copy(update={"chemin": "factures/2026-10/autre.txt"})
    controles = [premier.model_copy(update={"verification": [verification]}), *tache.controles[1:]]
    return tache.model_copy(update={"version": 2, "controles": controles})


def test_un_controle_change_depuis_le_run_change_le_verdict(tmp_path: Path) -> None:
    dossier, _ = passer(TemoinParfait(JOUET), tmp_path)
    j01, j02 = TACHES_JOUET
    lignes = rejouer(dossier, [(_plus_stricte(j01), 1), (j02, 1)], 1, ClasseurJouet(), verifier, juge_appele=False)
    j01_r1, j02_r1 = lignes
    assert j01_r1.change and j01_r1.reussie_avant and not j01_r1.reussie_apres
    assert (j01_r1.version_run, j01_r1.version_courante) == (1, 2)
    assert [numero for numero, _, _ in j01_r1.rates] == [1]
    assert not j02_r1.change
    texte = afficher(lignes, hors_jeu=0)
    assert f"CHANGE {j01.identifiant} r1 v1 → v2 : réussite 1,00 → échec" in texte
    assert "réussites 2 au run, 1 au rejeu ; verdicts changés : 1, dans 1 tâche(s)" in texte
    assert "Pas une mesure" in texte


def test_une_tache_hors_des_jeux_publics_est_comptee_sans_etre_ouverte(tmp_path: Path) -> None:
    dossier, _ = passer(TemoinParfait(JOUET), tmp_path)
    j01, j02 = TACHES_JOUET
    (dossier / "journaux" / f"{j02.identifiant}_r1.jsonl").write_text("illisible", encoding="utf-8")
    retenues, hors_jeu = taches_rejouables(lire_fiche_de_run(dossier / "fiche_de_run.json"), {j01.identifiant: j01})
    assert retenues == [(j01, 1)] and hors_jeu == 1
    lignes = rejouer(dossier, retenues, 1, ClasseurJouet(), verifier, juge_appele=False)
    assert [ligne.tache for ligne in lignes] == [j01.identifiant]
    assert "1 tâche(s) du run hors de tout jeu public, ni ouvertes ni rejouées." in afficher(lignes, hors_jeu)


def test_le_filtre_de_taches_ne_garde_que_les_prefixes(tmp_path: Path) -> None:
    dossier, _ = passer(TemoinParfait(JOUET), tmp_path)
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    publiques = {t.identifiant: t for t in TACHES_JOUET}
    retenues, hors_jeu = taches_rejouables(fiche, publiques, ["j02"])
    assert [t.identifiant for t, _ in retenues] == ["j02_archiver_devis"] and hors_jeu == 0


def test_sans_fiche_de_run_le_rejeu_refuse(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 2
