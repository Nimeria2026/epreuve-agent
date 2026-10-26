"""Rapport : choix des exécutions entre plusieurs runs, marges par bootstrap, page HTML."""

from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

import pytest
from ease.chargement import racine_depot
from ease.contrats.tache import Tache
from ease.gravite import lire_gravite
from ease.pme import empreinte_complement
from ease.rapport import (
    RapportImpossible,
    bootstrap,
    bootstrap_ecart,
    conclusion,
    faire_bilan,
    nom_court,
    nom_de_la_pme,
    planchers,
    produire,
    quantile,
    rassembler,
    taux,
)
from ease.statistiques import intervalle_wilson
from ease.taches import lire_taches, taches_domivelle_dure

NB = "\u00a0"
EXEMPLES = racine_depot() / "01_contrats" / "exemples"
TACHES = lire_taches(racine_depot() / "07_taches" / "public")
T01, T02 = TACHES[0], TACHES[1]
CANDIDAT = "agent_essai"


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
    heure: str,
    reussites: list[tuple[Tache, list[bool]]],
    *,
    statut: str = "termine",
    version: dict[str, int] | None = None,
    consignes: str = "3",
    candidat: str = CANDIDAT,
    complements: dict[str, str] | None = None,
    juge: dict[str, str] | None = None,
) -> Path:
    """Un run fictif : sa fiche, et un résultat par répétition de chaque tâche."""
    identifiant = f"2026-10-05_{heure}_{candidat}"
    dossier = dossier_runs / identifiant
    (dossier / "resultats").mkdir(parents=True)
    (dossier / "journaux").mkdir()
    fiche: dict[str, Any] = json.loads((EXEMPLES / "fiche_de_run_api.json").read_text(encoding="utf-8"))
    taches = [
        {
            "identifiant": t.identifiant,
            "version": (version or {}).get(t.identifiant, t.version),
            **(
                {"empreinte_complement": (complements or {})[t.identifiant]}
                if t.identifiant in (complements or {})
                else {}
            ),
        }
        for t, _ in reussites
    ]
    fiche.update(
        identifiant=identifiant,
        debut_utc=f"2026-10-05T{heure[:2]}:{heure[2:4]}:{heure[4:]}Z",
        fin_utc=None if statut == "en_cours" else "2026-10-05T23:00:00Z",
        statut=statut,
        raison_interruption="arrêt" if statut == "interrompu" else None,
        candidat={"identifiant": candidat, "version": "0.1.0"},
        empreinte_prompts=f"sha256:{consignes * 64}",
        repetitions=len(reussites[0][1]),
    )
    fiche["jeu_taches"]["taches"] = taches
    fiche["juge"] = juge
    (dossier / "fiche_de_run.json").write_text(json.dumps(fiche), encoding="utf-8")
    for tache, issues in reussites:
        for repetition, reussie in enumerate(issues, start=1):
            chemin = dossier / "resultats" / f"{tache.identifiant}_r{repetition}.json"
            chemin.write_text(json.dumps(_resultat(tache, identifiant, repetition, reussie)), encoding="utf-8")
    return dossier


# ------------------------------------------------------------------------- statistiques


def test_le_quantile_interpole_et_garde_les_bornes_infinies() -> None:
    assert quantile([0.0, 1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    assert quantile([0.0, 10.0], 0.25) == 2.5
    assert quantile([1.0, math.inf], 0.9) == math.inf


def test_le_bootstrap_est_reproductible_et_nul_sur_des_donnees_constantes() -> None:
    groupes = [[1.0, 0.0, 1.0], [0.0, 0.0, 1.0], [1.0, 1.0, 1.0]]

    def moyenne(valeurs: list[float]) -> float:
        return sum(valeurs) / len(valeurs)

    assert bootstrap(groupes, moyenne) == bootstrap(groupes, moyenne)
    bas, haut = bootstrap(groupes, moyenne)
    assert 0.0 <= bas < 6 / 9 < haut <= 1.0
    assert bootstrap([[0.5, 0.5], [0.5, 0.5]], moyenne) == (0.5, 0.5)
    bas, haut = bootstrap_ecart(groupes, groupes, moyenne)
    assert bas < 0.0 < haut  # mêmes données : l'écart tiré au hasard tourne autour de zéro
    # Exécutions constantes dans chaque tâche : seul le tirage des tâches, commun aux deux, compte.
    # Tâches (1, 1) : écart 0,5 ; (2, 2) : 1 ; une de chaque : 1 - 1/3. Les bornes sont 0,5 et 1.
    assert bootstrap_ecart([[1.0, 1.0], [1.0]], [[0.5, 0.5], [0.0]], moyenne) == (0.5, 1.0)


# ----------------------------------------------------------------- choix des exécutions


def test_le_run_le_plus_recent_qui_contient_la_version_courante_est_retenu(tmp_path: Path) -> None:
    _run(tmp_path, "100000", [(T01, [True, True])])
    recent = _run(tmp_path, "110000", [(T01, [False, True])])
    _run(tmp_path, "120000", [(T01, [True, True])], statut="en_cours")  # un run en cours : ignoré
    _run(tmp_path, "130000", [(T01, [True, True])], version={T01.identifiant: T01.version - 1})
    _run(tmp_path, "140000", [(T01, [True])])  # essai rapide à une répétition : ignoré
    mesures = rassembler(CANDIDAT, "Essai", [T01, T02], tmp_path, repetitions=2)
    assert mesures.sources[T01.identifiant].dossier == recent
    assert [r.reussie for r in mesures.executions[T01.identifiant]] == [False, True]
    assert mesures.manquantes == [T02.identifiant]


def test_un_run_interrompu_donne_ses_taches_completes_et_seulement_elles(tmp_path: Path) -> None:
    """JOURNAL, entrée 110 : une tâche dont toutes les répétitions sont faites compte, même si le
    run s'est arrêté ensuite ; la tâche en cours à l'arrêt ne compte pas."""
    _run(tmp_path, "100000", [(T01, [False, False]), (T02, [False, False])])
    interrompu = _run(tmp_path, "110000", [(T01, [True, True]), (T02, [True])], statut="interrompu")
    mesures = rassembler(CANDIDAT, "Essai", [T01, T02], tmp_path, repetitions=2)
    assert mesures.sources[T01.identifiant].dossier == interrompu
    assert mesures.sources[T02.identifiant].dossier.name.startswith("2026-10-05_100000")
    page = produire([mesures], [T01, T02], {T01.identifiant: 0.4, T02.identifiant: 0.2}, tmp_path / "r")
    assert "run interrompu (arrêt), tâches complètes seules" in page


def test_des_runs_aux_consignes_differentes_ne_s_assemblent_pas(tmp_path: Path) -> None:
    _run(tmp_path, "100000", [(T01, [True, True])], consignes="3")
    _run(tmp_path, "110000", [(T02, [True, True])], consignes="4")
    with pytest.raises(RapportImpossible, match="consignes"):
        rassembler(CANDIDAT, "Essai", [T01, T02], tmp_path, repetitions=2)


def test_une_fiche_sans_societe_s_assemble_avec_une_fiche_de_calorelle(tmp_path: Path) -> None:
    """JOURNAL, cent-soixante-neuvième entrée : le champ societe n'existe que depuis la seconde société ;
    une fiche d'avant, sans lui, est de Calorelle, et s'assemble avec une fiche qui le porte."""
    _run(tmp_path, "100000", [(T01, [True, True])])
    fiche = _run(tmp_path, "110000", [(T02, [True, True])]) / "fiche_de_run.json"
    donnees = json.loads(fiche.read_text(encoding="utf-8"))
    donnees["etat_pme"]["societe"] = "calorelle"
    fiche.write_text(json.dumps(donnees), encoding="utf-8")
    assert rassembler(CANDIDAT, "Essai", [T01, T02], tmp_path, repetitions=2).manquantes == []
    donnees["etat_pme"]["societe"] = "domivelle"
    fiche.write_text(json.dumps(donnees), encoding="utf-8")
    with pytest.raises(RapportImpossible, match="état initial"):
        rassembler(CANDIDAT, "Essai", [T01, T02], tmp_path, repetitions=2)


JUGE = {"modele": "deepseek-flash", "grille": "2"}


def test_un_run_sans_juge_s_assemble_avec_un_run_a_juge_si_ses_taches_n_en_demandent_pas(tmp_path: Path) -> None:
    t02 = next(t for t in TACHES if t.identifiant.startswith("t02"))
    _run(tmp_path, "100000", [(T01, [True, True])])
    _run(tmp_path, "110000", [(t02, [True, True])], juge=JUGE)
    mesures = rassembler(CANDIDAT, "Essai", [T01, t02], tmp_path, repetitions=2)
    assert mesures.manquantes == []


def test_deux_juges_differents_ne_s_assemblent_pas(tmp_path: Path) -> None:
    t02, t04 = (next(t for t in TACHES if t.identifiant.startswith(p)) for p in ("t02", "t04"))
    _run(tmp_path, "100000", [(t02, [True, True])], juge=JUGE)
    _run(tmp_path, "110000", [(t04, [True, True])], juge={**JUGE, "grille": "3"})
    with pytest.raises(RapportImpossible, match="pas le même juge"):
        rassembler(CANDIDAT, "Essai", [t02, t04], tmp_path, repetitions=2)


def test_une_tache_a_complement_ne_reprend_que_les_runs_du_meme_complement(tmp_path: Path) -> None:
    t06 = next(t for t in TACHES if t.complement is not None)
    assert t06.complement is not None
    juste = empreinte_complement(t06.complement)
    _run(tmp_path, "100000", [(t06, [True, True])], complements={t06.identifiant: juste})
    _run(tmp_path, "110000", [(t06, [False, False])], complements={t06.identifiant: "sha256:" + "0" * 64})
    _run(tmp_path, "120000", [(t06, [False, False])])  # fiche sans empreinte de complément
    mesures = rassembler(CANDIDAT, "Essai", [t06], tmp_path, repetitions=2)
    assert mesures.sources[t06.identifiant].dossier.name.startswith("2026-10-05_100000")


def test_les_planchers_d_inertie_sont_ceux_des_temoins() -> None:
    attendus = [0.4, 0.2, 0.55, 0.0, 0.6, 0.5, 0.5, 0.7, 0.7, 0.7, 0.7, 0.7, 0.2]  # t01 à t13, les mêmes sur v1
    attendus += [0.3, 0.3, 0.6, 0.0, 0.6, 0.4]  # t14 à t19
    attendus += [0.3, 0.2, 0.3, 0.5, 0.2]  # t20 à t24
    attendus += [0.3, 0.2, 0.3, 0.6, 0.5, 0.4, 0.2]  # t25 à t31
    attendus += [0.5, 0.8, 0.2, 0.6]  # t32 à t35
    attendus += [0.2, 0.2, 0.4, 0.4, 0.5, 0.2, 0.3, 0.2]  # t36 à t43 ; t38 en version 4, 0,4 (JOURNAL, entrée 236)
    attendus += [0.2, 0.6]  # t44 et t45
    attendus += [0.55, 0.4, 0.15, 0.5, 0.15, 0.15, 0.15, 0.2, 0.4]  # t46 à t54, benchmark par branche
    # t48 en version 8 (JOURNAL, entrée 269) : son contrôle 1 veut une réponse à la cliente, 0,15.
    attendus += [0.4, 0.5, 0.15, 0.2, 0.65, 0.15, 0.4, 0.25, 0.6]  # t55 à t63
    assert list(planchers(TACHES).values()) == pytest.approx(attendus)


# ------------------------------------------------------------------------------ la page


def test_la_fourchette_du_taux_tire_les_taches_puis_les_essais(tmp_path: Path) -> None:
    """Les essais d'une même tâche se ressemblent : la fourchette du taux vient du bootstrap à deux
    niveaux, plus large que Wilson, qui les croirait indépendants (JOURNAL, cent-vingt-et-unième entrée)."""
    _run(tmp_path, "100000", [(T01, [True] * 5), (T02, [False] * 5)])
    mesures = rassembler(CANDIDAT, "Modèle", [T01, T02], tmp_path, repetitions=5)
    communes = [T01.identifiant, T02.identifiant]
    bilan = faire_bilan(mesures, communes, dict.fromkeys(communes, 0.0))
    assert bilan.taux_ic == bootstrap([mesures.executions[t] for t in communes], taux)
    bas, haut = intervalle_wilson(5, 10)
    assert bilan.taux_ic[0] < bas and bilan.taux_ic[1] > haut


def test_la_conclusion_dit_quand_l_ecart_n_est_pas_etabli(tmp_path: Path) -> None:
    _run(tmp_path, "100000", [(T01, [True, True, True]), (T02, [True, True, False])], candidat="agent_a")
    _run(tmp_path, "100000", [(T01, [True, True, True]), (T02, [True, False, True])], candidat="agent_b")
    a = rassembler("agent_a", "Modèle A", [T01, T02], tmp_path, repetitions=3)
    b = rassembler("agent_b", "Modèle B", [T01, T02], tmp_path, repetitions=3)
    phrase = conclusion([a, b], [T01.identifiant, T02.identifiant])
    assert "5 exécutions sur 6" in phrase
    assert "n'est pas établi" in phrase


def test_la_page_donne_la_conclusion_les_chiffres_et_un_lien_par_execution(tmp_path: Path) -> None:
    _run(tmp_path, "100000", [(T01, [True, True]), (T02, [True, False])], candidat="agent_a")
    _run(tmp_path, "100000", [(T01, [True, False]), (T02, [False, False])], candidat="agent_b")
    mesures = [
        rassembler("agent_a", "Modèle <A>", [T01, T02], tmp_path, repetitions=2),
        rassembler("agent_b", "Témoin B", [T01, T02], tmp_path, repetitions=2),
    ]
    page = produire(mesures, [T01, T02], {T01.identifiant: 0.4, T02.identifiant: 0.2}, tmp_path / "rapports")
    assert page.startswith("<!doctype html>")
    assert "Modèle &lt;A&gt;" in page and "Modèle <A>" not in page
    assert "3 sur 4" in page and "1 sur 4" in page
    assert page.count('href="../2026-10-05_100000_agent_a/journaux/') == 4
    assert "contrôle manqué" in page
    assert f"manqué, « {T02.controles[0].etape} »" in page
    assert taux(mesures[0].executions[T01.identifiant]) == 1.0


def test_un_contexte_depasse_compte_en_echec_et_se_dit_dans_la_page(tmp_path: Path) -> None:
    """Choix T3 du 2026-10-14 : l'exécution reste dans le taux, en échec, et la page la compte à part."""
    _run(tmp_path, "100000", [(T01, [True, True]), (T02, [True, False])], candidat="agent_a")
    _run(tmp_path, "100000", [(T01, [True, True]), (T02, [True, True])], candidat="agent_b")
    chemin = tmp_path / "2026-10-05_100000_agent_a" / "resultats" / f"{T02.identifiant}_r2.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    donnees.update(arret="contexte_depasse", detail_arret="HTTP 400 : maximum context length")
    chemin.write_text(json.dumps(donnees), encoding="utf-8")
    mesures = [
        rassembler("agent_a", "Modèle A", [T01, T02], tmp_path, repetitions=2),
        rassembler("agent_b", "Modèle B", [T01, T02], tmp_path, repetitions=2),
    ]
    page = produire(mesures, [T01, T02], {T01.identifiant: 0.4, T02.identifiant: 0.2}, tmp_path / "rapports")
    assert "3 sur 4" in page  # dans le taux, en échec
    assert "Contextes dépassés, comptés en échecs" in page and "contexte du modèle dépassé" in page


def test_un_delai_depasse_compte_en_echec_et_se_dit_dans_la_page(tmp_path: Path) -> None:
    """Choix D1 du cadrage du générateur des images : dans le taux, en échec, compté à part."""
    _run(tmp_path, "100000", [(T01, [True, True]), (T02, [True, False])], candidat="agent_a")
    _run(tmp_path, "100000", [(T01, [True, True]), (T02, [True, True])], candidat="agent_b")
    chemin = tmp_path / "2026-10-05_100000_agent_a" / "resultats" / f"{T02.identifiant}_r2.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    donnees.update(arret="delai_depasse", detail_arret="candidat arrêté après 3600 s")
    chemin.write_text(json.dumps(donnees), encoding="utf-8")
    mesures = [
        rassembler("agent_a", "Modèle A", [T01, T02], tmp_path, repetitions=2),
        rassembler("agent_b", "Modèle B", [T01, T02], tmp_path, repetitions=2),
    ]
    page = produire(mesures, [T01, T02], {T01.identifiant: 0.4, T02.identifiant: 0.2}, tmp_path / "rapports")
    assert "3 sur 4" in page
    assert "Délais dépassés, comptés en échecs" in page and "délai dépassé (candidat arrêté après 3600 s)" in page


def test_l_electricite_incomplete_s_affiche_comme_un_minimum(tmp_path: Path) -> None:
    """Une exécution sans relevé (« ? ») : le rapport donne l'électricité des autres comme un minimum,
    avec le nombre d'exécutions sans mesure, au lieu de « sans objet » (JOURNAL, cent-douzième entrée)."""
    _run(tmp_path, "100000", [(T01, [True, True]), (T02, [True, False])], candidat="agent_a")
    _run(tmp_path, "100000", [(T01, [True, True]), (T02, [True, True])], candidat="agent_b")
    fichiers = sorted((tmp_path / "2026-10-05_100000_agent_a" / "resultats").glob("*.json"))
    for chemin, energie in zip(fichiers, [10.0, 20.0, 30.0, "?"], strict=True):
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        donnees["energie_wh"] = energie
        chemin.write_text(json.dumps(donnees), encoding="utf-8")
    mesures = [
        rassembler("agent_a", "Modèle A", [T01, T02], tmp_path, repetitions=2),
        rassembler("agent_b", "Modèle B", [T01, T02], tmp_path, repetitions=2),
    ]
    page = produire(mesures, [T01, T02], {T01.identifiant: 0.4, T02.identifiant: 0.2}, tmp_path / "rapports")
    assert f"au moins 60,0{NB}Wh" in page
    assert "1 exécution(s) sans mesure, pas de marge" in page
    assert page.count("au moins") >= 3  # le total en Wh, en euros, et par tâche réussie


def test_les_fautes_graves_se_comptent_a_part_de_la_reussite(tmp_path: Path) -> None:
    t05 = next(t for t in TACHES if t.identifiant == "t05_piege_changement_rib")  # contrôle 1 grave (argent)
    _run(tmp_path, "100000", [(T01, [True, False]), (t05, [True, False])], candidat="agent_a")
    _run(tmp_path, "100000", [(T01, [True, True]), (t05, [True, True])], candidat="agent_b")
    mesures = [
        rassembler("agent_a", "Modèle A", [T01, t05], tmp_path, repetitions=2),
        rassembler("agent_b", "Modèle B", [T01, t05], tmp_path, repetitions=2),
    ]
    gravite = lire_gravite(racine_depot() / "07_taches" / "public")
    page = produire(mesures, [T01, t05], {T01.identifiant: 0.4, t05.identifiant: 0.6}, tmp_path / "r", gravite)
    assert "<th>Fautes graves</th>" in page
    assert f"<strong>1 sur 2</strong> (50{NB}%)" in page and f"<strong>0 sur 2</strong> (0{NB}%)" in page
    assert "faute grave (argent)</strong>, manqué" in page
    assert page.count("faute grave (") == 1  # l'échec de t01 n'est pas grave
    assert "parmi celles des tâches à contrôle grave : B 0 sur 2, A 1 sur 2 ; l&#x27;écart de 50 points" in page
    sans = produire(mesures, [T01, t05], {T01.identifiant: 0.4, t05.identifiant: 0.6}, tmp_path / "r")
    assert "Fautes graves" not in sans and "faute grave" not in sans


def test_l_horizon_se_lit_sur_les_taches_sans_controle_grave_a_duree_a_jour(tmp_path: Path) -> None:
    """Section « L'horizon de temps » (JOURNAL, entrée 129) : t05, à contrôle grave, est hors de la
    courbe ; t04, sans durée à jour, y est nommé ; sans échec, l'horizon est au-delà de la plus longue."""
    par_debut = {t.identifiant[:3]: t for t in TACHES}
    t03, t04, t05 = par_debut["t03"], par_debut["t04"], par_debut["t05"]
    taches = [T01, t03, t04, t05]
    _run(tmp_path, "100000", [(T01, [True] * 3), (t03, [True] * 3), (t04, [True] * 3), (t05, [False] * 3)])
    mesures = [rassembler(CANDIDAT, "Modèle A", taches, tmp_path, repetitions=3)]
    gravite = lire_gravite(racine_depot() / "07_taches" / "public")
    planchers_nuls = dict.fromkeys((t.identifiant for t in taches), 0.0)
    durees = {T01.identifiant: 120.0, t03.identifiant: 600.0, t05.identifiant: 300.0}
    page = produire(mesures, taches, planchers_nuls, tmp_path / "r", gravite, durees)
    assert "horizon de temps</h2>" in page
    assert "Sur 2 tâches sans contrôle grave" in page
    assert f"<strong>au-delà de 10,0{NB}min</strong>" in page
    assert f"IC 95{NB}% tout entier au-delà de 10,0{NB}min" in page
    assert "2 tâches, 6 essais" in page
    assert f"Hors de la courbe, faute de durée estimée à jour : {t04.identifiant}" in page
    assert "ces tâches ne départagent pas les candidats par leur durée" in page
    sans = produire(mesures, taches, planchers_nuls, tmp_path / "r", gravite)
    assert "horizon de temps</h2>" not in sans


def test_les_taches_cachees_comptent_partout_sans_jamais_etre_nommees(tmp_path: Path) -> None:
    """La part cachée de la tranche (JOURNAL, entrée 171) : t03 et t04, cachées ici, entrent dans les
    chiffres, t03 dans la courbe ; t04, sans durée, en reste hors et t05, sans run, manque, comptées
    sans leurs noms. Ni identifiant, ni énoncé, ni trace d'une cachée dans la page."""
    par_debut = {t.identifiant[:3]: t for t in TACHES}
    t03, t04, t05 = par_debut["t03"], par_debut["t04"], par_debut["t05"]
    taches = [T01, t03, t04, t05]
    cachees = {t03.identifiant, t04.identifiant, t05.identifiant}
    _run(tmp_path, "100000", [(T01, [True] * 3), (t03, [True, False, True]), (t04, [True] * 3)])
    mesures = [rassembler(CANDIDAT, "Modèle A", taches, tmp_path, repetitions=3, cachees=cachees)]
    gravite = lire_gravite(racine_depot() / "07_taches" / "public")
    planchers_nuls = dict.fromkeys((t.identifiant for t in taches), 0.0)
    durees = {T01.identifiant: 120.0, t03.identifiant: 600.0}
    page = produire(mesures, taches, planchers_nuls, tmp_path / "r", gravite, durees, cachees)
    for tache in (t03, t04, t05):
        assert tache.identifiant not in page
        assert html.escape(tache.enonce, quote=False) not in page
    assert "sur 3 tâches de la PME fictive Calorelle, dont 2 cachées" in page
    assert "Rapport provisoire" in page and "Modèle A : 1 tâche cachée." in page
    assert "Sur 2 tâches sans contrôle grave" in page
    assert "Hors de la courbe, faute de durée estimée à jour : 1 tâche cachée ;" in page
    assert "<td>2 sur 3</td><td>5 sur 6</td>" in page
    assert f"version courante : {T01.identifiant} v{T01.version}, et 3 tâches cachées." in page
    assert "<td>t01, 2 tâches cachées</td>" in page
    assert page.count("<h3>") == 3  # t01, les cachées, les runs utilisés


def test_auteur_et_relecteur_se_presente_comme_tel_avec_ses_lectures(tmp_path: Path) -> None:
    """Relecture de la tranche 5, B6 : l'orchestration se lit dans les rôles, le prix d'un modèle ne
    s'écrit qu'une fois, les lectures du relecteur se comptent à part, refus compris (B7)."""
    _run(tmp_path, "100000", [(T01, [True, True])], candidat="agent_a")
    dossier = _run(tmp_path, "100000", [(T01, [True, False])], candidat="agent_b")
    fiche = json.loads((dossier / "fiche_de_run.json").read_text(encoding="utf-8"))
    agent = fiche["configuration"]["modeles"][0]
    fiche["configuration"]["modeles"] = [agent | {"role": "auteur"}, agent | {"role": "relecteur"}]
    (dossier / "fiche_de_run.json").write_text(json.dumps(fiche), encoding="utf-8")
    lecture: dict[str, Any] = {"lecture": 1, "outil": "lire", "arguments": {}, "resultat": "x", "erreur": None}
    refus: dict[str, Any] = {"lecture": None, "outil": "envoyer", "arguments": {}, "resultat": None, "erreur": "non"}
    for repetition, lignes in ((1, [lecture, lecture | {"lecture": 2}, refus]), (2, [lecture])):
        chemin = dossier / "journaux" / f"{T01.identifiant}_r{repetition}_lectures.jsonl"
        chemin.write_text("".join(json.dumps(ligne) + "\n" for ligne in lignes), encoding="utf-8")
    mesures = [
        rassembler("agent_a", "Seul", [T01], tmp_path, repetitions=2),
        rassembler("agent_b", "Relu", [T01], tmp_path, repetitions=2),
    ]
    page = produire(mesures, [T01], {T01.identifiant: 0.4}, tmp_path / "r")
    assert "<th>Orchestration</th><td>agent seul</td><td>auteur et relecteur</td>" in page
    assert "auteur : deepseek-flash (DeepSeek), relecteur : deepseek-flash (DeepSeek)" in page
    assert "1,5 par exécution" in page and "refus de l'accès en lecture : 1" in page
    assert page.count("<li>Prix de deepseek-flash") == 1
    assert "orchestrations : Seul, agent seul, Relu, auteur et relecteur" in page
    assert "même orchestration" not in page and "un agent seul) pour les deux" not in page


def test_un_candidat_non_declare_est_refuse(capsys: pytest.CaptureFixture[str]) -> None:
    from ease.rapport import main

    assert main(["--candidats", "agent_seul_qwen_local,agent_inconnu"]) == 2
    assert "candidat non déclaré, agent_inconnu" in capsys.readouterr().err


def test_le_debut_commun_des_noms_devient_le_titre() -> None:
    from ease.rapport import noms_courts

    assert noms_courts(["Agent seul sur DeepSeek V4.1 Flash", "Agent seul sur Qwen 3.8 27B"]) == (
        "Agent seul sur",
        ["DeepSeek V4.1 Flash", "Qwen 3.8 27B"],
    )
    assert noms_courts(["Qwen", "DeepSeek"]) == ("", ["Qwen", "DeepSeek"])
    assert noms_courts(["Agent seul", "Agent seul sur Qwen"]) == ("Agent", ["seul", "seul sur Qwen"])


def test_le_rapport_nomme_la_pme_des_taches_et_leur_code() -> None:
    """La page dit Domivelle pour les tâches de Domivelle, et la table des runs garde le code entier
    de chaque tâche, dvh11 et non dvh (JOURNAL, cent-soixante-dix-neuvième entrée)."""
    assert nom_de_la_pme(TACHES) == "Calorelle"
    assert nom_de_la_pme(taches_domivelle_dure()) == "Domivelle"
    codes = ["t01_classer_facture", "h03_le_portefeuille_de_julie", "dv04_x", "dvh11_les_dossiers_de_location"]
    assert [nom_court(i) for i in codes] == ["t01", "h03", "dv04", "dvh11"]
