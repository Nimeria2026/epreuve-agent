"""Candidat externe : budget épuisé, délai dépassé, panne et sortie du candidat, vus par EASE."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ease.candidat_externe import CandidatExterne, Creneau, Lancement
from ease.contrats.fiche_de_run import Configuration, Modele
from ease.contrats.resultat_execution import ResultatExecution
from ease.executeur import ArretDuRun, lancer_run
from ease.jouet import TACHES_JOUET, ClasseurJouet
from ease.temoins import fiche_temoin
from ease.verification import verifier

# Un candidat écrit en quelques lignes, lancé par « python -c » ; EASE ajoute --mcp, --enonce et --sortie.
BAVARD = """
import sys, anyio
from mcp import Client
adresse = sys.argv[sys.argv.index("--mcp") + 1]
async def bavarder():
    async with Client(adresse, mode="legacy", cache=None) as client:
        while True:
            await client.call_tool("lister", {"dossier": "arrivee"})
anyio.run(bavarder)
"""

ECONOME = """
import json, sys
from pathlib import Path
sortie = Path(sys.argv[sys.argv.index("--sortie") + 1])
sortie.write_text(json.dumps({
    "fin": "termine", "detail": None, "appels_modele": 2,
    "consommation": {"agent": {"entree": 1200, "entree_en_cache": 800, "sortie": 90}},
    "modeles_renvoyes": {"agent": "modele-annonce"},
}))
"""

# Un poste humain rend la durée qu'il a chronométrée, sans modèle ni jeton (JOURNAL, entrée 121).
CHRONOMETRE = """
import json, sys
from pathlib import Path
sortie = Path(sys.argv[sys.argv.index("--sortie") + 1])
sortie.write_text(json.dumps({
    "fin": "termine", "detail": None, "appels_modele": 0, "consommation": {}, "modeles_renvoyes": {},
    "duree_chronometree_secondes": 42.5,
}))
"""


# Le serveur du modèle a refusé une conversation trop longue (cadrage du 2026-10-14, choix T3).
TROP_LONG = """
import json, sys
from pathlib import Path
sortie = Path(sys.argv[sys.argv.index("--sortie") + 1])
sortie.write_text(json.dumps({
    "fin": "contexte_depasse", "detail": "HTTP 400 : maximum context length is 40960 tokens", "appels_modele": 3,
    "consommation": {"agent": {"entree": 52000, "entree_en_cache": 30000, "sortie": 700}},
    "modeles_renvoyes": {"agent": "modele-annonce"},
}))
"""


# Imite nvidia-smi -lms : une puissance de 200 W toutes les 50 ms, jusqu'à l'arrêt.
IMITATION = "import time\nwhile True:\n    print('200.00', flush=True)\n    time.sleep(0.05)"
CARTE_A_200_WATTS = [sys.executable, "-c", IMITATION]


def _candidat(
    script: str, delai: float = 60, creneau: Creneau | None = None, wattmetre: list[str] | None = None
) -> CandidatExterne:
    modele = Modele(
        role="agent", nom="modele-demande", fournisseur="local", version_renvoyee="?", parametres={}, tarif=None
    )
    return CandidatExterne(
        fiche=fiche_temoin("candidat_essai", "Candidat d'essai"),
        configuration=Configuration(modeles=[modele]),
        lancement=Lancement([sys.executable, "-c", script], delai_secondes=delai, creneau=creneau, wattmetre=wattmetre),
    )


def _run(candidat: CandidatExterne, dossier_runs: Path) -> Path:
    return lancer_run(
        candidat=candidat,
        environnement=ClasseurJouet(),
        taches=TACHES_JOUET,
        controleur=verifier,
        repetitions=1,
        nom_jeu="jouet",
        dossier_runs=dossier_runs,
    )


def _resultats(dossier: Path) -> list[ResultatExecution]:
    return [
        ResultatExecution.model_validate_json(chemin.read_text(encoding="utf-8"))
        for chemin in sorted((dossier / "resultats").glob("*.json"))
    ]


def test_un_candidat_qui_epuise_son_budget_est_arrete_et_note_en_budget_etapes(tmp_path: Path) -> None:
    dossier = _run(_candidat(BAVARD), tmp_path)
    for resultat in _resultats(dossier):
        assert (resultat.arret, resultat.etapes, resultat.reussie) == ("budget_etapes", 8, False)
        assert resultat.jetons.entree == "?"


def test_un_candidat_trop_lent_est_arrete_et_compte_en_echec_sous_delai_depasse(tmp_path: Path) -> None:
    """Choix D1 du cadrage du générateur des images : un échec de l'agent, dans le taux, plus une panne."""
    dossier = _run(_candidat("import time; time.sleep(30)", delai=1), tmp_path)
    for resultat in _resultats(dossier):
        assert (resultat.arret, resultat.reussie) == ("delai_depasse", False)
        assert "arrêté après 1 s" in (resultat.detail_arret or "")
        assert resultat.jetons.entree == "?"


def test_un_appel_trop_lent_signale_par_le_candidat_est_un_delai_depasse_avec_ses_jetons(tmp_path: Path) -> None:
    """Choix S1 du cadrage du second Qwen local : l'appel au modèle a dépassé son délai."""
    dossier = _run(_candidat(TROP_LONG.replace('"contexte_depasse"', '"delai_depasse"')), tmp_path)
    for resultat in _resultats(dossier):
        assert (resultat.arret, resultat.reussie) == ("delai_depasse", False)
        assert (resultat.jetons.entree, resultat.jetons.sortie) == (52000, 700)


def test_un_candidat_qui_plante_est_note_en_erreur_technique(tmp_path: Path) -> None:
    dossier = _run(_candidat("raise SystemExit(3)"), tmp_path)
    for resultat in _resultats(dossier):
        assert resultat.arret == "erreur_technique"
        assert "code 3" in (resultat.detail_arret or "")


def test_un_contexte_depasse_est_un_echec_de_l_agent_sous_son_arret_avec_ses_jetons(tmp_path: Path) -> None:
    """Choix T3 du 2026-10-14 : compté dans le taux, sous un arrêt à part, et non en erreur technique."""
    dossier = _run(_candidat(TROP_LONG), tmp_path)
    for resultat in _resultats(dossier):
        assert (resultat.arret, resultat.reussie) == ("contexte_depasse", False)
        assert "maximum context length" in (resultat.detail_arret or "")
        assert (resultat.jetons.entree, resultat.jetons.sortie) == (52000, 700)


def test_la_consommation_et_le_modele_annonce_viennent_de_la_sortie(tmp_path: Path) -> None:
    dossier = _run(_candidat(ECONOME), tmp_path)
    resultat = _resultats(dossier)[0]
    assert (resultat.jetons.entree, resultat.jetons.entree_en_cache, resultat.jetons.sortie) == (1200, 800, 90)
    assert resultat.energie_wh is None  # pas de wattmètre déclaré
    fiche = json.loads((dossier / "fiche_de_run.json").read_text(encoding="utf-8"))
    assert fiche["configuration"]["modeles"][0]["version_renvoyee"] == "modele-annonce"


def test_la_duree_chronometree_d_un_poste_humain_passe_dans_le_resultat(tmp_path: Path) -> None:
    dossier = _run(_candidat(CHRONOMETRE), tmp_path)
    for resultat in _resultats(dossier):
        assert resultat.arret == "termine" and resultat.duree_chronometree_secondes == 42.5
    agent = _resultats(_run(_candidat(ECONOME), tmp_path / "agent"))[0]
    assert agent.duree_chronometree_secondes is None


def test_l_energie_de_la_carte_est_notee_quand_un_wattmetre_est_declare(tmp_path: Path) -> None:
    for resultat in _resultats(_run(_candidat(ECONOME, wattmetre=CARTE_A_200_WATTS), tmp_path)):
        assert isinstance(resultat.energie_wh, float)
        # 200 W pendant toute l'exécution du candidat, au plus sa durée totale.
        assert 0 < resultat.energie_wh * 3600 <= 200 * resultat.duree_secondes


def _horloge(monkeypatch: pytest.MonkeyPatch, instant: datetime) -> None:
    monkeypatch.setattr("ease.candidat_externe.maintenant", lambda: instant)


def test_un_run_aux_heures_creuses_s_arrete_avant_les_heures_pleines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _horloge(monkeypatch, datetime(2026, 10, 5, 5, 50, tzinfo=UTC))  # un lundi, 10 minutes avant 6 h UTC
    with pytest.raises(ArretDuRun, match="06:00 UTC"):
        _run(_candidat(ECONOME, creneau="heures_creuses_deepseek"), tmp_path)
    (dossier,) = tmp_path.iterdir()
    fiche = json.loads((dossier / "fiche_de_run.json").read_text(encoding="utf-8"))
    assert fiche["statut"] == "interrompu"
    assert "heures pleines" in fiche["raison_interruption"]
    assert _resultats(dossier) == []


def test_un_run_aux_heures_creuses_tourne_en_heures_creuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _horloge(monkeypatch, datetime(2026, 10, 5, 12, 0, tzinfo=UTC))
    dossier = _run(_candidat(ECONOME, creneau="heures_creuses_deepseek"), tmp_path)
    assert len(_resultats(dossier)) == len(TACHES_JOUET)
