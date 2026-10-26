"""Les conversations airline publiées par Sierra, côté pont : données, jeu publie, utilisateur rejoué.

Aucun modèle : l'utilisateur redit les messages publiés, les gestes de l'agent viennent du fichier
publié ; la note est celle de l'évaluateur de τ²-bench, à comparer à celle que Sierra a publiée, et
la conversation rejouée doit être la publiée.
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from bancs_publics.tau2_bench import pont
from bancs_publics.tau2_bench.donnees import PUBLIES, dossier_local, fichier_publie, fichier_taches, verifier
from bancs_publics.tau2_bench.serveur import Pont, RefusPont

DOSSIER = dossier_local()
"""Récupéré par conftest.py avant ce module."""


def _publication(agent: str) -> dict[str, Any]:
    return json.loads(fichier_publie(DOSSIER, agent).read_text(encoding="utf-8"))


def _simulation(agent: str, numero: str, essai: int) -> dict[str, Any]:
    return next(s for s in _publication(agent)["simulations"] if s["task_id"] == numero and s["trial"] == essai)


def _rejouer(conversation: pont.Conversation, simulation: dict[str, Any]) -> None:
    """Les gestes publiés de l'agent : ses appels d'outil un à un, ses messages qui ne sont que du texte."""
    for message in simulation["messages"][1:]:
        if message["role"] != "assistant":
            continue
        if message.get("tool_calls"):
            for appel in message["tool_calls"]:
                conversation.outil(appel["name"], appel["arguments"])
        elif message.get("content"):
            conversation.message(message["content"])


def test_les_conversations_publiees_ont_leurs_empreintes() -> None:
    assert verifier(DOSSIER) == []
    assert sorted(PUBLIES) == ["claude_3_7_sonnet", "gpt_4_1", "gpt_4_1_mini", "o4_mini"]
    assert all(len(_publication(agent)["simulations"]) == 200 for agent in PUBLIES)


def test_le_jeu_publie_est_tire_des_taches_embarquees(tmp_path: Path) -> None:
    jeu = json.loads(fichier_taches(DOSSIER, "publie").read_text(encoding="utf-8"))
    assert all(_publication(agent)["tasks"] == jeu for agent in PUBLIES)
    copie = tmp_path / "tau2"
    shutil.copytree(DOSSIER, copie)
    modifie = copie / "jeux" / "publie.json"
    modifie.write_text(modifie.read_text(encoding="utf-8").replace('"0"', '"zero"', 1), encoding="utf-8")
    assert verifier(copie) == ["jeux/publie.json"]


def test_les_conversations_publiees_vues_du_pont() -> None:
    publiees = pont.lire_publiees(fichier_publie(DOSSIER, "gpt_4_1"))
    assert len(publiees) == 200 and ("0", 3) in publiees
    simulation = _simulation("gpt_4_1", "14", 0)
    publiee = publiees[("14", 0)]
    assert publiee.utilisateur == [m["content"] for m in simulation["messages"] if m["role"] == "user"]
    assert "###STOP###" in publiee.utilisateur[-1]
    assert publiee.reponses == [(m["content"], m["error"]) for m in simulation["messages"] if m["role"] == "tool"]
    assert publiee.terminaison == "user_stop"


def _rejouee(agent: str, numero: str, essai: int, publiee: pont.Publiee | None = None) -> dict[str, Any]:
    """La note d'une conversation publiée rejouée par le pont, face à la publiée ou à une autre."""
    publiee = publiee or pont.lire_publiees(fichier_publie(DOSSIER, agent))[(numero, essai)]
    taches = pont.lire_taches(fichier_taches(DOSSIER, "publie"))
    conversation = pont.Conversation(taches[numero], "publie", f"rejoue:{agent}", publiee)
    assert conversation.ouvrir().endswith(f"user: {publiee.utilisateur[0]}")
    _rejouer(conversation, _simulation(agent, numero, essai))
    assert conversation.terminee
    return conversation.cloturer()[1]


@pytest.mark.parametrize(
    ("agent", "numero", "essai"),
    [("gpt_4_1", "14", 0), ("gpt_4_1", "26", 1), ("claude_3_7_sonnet", "33", 2), ("claude_3_7_sonnet", "18", 0)],
)
def test_l_utilisateur_rejoue_refait_la_conversation_et_sa_note(agent: str, numero: str, essai: int) -> None:
    """Notes publiées 0 et 1 : gpt-4.1 y groupe des appels d'outil, claude-3-7 y mêle texte et appels (en
    18, essai 0, avec des phrases à dire) ; la note reste la publiée, la conversation aussi."""
    note = _rejouee(agent, numero, essai)
    assert note["recompense"] == _simulation(agent, numero, essai)["reward_info"]["reward"]
    assert (note["terminaison"], note["divergence"]) == ("user_stop", None)


def test_une_reponse_d_outil_qui_differe_se_voit() -> None:
    publiee = pont.lire_publiees(fichier_publie(DOSSIER, "gpt_4_1"))[("14", 0)]
    (texte, erreur), *suite = publiee.reponses
    assert texte is not None and "mohamed" in texte
    modifiee = dataclasses.replace(publiee, reponses=[(f"{texte} ", erreur), *suite])
    assert _rejouee("gpt_4_1", "14", 0, modifiee)["divergence"] is None  # même JSON, espace en plus
    modifiee = dataclasses.replace(publiee, reponses=[(texte.replace("mohamed", "mohammed"), erreur), *suite])
    assert _rejouee("gpt_4_1", "14", 0, modifiee)["divergence"] == "réponse d'outil 1 différente de la publiée"


def test_un_rejeu_qui_diverge_se_voit() -> None:
    """L'utilisateur rejoué qui n'a plus rien à dire clôt, et la note dit où la conversation a divergé."""
    taches = pont.lire_taches(fichier_taches(DOSSIER, "publie"))
    publiee = pont.Publiee(["Hello."], [], "user_stop")
    conversation = pont.Conversation(taches["0"], "publie", "rejoue:gpt_4_1", publiee)
    conversation.ouvrir()
    reponse = conversation.message("Could you give me your user id?")
    assert reponse.texte == "###STOP###" and reponse.terminee
    _, note = conversation.cloturer()
    assert note["divergence"] == "2 messages de l'utilisateur pour 1 publiés"


def test_le_serveur_n_ouvre_un_rejeu_que_sur_un_essai_publie(tmp_path: Path) -> None:
    etat = Pont(
        "publie",
        fichier_taches(DOSSIER, "publie"),
        tmp_path,
        "rejoue:o4_mini",
        fichier_publie(DOSSIER, "o4_mini"),
    )
    with pytest.raises(RefusPont, match="essai None"):
        etat.ouvrir("0", "essai_r1")
    with pytest.raises(RefusPont, match="essai 4"):
        etat.ouvrir("0", "essai_r1", 4)
    with pytest.raises(ValueError, match="sans fichier"):
        Pont("publie", fichier_taches(DOSSIER, "publie"), tmp_path, "rejoue:o4_mini")
