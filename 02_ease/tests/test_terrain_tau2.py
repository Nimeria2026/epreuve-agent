"""τ²-bench comme terrain d'EASE (étape 7) : témoins, frontière, chaîne d'un vrai candidat.

Le serveur de 11_bancs_publics tourne dans son propre processus, avec l'utilisateur écrit d'avance :
aucun modèle n'est appelé. Les données de τ²-bench sont récupérées une fois par la commande du
pont (réseau la première fois seulement).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from ease.candidat_externe import CandidatExterne, Lancement
from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import Configuration, Machine, Modele
from ease.executeur import Consommation, DescriptionOutil, ErreurOutil, Outils
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.temoins_tau2 import TerrainTau2, mesurer, temoins, terrain_tau2
from ease.terrain_tau2 import (
    OUTIL_CLIENT,
    RESERVES,
    EnvironnementTau2,
    TacheTau2,
    executer_une_fois,
    lire_evaluation,
)

PLANCHER_SIERRA = [
    str(n) for n in (0, 1, 2, 4, 5, 6, 9, 10, 13, 26, 27, 28, 31, 34, 36, 38, 41, 43, 45, 46, 47, 48, 49)
]
"""Les 23 tâches d'airline qu'un agent inerte réussit (2026-10-08_faits_tau2_bench.md, script 1)."""


@pytest.fixture(scope="module")
def donnees() -> None:
    subprocess.run([sys.executable, "-m", "bancs_publics.tau2_bench.donnees"], check=True, capture_output=True)


@pytest.fixture
def environnement(donnees: None, tmp_path: Path) -> Iterator[EnvironnementTau2]:
    del donnees
    with EnvironnementTau2("sierra", travail=tmp_path / "travail") as environnement:
        yield environnement


def test_l_agent_ne_voit_ni_n_appelle_les_outils_reserves(environnement: EnvironnementTau2) -> None:
    noms = [o.nom for o in environnement.outils()]
    assert len(noms) == 15 and OUTIL_CLIENT in noms
    assert not RESERVES & set(noms)
    environnement.ouvrir(TacheTau2("0"), "essai_r1")
    for reserve in sorted(RESERVES):
        with pytest.raises(ErreurOutil, match="Unknown tool"):
            environnement.appeler(reserve, {})
    assert environnement.enonce().startswith("<instructions>")
    evaluation = environnement.fermer()
    assert (evaluation.recompense, evaluation.terminaison) == (1.0, "agent_stop")


def test_le_plancher_d_inertie_d_airline_se_calcule_sans_tau2(environnement: EnvironnementTau2) -> None:
    """Depuis le fichier de tâches et ce que chaque outil annonce : 23 tâches sur 50."""
    terrain = terrain_tau2("sierra")
    plancher = terrain.plancher(environnement.outils())
    assert plancher == [f"airline_{n}" for n in PLANCHER_SIERRA]
    assert len(terrain.taches) == 50


def test_les_quatre_temoins_obtiennent_leurs_taux(environnement: EnvironnementTau2, tmp_path: Path) -> None:
    """Parfait 100 %, toujours faux 0 %, une fois sur deux 50 %, inerte son plancher (0 et 1 sur 0, 1, 14, 33)."""
    terrain = terrain_tau2("sierra", ["0", "1", "14", "33"])
    plancher = terrain.plancher(environnement.outils())
    assert plancher == ["airline_0", "airline_1"]
    obtenus: dict[str, tuple[int, int]] = {}
    for temoin in temoins(terrain):
        dossier, resume = mesurer(temoin, terrain, environnement, 2, tmp_path / "runs")
        assert resume.erreurs_techniques == 0
        assert resume.reussites == temoin.reussites_attendues(resume.executions, len(plancher))
        obtenus[temoin.identifiant] = (resume.reussites, resume.executions)
        fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
        assert fiche.statut == "termine" and fiche.jeu_taches.nom == "tau2_airline_sierra"
        assert [t.identifiant for t in fiche.jeu_taches.taches] == [t.identifiant for t in terrain.taches]
        assert fiche.etat_pme.version == "v1" and fiche.etat_pme.empreinte == environnement.empreinte()
    assert obtenus == {
        "temoin_parfait": (8, 8),
        "temoin_toujours_faux": (0, 8),
        "temoin_une_fois_sur_deux": (4, 8),
        "temoin_inerte": (4, 8),
    }


def test_un_resultat_porte_la_note_de_tau2_bench_et_le_journal_chaque_geste(
    environnement: EnvironnementTau2, tmp_path: Path
) -> None:
    terrain = terrain_tau2("sierra", ["14"])
    dossier, resume = mesurer(temoins(terrain)[0], terrain, environnement, 1, tmp_path / "runs")
    assert resume.pass_k == {1: 1.0}
    resultat = lire_resultat(dossier / "resultats" / "airline_14_r1.json")
    assert resultat.reussie and resultat.etapes == 3
    assert resultat.controles[0].detail is not None
    assert resultat.controles[0].detail.startswith("τ²-bench : récompense 1 ; fin user_stop ; base égale")
    gestes = [json.loads(ligne)["outil"] for ligne in (dossier / "journaux" / "airline_14_r1.jsonl").open()]
    assert gestes == ["cancel_reservation", "book_reservation", OUTIL_CLIENT]
    note = lire_evaluation(environnement.travail / f"{dossier.name}_airline_14_r1" / "evaluation.json")
    assert [p.phrase for p in note.phrases] == ["327", "1000", "1786"]
    assert (environnement.travail / f"{dossier.name}_airline_14_r1" / "simulation.json").is_file()


def test_le_jeu_verified_se_mesure_a_part(donnees: None, tmp_path: Path) -> None:
    del donnees
    terrain = terrain_tau2("verified", ["14", "33"])
    with EnvironnementTau2("verified", travail=tmp_path / "travail") as environnement:
        dossier, resume = mesurer(temoins(terrain)[0], terrain, environnement, 1, tmp_path / "runs")
    assert (resume.reussites, resume.executions) == (2, 2)
    assert lire_fiche_de_run(dossier / "fiche_de_run.json").jeu_taches.nom == "tau2_airline_verified"
    assert terrain.solutions["airline_14"][-1] == (OUTIL_CLIENT, {"message": "327 1000 44"})


def _repondre(terrain: TerrainTau2, corps: dict[str, Any]) -> dict[str, Any]:
    """Le modèle simulé reconnaît la tâche à l'énoncé et rejoue la solution du témoin parfait,
    un appel d'outil par tour, message au client compris ; puis il rend la main."""
    messages: list[dict[str, Any]] = corps["messages"]
    actions = terrain.solutions[terrain.tache(messages[1]["content"])]
    faits = sum(1 for m in messages if m["role"] == "assistant")
    if faits < len(actions):
        nom, arguments = actions[faits]
        appel = {
            "id": f"appel-{faits}",
            "type": "function",
            "function": {"name": nom, "arguments": json.dumps(arguments)},
        }
        message: dict[str, Any] = {"role": "assistant", "content": None, "tool_calls": [appel]}
    else:
        message = {"role": "assistant", "content": "Conversation terminée."}
    usage = {"prompt_tokens": len(json.dumps(messages)) // 4, "completion_tokens": 10}
    return {"model": "modele-simule", "choices": [{"index": 0, "message": message}], "usage": usage}


@pytest.fixture
def modele_simule(tmp_path: Path, donnees: None) -> Iterator[tuple[Path, TerrainTau2]]:
    del donnees
    terrain = terrain_tau2("sierra", ["0", "14"])

    class Gestionnaire(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            reponse = json.dumps(_repondre(terrain, corps)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reponse)))
            self.end_headers()
            self.wfile.write(reponse)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    configuration = tmp_path / "modele_simule.yaml"
    configuration.write_text(
        f"role: agent\nmodele: modele-demande\nadresse: http://127.0.0.1:{serveur.server_address[1]}/v1\n"
        "cle_env: null\nparametres: {}\nraisonnement_renvoye: null\ndelai_appel_secondes: 30\ntours_max: 40\n",
        encoding="utf-8",
    )
    yield configuration, terrain
    serveur.shutdown()
    fil.join(5)


def test_l_agent_seul_et_un_modele_simule_jouent_tau2_bench_par_le_relais(
    modele_simule: tuple[Path, TerrainTau2], tmp_path: Path
) -> None:
    """La chaîne d'un vrai candidat : agent seul dans son processus, relais d'EASE, serveur de τ²-bench."""
    configuration, terrain = modele_simule
    modele = Modele(
        role="agent", nom="modele-demande", fournisseur="local", version_renvoyee="?", parametres={}, tarif=None
    )
    fiche = FicheCandidat(
        identifiant="agent_seul_modele_simule",
        nom="Agent seul sur un modèle simulé",
        version="0.1.0",
        origine="fait_main",
        division="a_modele_egal",
        branchement="mcp",
        editeur="Épreuve d'agent",
        url=None,
        modeles="?",
        cout_mesurable=False,
        conditions_utilisation=None,
    )
    commande = [sys.executable, "-m", "orchestrations.agent_seul", "--configuration", str(configuration)]
    candidat = CandidatExterne(fiche, Configuration(modeles=[modele]), Lancement(commande, delai_secondes=120))
    with EnvironnementTau2("sierra", travail=tmp_path / "travail") as environnement:
        dossier, resume = mesurer(candidat, terrain, environnement, 1, tmp_path / "runs")
    assert (resume.reussites, resume.executions, resume.erreurs_techniques) == (2, 2, 0)
    fiche_run = lire_fiche_de_run(dossier / "fiche_de_run.json")
    assert fiche_run.configuration.modeles[0].version_renvoyee == "modele-simule"
    resultat = lire_resultat(dossier / "resultats" / "airline_14_r1.json")
    assert resultat.etapes == 3 and resultat.jetons.entree != "?"


class _ServeurSansNote(EnvironnementTau2):
    """Un serveur de τ²-bench dont la clôture ne rend pas de note, comme le 2026-10-27 à airline_33,
    quand le client simulé n'a pas répondu (JOURNAL, entrée 325). Aucun processus n'est lancé."""

    def __init__(self, travail: Path) -> None:
        super().__init__("sierra", travail=travail)
        self.ouvertes: list[str] = []
        self.clotures = 0

    def ouvrir(self, tache: TacheTau2, execution: str, essai: int = 0) -> None:
        del tache, essai
        self.ouvertes.append(execution)

    def enonce(self) -> str:
        return "Un client appelle au sujet de sa réservation."

    def outils(self) -> list[DescriptionOutil]:
        return []

    def fermer(self) -> Any:
        self.clotures += 1
        raise RuntimeError("τ²-bench n'a pas rendu de simulation")


class _CandidatQuiParle:
    """Un candidat sans modèle, qui rend la main sans geste."""

    def __init__(self) -> None:
        modele = Modele(role="agent", nom="aucun", fournisseur="local", version_renvoyee="?", parametres={}, tarif=None)
        self.configuration = Configuration(modeles=[modele])
        self.fiche = FicheCandidat(
            identifiant="candidat_qui_parle",
            nom="Candidat qui parle",
            version="0.1.0",
            origine="fait_main",
            division="a_modele_egal",
            branchement="mcp",
            editeur="Épreuve d'agent",
            url=None,
            modeles="?",
            cout_mesurable=False,
            conditions_utilisation=None,
        )
        self.empreinte_prompts: str | None = None
        self.machine: Machine | None = None

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        del enonce, outils
        return Consommation()


RUN = "2026-10-27_103013_candidat_qui_parle"


def test_une_cloture_sans_note_finit_en_erreur_technique_et_le_run_continue(tmp_path: Path) -> None:
    (tmp_path / "journaux").mkdir()
    serveur, candidat = _ServeurSansNote(tmp_path / "travail"), _CandidatQuiParle()
    resultats = [executer_une_fois(candidat, serveur, TacheTau2(numero), RUN, 1, tmp_path) for numero in ("33", "34")]
    assert serveur.clotures == 2 and len(serveur.ouvertes) == 2
    for resultat in resultats:
        assert resultat.arret == "erreur_technique" and not resultat.reussie
        assert resultat.detail_arret is not None and "n'a pas rendu de simulation" in resultat.detail_arret
        assert [c.score for c in resultat.controles] == [0.0]
