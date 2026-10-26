"""Fiche de run, résultat d'exécution et fiche candidat : les exemples passent, les écarts sont refusés."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ease.chargement import ContratInvalide, racine_depot
from ease.courriels import lire_courriel
from ease.fiches import (
    coherence_resultat,
    lire_fiche_candidat,
    lire_fiche_de_run,
    lire_resultat,
    lire_sortie_candidat,
    raisons_non_classable,
)
from ease.taches import lire_tache
from jsonschema import Draft202012Validator

RACINE = racine_depot()
EXEMPLES = RACINE / "01_contrats" / "exemples"
TACHES = RACINE / "07_taches" / "public"
LECTEURS: dict[str, Callable[[Path], Any]] = {
    "courriel": lire_courriel,
    "fiche_candidat": lire_fiche_candidat,
    "fiche_de_run": lire_fiche_de_run,
    "resultat_execution": lire_resultat,
    "sortie_candidat": lire_sortie_candidat,
}


def _lecteur(chemin: Path) -> Callable[[Path], Any]:
    for prefixe, lecteur in LECTEURS.items():
        if chemin.name.startswith(prefixe):
            return lecteur
    raise AssertionError(f"exemple sans contrat reconnu : {chemin.name}")


@pytest.mark.parametrize("schema", sorted((RACINE / "01_contrats").glob("*.schema.json")), ids=lambda c: c.name)
def test_chaque_schema_est_un_json_schema_2020_12_valide(schema: Path) -> None:
    Draft202012Validator.check_schema(json.loads(schema.read_text(encoding="utf-8")))


@pytest.mark.parametrize("exemple", sorted(EXEMPLES.glob("*.json")), ids=lambda c: c.stem)
def test_chaque_exemple_respecte_son_contrat(exemple: Path) -> None:
    _lecteur(exemple)(exemple)


@pytest.mark.parametrize("exemple", sorted(EXEMPLES.glob("resultat_execution*.json")), ids=lambda c: c.stem)
def test_les_resultats_d_exemple_sont_coherents_avec_leur_tache(exemple: Path) -> None:
    resultat = lire_resultat(exemple)
    tache = lire_tache(TACHES / f"{resultat.tache.identifiant}.yaml")
    assert coherence_resultat(resultat, tache) == []


# Variantes refusées : un exemple modifié, écrit dans un dossier temporaire.


def _variante(tmp_path: Path, exemple: str, modifier: Callable[[dict[str, Any]], None]) -> Path:
    donnees = json.loads((EXEMPLES / f"{exemple}.json").read_text(encoding="utf-8"))
    modifier(donnees)
    chemin = tmp_path / f"{exemple}.json"
    chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    return chemin


def _refus(tmp_path: Path, exemple: str, modifier: Callable[[dict[str, Any]], None]) -> str:
    chemin = _variante(tmp_path, exemple, modifier)
    with pytest.raises(ContratInvalide) as erreur:
        _lecteur(chemin)(chemin)
    return str(erreur.value)


def _poser(**valeurs: Any) -> Callable[[dict[str, Any]], None]:
    def modifier(donnees: dict[str, Any]) -> None:
        donnees.update(valeurs)

    return modifier


def _commit_court(donnees: dict[str, Any]) -> None:
    donnees["code"]["commit"] = "cd571c5"


def _tache_en_double(donnees: dict[str, Any]) -> None:
    taches = donnees["jeu_taches"]["taches"]
    taches.append(taches[0])


def _cache_trop_grand(donnees: dict[str, Any]) -> None:
    donnees["jetons"]["entree_en_cache"] = 60000


# Fiche de run


@pytest.mark.parametrize(
    ("modification", "message"),
    [
        (_poser(fin_utc=None), "vide si et seulement si le run est en cours"),
        (_poser(statut="interrompu"), "renseignée si et seulement si le run est interrompu"),
        (_poser(fin_utc="2026-11-03T13:00:00Z"), "antérieure au début"),
        (_poser(identifiant="2026-11-04_agent_seul_deepseek_v41_flash"), "sa date doit être celle du début"),
        (_poser(debut_utc="2026-11-03T15:00:00+01:00"), "n'est pas en UTC"),
        (_poser(repetitions="?"), "repetitions"),
        (_poser(champ_inconnu=1), "champ_inconnu"),
        (_commit_court, "commit"),
        (_tache_en_double, "une tâche figure deux fois"),
    ],
    ids=[
        "termine_sans_fin",
        "interrompu_sans_raison",
        "fin_avant_debut",
        "date_identifiant",
        "pas_utc",
        "inconnu_interdit",
        "champ_inconnu",
        "commit_court",
        "tache_en_double",
    ],
)
def test_la_fiche_de_run_refuse(tmp_path: Path, modification: Callable[[dict[str, Any]], None], message: str) -> None:
    assert message in _refus(tmp_path, "fiche_de_run_api", modification)


def test_un_run_en_cours_ne_peut_pas_avoir_de_fin(tmp_path: Path) -> None:
    assert "en cours" in _refus(tmp_path, "fiche_de_run_local", _poser(fin_utc="2026-11-04T10:00:00Z"))


# Résultat d'exécution


def _controle(rang: int, **valeurs: Any) -> Callable[[dict[str, Any]], None]:
    def modifier(donnees: dict[str, Any]) -> None:
        donnees["controles"][rang - 1].update(valeurs)

    return modifier


@pytest.mark.parametrize(
    ("exemple", "modification", "message"),
    [
        ("resultat_execution_reussite", _poser(score=0.9), "recalculé depuis les contrôles"),
        ("resultat_execution_echec_partiel", _poser(reussie=True), "reussie : vraie si et seulement si"),
        ("resultat_execution_reussite", _poser(arret="budget_etapes"), "reussie : vraie si et seulement si"),
        (
            "resultat_execution_echec_partiel",
            _poser(arret="erreur_technique"),
            "obligatoire pour l'arrêt erreur_technique",
        ),
        ("resultat_execution_reussite", _controle(2, numero=3), "de 1 à n"),
        ("resultat_execution_reussite", _controle(2, poids=0.3, score=1), "somme des poids"),
        ("resultat_execution_reussite", _poser(journal="journaux/../../secret.jsonl"), "sortir du dossier du run"),
        ("resultat_execution_reussite", _cache_trop_grand, "dépasse l'entrée"),
        ("resultat_execution_reussite", _controle(1, score=1.5), "score"),
    ],
    ids=[
        "score_faux",
        "reussite_partielle",
        "reussite_hors_budget",
        "erreur_sans_detail",
        "numeros",
        "poids",
        "journal_hors_run",
        "cache_trop_grand",
        "score_hors_bornes",
    ],
)
def test_le_resultat_refuse(
    tmp_path: Path, exemple: str, modification: Callable[[dict[str, Any]], None], message: str
) -> None:
    assert message in _refus(tmp_path, exemple, modification)


def test_un_resultat_ne_se_rattache_pas_a_une_autre_tache() -> None:
    resultat = lire_resultat(EXEMPLES / "resultat_execution_reussite.json")
    autre = lire_tache(TACHES / "t02_envoyer_copie_contrat.yaml")
    assert coherence_resultat(resultat, autre)[0].startswith("tache : le résultat porte sur")


def test_une_erreur_technique_detaillee_est_acceptee_et_non_reussie(tmp_path: Path) -> None:
    def modifier(d: dict[str, Any]) -> None:
        d.update(arret="erreur_technique", detail_arret="API indisponible (HTTP 503)")

    resultat = lire_resultat(_variante(tmp_path, "resultat_execution_echec_partiel", modifier))
    assert not resultat.reussie


# Fiche candidat


@pytest.mark.parametrize(
    ("exemple", "modification", "message"),
    [
        ("fiche_candidat_temoin_parfait", _poser(division="a_modele_egal"), "vide pour un témoin"),
        ("fiche_candidat_temoin_parfait", _poser(modeles=[{"nom": "x", "fournisseur": "y"}]), "aucun modèle"),
        ("fiche_candidat_reference_locale", _poser(division=None), "renseignée pour tout autre candidat"),
        ("fiche_candidat_pret_a_l_emploi", _poser(conditions_utilisation=None), "obligatoires pour un produit"),
        (
            "fiche_candidat_reference_locale",
            _poser(
                conditions_utilisation={
                    "url": "https://a.example",
                    "lues_le": "2026-10-05",
                    "publication_permise": "oui",
                }
            ),
            "sans objet pour un candidat fait main",
        ),
        ("fiche_candidat_pret_a_l_emploi", _poser(origine="inconnue"), "origine"),
        ("fiche_candidat_humain", _poser(division="a_modele_egal"), "vide pour un témoin ou un humain"),
        ("fiche_candidat_humain", _poser(modeles=[{"nom": "x", "fournisseur": "y"}]), "aucun modèle"),
        ("fiche_candidat_humain", _poser(cout_mesurable=True), "faux pour un humain"),
    ],
    ids=[
        "temoin_divise",
        "temoin_avec_modele",
        "fait_main_sans_division",
        "sans_conditions",
        "conditions_fait_main",
        "origine_inconnue",
        "humain_divise",
        "humain_avec_modele",
        "humain_au_cout_mesurable",
    ],
)
def test_la_fiche_candidat_refuse(
    tmp_path: Path, exemple: str, modification: Callable[[dict[str, Any]], None], message: str
) -> None:
    assert message in _refus(tmp_path, exemple, modification)


def test_seul_un_candidat_publiable_est_classable(tmp_path: Path) -> None:
    assert raisons_non_classable(lire_fiche_candidat(EXEMPLES / "fiche_candidat_reference_locale.json")) == []
    assert raisons_non_classable(lire_fiche_candidat(EXEMPLES / "fiche_candidat_temoin_parfait.json"))
    assert raisons_non_classable(lire_fiche_candidat(EXEMPLES / "fiche_candidat_pret_a_l_emploi.json"))
    assert raisons_non_classable(lire_fiche_candidat(EXEMPLES / "fiche_candidat_humain.json")) == [
        "humain : la référence humaine du poste humain, jamais classée"
    ]

    def permettre(d: dict[str, Any]) -> None:
        d["conditions_utilisation"]["publication_permise"] = "oui"

    permis = lire_fiche_candidat(_variante(tmp_path, "fiche_candidat_pret_a_l_emploi", permettre))
    assert raisons_non_classable(permis) == []

    def debrancher(d: dict[str, Any]) -> None:
        d["branchement"] = "aucun"

    debranche = lire_fiche_candidat(_variante(tmp_path, "fiche_candidat_reference_locale", debrancher))
    assert raisons_non_classable(debranche) == ["non évaluable : aucun branchement possible"]


def test_une_fiche_candidat_en_yaml_garde_ses_dates_en_texte(tmp_path: Path) -> None:
    chemin = tmp_path / "fiche_candidat.yaml"
    chemin.write_text(
        "identifiant: agent_exemple\nnom: Agent Exemple\nversion: '2.3'\norigine: pret_a_l_emploi\n"
        "division: systeme_complet\nbranchement: mcp\nediteur: Éditeur fictif\nurl: '?'\nmodeles: '?'\n"
        "cout_mesurable: false\nconditions_utilisation:\n  url: https://editeur.example/conditions\n"
        "  lues_le: 2026-10-05\n  publication_permise: oui\n",
        encoding="utf-8",
    )
    assert str(lire_fiche_candidat(chemin).conditions_utilisation.lues_le) == "2026-10-05"  # type: ignore[union-attr]


# Courriel


@pytest.mark.parametrize(
    ("modification", "message"),
    [
        (_poser(a=["patrick@gmail.com"]), "a/0"),
        (_poser(date="2026-11-02T08:12:00"), "date"),
        (_poser(transfere_de="m-cpt-001"), "ne peut pas se citer lui-même"),
        (
            _poser(pieces_jointes=[{"nom": "x.pdf", "fichier": "pieces/m-autre/x.pdf", "taille_octets": 1}]),
            "doit être rangé sous pieces/m-cpt-001/",
        ),
    ],
    ids=["adresse_reelle", "date_sans_decalage", "se_cite", "piece_mal_rangee"],
)
def test_le_courriel_refuse(tmp_path: Path, modification: Callable[[dict[str, Any]], None], message: str) -> None:
    assert message in _refus(tmp_path, "courriel_facture", modification)


def test_une_sortie_de_candidat_qui_finit_mal_doit_s_expliquer(tmp_path: Path) -> None:
    donnees = json.loads((EXEMPLES / "sortie_candidat_agent_seul.json").read_text(encoding="utf-8"))
    donnees["fin"] = "erreur"
    chemin = tmp_path / "sortie.json"
    chemin.write_text(json.dumps(donnees), encoding="utf-8")
    with pytest.raises(ContratInvalide, match="detail : obligatoire"):
        lire_sortie_candidat(chemin)
    donnees |= {"fin": "termine", "appels_modele": 0}
    chemin.write_text(json.dumps(donnees), encoding="utf-8")
    with pytest.raises(ContratInvalide, match="sans aucun appel"):
        lire_sortie_candidat(chemin)
