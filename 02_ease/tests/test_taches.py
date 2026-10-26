"""Les tâches de 07_taches/public/ respectent leur contrat, et le contrat refuse ce qu'il doit."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from ease.contrats.tache import Tache
from ease.solutions_pme import SOLUTIONS_PME
from ease.taches import TacheInvalide, budget_etapes, coherence_pme, lire_tache, lire_taches, racine_depot
from jsonschema import Draft202012Validator

RACINE = racine_depot()
PUBLIC = RACINE / "07_taches" / "public"
TACHES = sorted(PUBLIC.glob("t[0-9]*.yaml"))
REFERENCE = PUBLIC / "t01_ranger_facture_fournisseur.yaml"


def test_le_schema_de_tache_est_un_json_schema_2020_12_valide() -> None:
    schema = json.loads((RACINE / "01_contrats" / "tache.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_les_cinq_premieres_taches_sont_presentes() -> None:
    assert [chemin.stem[:3] for chemin in TACHES][:5] == ["t01", "t02", "t03", "t04", "t05"]


@pytest.mark.parametrize("chemin", TACHES, ids=lambda c: c.stem)
def test_chaque_tache_respecte_son_contrat(chemin: Path) -> None:
    tache = lire_tache(chemin)
    assert tache.identifiant == chemin.stem


@pytest.mark.parametrize("chemin", TACHES, ids=lambda c: c.stem)
def test_chaque_tache_est_coherente_avec_la_pme(chemin: Path) -> None:
    assert coherence_pme(lire_tache(chemin)) == []


@pytest.mark.parametrize("chemin", TACHES, ids=lambda c: c.stem)
def test_chaque_budget_suit_la_regle_du_temoin(chemin: Path) -> None:
    tache = lire_tache(chemin)
    assert tache.budget.etapes_max == budget_etapes(len(SOLUTIONS_PME[tache.identifiant]))


def test_la_regle_du_budget_arrondit_aux_cinq_du_dessus() -> None:
    assert [budget_etapes(n) for n in (2, 3, 4, 38)] == [30, 35, 35, 105]


def test_le_modele_de_tache_respecte_le_contrat() -> None:
    lire_tache(PUBLIC / "modele_tache.yaml")


def test_lire_taches_les_charge_toutes_dans_l_ordre() -> None:
    assert [t.identifiant for t in lire_taches(PUBLIC)] == [c.stem for c in TACHES]


# Cas refusés : une copie de t01, modifiée, écrite dans un dossier temporaire.


def _copie(tmp_path: Path, modifier: Callable[[dict[str, Any]], object], nom: str = REFERENCE.name) -> Path:
    donnees = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    modifier(donnees)
    chemin = tmp_path / nom
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _refus(chemin: Path) -> str:
    with pytest.raises(TacheInvalide) as erreur:
        lire_tache(chemin)
    return str(erreur.value)


def test_un_champ_inconnu_est_refuse(tmp_path: Path) -> None:
    assert "solution" in _refus(_copie(tmp_path, lambda d: d.update(solution="tricher")))


def test_un_champ_manquant_est_refuse(tmp_path: Path) -> None:
    assert "budget" in _refus(_copie(tmp_path, lambda d: d.pop("budget")))


def test_une_famille_de_controle_inconnue_est_refusee(tmp_path: Path) -> None:
    def modifier(d: dict[str, Any]) -> None:
        d["controles"][0]["famille"] = "ressenti"

    assert "ressenti" in _refus(_copie(tmp_path, modifier))


def test_des_poids_dont_la_somme_ne_vaut_pas_1_sont_refuses(tmp_path: Path) -> None:
    def modifier(d: dict[str, Any]) -> None:
        d["controles"][0]["poids"] = 0.5

    assert "somme des poids vaut 0.9" in _refus(_copie(tmp_path, modifier))


def test_un_service_en_double_est_refuse(tmp_path: Path) -> None:
    assert "services" in _refus(_copie(tmp_path, lambda d: d.update(services=["dossiers", "dossiers"])))


def test_un_identifiant_different_du_nom_de_fichier_est_refuse(tmp_path: Path) -> None:
    chemin = _copie(tmp_path, lambda d: None, nom="t99_autre_nom.yaml")
    assert "diffère du nom du fichier" in _refus(chemin)


def test_une_personne_absente_de_l_organigramme_est_signalee() -> None:
    tache = lire_tache(REFERENCE).model_copy(update={"agent_pour": "personne.inconnue"})
    assert coherence_pme(tache) == ["agent_pour : « personne.inconnue » est absent de l'organigramme v3"]


def test_un_service_inconnu_de_la_pme_est_signale() -> None:
    tache = lire_tache(REFERENCE).model_copy(update={"services": ["messagerie", "dossiers", "telepathie"]})
    assert coherence_pme(tache) == ["services : « telepathie » n'est pas un service de la PME"]


def test_une_tache_qui_renvoie_au_manuel_sans_le_service_dossiers_est_signalee() -> None:
    tache = lire_tache(REFERENCE).model_copy(update={"services": ["messagerie"]})
    assert coherence_pme(tache) == [
        "services : l'énoncé renvoie au manuel, qui ne se lit que par le service dossiers (commun/)"
    ]


def test_un_complement_absent_est_signale() -> None:
    tache = lire_tache(REFERENCE).model_copy(update={"complement": "inexistant"})
    assert coherence_pme(tache) == [
        "complement : « inexistant » n'existe ni pour les tâches publiques ni pour les cachées"
    ]


def test_des_envois_a_la_fois_au_plus_et_au_moins_sont_refuses(tmp_path: Path) -> None:
    def modifier(d: dict[str, Any]) -> None:
        d["controles"][0]["verification"].append({"type": "envois", "nombre": 1, "au_plus": True, "au_moins": True})

    assert "à la fois au_plus et au_moins" in _refus(_copie(tmp_path, modifier))


def test_un_etat_initial_absent_est_signale() -> None:
    tache = lire_tache(REFERENCE).model_copy(update={"etat_initial": "v99"})
    assert coherence_pme(tache) == ["etat_initial : 05_pme/societes/calorelle/v99 n'existe pas"]


def test_un_run_prend_les_publiques_les_cachees_en_plus_ou_les_cachees_seules(monkeypatch: pytest.MonkeyPatch) -> None:
    # JOURNAL, entrée 111 : un candidat déjà mesuré sur les publiques ne passe que les cachées ; entrée
    # 171 : la tranche dure a sa propre part cachée, les autres jeux aucune.
    import ease.mesure as mesure
    from ease.taches import taches_dure

    modele = lire_tache(racine_depot() / "07_taches" / "public" / "t01_ranger_facture_fournisseur.yaml")
    cachee = modele.model_copy(update={"identifiant": "c01_essai_cachee"})
    cachee_dure = modele.model_copy(update={"identifiant": "hc01_essai_cachee"})
    parts = {"public": [cachee], "dure": [cachee_dure]}

    def cachees_du_jeu(jeu: str) -> list[Tache]:
        return parts.get(jeu, [])

    monkeypatch.setattr(mesure, "cachees_du_jeu", cachees_du_jeu)
    publiques = mesure.taches_du_run([])
    assert cachee not in publiques and len(publiques) == len(lire_taches(racine_depot() / "07_taches" / "public"))
    assert mesure.taches_du_run([], cachees=True) == [*publiques, cachee]
    assert mesure.taches_du_run([], seules=True) == [cachee]
    assert mesure.taches_du_run(["t01"], cachees=True) == [publiques[0]]
    assert mesure.taches_du_run([], cachees=True, jeu="dure") == [*taches_dure(), cachee_dure]
    assert mesure.taches_du_run([], seules=True, jeu="dure") == [cachee_dure]
    assert mesure.taches_du_run(["h01"], cachees=True, jeu="dure") == [taches_dure()[0]]
    assert mesure.taches_du_run([], cachees=True, jeu="documents") == mesure.taches_du_run([], jeu="documents")


def test_un_jeu_sans_part_cachee_refuse_les_cachees(capsys: pytest.CaptureFixture[str]) -> None:
    from ease.mesure import main

    assert main(["agent_seul_deepseek_flash", "--jeu", "documents", "--cachees"]) == 2
    assert "le jeu documents n'a pas de tâches cachées" in capsys.readouterr().err


def test_la_tranche_dure_est_un_jeu_a_part() -> None:
    """Ses tâches, h01 et suivantes, vivent dans 07_taches/public/dure/ (JOURNAL, entrée 130)."""
    import ease.mesure as mesure
    from ease.taches import dossier_du_jeu, taches_dure
    from ease.temoins import TERRAINS

    assert dossier_du_jeu("dure") == racine_depot() / "07_taches" / "public" / "dure"
    assert mesure.taches_du_run([], jeu="dure") == taches_dure()
    assert all(t.identifiant.startswith("h") for t in taches_dure())
    assert "dure" in TERRAINS
    with pytest.raises(ValueError, match="jeu inconnu"):
        dossier_du_jeu("autre")


def test_les_taches_cachees_ne_vont_jamais_chez_gmi_cloud() -> None:
    # Ce que GMI Cloud fait des requêtes n'a pas été lu (JOURNAL, entrées 103 et 111).
    from ease.candidats import lire_candidat
    from ease.mesure import main, refus_cachees

    for nom in ("agent_seul_qwen_max_gmi", "auteur_relecteur_qwen_max_gmi"):
        assert refus_cachees(lire_candidat(nom)) == "les tâches cachées ne vont pas chez GMI Cloud"
    assert refus_cachees(lire_candidat("agent_seul_deepseek_flash")) is None
    assert main(["auteur_relecteur_qwen_max_gmi", "--cachees-seules"]) == 2
    assert main(["agent_seul_qwen_max_gmi", "--cachees"]) == 2


def test_les_taches_cachees_ne_passent_jamais_par_la_route_gratuite_d_openrouter() -> None:
    # Ce que la route gratuite d'OpenRouter fait des requêtes n'est pas écrit (JOURNAL, entrée 224).
    from ease.candidats import lire_candidat
    from ease.mesure import main, refus_cachees

    nom = "agent_seul_minimax_m31_flash_openrouter"
    assert refus_cachees(lire_candidat(nom)) == "les tâches cachées ne vont pas chez OpenRouter, route gratuite"
    assert main([nom, "--cachees"]) == 2
    assert main([nom, "--cachees-seules"]) == 2
