"""Le pont de τ²-bench : données, outils, conversations jouées, note, serveur MCP.

Aucun modèle : l'utilisateur est écrit d'avance. Les gestes de référence viennent du fichier de
tâches de τ²-bench ; la note est celle de son évaluateur.
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import anyio
import pytest
from bancs_publics.tau2_bench import pont
from bancs_publics.tau2_bench.donnees import DONNEES, TACHES, Jeu, dossier_local, fichier_taches, verifier
from bancs_publics.tau2_bench.serveur import CLOTURER, OUVRIR, outils_mcp
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

RACINE = Path(__file__).resolve().parents[2]
DOSSIER = dossier_local()
"""Récupéré par conftest.py avant ce module."""


def _taches(jeu: Jeu) -> dict[str, Any]:
    return pont.lire_taches(fichier_taches(DOSSIER, jeu))


def _brutes(jeu: Jeu) -> dict[str, dict[str, Any]]:
    return {str(t["id"]): t for t in json.loads(fichier_taches(DOSSIER, jeu).read_text(encoding="utf-8"))}


def _jouer_reference(conversation: pont.Conversation, brute: dict[str, Any]) -> None:
    criteres = brute["evaluation_criteria"]
    for action in criteres["actions"] or []:
        reponse = conversation.outil(action["name"], action["arguments"])
        assert not reponse.erreur, reponse.texte
    conversation.message(" ".join(criteres["communicate_info"] or []) or "Done.")


def test_les_donnees_ont_leurs_empreintes() -> None:
    assert verifier(DOSSIER) == []
    assert len(DONNEES) == 6
    assert sorted(TACHES) == ["sierra", "verified"]


def test_un_fichier_modifie_est_signale(tmp_path: Path) -> None:
    copie = tmp_path / "tau2"
    shutil.copytree(DOSSIER, copie)
    politique = copie / "donnees" / "tau2" / "domains" / "airline" / "policy.md"
    politique.write_text(politique.read_text(encoding="utf-8") + "\nAjout.\n", encoding="utf-8")
    (copie / "jeux" / "verified.json").unlink()
    assert verifier(copie) == ["donnees/tau2/domains/airline/policy.md", "jeux/verified.json"]


def test_les_deux_jeux_ont_les_memes_50_taches() -> None:
    assert sorted(_brutes("sierra"), key=int) == sorted(_brutes("verified"), key=int) == [str(i) for i in range(50)]


def test_les_outils_sont_ceux_de_tau2_bench() -> None:
    outils = pont.outils_airline()
    types = {o.nom: o.type for o in outils}
    assert len(outils) == 14
    assert sorted(n for n, t in types.items() if t == "ecriture") == [
        "book_reservation",
        "cancel_reservation",
        "send_certificate",
        "update_reservation_baggages",
        "update_reservation_flights",
        "update_reservation_passengers",
    ]
    assert sorted(n for n, t in types.items() if t == "generique") == ["calculate", "transfer_to_human_agents"]
    assert all(o.description and o.schema.get("type") == "object" for o in outils)


def test_lecture_seule_annoncee_selon_le_type_de_tau2_bench() -> None:
    annonces = {o.name: o.annotations for o in outils_mcp(pont.outils_airline())}
    lecture = {nom: None if a is None else a.read_only_hint for nom, a in annonces.items()}
    assert lecture["get_user_details"] is True
    assert lecture["cancel_reservation"] is False
    assert annonces["calculate"] is None
    assert lecture[pont.OUTIL_CLIENT] is False
    assert {OUVRIR, CLOTURER} <= set(annonces)
    assert len(annonces) == 17


def test_l_enonce_est_la_consigne_de_tau2_bench_puis_le_debut_de_conversation() -> None:
    tache = _taches("sierra")["14"]
    conversation = pont.Conversation(tache, "sierra", pont.ECRIT_D_AVANCE)
    enonce = conversation.ouvrir()
    assert enonce.startswith("<instructions>\nYou are a customer service agent")
    assert "# Airline Agent Policy" in enonce
    assert enonce.endswith(f"assistant: Hi! How can I help you today?\nuser: {pont.premier_message_ecrit(tache)}")
    conversation.cloturer()


@pytest.mark.parametrize(("jeu", "numero"), [("sierra", "0"), ("sierra", "14"), ("verified", "14"), ("verified", "33")])
def test_les_gestes_de_reference_valent_1(jeu: Jeu, numero: str) -> None:
    conversation = pont.Conversation(_taches(jeu)[numero], jeu, pont.ECRIT_D_AVANCE)
    conversation.ouvrir()
    _jouer_reference(conversation, _brutes(jeu)[numero])
    assert conversation.terminee
    simulation, note = conversation.cloturer()
    assert note["recompense"] == 1.0
    assert note["terminaison"] == "user_stop"
    assert simulation["task_id"] == numero


@pytest.mark.parametrize("numero", ["14", "33"])
def test_le_jeu_compte(numero: str) -> None:
    """Les gestes de Sierra échouent sur les tâches 14 (phrase à dire) et 33 (bagages payants) de Verified."""
    conversation = pont.Conversation(_taches("verified")[numero], "verified", pont.ECRIT_D_AVANCE)
    conversation.ouvrir()
    _jouer_reference(conversation, _brutes("sierra")[numero])
    _, note = conversation.cloturer()
    assert note["recompense"] == 0.0


@pytest.mark.parametrize(("numero", "attendue"), [("0", 1.0), ("14", 0.0)])
def test_ne_rien_faire(numero: str, attendue: float) -> None:
    """La tâche 0 attend un refus : ne rien écrire suffit. La tâche 14 attend deux écritures."""
    conversation = pont.Conversation(_taches("sierra")[numero], "sierra", pont.ECRIT_D_AVANCE)
    conversation.ouvrir()
    _, note = conversation.cloturer()
    assert note["terminaison"] == "agent_stop"
    assert note["recompense"] == attendue


def test_la_reponse_d_un_outil_se_lit_apres_sa_mise_a_jour(monkeypatch: pytest.MonkeyPatch) -> None:
    """La course du gymnase rendue certaine : l'agent du gymnase copie son observation lentement,
    sous son verrou, après avoir annoncé son tour. Sans lecture sous ce verrou, le pont lisait
    l'observation d'avant, sans la réponse de l'outil (1 exécution sur 400 le 2026-10-08)."""

    def copie_lente(objet: Any) -> Any:
        time.sleep(0.2)
        return copy.deepcopy(objet)

    monkeypatch.setattr("tau2.gym.gym_agent.deepcopy", copie_lente)
    conversation = pont.Conversation(_taches("sierra")["14"], "sierra", pont.ECRIT_D_AVANCE)
    conversation.ouvrir()
    for action in _brutes("sierra")["14"]["evaluation_criteria"]["actions"]:
        reponse = conversation.outil(action["name"], action["arguments"])
        assert not reponse.erreur, reponse.texte
    _, note = conversation.cloturer()
    assert note["base_egale"] is True


def test_une_erreur_d_outil_revient_a_l_agent_et_la_conversation_continue() -> None:
    conversation = pont.Conversation(_taches("sierra")["1"], "sierra", pont.ECRIT_D_AVANCE)
    conversation.ouvrir()
    reponse = conversation.outil("get_reservation_details", {"reservation_id": "AUCUNE"})
    assert reponse.erreur and not reponse.terminee
    assert "Error" in reponse.texte
    conversation.cloturer()


def test_rien_apres_la_fin_de_la_conversation() -> None:
    conversation = pont.Conversation(_taches("sierra")["0"], "sierra", pont.ECRIT_D_AVANCE)
    conversation.ouvrir()
    reponse = conversation.message("I cannot cancel this reservation.")
    assert reponse.texte == "###STOP###" and reponse.terminee
    with pytest.raises(pont.ConversationTerminee):
        conversation.outil("get_user_details", {"user_id": "emma_kim_9957"})
    _, note = conversation.cloturer()
    assert note["terminaison"] == "user_stop"


def test_dix_erreurs_d_outil_arretent_la_conversation_comme_dans_tau2_bench() -> None:
    conversation = pont.Conversation(_taches("sierra")["0"], "sierra", pont.ECRIT_D_AVANCE)
    conversation.ouvrir()
    for _ in range(20):
        if conversation.terminee:
            break
        conversation.outil("get_reservation_details", {"reservation_id": "AUCUNE"})
    _, note = conversation.cloturer()
    assert note["terminaison"] == "too_many_errors"
    assert note["recompense"] == 0.0


def test_la_note_se_refait_depuis_le_disque(tmp_path: Path) -> None:
    conversation = pont.Conversation(_taches("verified")["14"], "verified", pont.ECRIT_D_AVANCE)
    conversation.ouvrir()
    _jouer_reference(conversation, _brutes("verified")["14"])
    simulation, note = conversation.cloturer()
    chemin = tmp_path / "simulation.json"
    chemin.write_text(json.dumps(simulation), encoding="utf-8")
    sortie = subprocess.run(
        [sys.executable, "-m", "bancs_publics.tau2_bench.evaluer", "--jeu", "verified", "--simulation", str(chemin)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(sortie.stdout) == note


async def _par_mcp(travail: Path) -> dict[str, Any]:
    parametres = StdioServerParameters(
        command=sys.executable,
        args=["-m", "bancs_publics.tau2_bench", "--jeu", "sierra", "--travail", str(travail)],
    )
    async with Client(stdio_client(parametres), mode="legacy", cache=None) as client:
        noms = [o.name for o in (await client.list_tools()).tools]
        refus = await client.call_tool(OUVRIR, {"tache": "0", "execution": "../dehors"})
        ouverture = await client.call_tool(OUVRIR, {"tache": "0", "execution": "essai_r1"})
        inconnu = await client.call_tool("drop_database", {})
        reponse = await client.call_tool(pont.OUTIL_CLIENT, {"message": "I cannot cancel it."})
        cloture = await client.call_tool(CLOTURER, {})

        def texte(resultat: Any) -> str:
            return "\n".join(b.text for b in resultat.content if isinstance(b, TextContent))

        return {
            "noms": noms,
            "refus": (refus.is_error, texte(refus)),
            "enonce": json.loads(texte(ouverture))["enonce"],
            "inconnu": (inconnu.is_error, texte(inconnu)),
            "reponse": (texte(reponse), reponse.structured_content),
            "cloture": json.loads(texte(cloture)),
        }


def test_le_serveur_par_mcp(tmp_path: Path) -> None:
    vu = anyio.run(_par_mcp, tmp_path / "travail")
    assert len(vu["noms"]) == 17 and vu["noms"][-2:] == [OUVRIR, CLOTURER]
    assert vu["refus"] == (True, "nom d'exécution invalide : ../dehors")
    assert "Conversation so far:" in vu["enonce"]
    assert vu["inconnu"] == (True, "Unknown tool: drop_database")
    assert vu["reponse"] == ("###STOP###", {"conversation_terminee": True})
    note = json.loads(Path(vu["cloture"]["evaluation"]).read_text(encoding="utf-8"))
    assert note["recompense"] == 1.0 and note["terminaison"] == "user_stop"
    assert Path(vu["cloture"]["evaluation"]).parent == tmp_path / "travail" / "essai_r1"
    assert not (tmp_path / "dehors").exists()


def test_bancs_publics_n_importe_ni_ease_ni_orchestration() -> None:
    """Le terrain ne dépend pas du banc qui le mesure, ni des candidats."""
    interdit = re.compile(r"^\s*(from|import)\s+(ease|orchestrations|gardien|eke)\b", re.MULTILINE)
    sources = (RACINE / "11_bancs_publics" / "src").rglob("*.py")
    assert [str(s) for s in sources if interdit.search(s.read_text(encoding="utf-8"))] == []
