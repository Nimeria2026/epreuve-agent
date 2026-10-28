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
DS, QW, FN = "agent_seul_deepseek_flash_1017", "agent_seul_qwen_local_100k", "agent_seul_qwen_flash_next_strata"
QW_40K = PARTS[QW][1]
CANDIDATS = ((DS, "DeepSeek V4.1 Flash"), (QW, "Qwen 3.8 27B"))
TROIS = (*CANDIDATS, (FN, "Qwen3.8-Flash-Next"))


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

    repro_ds, repro_qw = (t[1] for t in TAU2[:2])
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


def test_trois_candidats_font_trois_paires_dans_leur_ordre(tmp_path: Path) -> None:
    # JOURNAL, entrée 338 : avec trois modèles, chaque chiffre a l'écart de chaque paire ; celui d'une
    # paire ne dépend pas du troisième candidat.
    compta, planning = _une_par_famille("comptabilite", "planning")
    _run(tmp_path, DS, [(compta, [True] * 5), (planning, [True] * 5)])
    _run(tmp_path, QW, [(compta, [True, True, False, True, False]), (planning, [True] * 5)])
    _run(tmp_path, FN, [(compta, [True, False, True, True, True]), (planning, [False, True, True, True, True])])
    trois = donnees_premier_post(tmp_path, [compta, planning], TROIS)
    deux = donnees_premier_post(tmp_path, [compta, planning], CANDIDATS)
    paires = trois["ensemble"]["paires"]
    assert [(p["a"], p["b"]) for p in paires] == [(DS, QW), (DS, FN), (QW, FN)]
    assert "ecarts" not in trois["ensemble"]
    assert paires[0]["essais"] == deux["ensemble"]["ecarts"]["essais"]
    assert paires[0]["essais"] == deux["ensemble"]["paires"][0]["essais"]
    assert trois["ensemble"]["libelle"] == "Les deux"
    assert donnees_video(trois)["flashnext"] == [4, 4]


def test_tau2_dit_dedans_hors_ou_aucun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # JOURNAL, entrée 277 : le contrôle repose sur les scores publiés qui portent un écart type ; un
    # score hors de notre fourchette se dit ; Flash-Next n'a pas de score publié (entrée 329).
    from ease.donnees_publication import _tau2  # pyright: ignore[reportPrivateUsage]

    compta, planning = _une_par_famille("comptabilite", "planning")
    reproductions = [t[1] for t in TAU2]
    for reproduction in reproductions:
        _run(tmp_path, reproduction, [(compta, [True] * 5), (planning, [True, True, True, True, False])])
    monkeypatch.setattr(
        publication,
        "TAU2",
        (
            (DS, reproductions[0], 0.2, None, "2026-10-26"),
            (QW, reproductions[1], 0.85, 0.024, "2026-10-26"),
            (FN, reproductions[2], None, None, "2026-10-27"),
        ),
    )
    tau2 = _tau2(tmp_path, TROIS)
    assert [tau2[c]["verdict"] for c in (DS, QW, FN)] == ["hors", "dedans", "aucun"]
    assert [tau2[c]["controle"] for c in (DS, QW, FN)] == [False, True, False]
    assert tau2[QW]["publie"]["ecart_type_points"] == "2,4"
    assert tau2[QW]["publie"]["source"] == "OpenRouter, relevé le 2026-10-26"
    assert tau2[FN]["publie"] is None
    assert tau2[FN]["dans_la_fourchette"] is None


def test_le_journal_du_gardien_compte_ses_gestes_par_regle(tmp_path: Path) -> None:
    # Ce que dit le journal du gardien (maquette refondue, refonte 15 ; JOURNAL, entrée 339) : ses
    # blocages et ses demandes d'accord, lus dans le run d'où viennent les exécutions retenues.
    from types import SimpleNamespace

    from ease.donnees_publication import _journal_du_gardien  # pyright: ignore[reportPrivateUsage]
    from ease.rapport import Mesures

    compta, planning = _une_par_famille("comptabilite", "planning")
    retenu, ancien = tmp_path / "retenu", tmp_path / "ancien"
    retenu.mkdir()
    ancien.mkdir()
    lignes = [
        {"tache": compta.identifiant, "verdict": "autorise"},
        {"tache": compta.identifiant, "verdict": "bloque", "regle": "destinataires_connus"},
        {"tache": compta.identifiant, "verdict": "validation", "regle": "remise_gerante", "reponse": "accepter"},
        {"tache": planning.identifiant, "verdict": "validation", "regle": "rib", "reponse": "refuser"},
        {"tache": planning.identifiant, "verdict": "bloque", "regle": "destinataires_connus"},
    ]
    (retenu / "gardien.jsonl").write_text("\n".join(json.dumps(x) for x in lignes) + "\n", encoding="utf-8")
    (ancien / "gardien.jsonl").write_text(json.dumps(lignes[4]) + "\n", encoding="utf-8")
    sources = {
        compta.identifiant: SimpleNamespace(dossier=retenu),
        planning.identifiant: SimpleNamespace(dossier=ancien),
    }
    m = Mesures(FN, "Qwen3.8-Flash-Next", {}, sources, [])  # pyright: ignore[reportArgumentType]
    journal = _journal_du_gardien([m], [compta, planning])[FN]
    assert (journal["bloques"], journal["acceptes"], journal["refuses"]) == (2, 1, 0)
    assert journal["par_regle"]["destinataires_connus"] == {"bloque": 2, "accepte": 0, "refuse": 0}
    assert journal["taches_par_regle"] == {
        "destinataires_connus": sorted([compta.identifiant, planning.identifiant]),
        "remise_gerante": [compta.identifiant],
    }


def test_les_durees_de_la_grille_s_arrondissent_sans_rendre_la_phrase_fausse() -> None:
    # Maquette de la page, refonte 11 : à la minute sous une heure, aux cinq minutes au-delà ; une
    # borne « moins de » s'arrondit au-dessus, une borne « plus de » au-dessous.
    from ease.donnees_publication import (
        _fourchette_de_grille,  # pyright: ignore[reportPrivateUsage]
        _lecture_de_grille,  # pyright: ignore[reportPrivateUsage]
        _minutes_de_grille,  # pyright: ignore[reportPrivateUsage]
    )

    assert [_minutes_de_grille(m) for m in (15.8, 22.5, 23.0, 37.9, 60.0, 64.0, 91.0)] == [
        f"16{NB}min",
        f"23{NB}min",
        f"23{NB}min",
        f"38{NB}min",
        f"1{NB}h",
        f"1{NB}h{NB}05",
        f"1{NB}h{NB}30",
    ]
    assert _minutes_de_grille(15.2, math.ceil) == f"16{NB}min"
    assert _minutes_de_grille(93.0, math.floor) == f"1{NB}h{NB}30"
    plage = (15.8, 91.0)
    assert _lecture_de_grille(math.inf, plage) == f"au-delà de 1{NB}h{NB}30"
    assert _fourchette_de_grille((0.0, 37.9), plage) == (
        [f"moins de 16{NB}min", f"38{NB}min"],
        f"de moins de 16{NB}min à 38{NB}min",
    )
    assert _fourchette_de_grille((0.0, math.inf), plage)[1] == f"de moins de 16{NB}min à plus de 1{NB}h{NB}30"
    # Tout entière au-delà de la plus longue tâche : une phrase, pas « de au-delà de 1 h 30 à plus de 1 h 30 ».
    assert _fourchette_de_grille((math.inf, math.inf), plage)[1] == f"au-delà de 1{NB}h{NB}30"


def test_chaque_ecart_a_son_texte_et_chaque_taux_sa_position(tmp_path: Path) -> None:
    # Maquette de la page, refonte 11 : la page ne calcule rien, les données lui donnent les essais
    # ratés, la position de chaque taux sur l'échelle de 60 à 100 % et le texte de chaque écart.
    compta, planning = _une_par_famille("comptabilite", "planning")
    _run(tmp_path, DS, [(compta, [True] * 5), (planning, [True] * 5)])
    _run(tmp_path, QW, [(compta, [True, True, False, True, False]), (planning, [True] * 5)])
    _run(tmp_path, FN, [(compta, [True, False, True, True, True]), (planning, [False, True, True, True, True])])
    d = donnees_premier_post(tmp_path, [compta, planning], TROIS)
    essais = d["ensemble"]["par_candidat"]
    assert [essais[c]["essais"]["rates"] for c in (DS, QW, FN)] == [0, 2, 2]
    assert essais[DS]["essais"]["position"] == 100.0
    assert essais[QW]["essais"]["position"] == pytest.approx(50.0)
    assert [g["position"] for g in d["echelle_taux"]["graduations"]] == pytest.approx([0.0, 50.0, 100.0])
    noms = {DS: "DeepSeek", QW: "Qwen 27B", FN: "Flash-Next"}
    for paire in d["ensemble"]["paires"]:
        e = paire["essais"]
        lo, hi = (x.replace("-", "−") for x in e["fourchette_points"])
        unite = "point" if abs(e["valeur"]) < 0.02 else "points"
        if e["etabli"]:
            autre = paire["b"] if e["devant"] == paire["a"] else paire["a"]
            attendu = f"{noms[e['devant']]} devant {noms[autre]} de {e['points']} {unite} ({lo} à {hi})."
        else:
            attendu = f"{noms[paire['a']]} et {noms[paire['b']]}{NB}: {e['points']} {unite} ({lo} à {hi})."
        assert e["texte"] == attendu


def test_les_textes_des_fautes_de_la_duree_et_de_l_horizon() -> None:
    # Une faute grave de plus se dit « en commet plus », pas « devant », qui se lisait comme une
    # victoire ; l'horizon nomme celui qui tient plus longtemps, quel que soit l'ordre de la paire.
    from ease.donnees_publication import _textes_des_paires  # pyright: ignore[reportPrivateUsage]

    def ecart(devant: str, etabli: bool) -> dict[str, Any]:
        return {
            "valeur": 0.096,
            "points": "9,6",
            "fourchette_points": ["3,2", "18,4"],
            "etabli": etabli,
            "devant": devant,
        }

    d: dict[str, Any] = {
        "candidats": [{"identifiant": DS, "court": "DeepSeek"}, {"identifiant": QW, "court": "Qwen 27B"}],
        "socle": {
            "paires": [
                {
                    "a": DS,
                    "b": QW,
                    "essais": ecart(DS, True),
                    "cinq_sur_cinq": ecart(DS, False),
                    "duree_mediane": {
                        "secondes": 154.0,
                        "fourchette_secondes": [104.0, 161.4],
                        "etabli": True,
                        "devant": QW,
                    },
                }
            ]
        },
        "graves": {"sans_gardien": {"paires": [{"a": DS, "b": QW, "ecart": ecart(QW, True)}]}},
        "horizon": {"paires": [{"a": DS, "b": QW, "etabli": True, "devant": QW}]},
    }
    _textes_des_paires(d)
    paire = d["socle"]["paires"][0]
    assert paire["essais"]["texte"] == "DeepSeek devant Qwen 27B de 9,6 points (3,2 à 18,4)."
    assert paire["cinq_sur_cinq"]["texte"] == f"DeepSeek et Qwen 27B{NB}: 9,6 points (3,2 à 18,4)."
    assert (
        paire["duree_mediane"]["texte"]
        == f"Qwen 27B plus long que DeepSeek de 2{NB}min{NB}34{NB}s (1{NB}min{NB}44{NB}s à 2{NB}min{NB}41{NB}s)."
    )
    faute = d["graves"]["sans_gardien"]["paires"][0]["ecart"]
    assert faute["texte"] == f"Qwen 27B en commet plus que DeepSeek{NB}: 9,6 points (3,2 à 18,4)."
    assert d["horizon"]["paires"][0]["texte"] == "Qwen 27B tient plus longtemps que DeepSeek."
    # Sous deux points, « point » reste au singulier.
    d["socle"]["paires"][0]["essais"] |= {"valeur": 0.014, "points": "1,4", "etabli": False}
    _textes_des_paires(d)
    assert d["socle"]["paires"][0]["essais"]["texte"] == f"DeepSeek et Qwen 27B{NB}: 1,4 point (3,2 à 18,4)."


def test_les_taches_ratees_au_moins_une_fois_s_ecrivent_pour_la_page(tmp_path: Path) -> None:
    # Cadrage du 2026-10-28, figer la publication v1, section 2 : l'accueil dit « Qwen 27B rate au
    # moins une fois 22 tâches sur 83 », le tableau « 27 % ».
    compta, planning = _une_par_famille("comptabilite", "planning")
    _run(tmp_path, DS, [(compta, [True] * 5), (planning, [True] * 5)])
    _run(tmp_path, QW, [(compta, [True, True, False, True, False]), (planning, [True] * 5)])
    donnees = donnees_premier_post(tmp_path, [compta, planning], CANDIDATS)
    ensemble = donnees["ensemble"]["par_candidat"]
    assert ensemble[QW]["cinq_sur_cinq"]["ratees"] == {
        "taches": 1,
        "texte": "1 sur 2",
        "pourcent": "50",
        "pourcent_entier": "50",
    }
    assert ensemble[DS]["cinq_sur_cinq"]["ratees"]["taches"] == 0


def test_les_sortes_de_fautes_graves_et_les_metiers_se_comptent_en_taches() -> None:
    # Les deux comptes que les pages citent et que les données n'avaient pas (même cadrage).
    from ease.donnees_publication import (  # pyright: ignore[reportPrivateUsage]
        _categories,  # pyright: ignore[reportPrivateUsage]
        _metiers_du_socle,  # pyright: ignore[reportPrivateUsage]
    )
    from ease.gravite import Gravite

    compta, planning, client = _une_par_famille("comptabilite", "planning", "relation_client")
    gravite = Gravite(
        1,
        {"fuite": "une donnée sort", "argent": "un engagement"},
        {compta.identifiant: {"a": "fuite", "b": "argent"}, planning.identifiant: {"c": "fuite"}},
    )
    assert _categories([compta, planning, client], gravite) == [
        {"cle": "fuite", "libelle": "une donnée qui sort", "definition": "une donnée sort", "taches": 2},
        {"cle": "argent", "libelle": "de l'argent engagé", "definition": "un engagement", "taches": 1},
    ]
    with pytest.raises(RapportImpossible, match="sans définition"):
        _categories([compta], Gravite(1, {}, {compta.identifiant: {"a": "fuite"}}))
    metiers = {m["cle"]: m for m in _metiers_du_socle([compta, planning], [client])}
    client_compte = metiers["relation_client"]
    assert (client_compte["publiques"], client_compte["cachees"], client_compte["taches"]) == (0, 1, 1)
    assert metiers["comptabilite"]["taches"] == 1
    assert metiers["administration"]["taches"] == 0


def test_les_fautes_graves_se_comptent_par_sorte_et_chaque_essai_fautif_se_retrouve() -> None:
    # « 7 chez Qwen 27B, 1 chez Flash-Next » : les fuites qui passent derrière le gardien ; et chaque
    # essai fautif nommé par son run, sa tâche et son essai, pour vérifier un récit (relecture R10).
    from types import SimpleNamespace

    from ease.contrats.resultat_execution import ResultatExecution
    from ease.donnees_publication import _essais_fautifs, _par_categorie  # pyright: ignore[reportPrivateUsage]
    from ease.gravite import exposee, lire_gravite, numeros_graves

    gravite = lire_gravite(racine_depot() / "07_taches" / "public")
    tache = next(t for t in SOCLE if exposee(t, gravite))
    numero, sorte = next(iter(numeros_graves(tache, gravite).items()))

    def essai(rang: int, manque: bool) -> ResultatExecution:
        r = _resultat(tache, "2026-10-21_120000_candidat_fictif", rang, True)
        for c in r["controles"]:
            c["score"], c["detail"] = (0.0, "contrôle manqué") if manque and c["numero"] == numero else (1.0, None)
        return ResultatExecution.model_validate(r)

    m = SimpleNamespace(executions={tache.identifiant: [essai(1, True), essai(2, False), essai(3, True)]})
    assert _par_categorie(m, [tache], gravite) == {sorte: 2}  # pyright: ignore[reportArgumentType]
    run = "2026-10-21_120000_candidat_fictif"
    assert _essais_fautifs(m, [tache], gravite) == [  # pyright: ignore[reportArgumentType]
        {"run": run, "tache": tache.identifiant, "essai": 1, "sortes": [sorte]},
        {"run": run, "tache": tache.identifiant, "essai": 3, "sortes": [sorte]},
    ]


def test_les_parts_de_qwen_disent_combien_de_taches_a_chaque_contexte(tmp_path: Path) -> None:
    # Relecture R10 du 2026-10-28 : le tableau dit « 102 400 jetons ou 40 960 selon la tâche », et
    # combien de tâches à 40 960 ; planning compte ici comme une tâche cachée.
    from ease.donnees_publication import _parts, rassembler_reference  # pyright: ignore[reportPrivateUsage]

    compta, planning = _une_par_famille("comptabilite", "planning")
    _run(tmp_path, QW, [(compta, [True] * 5)])
    _run(tmp_path, QW_40K, [(compta, [False] * 5), (planning, [True] * 5)])
    m = rassembler_reference(QW, "Qwen 3.8 27B", [compta, planning], tmp_path)
    assert _parts([m], [compta]) == {
        QW: [
            {
                "candidat": QW,
                "contexte": 102400,
                "contexte_texte": f"102{NB}400",
                "taches": 1,
                "publiques": 1,
                "cachees": 0,
            },
            {
                "candidat": QW_40K,
                "contexte": 40960,
                "contexte_texte": f"40{NB}960",
                "taches": 1,
                "publiques": 0,
                "cachees": 1,
            },
        ]
    }


def test_les_dates_et_les_periodes_s_ecrivent_pour_la_page() -> None:
    # Les textes publiés renvoient aux dates des données, écrites par EASE (JOURNAL, entrée 355).
    assert publication.date_ecrite("2026-10-26") == f"26{NB}octobre 2026"
    assert publication.date_ecrite("2026-11-01") == f"1er{NB}novembre 2026"
    assert publication.periode_ecrite({"2026-10-27", "2026-10-21", "2026-10-24"}) == f"du 21 au 27{NB}octobre 2026"
    assert publication.periode_ecrite({"2026-10-21"}) == f"le 21{NB}octobre 2026"
    assert publication.periode_ecrite({"2026-10-30", "2026-11-01"}) == f"du 30{NB}octobre au 1er{NB}novembre 2026"
    assert publication.periode_ecrite({"2026-12-30", "2027-01-01"}) == f"du 30{NB}décembre 2026 au 1er{NB}janvier 2027"


def test_le_rapport_de_deux_durees_se_dit_a_l_entier_le_plus_proche() -> None:
    # « Flash-Next va environ trois fois plus vite » : 3 min contre 63 s, dans un sens ou dans l'autre.
    from ease.donnees_publication import _fois  # pyright: ignore[reportPrivateUsage]

    assert _fois(63.0, 186.0) == _fois(186.0, 63.0) == 3
    assert _fois(26.0, 186.0) == 7
    assert _fois(10.0, 25.0) == 3
    assert _fois(0.0, 25.0) is None


def test_une_duree_mediane_s_ecrit_en_minutes_et_secondes() -> None:
    # Relecture R10 du 2026-10-28 : « 3 min 6 s », et non « 3 min » pour 186 secondes.
    from ease.donnees_publication import _duree  # pyright: ignore[reportPrivateUsage]

    assert _duree(186.0) == {"secondes": 186.0, "texte": f"3{NB}min{NB}6{NB}s"}
    assert _duree(63.0)["texte"] == f"63{NB}s"
    assert _duree(240.0)["texte"] == f"4{NB}min"


def test_le_juge_est_nomme_avec_la_reference_qui_a_son_modele() -> None:
    # Relecture R10 du 2026-10-28 : le juge est le modèle de DeepSeek, l'un des modèles mesurés.
    from types import SimpleNamespace

    from ease.donnees_publication import _demande_un_juge, _juge  # pyright: ignore[reportPrivateUsage]

    jugee = next(t for t in SOCLE if _demande_un_juge(t))
    simple = next(t for t in SOCLE if not _demande_un_juge(t))

    def mesures(identifiant: str, agent: str, juge: str | None = "deepseek-flash") -> SimpleNamespace:
        fiche = SimpleNamespace(
            juge=None if juge is None else SimpleNamespace(modele=juge),
            configuration=SimpleNamespace(modeles=[SimpleNamespace(role="agent", nom=agent)]),
        )
        return SimpleNamespace(
            identifiant=identifiant, sources={t.identifiant: SimpleNamespace(fiche=fiche) for t in (jugee, simple)}
        )

    deux = [mesures(DS, "deepseek-flash"), mesures(QW, "qwen-27b")]
    attendu = {"modele": "deepseek-flash", "candidat": DS, "taches": 1, "publiques": 1, "cachees": 0}
    assert _juge(deux, [jugee], [simple]) == attendu  # pyright: ignore[reportArgumentType]
    with pytest.raises(RapportImpossible, match="un seul juge"):
        _juge([*deux, mesures(FN, "flash-next", juge=None)], [jugee], [simple])  # pyright: ignore[reportArgumentType]


def test_qwen_se_declare_a_102_400_jetons_avec_ses_autres_parts_entre_parentheses() -> None:
    # Décision d'Alexandre du 2026-10-28 : « 102 400 en tête », l'exception dans la même ligne.
    from ease.donnees_publication import detail_avec_parts

    base = "en local, une carte RTX 3090, contexte de 102 400 jetons"
    lignes = [{"contexte_texte": "102 400", "taches": 26}, {"contexte_texte": "40 960", "taches": 57}]
    attendu = f"{base} (40 960 sur 57 tâches, mesurées avant l'élargissement)"
    assert detail_avec_parts(base, lignes) == attendu
    une = detail_avec_parts(base, [lignes[0], {"contexte_texte": "40 960", "taches": 1}])
    assert une.endswith("sur 1 tâche, mesurées avant l'élargissement)")
    assert detail_avec_parts(base, [lignes[0], {"contexte_texte": "40 960", "taches": 0}]) == base
    assert detail_avec_parts("par API", []) == "par API"


def test_le_mois_d_une_publication_est_celui_de_ses_runs_pas_du_jour_de_calcul() -> None:
    # Un constat d'octobre calculé par make publier le 2 novembre reste le constat d'octobre.
    from ease.donnees_publication import mois_des_runs

    donnees = {
        "socle": {"runs": {"a": ["2026-10-09_220655_agent_seul_qwen_local", "2026-10-27_074428_agent_seul_x"]}},
        "tau2": {"a": {"runs": ["2026-10-13_040310_reproduction_tau2_qwen_local"], "releve": "2026-11-02"}},
        "produit_le": "2026-11-02",
    }
    assert mois_des_runs(donnees) == "octobre 2026"
    assert mois_des_runs({"runs": {"a": ["2026-12-30_120000_x", "2027-01-02_080000_y"]}}) == "janvier 2027"
    with pytest.raises(RapportImpossible, match="aucun run nommé"):
        mois_des_runs({"produit_le": "2026-11-02"})
