"""Agent de reproduction τ²-bench : énoncé redécoupé, texte porté au client, fins de conversation.

Modèle et outils simulés ; le passage par le vrai serveur de τ²-bench est dans
02_ease/tests/test_mesure_tau2.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import anyio
import pytest
from orchestrations.agent_seul import Bilan, outil_openai
from orchestrations.modele import ConfigurationModele, ErreurModele, lire_configuration
from orchestrations.reproduction_tau2 import (
    CONVERSATION_FINIE,
    OUTIL_CLIENT,
    SALUT,
    EnonceIllisible,
    converser,
    decouper,
)

RACINE = Path(__file__).resolve().parents[2]
CONFIGURATIONS_TAU2 = RACINE / "03_orchestrations" / "src" / "orchestrations" / "configurations_tau2"
CONSIGNE = "<instructions>\nYou are a customer service agent.\n</instructions>\n<policy>\nBe nice.\n</policy>"
ENONCE = f"{CONSIGNE}\n\nConversation so far:\nassistant: {SALUT}\nuser: Hi.\nI want to cancel."


def _configuration(**changements: Any) -> ConfigurationModele:
    valeurs: dict[str, Any] = {
        "role": "agent",
        "modele": "modele-essai",
        "adresse": "http://modele.essai/v1",
        "cle_env": None,
        "parametres": {},
        "raisonnement_renvoye": None,
        "delai_appel_secondes": 5,
        "tours_max": 6,
    }
    return ConfigurationModele(**(valeurs | changements))


def _reponse(message: dict[str, Any]) -> dict[str, Any]:
    usage = {"prompt_tokens": 100, "completion_tokens": 10}
    return {"model": "modele-annonce", "choices": [{"message": message}], "usage": usage}


def _texte(texte: str) -> dict[str, Any]:
    return _reponse({"content": texte})


def _appel(nom: str, arguments: str = "{}", identifiant: str = "a1", texte: str | None = None) -> dict[str, Any]:
    appel = {"id": identifiant, "type": "function", "function": {"name": nom, "arguments": arguments}}
    return _reponse({"content": texte, "tool_calls": [appel]})


class ModeleScripte:
    def __init__(self, reponses: Sequence[dict[str, Any] | Exception]) -> None:
        self._reponses = list(reponses)
        self.recus: list[list[dict[str, Any]]] = []
        self.catalogues: list[list[str]] = []

    async def repondre(self, messages: list[dict[str, Any]], outils: list[dict[str, Any]]) -> dict[str, Any]:
        self.recus.append([dict(m) for m in messages])
        self.catalogues.append([o["function"]["name"] for o in outils])
        reponse = self._reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse


class ServeurSimule:
    """Les outils tels que le relais d'EASE les présente pour τ²-bench : un outil d'airline et le client."""

    def __init__(self, client: Sequence[str] = ("Thanks. ###STOP###",), avec_client: bool = True) -> None:
        self._client = list(client)
        self._avec_client = avec_client
        self.appels: list[tuple[str, dict[str, Any]]] = []

    async def lister(self) -> list[dict[str, Any]]:
        outils = [outil_openai("get_user_details", "Get user details.", {"type": "object", "properties": {}})]
        if self._avec_client:
            outils.append(outil_openai(OUTIL_CLIENT, "Send a message to the user.", {"type": "object"}))
        return outils

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        self.appels.append((nom, arguments))
        if nom == OUTIL_CLIENT:
            return (self._client.pop(0), False) if self._client else (CONVERSATION_FINIE, True)
        if nom == "get_user_details":
            return ("Error: User not found", True) if arguments.get("user_id") == "x" else ('{"name": "Ana"}', False)
        return (f"Unknown tool: {nom}", True)


def _tourner(
    modele: ModeleScripte,
    serveur: ServeurSimule,
    configuration: ConfigurationModele | None = None,
    enonce: str = ENONCE,
) -> tuple[Bilan, list[str]]:
    recits: list[str] = []
    reglages = configuration or _configuration()

    async def executer() -> Bilan:
        return await converser(enonce, serveur, modele, reglages, lambda b: None, recits.append)

    return anyio.run(executer), recits


def test_l_enonce_redevient_consigne_et_messages() -> None:
    depart = decouper(ENONCE)
    assert depart.consigne == CONSIGNE
    assert depart.messages == [
        {"role": "assistant", "content": SALUT},
        {"role": "user", "content": "Hi.\nI want to cancel."},
    ]


@pytest.mark.parametrize(
    "enonce",
    [
        "Sans conversation.",
        f"\n\nConversation so far:\nassistant: {SALUT}\nuser: Hi.",
        f"{CONSIGNE}\n\nConversation so far:\nassistant: Hello.\nuser: Hi.",
        f"{CONSIGNE}\n\nConversation so far:\nassistant: {SALUT}\n",
        f"{CONSIGNE}\n\nConversation so far:\nassistant: {SALUT}\nuser:  ",
    ],
)
def test_un_enonce_d_une_autre_forme_est_refuse(enonce: str) -> None:
    with pytest.raises(EnonceIllisible):
        decouper(enonce)
    bilan, _ = _tourner(ModeleScripte([]), ServeurSimule(), enonce=enonce)
    assert bilan.fin == "erreur" and bilan.detail is not None and "illisible" in bilan.detail


def test_le_modele_voit_le_format_de_tau2_et_son_texte_va_au_client() -> None:
    modele = ModeleScripte([_appel("get_user_details"), _texte("Done, Ana.")])
    serveur = ServeurSimule()
    bilan, _ = _tourner(modele, serveur)
    assert (bilan.fin, bilan.detail, bilan.appels_modele) == ("termine", None, 2)
    premier = modele.recus[0]
    assert [m["role"] for m in premier] == ["system", "assistant", "user"]
    assert premier[0]["content"] == CONSIGNE
    assert modele.catalogues[0] == ["get_user_details"]  # l'outil du client reste caché au modèle
    assert modele.recus[1][-1] == {"role": "tool", "tool_call_id": "a1", "content": '{"name": "Ana"}'}
    assert serveur.appels == [("get_user_details", {}), (OUTIL_CLIENT, {"message": "Done, Ana."})]


def test_la_reponse_du_client_revient_en_message_de_l_utilisateur() -> None:
    modele = ModeleScripte([_texte("Your user id?"), _texte("Thanks.")])
    serveur = ServeurSimule(client=["It is ana_1.", "Bye. ###TRANSFER###"])
    bilan, recits = _tourner(modele, serveur)
    assert bilan.fin == "termine"
    assert modele.recus[1][-2:] == [
        {"role": "assistant", "content": "Your user id?"},
        {"role": "user", "content": "It is ana_1."},
    ]
    assert "client : It is ana_1." in recits


def test_une_erreur_d_outil_revient_telle_que_tau2_la_rend() -> None:
    modele = ModeleScripte(
        [_appel("get_user_details", '{"user_id": "x"}'), _appel("get_user_details", "pas du JSON"), _texte("Sorry.")]
    )
    _tourner(modele, ServeurSimule())
    assert modele.recus[1][-1]["content"] == "Error: User not found"
    assert modele.recus[2][-1]["content"] == "Error: invalid arguments, a JSON object is expected"


def test_un_texte_ecrit_avec_un_appel_n_atteint_pas_le_client() -> None:
    modele = ModeleScripte([_appel("get_user_details", texte="Let me check."), _texte("Done.")])
    serveur = ServeurSimule()
    bilan, recits = _tourner(modele, serveur)
    assert bilan.fin == "termine"
    assert [nom for nom, _ in serveur.appels] == ["get_user_details", OUTIL_CLIENT]
    assert modele.recus[1][-2]["content"] == "Let me check."  # gardé pour le modèle
    assert any("non transmis au client" in r for r in recits)


@pytest.mark.parametrize(
    ("reponses", "client", "detail"),
    [
        ([_texte("Bye. ###STOP###")], ["Hello?"], "l'agent a clos la conversation"),
        ([_texte("Anything else?")], [], "τ²-bench a clos la conversation"),
        ([_reponse({"content": ""})], [], "réponse vide du modèle : conversation close par l'agent"),
    ],
)
def test_les_fins_de_conversation(reponses: list[dict[str, Any]], client: list[str], detail: str) -> None:
    bilan, _ = _tourner(ModeleScripte(reponses), ServeurSimule(client=client))
    assert (bilan.fin, bilan.detail) == ("termine", detail)


def test_un_outil_apres_la_fin_clot_la_conversation() -> None:
    class Fini(ServeurSimule):
        async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
            return CONVERSATION_FINIE, True

    bilan, _ = _tourner(ModeleScripte([_appel("get_user_details")]), Fini())
    assert (bilan.fin, bilan.detail) == ("termine", "τ²-bench a clos la conversation")


def test_la_limite_de_tours_et_les_pannes() -> None:
    bilan, _ = _tourner(ModeleScripte([_appel("get_user_details")] * 2), ServeurSimule(), _configuration(tours_max=2))
    assert bilan.fin == "tours_max"
    bilan, _ = _tourner(ModeleScripte([_texte("Hi"), ErreurModele("HTTP 500")]), ServeurSimule(client=["Yes?"]))
    assert (bilan.fin, bilan.detail, bilan.appels_modele) == ("erreur", "HTTP 500", 1)
    bilan, _ = _tourner(ModeleScripte([]), ServeurSimule(avec_client=False))
    assert bilan.fin == "erreur" and bilan.detail == f"le relais ne présente pas {OUTIL_CLIENT}"


def test_le_raisonnement_est_renvoye_si_la_configuration_le_demande() -> None:
    pense = _reponse({"content": None, "reasoning_content": "Je cherche.", "tool_calls": [
        {"id": "a1", "type": "function", "function": {"name": "get_user_details", "arguments": "{}"}}
    ]})  # fmt: skip
    modele = ModeleScripte([pense, _texte("Done.")])
    _tourner(modele, ServeurSimule(), _configuration(raisonnement_renvoye="reasoning_content"))
    assert modele.recus[1][-2]["reasoning_content"] == "Je cherche."


def test_les_configurations_de_reproduction_portent_les_reglages_de_tau2() -> None:
    """Température 0 et tool_choice auto, comme l'agent de τ²-bench 1.0.1 ; le reste comme l'agent seul."""
    lues = {chemin.stem: lire_configuration(chemin) for chemin in sorted(CONFIGURATIONS_TAU2.glob("*.yaml"))}
    assert sorted(lues) == ["deepseek_flash", "mimo_v26_flash_deepinfra", "qwen_local", "qwen_local_100k"]
    # Le Qwen à 102 400 jetons attend un tour qui remplit le contexte (JOURNAL, entrée 226).
    assert lues["qwen_local_100k"].delai_appel_secondes == 3600
    assert all(c.parametres == {"temperature": 0.0, "tool_choice": "auto"} for c in lues.values())
    seul = RACINE / "03_orchestrations" / "src" / "orchestrations" / "configurations"
    for nom, configuration in lues.items():
        reference = lire_configuration(seul / f"{nom}.yaml")
        assert (configuration.modele, configuration.adresse, configuration.cle_env) == (
            reference.modele,
            reference.adresse,
            reference.cle_env,
        )
        assert configuration.raisonnement_renvoye == reference.raisonnement_renvoye
