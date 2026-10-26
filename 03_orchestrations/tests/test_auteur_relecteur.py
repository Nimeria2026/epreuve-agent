"""Auteur et relecteur, avec deux modèles et des outils simulés : ce qui passe par le relecteur,
ce qu'il voit, ce qu'il peut faire, et ce que l'orchestration rend à EASE."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import anyio
from jsonschema import Draft202012Validator
from orchestrations.agent_seul import outil_openai
from orchestrations.auteur_relecteur import TOURS_RELECTURE, Bilans, orchestrer
from orchestrations.modele import ConfigurationModele

RACINE = Path(__file__).resolve().parents[2]
SCHEMA_SORTIE = json.loads((RACINE / "01_contrats" / "sortie_candidat.schema.json").read_text(encoding="utf-8"))
ENONCE = "Réponds au client c-0142."


def _configuration(role: str) -> ConfigurationModele:
    return ConfigurationModele(
        role=role,
        modele="modele-essai",
        adresse="http://modele.essai/v1",
        cle_env=None,
        parametres={},
        raisonnement_renvoye=None,
        delai_appel_secondes=5,
        tours_max=6,
    )


def _reponse(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": "modele-annonce",
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    }


def _appel(nom: str, arguments: dict[str, Any], identifiant: str = "a1") -> dict[str, Any]:
    return {"id": identifiant, "type": "function", "function": {"name": nom, "arguments": json.dumps(arguments)}}


def _outils(*noms: str) -> dict[str, Any]:
    return _reponse({"content": None, "tool_calls": [_appel(n, {}, f"a{i}") for i, n in enumerate(noms)]})


def _fin(texte: str = "Fait.") -> dict[str, Any]:
    return _reponse({"content": texte})


def _verdict(accord: bool, raison: str) -> dict[str, Any]:
    return _reponse({"content": None, "tool_calls": [_appel("verdict", {"accord": accord, "raison": raison})]})


class ModeleScripte:
    def __init__(self, reponses: Sequence[dict[str, Any]]) -> None:
        self._reponses = list(reponses)
        self.recus: list[list[dict[str, Any]]] = []
        self.catalogues: list[list[str]] = []

    async def repondre(self, messages: list[dict[str, Any]], outils: list[dict[str, Any]]) -> dict[str, Any]:
        self.recus.append([dict(m) for m in messages])
        self.catalogues.append([o["function"]["name"] for o in outils])
        return self._reponses.pop(0)


class SourceSimulee:
    """Des outils annotés comme les déclarent les services : lire (lecture seule), envoyer (écrit),
    archiver (ne déclare rien)."""

    def __init__(self) -> None:
        self.appels: list[str] = []

    async def lister_annotes(self) -> list[tuple[dict[str, Any], bool | None]]:
        schema: dict[str, Any] = {"type": "object", "properties": {}}
        return [
            (outil_openai("lire", "Lit un document.", schema), True),
            (outil_openai("envoyer", "Envoie un courriel.", schema), False),
            (outil_openai("archiver", "Archive un document.", schema), None),
        ]

    async def lister(self) -> list[dict[str, Any]]:
        return [o for o, _ in await self.lister_annotes()]

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        self.appels.append(nom)
        return f"{nom} fait", False


def _orchestrer(
    auteur: ModeleScripte, relecteur: ModeleScripte, lecture: SourceSimulee | None = None
) -> tuple[Bilans, SourceSimulee, list[str]]:
    source, recits, notes = SourceSimulee(), list[str](), list[Bilans]()

    async def executer() -> Bilans:
        return await orchestrer(
            ENONCE,
            source,
            lecture or source,
            (auteur, _configuration("auteur")),
            (relecteur, _configuration("relecteur")),
            notes.append,
            recits.append,
        )

    return anyio.run(executer), source, recits


def test_une_lecture_part_sans_relecture() -> None:
    auteur, relecteur = ModeleScripte([_outils("lire"), _fin()]), ModeleScripte([])
    bilans, source, _ = _orchestrer(auteur, relecteur)
    assert source.appels == ["lire"]
    assert relecteur.recus == []
    assert bilans.auteur.fin == "termine"


def test_une_action_accordee_part_et_le_relecteur_n_a_vu_que_l_enonce_et_l_action() -> None:
    auteur = ModeleScripte(
        [
            _reponse({"content": "Je pense que c'est bon.", "tool_calls": [_appel("envoyer", {"a": "x@y.example"})]}),
            _fin(),
        ]
    )
    relecteur = ModeleScripte([_outils("lire"), _verdict(True, "conforme")])
    bilans, source, recits = _orchestrer(auteur, relecteur)
    assert source.appels == ["lire", "envoyer"]  # la lecture du relecteur, puis l'action accordée
    demande = relecteur.recus[0][1]["content"]
    assert ENONCE in demande and '"a": "x@y.example"' in demande and "envoyer(" in demande
    assert all("Je pense" not in str(m.get("content")) for m in relecteur.recus[0])
    assert auteur.recus[1][-1] == {"role": "tool", "tool_call_id": "a1", "content": "envoyer fait"}
    assert "verdict : accordée (conforme)" in recits
    assert bilans.relecteur.appels_modele == 2


def test_une_action_renvoyee_ne_part_pas_et_l_auteur_lit_la_raison() -> None:
    auteur = ModeleScripte([_outils("envoyer"), _fin("Je renonce.")])
    relecteur = ModeleScripte([_verdict(False, "le manuel interdit cet envoi")])
    _, source, _ = _orchestrer(auteur, relecteur)
    assert source.appels == []
    assert auteur.recus[1][-1]["content"] == "Erreur : renvoyé par le relecteur : le manuel interdit cet envoi"


def test_un_outil_qui_ne_declare_rien_est_relu() -> None:
    auteur = ModeleScripte([_outils("archiver"), _fin()])
    relecteur = ModeleScripte([_verdict(True, "rien à redire")])
    _, source, _ = _orchestrer(auteur, relecteur)
    assert source.appels == ["archiver"] and len(relecteur.recus) == 1


def test_le_relecteur_ne_voit_que_les_lectures_et_ne_peut_rien_ecrire() -> None:
    auteur = ModeleScripte([_outils("envoyer"), _fin()])
    relecteur = ModeleScripte([_outils("envoyer"), _verdict(False, "non")])
    _, source, _ = _orchestrer(auteur, relecteur)
    assert relecteur.catalogues[0] == ["lire", "verdict"]
    assert source.appels == []
    assert relecteur.recus[1][-1]["content"] == "Erreur : outil non permis au relecteur, qui ne fait que lire : envoyer"


def test_un_relecteur_muet_est_relance_puis_l_action_part_au_bout_des_tours() -> None:
    auteur = ModeleScripte([_outils("envoyer"), _fin()])
    relecteur = ModeleScripte([_fin("Hum.")] * TOURS_RELECTURE)
    _, source, recits = _orchestrer(auteur, relecteur)
    assert relecteur.recus[1][-1] == {"role": "user", "content": "Rends ton verdict avec l'outil verdict."}
    assert source.appels == ["envoyer"]
    assert f"relecture sans verdict en {TOURS_RELECTURE} tours : l'action part" in recits


def test_la_sortie_compte_les_deux_roles_au_contrat_sortie_candidat() -> None:
    auteur = ModeleScripte([_outils("envoyer"), _fin()])
    relecteur = ModeleScripte([_verdict(True, "ok")])
    bilans, _, _ = _orchestrer(auteur, relecteur)
    sortie = bilans.en_json()
    valide: Callable[[Any], bool] = Draft202012Validator(SCHEMA_SORTIE).is_valid  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert valide(sortie)
    assert sortie["appels_modele"] == 3
    assert sortie["consommation"] == {
        "auteur": {"entree": 20, "entree_en_cache": "?", "sortie": 4},
        "relecteur": {"entree": 10, "entree_en_cache": "?", "sortie": 2},
    }
    assert sortie["modeles_renvoyes"] == {"auteur": "modele-annonce", "relecteur": "modele-annonce"}


def test_le_relecteur_lit_par_l_acces_en_lecture_seule_et_l_auteur_par_le_relais() -> None:
    auteur = ModeleScripte([_outils("envoyer"), _fin()])
    relecteur = ModeleScripte([_outils("lire"), _verdict(True, "ok")])
    lecture = SourceSimulee()
    _, source, _ = _orchestrer(auteur, relecteur, lecture)
    assert (source.appels, lecture.appels) == (["envoyer"], ["lire"])


def test_un_verdict_mal_forme_est_rendu_au_relecteur_qui_le_refait() -> None:
    auteur = ModeleScripte([_outils("envoyer"), _fin()])
    mal_forme = _reponse({"content": None, "tool_calls": [_appel("verdict", {"accord": "true", "raison": "ok"})]})
    relecteur = ModeleScripte([mal_forme, _verdict(False, "non")])
    _, source, _ = _orchestrer(auteur, relecteur)
    assert relecteur.recus[1][-1]["content"] == "Erreur : verdict mal formé ; accord est vrai ou faux, raison un texte"
    assert source.appels == []


def test_le_relecteur_garde_sa_conversation_d_une_relecture_a_l_autre() -> None:
    # JOURNAL, entrée 111 : repartir de zéro à chaque action épuisait le plafond de lectures.
    auteur = ModeleScripte(
        [
            _reponse({"content": None, "tool_calls": [_appel("envoyer", {"a": "x@y.example"})]}),
            _reponse({"content": None, "tool_calls": [_appel("envoyer", {"a": "z@y.example"}, "a2")]}),
            _fin(),
        ]
    )
    relecteur = ModeleScripte([_outils("lire"), _verdict(True, "conforme"), _verdict(True, "conforme aussi")])
    _, source, _ = _orchestrer(auteur, relecteur)
    assert source.appels == ["lire", "envoyer", "envoyer"]  # une seule lecture pour deux relectures
    seconde = relecteur.recus[2]
    assert seconde[: len(relecteur.recus[1])] == relecteur.recus[1]  # tout ce qu'il a lu reste
    assert {"role": "tool", "tool_call_id": "a0", "content": "lire fait"} in seconde
    assert sum(m["role"] == "system" for m in seconde) == 1
    assert seconde[-1]["role"] == "user" and "z@y.example" in seconde[-1]["content"]
    assert ENONCE not in seconde[-1]["content"]  # la demande n'est donnée qu'une fois
    # Chaque appel d'outil du relecteur, verdict compris, a sa réponse : la conversation reste valide.
    appels: set[str] = set()
    for m in seconde:
        if m["role"] == "assistant":
            appels |= {str(a["id"]) for a in cast(list[dict[str, Any]], m.get("tool_calls") or [])}
    assert appels == {m["tool_call_id"] for m in seconde if m["role"] == "tool"}
