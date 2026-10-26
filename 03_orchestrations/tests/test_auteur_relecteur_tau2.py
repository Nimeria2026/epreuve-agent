"""Auteur et relecteur sur τ²-bench, avec deux modèles et des outils simulés : ce que voit
l'auteur, ce qui passe par le relecteur, ce qu'il voit, ce qu'il peut faire, et ce que
l'orchestration rend à EASE. Le passage par le vrai serveur de τ²-bench est dans
02_ease/tests/test_auteur_relecteur_tau2_ease.py."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from jsonschema import Draft202012Validator
from orchestrations.agent_seul import outil_openai
from orchestrations.auteur_relecteur import TOURS_RELECTURE, Bilans
from orchestrations.auteur_relecteur_tau2 import (
    CONSIGNE_RELECTEUR,
    RELANCE,
    RELECTURE_AUTEUR,
    RENVOI,
    VERDICT_MAL_FORME,
    enonce_de_l_auteur,
    orchestrer,
    politique,
)
from orchestrations.modele import ConfigurationModele, ErreurModele
from orchestrations.reproduction_tau2 import CONVERSATION_FINIE, OUTIL_CLIENT, SALUT, EnonceIllisible

RACINE = Path(__file__).resolve().parents[2]
ORCHESTRATIONS = RACINE / "03_orchestrations" / "src" / "orchestrations"
SCHEMA_SORTIE = json.loads((RACINE / "01_contrats" / "sortie_candidat.schema.json").read_text(encoding="utf-8"))
POLITIQUE = "# Airline Agent Policy\nGet an explicit yes before any update."
CONSIGNE = f"<instructions>\nYou are a customer service agent.\n</instructions>\n<policy>\n{POLITIQUE}\n</policy>"
ENONCE = f"{CONSIGNE}\n\nConversation so far:\nassistant: {SALUT}\nuser: Cancel my booking ABC123."


def _configuration(role: str) -> ConfigurationModele:
    return ConfigurationModele(
        role=role,
        modele="modele-essai",
        adresse="http://modele.essai/v1",
        cle_env=None,
        parametres={},
        raisonnement_renvoye=None,
        delai_appel_secondes=5,
        tours_max=8,
    )


def _reponse(message: dict[str, Any]) -> dict[str, Any]:
    usage = {"prompt_tokens": 10, "completion_tokens": 2}
    return {"model": "modele-annonce", "choices": [{"message": message}], "usage": usage}


def _appel(nom: str, arguments: dict[str, Any], identifiant: str = "a1") -> dict[str, Any]:
    return {"id": identifiant, "type": "function", "function": {"name": nom, "arguments": json.dumps(arguments)}}


def _outil(nom: str, arguments: dict[str, Any] | None = None, identifiant: str = "a1") -> dict[str, Any]:
    return _reponse({"content": None, "tool_calls": [_appel(nom, arguments or {}, identifiant)]})


def _texte(texte: str) -> dict[str, Any]:
    return _reponse({"content": texte})


def _verdict(accord: bool, raison: str, identifiant: str = "v1") -> dict[str, Any]:
    return _outil("verdict", {"approved": accord, "reason": raison}, identifiant)


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
    """Les outils de τ²-bench annotés comme les annonce son serveur : get_reservation_details en
    lecture, cancel_reservation en écriture, calculate générique (rien d'annoncé), et le client."""

    def __init__(self, client: Sequence[str] = ("Yes, cancel it.", "Thanks. ###STOP###")) -> None:
        self._client = list(client)
        self.appels: list[tuple[str, dict[str, Any]]] = []

    async def lister_annotes(self) -> list[tuple[dict[str, Any], bool | None]]:
        schema: dict[str, Any] = {"type": "object", "properties": {}}
        return [
            (outil_openai("get_reservation_details", "Get the details of a reservation.", schema), True),
            (outil_openai("cancel_reservation", "Cancel the whole reservation.", schema), False),
            (outil_openai("calculate", "Calculate the result of a mathematical expression.", schema), None),
            (outil_openai(OUTIL_CLIENT, "Send a message to the user.", schema), False),
        ]

    async def lister(self) -> list[dict[str, Any]]:
        return [o for o, _ in await self.lister_annotes()]

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        self.appels.append((nom, arguments))
        if nom == OUTIL_CLIENT:
            return (self._client.pop(0), False) if self._client else (CONVERSATION_FINIE, True)
        if nom == "get_reservation_details":
            return '{"reservation_id": "ABC123", "status": "active"}', False
        return f"{nom} done", False


def _orchestrer(
    auteur: ModeleScripte,
    relecteur: ModeleScripte,
    serveur: ServeurSimule | None = None,
    lecture: ServeurSimule | None = None,
    enonce: str = ENONCE,
) -> tuple[Bilans, ServeurSimule, list[str]]:
    source, recits, notes = serveur or ServeurSimule(), list[str](), list[Bilans]()

    async def executer() -> Bilans:
        return await orchestrer(
            enonce,
            source,
            lecture or source,
            (auteur, _configuration("auteur")),
            (relecteur, _configuration("relecteur")),
            notes.append,
            recits.append,
        )

    return anyio.run(executer), source, recits


def test_l_auteur_voit_la_consigne_de_tau2_suivie_de_la_phrase_sur_la_relecture() -> None:
    auteur = ModeleScripte([_texte("Done. ###STOP###")])
    bilans, _, _ = _orchestrer(auteur, ModeleScripte([]))
    assert bilans.auteur.fin == "termine"
    systeme = auteur.recus[0][0]
    phrase = RELECTURE_AUTEUR.read_text(encoding="utf-8").strip()
    assert systeme == {"role": "system", "content": f"{CONSIGNE}\n\n{phrase}"}
    assert [m["role"] for m in auteur.recus[0]] == ["system", "assistant", "user"]
    # Les mêmes outils que le bras agent seul : ceux de τ²-bench, sans celui du client.
    assert auteur.catalogues[0] == ["get_reservation_details", "cancel_reservation", "calculate"]


def test_une_lecture_et_un_message_au_client_partent_sans_relecture() -> None:
    auteur = ModeleScripte([_outil("get_reservation_details"), _texte("It is active."), _texte("Bye. ###STOP###")])
    relecteur = ModeleScripte([])
    _, serveur, _ = _orchestrer(auteur, relecteur)
    assert [nom for nom, _ in serveur.appels] == ["get_reservation_details", OUTIL_CLIENT, OUTIL_CLIENT]
    assert relecteur.recus == []


def test_un_geste_qui_ecrit_est_relu_et_le_relecteur_voit_politique_conversation_et_action() -> None:
    auteur = ModeleScripte(
        [
            _texte("Shall I cancel ABC123?"),
            _reponse(
                {
                    "content": None,
                    "reasoning_content": "Je pense que c'est bon.",
                    "tool_calls": [_appel("cancel_reservation", {"reservation_id": "ABC123"})],
                }
            ),
            _texte("Cancelled. ###STOP###"),
        ]
    )
    relecteur = ModeleScripte([_outil("get_reservation_details", {"reservation_id": "ABC123"}), _verdict(True, "ok")])
    bilans, serveur, recits = _orchestrer(auteur, relecteur)
    assert [nom for nom, _ in serveur.appels] == [
        OUTIL_CLIENT,
        "get_reservation_details",  # la lecture du relecteur
        "cancel_reservation",  # l'action accordée
        OUTIL_CLIENT,
    ]
    systeme, demande = relecteur.recus[0]
    assert systeme == {"role": "system", "content": CONSIGNE_RELECTEUR.read_text(encoding="utf-8")}
    texte = demande["content"]
    assert POLITIQUE in texte and "<instructions>" not in texte
    attendue = "\n".join(
        [
            f"assistant: {SALUT}",
            "user: Cancel my booking ABC123.",
            "assistant: Shall I cancel ABC123?",
            "user: Yes, cancel it.",
        ]
    )
    assert f"Conversation with the customer so far:\n{attendue}\n\nAction it proposes:" in texte
    assert texte.endswith('cancel_reservation({\n  "reservation_id": "ABC123"\n})')
    assert all("Je pense" not in json.dumps(m) for m in relecteur.recus[0])
    assert relecteur.catalogues[0] == ["get_reservation_details", "verdict"]
    assert auteur.recus[2][-1] == {"role": "tool", "tool_call_id": "a1", "content": "cancel_reservation done"}
    assert "verdict : accordée (ok)" in recits
    assert bilans.relecteur.appels_modele == 2


def test_un_geste_renvoye_ne_part_pas_et_l_auteur_lit_la_raison_en_erreur_de_tau2() -> None:
    auteur = ModeleScripte([_outil("cancel_reservation"), _texte("I cannot. ###STOP###")])
    relecteur = ModeleScripte([_verdict(False, "the customer did not confirm")])
    _, serveur, _ = _orchestrer(auteur, relecteur)
    assert "cancel_reservation" not in [nom for nom, _ in serveur.appels]
    assert auteur.recus[1][-1]["content"] == f"{RENVOI}the customer did not confirm"
    assert RENVOI == "Error: sent back by the reviewer: "


def test_un_outil_generique_qui_n_annonce_rien_est_relu() -> None:
    auteur = ModeleScripte([_outil("calculate", {"expression": "2+2"}), _texte("4. ###STOP###")])
    relecteur = ModeleScripte([_verdict(True, "harmless")])
    _, serveur, _ = _orchestrer(auteur, relecteur)
    assert ("calculate", {"expression": "2+2"}) in serveur.appels and len(relecteur.recus) == 1


def test_le_relecteur_ne_peut_rien_ecrire_et_lit_par_l_acces_en_lecture_seule() -> None:
    auteur = ModeleScripte([_outil("cancel_reservation"), _texte("Done. ###STOP###")])
    relecteur = ModeleScripte(
        [
            _outil("cancel_reservation", identifiant="r1"),
            _outil("get_reservation_details", identifiant="r2"),
            _verdict(False, "no"),
        ]
    )
    lecture = ServeurSimule()
    _, serveur, _ = _orchestrer(auteur, relecteur, lecture=lecture)
    refus = "Error: tool not allowed to the reviewer, who only reads: cancel_reservation"
    assert relecteur.recus[1][-1]["content"] == refus
    assert [nom for nom, _ in lecture.appels] == ["get_reservation_details"]
    assert "cancel_reservation" not in [nom for nom, _ in serveur.appels]


def test_le_relecteur_garde_sa_conversation_et_recoit_la_suite_de_celle_du_client() -> None:
    auteur = ModeleScripte(
        [
            _outil("calculate", {"expression": "1+1"}),
            _texte("Shall I cancel?"),
            _outil("cancel_reservation", {"reservation_id": "ABC123"}, "a2"),
            _texte("Done. ###STOP###"),
        ]
    )
    relecteur = ModeleScripte(
        [_outil("get_reservation_details", identifiant="r1"), _verdict(True, "ok"), _verdict(True, "confirmed", "v2")]
    )
    _, serveur, _ = _orchestrer(auteur, relecteur)
    assert [nom for nom, _ in serveur.appels].count("get_reservation_details") == 1  # une lecture pour deux relectures
    premiere, seconde = relecteur.recus[1], relecteur.recus[2]
    assert seconde[: len(premiere)] == premiere
    assert sum(m["role"] == "system" for m in seconde) == 1
    suite = seconde[-1]["content"]
    assert suite.startswith(
        "Conversation with the customer since the previous action:\n"
        "assistant: Shall I cancel?\nuser: Yes, cancel it.\n\n"
        "New action that the assistant proposes, for the same request:\ncancel_reservation("
    )
    assert POLITIQUE not in suite  # la politique n'est donnée qu'une fois
    appels: set[str] = set()
    for m in seconde:
        if m["role"] == "assistant":
            appels |= {str(a["id"]) for a in cast(list[dict[str, Any]], m.get("tool_calls") or [])}
    assert appels == {m["tool_call_id"] for m in seconde if m["role"] == "tool"}


def test_une_action_sans_conversation_nouvelle_ne_recoit_que_l_action() -> None:
    auteur = ModeleScripte(
        [
            _outil("calculate", {"expression": "1+1"}),
            _outil("calculate", {"expression": "2+2"}, "a2"),
            _texte("Done. ###STOP###"),
        ]
    )
    relecteur = ModeleScripte([_verdict(True, "ok"), _verdict(True, "ok", "v2")])
    _orchestrer(auteur, relecteur)
    assert relecteur.recus[1][-1]["content"].startswith("New action that the assistant proposes, for the same request:")


def test_un_relecteur_muet_est_relance_puis_l_action_part_au_bout_des_tours() -> None:
    auteur = ModeleScripte([_outil("cancel_reservation"), _texte("Done. ###STOP###")])
    relecteur = ModeleScripte([_texte("Hmm.")] * TOURS_RELECTURE)
    _, serveur, recits = _orchestrer(auteur, relecteur)
    assert relecteur.recus[1][-1] == {"role": "user", "content": RELANCE}
    assert "cancel_reservation" in [nom for nom, _ in serveur.appels]
    assert f"relecture sans verdict en {TOURS_RELECTURE} tours : l'action part" in recits


def test_un_verdict_mal_forme_est_rendu_au_relecteur_qui_le_refait() -> None:
    auteur = ModeleScripte([_outil("cancel_reservation"), _texte("Done. ###STOP###")])
    mal_forme = _outil("verdict", {"approved": "true", "reason": "ok"})
    relecteur = ModeleScripte([mal_forme, _verdict(False, "no", "v2")])
    _, serveur, _ = _orchestrer(auteur, relecteur)
    assert relecteur.recus[1][-1]["content"] == VERDICT_MAL_FORME
    assert "cancel_reservation" not in [nom for nom, _ in serveur.appels]


def test_la_sortie_compte_les_deux_roles_au_contrat_sortie_candidat() -> None:
    auteur = ModeleScripte([_outil("cancel_reservation"), _texte("Done. ###STOP###")])
    relecteur = ModeleScripte([_verdict(True, "ok")])
    bilans, _, _ = _orchestrer(auteur, relecteur)
    sortie = bilans.en_json()
    valide: Callable[[Any], bool] = Draft202012Validator(SCHEMA_SORTIE).is_valid  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert valide(sortie)
    assert sortie["fin"] == "termine" and sortie["appels_modele"] == 3
    assert sortie["consommation"] == {
        "auteur": {"entree": 20, "entree_en_cache": "?", "sortie": 4},
        "relecteur": {"entree": 10, "entree_en_cache": "?", "sortie": 2},
    }


def test_une_panne_du_modele_du_relecteur_finit_en_erreur() -> None:
    auteur = ModeleScripte([_outil("cancel_reservation")])
    bilans, serveur, _ = _orchestrer(auteur, ModeleScripte([ErreurModele("HTTP 500")]))
    assert (bilans.auteur.fin, bilans.auteur.detail) == ("erreur", "relecteur : HTTP 500")
    assert "cancel_reservation" not in [nom for nom, _ in serveur.appels]


@pytest.mark.parametrize(
    "enonce",
    [
        "Sans conversation.",
        f"<instructions>\nAgent.\n</instructions>\n\nConversation so far:\nassistant: {SALUT}\nuser: Hi.",
    ],
)
def test_un_enonce_sans_politique_ou_sans_conversation_est_refuse(enonce: str) -> None:
    bilans, serveur, _ = _orchestrer(ModeleScripte([]), ModeleScripte([]), enonce=enonce)
    assert bilans.auteur.fin == "erreur" and bilans.auteur.detail is not None and "illisible" in bilans.auteur.detail
    assert serveur.appels == []


def test_la_politique_et_l_enonce_de_l_auteur() -> None:
    assert politique(CONSIGNE) == POLITIQUE
    with pytest.raises(EnonceIllisible):
        politique("<policy>\n\n</policy>")
    assert enonce_de_l_auteur(ENONCE, "Reviewed.\n") == ENONCE.replace("</policy>\n\n", "</policy>\n\nReviewed.\n\n", 1)
    assert enonce_de_l_auteur("Sans conversation.", "Reviewed.") == "Sans conversation."


EMPREINTES_FIGEES = {
    "auteur_relecteur.py": "a0109e3c128cc11699c023bcd33f237bf14d7181c535b5b6b82580157d1e9127",
    "consignes/auteur.md": "1f40f4fc75158d9d06377c8eadd255d6dea5ab675fb2e7898c4413576ef95c60",
    "consignes/relecteur.md": "5bb54f704ba3f28c7641ba2948384e62dc563c370f418d0e48139c7eb8bc72a7",
}
"""Les fichiers de l'auteur et relecteur de Calorelle, figés pour l'A/B de l'étape 5 (3420c93)."""


def test_l_auteur_et_relecteur_de_calorelle_reste_fige_et_les_consignes_anglaises_sont_a_cote() -> None:
    for chemin, empreinte in EMPREINTES_FIGEES.items():
        assert hashlib.sha256((ORCHESTRATIONS / chemin).read_bytes()).hexdigest() == empreinte, chemin
    assert CONSIGNE_RELECTEUR.parent == (ORCHESTRATIONS / "consignes")
    # Traduction fidèle : les trois paragraphes de relecteur.md, et la phrase sur la relecture,
    # dernier paragraphe d'auteur.md.
    original = (ORCHESTRATIONS / "consignes" / "relecteur.md").read_text(encoding="utf-8")
    traduit = CONSIGNE_RELECTEUR.read_text(encoding="utf-8")
    assert len(original.strip().split("\n\n")) == len(traduit.strip().split("\n\n")) == 3
    auteur = (ORCHESTRATIONS / "consignes" / "auteur.md").read_text(encoding="utf-8")
    assert auteur.strip().split("\n\n")[-1].startswith("Chaque action qui écrit ou envoie est relue")
    assert RELECTURE_AUTEUR.read_text(encoding="utf-8").startswith("Each action that writes or sends is reviewed")
