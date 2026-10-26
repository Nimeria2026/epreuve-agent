"""Le témoin rejoueur (ease.rejeu_tau2) : les conversations publiées par Sierra, rejouées par EASE.

Aucun modèle : le serveur de 11_bancs_publics fait parler l'utilisateur rejoué, le témoin redonne
les gestes publiés de l'agent ; la note d'EASE doit être la note publiée.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.rejeu_tau2 import Comparaison, Rejeu, comparer, gestes, rejouer, tableau
from ease.terrain_tau2 import OUTIL_CLIENT


@pytest.fixture(scope="module")
def donnees() -> None:
    subprocess.run([sys.executable, "-m", "bancs_publics.tau2_bench.donnees"], check=True, capture_output=True)


def test_les_gestes_d_une_conversation_publiee() -> None:
    """Appels groupés séparés dans l'ordre ; texte d'un message mixte laissé ; accueil fixe sauté."""
    messages = [
        {"role": "assistant", "content": "Hi! How can I help you today?", "tool_calls": None},
        {"role": "user", "content": "Cancel my trip.", "tool_calls": None},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "a", "name": "get_user_details", "arguments": {"user_id": "u1"}},
                {"id": "b", "name": "get_reservation_details", "arguments": {"reservation_id": "R1"}},
            ],
        },
        {"role": "tool", "content": "{}", "tool_calls": None},
        {"role": "tool", "content": "{}", "tool_calls": None},
        {
            "role": "assistant",
            "content": "Let me cancel it.",
            "tool_calls": [{"id": "c", "name": "cancel_reservation", "arguments": {"reservation_id": "R1"}}],
        },
        {"role": "tool", "content": "{}", "tool_calls": None},
        {"role": "assistant", "content": "Done.", "tool_calls": None},
        {"role": "user", "content": "###STOP###", "tool_calls": None},
    ]
    assert gestes(messages) == [
        ("get_user_details", {"user_id": "u1"}),
        ("get_reservation_details", {"reservation_id": "R1"}),
        ("cancel_reservation", {"reservation_id": "R1"}),
        (OUTIL_CLIENT, {"message": "Done."}),
    ]


def test_le_rejeu_suit_l_ordre_du_run_et_refuse_un_enonce_desaligne(donnees: None) -> None:
    del donnees
    rejeu = Rejeu("gpt_4_1", ["0", "14"])
    assert [(c.numero, c.essai) for c in rejeu.ordre] == [("0", e) for e in range(4)] + [("14", e) for e in range(4)]
    premiere = rejeu.ordre[0]
    assert rejeu.conversation(0, f"Conversation so far:\nuser: {premiere.premier}") is premiere
    with pytest.raises(ValueError, match="désaligné"):
        rejeu.conversation(4, f"Conversation so far:\nuser: {premiere.premier}")
    with pytest.raises(ValueError, match="au-delà"):
        rejeu.conversation(8, "")


@pytest.mark.parametrize(("agent", "numeros"), [("gpt_4_1", ["14", "26"]), ("claude_3_7_sonnet", ["18", "33"])])
def test_le_temoin_rejoueur_retrouve_chaque_note_publiee(
    donnees: None, tmp_path: Path, agent: str, numeros: list[str]
) -> None:
    """gpt-4.1 y groupe des appels d'outil, claude-3-7 y mêle texte et appels ; notes publiées 0 et 1."""
    del donnees
    dossier, comparaison = rejouer(
        agent, numeros, externe=False, dossier_runs=tmp_path / "runs", travail=tmp_path / "t"
    )
    assert len(comparaison.conversations) == 8 and comparaison.erreurs_techniques == 0
    assert (comparaison.ecarts, comparaison.divergences) == ([], [])
    assert {c[2] for c in comparaison.conversations} == {0.0, 1.0}
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    assert fiche.jeu_taches.nom == "tau2_airline_publie" and fiche.candidat.identifiant == f"temoin_rejoueur_{agent}"


def test_le_temoin_rejoueur_passe_par_le_relais_comme_un_vrai_candidat(donnees: None, tmp_path: Path) -> None:
    del donnees
    dossier, comparaison = rejouer(
        "o4_mini", ["0"], externe=True, dossier_runs=tmp_path / "runs", travail=tmp_path / "t"
    )
    assert (len(comparaison.conversations), comparaison.ecarts, comparaison.erreurs_techniques) == (4, [], 0)
    assert comparaison.divergences == []
    resultat = lire_resultat(dossier / "resultats" / "airline_0_r1.json")
    assert resultat.etapes > 0
    assert (dossier / "journaux" / "airline_0_r1_candidat.log").is_file()
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    assert fiche.candidat.identifiant == "temoin_rejoueur_o4_mini_externe"
    # une divergence notée par le serveur, ou une note qui n'en dit rien, se retrouve dans la comparaison
    for repetition, divergence in ((2, "réponse d'outil 1 différente de la publiée"), (3, None)):
        chemin = tmp_path / "t" / f"{fiche.identifiant}_airline_0_r{repetition}" / "evaluation.json"
        note = json.loads(chemin.read_text(encoding="utf-8"))
        assert note.pop("divergence") is None
        if divergence is not None:
            note["divergence"] = divergence
        chemin.write_text(json.dumps(note), encoding="utf-8")
    divergences = comparer(Rejeu("o4_mini", ["0"]), dossier, tmp_path / "t").divergences
    assert [(n, e) for n, e, _ in divergences] == [("0", 1), ("0", 2)]
    assert divergences[0][2] == "réponse d'outil 1 différente de la publiée"
    assert divergences[1][2].startswith("note du serveur sans divergence")


def test_le_tableau_publie_contre_retrouve() -> None:
    comparaison = Comparaison(
        "gpt_4_1",
        [("0", 0, 1.0, 1.0), ("0", 1, 0.0, 1.0)],
        (1, 2, [0.5, 0.0]),
        (2, 2, [1.0, 1.0]),
        0,
        [("0", 1, "réponse d'outil 3 différente de la publiée")],
    )
    assert comparaison.ecarts == [("0", 1, 0.0, 1.0)]
    lignes = tableau([comparaison])
    assert lignes[2] == (
        "| gpt_4_1 | 1/2 | 2/2 | 1 | 1 | 50,0 % ; 0,0 % | 100,0 % ; 100,0 % | 56,0 ; 47,8 ; 42,4 ; 38,1 % |"
    )
