"""Auteur et relecteur sur τ²-bench, par EASE et le vrai serveur de τ²-bench (étape 7, A/B décidé
par Alexandre le 2026-10-11) : le relais, l'accès en lecture seule du relecteur, la fiche.

Le serveur tourne avec l'utilisateur écrit d'avance ; un modèle simulé joue l'auteur (la solution
du témoin parfait, comme dans test_mesure_tau2.py) et le relecteur : aucun modèle réel n'est
appelé, aucune clé n'est lue.
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
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.mesure_tau2 import lire_candidat_tau2
from ease.temoins_tau2 import TerrainTau2, terrain_tau2
from ease.terrain_tau2 import OUTIL_CLIENT, EnvironnementTau2, lancer_run

RACINE = Path(__file__).resolve().parents[2]
CONSIGNES = RACINE / "03_orchestrations" / "src" / "orchestrations" / "consignes"
CANDIDAT = "auteur_relecteur_tau2_deepseek_flash"


@pytest.fixture(scope="module")
def donnees() -> None:
    subprocess.run([sys.executable, "-m", "bancs_publics.tau2_bench.donnees"], check=True, capture_output=True)


def _message(message: dict[str, Any]) -> dict[str, Any]:
    usage = {"prompt_tokens": 100, "completion_tokens": 10}
    return {"model": "modele-simule", "choices": [{"index": 0, "message": message}], "usage": usage}


def _appel(nom: str, arguments: dict[str, Any], identifiant: str) -> dict[str, Any]:
    appel = {"id": identifiant, "type": "function", "function": {"name": nom, "arguments": json.dumps(arguments)}}
    return {"role": "assistant", "content": None, "tool_calls": [appel]}


def _auteur(terrain: TerrainTau2, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """La solution du témoin parfait, un geste par tour ; un geste renvoyé compte comme fait."""
    actions = terrain.solutions[terrain.tache(f"user: {messages[2]['content']}")]
    faits = sum(1 for m in messages if m["role"] == "assistant") - 1  # le salut est de τ²-bench
    if faits < len(actions) and actions[faits][0] != OUTIL_CLIENT:
        nom, arguments = actions[faits]
        return _appel(nom, arguments, f"auteur-{faits}")
    if faits < len(actions):
        return {"role": "assistant", "content": actions[faits][1]["message"]}
    return {"role": "assistant", "content": "Anything else?"}


def _relecteur(messages: list[dict[str, Any]], accord: bool) -> dict[str, Any]:
    """Une lecture par l'accès en lecture seule à chaque nouvelle action, puis le verdict."""
    numero = len(messages)
    if messages[-1]["role"] == "user":
        return _appel("list_all_airports", {}, f"lecture-{numero}")
    raison = "approved after checking" if accord else "the customer did not confirm"
    return _appel("verdict", {"approved": accord, "reason": raison}, f"verdict-{numero}")


@pytest.fixture
def modeles(
    tmp_path: Path, donnees: None, request: pytest.FixtureRequest
) -> Iterator[tuple[Path, TerrainTau2, list[dict[str, Any]]]]:
    del donnees
    accord: bool = request.param
    terrain = terrain_tau2("sierra", ["0", "14"])
    consigne_relecteur = (CONSIGNES / "relecteur_en.md").read_text(encoding="utf-8")
    recus: list[dict[str, Any]] = []

    class Gestionnaire(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            recus.append(corps)
            messages: list[dict[str, Any]] = corps["messages"]
            if messages[0]["content"] == consigne_relecteur:
                reponse = _message(_relecteur(messages, accord))
            else:
                reponse = _message(_auteur(terrain, messages))
            donnees = json.dumps(reponse).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    configuration = tmp_path / "modele_simule.yaml"
    configuration.write_text(
        f"role: agent\nmodele: modele-demande\nadresse: http://127.0.0.1:{serveur.server_address[1]}/v1\n"
        "cle_env: null\nparametres: {temperature: 0.0, tool_choice: auto}\nraisonnement_renvoye: null\n"
        "delai_appel_secondes: 30\ntours_max: 40\n",
        encoding="utf-8",
    )
    yield configuration, terrain, recus
    serveur.shutdown()
    fil.join(5)


def _candidat(configuration: Path) -> CandidatExterne:
    """Le candidat déclaré, relancé sur le modèle simulé pour les deux rôles, hors créneau."""
    declare = lire_candidat_tau2(CANDIDAT)
    assert declare.lancement.acces_lecture
    commande = [
        sys.executable,
        "-m",
        "orchestrations.auteur_relecteur_tau2",
        "--configuration",
        str(configuration),
        "--relecteur",
        str(configuration),
    ]
    lancement = Lancement(commande, delai_secondes=120, acces_lecture=True)
    return CandidatExterne(declare.fiche, declare.configuration, lancement, declare.empreinte_prompts)


def _lancer(configuration: Path, terrain: TerrainTau2, tmp_path: Path) -> Path:
    with EnvironnementTau2("sierra", travail=tmp_path / "travail") as environnement:
        return lancer_run(
            candidat=_candidat(configuration),
            environnement=environnement,
            taches=terrain.taches,
            repetitions=1,
            dossier_runs=tmp_path / "runs",
        )


def _lignes(chemin: Path) -> list[dict[str, Any]]:
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("modeles", [True], indirect=True)
def test_les_gestes_accordes_partent_et_le_relecteur_lit_a_part(
    modeles: tuple[Path, TerrainTau2, list[dict[str, Any]]], tmp_path: Path
) -> None:
    configuration, terrain, recus = modeles
    dossier = _lancer(configuration, terrain, tmp_path)
    resultats = [lire_resultat(c) for c in sorted((dossier / "resultats").glob("*.json"))]
    assert [(r.tache.identifiant, r.reussie, r.arret) for r in resultats] == [
        ("airline_0", True, "termine"),
        ("airline_14", True, "termine"),
    ]
    # Les gestes de l'auteur, au budget de la tâche ; les lectures du relecteur, à part.
    gestes = [ligne["outil"] for ligne in _lignes(dossier / "journaux" / "airline_14_r1.jsonl")]
    assert gestes == ["cancel_reservation", "book_reservation", OUTIL_CLIENT]
    lectures = _lignes(dossier / "journaux" / "airline_14_r1_lectures.jsonl")
    assert [(ligne["outil"], ligne["erreur"]) for ligne in lectures] == [("list_all_airports", None)] * 2
    # L'auteur : la consigne de τ²-bench, puis la phrase sur la relecture ; les 14 outils.
    auteur = next(r for r in recus if r["messages"][0]["content"].startswith("<instructions>"))
    phrase = (CONSIGNES / "relecture_auteur_en.md").read_text(encoding="utf-8").strip()
    assert auteur["messages"][0]["content"].endswith(f"</policy>\n\n{phrase}")
    assert len(auteur["tools"]) == 14 and OUTIL_CLIENT not in {o["function"]["name"] for o in auteur["tools"]}
    assert (auteur["temperature"], auteur["tool_choice"]) == (0.0, "auto")
    # Le relecteur : la politique et la conversation, les seuls outils en lecture et le verdict.
    relecteur = next(r for r in recus if r["messages"][0]["content"].startswith("You review"))
    demande = relecteur["messages"][1]["content"]
    assert "# Airline Agent Policy" in demande and "assistant: Hi! How can I help you today?\nuser: " in demande
    assert sorted(o["function"]["name"] for o in relecteur["tools"]) == [
        "get_flight_status",
        "get_reservation_details",
        "get_user_details",
        "list_all_airports",
        "search_direct_flight",
        "search_onestop_flight",
        "verdict",
    ]
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    assert fiche.candidat.identifiant == CANDIDAT and fiche.banc_public is not None
    assert {m.role for m in fiche.configuration.modeles} == {"auteur", "relecteur"}
    # Les jetons des deux rôles s'additionnent ; le modèle simulé ne dit rien du cache, d'où « ? ».
    assert all(isinstance(r.jetons.entree, int) and r.jetons.entree > 0 for r in resultats)
    assert all(r.jetons.entree_en_cache == "?" and r.cout_dollars == "?" for r in resultats)


@pytest.mark.parametrize("modeles", [False], indirect=True)
def test_un_geste_renvoye_ne_part_pas_et_la_tache_echoue(
    modeles: tuple[Path, TerrainTau2, list[dict[str, Any]]], tmp_path: Path
) -> None:
    configuration, terrain, recus = modeles
    dossier = _lancer(configuration, terrain, tmp_path)
    resultat = lire_resultat(dossier / "resultats" / "airline_14_r1.json")
    assert (resultat.reussie, resultat.arret) == (False, "termine")
    gestes = [ligne["outil"] for ligne in _lignes(dossier / "journaux" / "airline_14_r1.jsonl")]
    assert gestes == [OUTIL_CLIENT]  # les deux gestes qui écrivent sont renvoyés
    renvois = [
        m["content"]
        for r in recus
        if r["messages"][0]["content"].startswith("<instructions>")
        for m in r["messages"]
        if m["role"] == "tool"
    ]
    assert "Error: sent back by the reviewer: the customer did not confirm" in renvois
