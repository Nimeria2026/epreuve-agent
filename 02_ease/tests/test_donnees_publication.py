"""Données d'une publication : chaque chiffre calculé par EASE, écrit comme il s'affichera."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import ease.donnees_publication as publication
import pytest
from ease.cachees import cachees_du_jeu
from ease.chargement import racine_depot
from ease.contrats.tache import Tache
from ease.donnees_publication import (
    PARTS,
    TAU2,
    cachees_publiees,
    contexte_plus_court,
    donnees_premier_post,
    donnees_video,
    ecart_ordonne,
    essais_tau2,
    nombre,
    points,
    pourcent,
    publiques_publiees,
)
from ease.rapport import RapportImpossible, bootstrap_ecart
from ease.taches import lire_taches

NB = " "
EXEMPLES = racine_depot() / "01_contrats" / "exemples"
SOCLE = lire_taches(racine_depot() / "07_taches" / "public")
DS, QW = "agent_seul_deepseek_flash_1017", "agent_seul_qwen_local_100k"
QW_40K = PARTS[QW][1]
CANDIDATS = ((DS, "DeepSeek V4.1 Flash"), (QW, "Qwen 3.8 27B"))


def _une_par_famille(*familles: str) -> list[Tache]:
    """Une tâche publique du socle par famille, sans complément d'état, pour un run fictif simple."""
    return [next(t for t in SOCLE if t.famille == f and t.complement is None) for f in familles]


def _resultat(tache: Tache, run: str, repetition: int, reussie: bool) -> dict[str, Any]:
    controles: list[dict[str, Any]] = [
        {
            "numero": i,
            "famille": c.famille,
            "poids": c.poids,
            "score": 1.0 if reussie or i > 1 else 0.0,
            "detail": None if reussie or i > 1 else "contrôle manqué",
        }
        for i, c in enumerate(tache.controles, start=1)
    ]
    return {
        "run": run,
        "tache": {"identifiant": tache.identifiant, "version": tache.version},
        "repetition": repetition,
        "debut_utc": "2026-10-05T18:00:00Z",
        "fin_utc": "2026-10-05T18:01:00Z",
        "arret": "termine",
        "detail_arret": None,
        "controles": controles,
        "score": math.fsum(c["poids"] * c["score"] for c in controles),
        "reussie": reussie,
        "etapes": 7,
        "jetons": {"entree": 1000, "entree_en_cache": 800, "sortie": 100},
        "cout_dollars": 0.001,
        "energie_wh": None,
        "duree_secondes": 60.0,
        "journal": f"journaux/{tache.identifiant}_r{repetition}.jsonl",
    }


def _run(
    dossier_runs: Path,
    candidat: str,
    reussites: list[tuple[Tache, list[bool]]],
    debut: str = "2026-10-05T18:00:00Z",
    statut: str = "termine",
    jeu: list[Tache] | None = None,
) -> Path:
    """Un run fictif d'un candidat : sa fiche, et un résultat par répétition de chaque tâche ; son jeu
    est celui des tâches faites, ou jeu pour un run interrompu."""
    identifiant = f"{debut[:10]}_{debut[11:19].replace(':', '')}_{candidat}"
    dossier = dossier_runs / identifiant
    (dossier / "resultats").mkdir(parents=True)
    (dossier / "journaux").mkdir()
    fiche: dict[str, Any] = json.loads((EXEMPLES / "fiche_de_run_api.json").read_text(encoding="utf-8"))
    fiche.update(
        identifiant=identifiant,
        debut_utc=debut,
        fin_utc=debut,
        statut=statut,
        raison_interruption=None,
        candidat={"identifiant": candidat, "version": "0.1.0"},
        repetitions=5,
    )
    faites = [t for t, _ in reussites] if jeu is None else jeu
    fiche["jeu_taches"]["taches"] = [{"identifiant": t.identifiant, "version": t.version} for t in faites]
    fiche["juge"] = None
    (dossier / "fiche_de_run.json").write_text(json.dumps(fiche), encoding="utf-8")
    for tache, issues in reussites:
        for repetition, reussie in enumerate(issues, start=1):
            chemin = dossier / "resultats" / f"{tache.identifiant}_r{repetition}.json"
            chemin.write_text(json.dumps(_resultat(tache, identifiant, repetition, reussie)), encoding="utf-8")
    return dossier


def test_les_nombres_s_ecrivent_comme_dans_le_rapport() -> None:
    assert pourcent(217 / 225) == "96,4"
    assert pourcent(1.0) == "100"
    assert pourcent(0.5) == "50"
    assert points(-2 / 15) == "-13,3"
    assert nombre(1234.5, 1) == f"1{NB}234,5"


def test_les_chiffres_d_un_metier_de_l_ensemble_et_leurs_ecarts(tmp_path: Path) -> None:
    compta, planning = _une_par_famille("comptabilite", "planning")
    _run(tmp_path, DS, [(compta, [True] * 5), (planning, [True] * 5)])
    _run(tmp_path, QW, [(compta, [True, True, False, True, False]), (planning, [True] * 5)])
    donnees = donnees_premier_post(tmp_path, [compta, planning], CANDIDATS)
    assert [m["libelle"] for m in donnees["metiers"]] == ["Comptabilité", "Planning"]
    assert donnees["ensemble"]["libelle"] == "Les deux"
    ensemble = donnees["ensemble"]["par_candidat"]
    assert ensemble[DS]["essais"]["texte"] == "10 sur 10"
    assert ensemble[QW]["essais"]["texte"] == "8 sur 10"
    assert ensemble[QW]["essais"]["pourcent"] == "80"
    assert ensemble[QW]["cinq_sur_cinq"]["texte"] == "1 sur 2"
    assert ensemble[DS]["essais"]["fourchette_pourcent"] == ["100", "100"]
    compta_qw = donnees["metiers"][0]["par_candidat"][QW]["essais"]
    assert (compta_qw["texte"], compta_qw["pourcent"], compta_qw["fourchette"]) == ("3 sur 5", "60", [0.2, 1.0])
    ecart = donnees["metiers"][0]["ecarts"]["essais"]
    assert ecart["points"] == "40"
    assert ecart["etabli"] is False
    assert donnees["metiers"][1]["ecarts"]["essais"]["points"] == "0"
    assert donnees["par_tache"][QW] == {compta.identifiant: 3, planning.identifiant: 5}
    assert donnees["runs"][DS] == [f"2026-10-05_180000_{DS}"]
    assert donnees_video(donnees) == {"deepseek": [5, 5], "qwen": [3, 5]}


def test_un_ecart_est_etabli_quand_sa_fourchette_exclut_zero(tmp_path: Path) -> None:
    taches = _une_par_famille("comptabilite", "planning", "relation_client", "administration")
    _run(tmp_path, DS, [(t, [True] * 5) for t in taches])
    _run(tmp_path, QW, [(t, [False] * 5) for t in taches])
    ecarts = donnees_premier_post(tmp_path, taches, CANDIDATS)["ensemble"]["ecarts"]
    assert ecarts["essais"]["etabli"] is True
    assert ecarts["essais"]["points"] == "100"
    assert ecarts["cinq_sur_cinq"]["fourchette_points"] == ["100", "100"]


def test_une_tache_sans_run_complet_rend_les_donnees_impossibles(tmp_path: Path) -> None:
    compta, planning = _une_par_famille("comptabilite", "planning")
    _run(tmp_path, DS, [(compta, [True] * 5), (planning, [True] * 5)])
    _run(tmp_path, QW, [(compta, [True] * 5)])
    with pytest.raises(RapportImpossible, match="pas de run complet"):
        donnees_premier_post(tmp_path, [compta, planning], CANDIDATS)


def test_qwen_prend_chaque_tache_a_100k_puis_a_40k(tmp_path: Path) -> None:
    # JOURNAL, entrée 226 : la part à 100k d'abord, celle à 40k pour les tâches qu'elle n'a pas.
    compta, planning = _une_par_famille("comptabilite", "planning")
    _run(tmp_path, DS, [(compta, [True] * 5), (planning, [True] * 5)])
    _run(tmp_path, QW, [(compta, [True, True, False, True, False])])
    _run(tmp_path, QW_40K, [(compta, [False] * 5), (planning, [True, False, True, True, True])])
    donnees = donnees_premier_post(tmp_path, [compta, planning], CANDIDATS)
    assert donnees["par_tache"][QW] == {compta.identifiant: 3, planning.identifiant: 4}
    assert sorted(donnees["runs"][QW]) == [f"2026-10-05_180000_{QW_40K}", f"2026-10-05_180000_{QW}"]


def test_une_tache_coupee_par_le_contexte_a_40k_se_remesure_a_100k(tmp_path: Path) -> None:
    compta, planning = _une_par_famille("comptabilite", "planning")
    _run(tmp_path, DS, [(compta, [True] * 5), (planning, [True] * 5)])
    _run(tmp_path, QW, [(compta, [True] * 5)])
    run_40k = _run(tmp_path, QW_40K, [(planning, [True] * 5)])
    chemin = run_40k / "resultats" / f"{planning.identifiant}_r3.json"
    coupe = json.loads(chemin.read_text(encoding="utf-8")) | {
        "arret": "contexte_depasse",
        "detail_arret": "contexte du serveur dépassé",
        "reussie": False,
    }
    chemin.write_text(json.dumps(coupe), encoding="utf-8")
    with pytest.raises(RapportImpossible, match="coupée par le contexte"):
        donnees_premier_post(tmp_path, [compta, planning], CANDIDATS)


def test_tau2_prend_chaque_tache_du_dernier_run_qui_l_a_faite_en_entier(tmp_path: Path) -> None:
    # JOURNAL, entrée 273 : un run interrompu garde ses tâches complètes ; une tâche refaite plus
    # tard ne compte qu'une fois, avec les essais du run le plus récent.
    compta, planning = _une_par_famille("comptabilite", "planning")
    candidat = "reproduction_tau2_fictif"
    jeu = [compta, planning]
    premier = _run(
        tmp_path, candidat, [(compta, [False] * 5), (planning, [True] * 3)], "2026-10-21T10:00:00Z", "interrompu", jeu
    )
    with pytest.raises(RapportImpossible, match="1 tâches complètes sur 2"):
        essais_tau2(tmp_path, candidat)
    deuxieme = _run(tmp_path, candidat, [(planning, [True, True, False, True, True])], "2026-10-21T12:00:00Z")
    troisieme = _run(tmp_path, candidat, [(compta, [True] * 5)], "2026-10-21T13:00:00Z")
    essais, runs = essais_tau2(tmp_path, candidat)
    assert runs == [deuxieme.name, troisieme.name]
    assert premier.name not in {r.run for r in essais}
    assert (len(essais), sum(r.reussie for r in essais)) == (10, 9)


def _couper(run: Path, tache: Tache, repetition: int) -> None:
    """Un essai d'un run fictif, coupé par le contexte du serveur."""
    chemin = run / "resultats" / f"{tache.identifiant}_r{repetition}.json"
    coupe = json.loads(chemin.read_text(encoding="utf-8")) | {
        "arret": "contexte_depasse",
        "detail_arret": "contexte du serveur dépassé",
        "reussie": False,
    }
    chemin.write_text(json.dumps(coupe), encoding="utf-8")


def test_tau2_de_qwen_a_40k_refuse_un_essai_coupe_par_le_contexte(tmp_path: Path) -> None:
    # Cadrage du dépôt public, section 8 : la règle des parts du socle vaut pour τ²-bench. Qwen y est
    # mesuré à 40 960 jetons pour sa référence à 102 400 ; DeepSeek à son propre contexte, où une
    # coupure compte comme un échec du modèle.
    from ease.donnees_publication import _tau2  # pyright: ignore[reportPrivateUsage]

    repro_ds, repro_qw = (reproduction for _, reproduction, _ in TAU2)
    assert contexte_plus_court(repro_qw, QW)
    assert not contexte_plus_court(repro_ds, DS)
    compta, planning = _une_par_famille("comptabilite", "planning")
    run_ds = _run(tmp_path, repro_ds, [(compta, [True] * 5), (planning, [True] * 5)])
    run_qw = _run(tmp_path, repro_qw, [(compta, [True] * 5), (planning, [True] * 5)])
    _couper(run_ds, planning, 2)
    assert _tau2(tmp_path, CANDIDATS)[DS]["texte"] == "9 sur 10"
    _couper(run_qw, compta, 4)
    with pytest.raises(RapportImpossible, match="coupé par le contexte"):
        _tau2(tmp_path, CANDIDATS)


def test_l_ecart_se_prend_comme_dans_le_rapport_le_plus_haut_d_abord() -> None:
    """Le rapport tire l'écart du plus haut sur le plus bas ; le même ordre donne la même fourchette."""

    def part(valeurs: list[bool]) -> float:
        return sum(valeurs) / len(valeurs)

    bas = [[False, False, True], [False, True, True], [False, False, False]]
    haut = [[True, True, True], [True, False, True], [True, True, False]]
    e = ecart_ordonne({"b": bas, "a": haut}, part)
    assert e["devant"] == "a"
    assert e["fourchette"] == list(bootstrap_ecart(haut, bas, part))
    assert e["points"] == "44,4"


def test_les_publications_gardent_leurs_taches_quand_le_jeu_grandit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Le premier post et le constat publient le socle de Calorelle complet, t01 à t63 et les 20
    # cachées (JOURNAL, entrée 235) ; une tâche de plus dans le jeu n'y entre pas (entrée 226).
    publiees = publiques_publiees()
    assert [t.identifiant.split("_")[0] for t in publiees] == [f"t{n:02d}" for n in range(1, 64)]
    if cachees_du_jeu("public"):  # hors git : ni dans un clone neuf ni dans l'intégration continue
        assert len(cachees_publiees()) == 20
    une = publiees[0]
    plus_grand = [*publiees, une.model_copy(update={"identifiant": "t64_une_tache_de_plus"})]

    def jeu_agrandi(jeu: str) -> list[Tache]:
        return plus_grand

    def jeu_ampute(jeu: str) -> list[Tache]:
        return publiees[1:]

    def cachees_en_trop(jeu: str) -> list[Tache]:
        return [une] * 21

    monkeypatch.setattr(publication, "taches_du_jeu", jeu_agrandi)
    assert publiques_publiees() == publiees
    monkeypatch.setattr(publication, "taches_du_jeu", jeu_ampute)
    with pytest.raises(RapportImpossible, match="62 tâches publiques"):
        publiques_publiees()
    monkeypatch.setattr(publication, "cachees_du_jeu", cachees_en_trop)
    with pytest.raises(RapportImpossible, match="21 tâches cachées dans le socle, 20 publiées"):
        cachees_publiees()


def test_les_donnees_s_ecrivent_en_json_strict(tmp_path: Path) -> None:
    # JavaScript refuse Infinity : un horizon au-delà de la plus longue tâche s'écrit null (cadrage
    # de la page Épreuve d'agent, §9).
    from ease.donnees_publication import _ecrire, _fini  # pyright: ignore[reportPrivateUsage]

    assert _fini(math.inf) is None
    assert _fini(23.0) == 23.0
    with pytest.raises(ValueError, match="JSON compliant"):
        _ecrire(tmp_path / "donnees.json", {"minutes": math.inf})
