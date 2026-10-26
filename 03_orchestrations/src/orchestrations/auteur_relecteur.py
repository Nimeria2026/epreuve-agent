"""Auteur et relecteur : l'agent seul, dont chaque action qui écrit ou envoie passe d'abord par un
second agent, le relecteur (JOURNAL, entrées 80 et 92).

EASE le lance dans son propre processus (règle 6) :

    python -m orchestrations.auteur_relecteur --configuration <auteur.yaml> \\
        --relecteur <relecteur.yaml> --mcp <adresse du relais> --mcp-lecture <adresse> \\
        --enonce <fichier> --sortie <fichier>

L'auteur travaille comme l'agent seul (`agent_seul.boucle`), avec sa propre consigne
(consignes/auteur.md). Quand il appelle un outil que son service ne déclare pas en lecture seule
(annotation MCP readOnlyHint), l'appel ne part pas tout de suite. Le relecteur reçoit l'énoncé et
l'action proposée, sans le raisonnement de l'auteur, et lit ce qu'il veut par l'accès en lecture
seule du relais (--mcp-lecture), où ne passent que les outils déclarés en lecture seule
(consignes/relecteur.md). Il garde une seule conversation pour toute l'exécution : ce qu'il a lu
pour une action reste sous ses yeux pour les suivantes (décision d'Alexandre, JOURNAL, entrée 111 ;
repartir de zéro à chaque action épuisait le plafond de lectures de l'exécution, et le relecteur
renvoyait alors tout faute de pouvoir vérifier). Il rend son verdict par l'outil « verdict » :
- accordée, l'action part, et l'auteur reçoit son résultat ;
- renvoyée, elle ne part pas, et l'auteur reçoit la raison, comme une erreur d'outil.

L'orchestration ne connaît aucun nom d'outil de la PME : ce qu'il faut relire, chaque service le
déclare. Un outil qui ne déclare rien est relu. Le budget d'étapes de la tâche reste celui de
l'auteur, comme pour l'agent seul : les lectures du relecteur passent par l'accès en lecture
seule, comptées à part par EASE (décision d'Alexandre, JOURNAL, entrée 94). Un relecteur qui ne
rend pas de verdict en TOURS_RELECTURE tours laisse partir l'action ; le journal du candidat le
note.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, cast

import anyio
from mcp import Client

from orchestrations.agent_seul import (
    Bilan,
    Outils,
    OutilsMCP,
    Repondeur,
    boucle,
    ecrire_sortie_json,
    executer_appel,
    outil_openai,
    recit,
)
from orchestrations.modele import ConfigurationModele, Modele, cle_api, lire_configuration, raisonnement

CONSIGNES = Path(__file__).parent / "consignes"
CONSIGNE_AUTEUR = CONSIGNES / "auteur.md"
CONSIGNE_RELECTEUR = CONSIGNES / "relecteur.md"
TOURS_RELECTURE = 12
"""Tours au plus pour une relecture ; au-delà, l'action part (relecture sans verdict)."""

VERDICT = outil_openai(
    "verdict",
    "Rend le verdict sur l'action proposée : accordée telle quelle, ou renvoyée à l'assistant avec la raison.",
    {
        "type": "object",
        "properties": {
            "accord": {"type": "boolean", "description": "vrai si l'action peut partir telle quelle"},
            "raison": {"type": "string", "description": "pourquoi ; l'assistant la lira si l'action est renvoyée"},
        },
        "required": ["accord", "raison"],
        "additionalProperties": False,
    },
)


@dataclass(frozen=True)
class Verdict:
    accord: bool
    raison: str
    rendu: bool = True
    """Faux pour une relecture sans verdict, qui laisse partir l'action."""


class OutilsAnnotes(OutilsMCP):
    """Les outils du relais, avec ce que chaque service déclare : lecture seule ou non."""

    async def lister_annotes(self) -> list[tuple[dict[str, Any], bool | None]]:
        outils: list[tuple[dict[str, Any], bool | None]] = []
        curseur: str | None = None
        while True:
            page = await self._client.list_tools(cursor=curseur)
            outils += [
                (
                    outil_openai(o.name, o.description or "", dict(o.input_schema)),
                    None if o.annotations is None else o.annotations.read_only_hint,
                )
                for o in page.tools
            ]
            curseur = page.next_cursor
            if curseur is None:
                return outils


class SourceAnnotee(Outils, Protocol):
    async def lister_annotes(self) -> list[tuple[dict[str, Any], bool | None]]: ...


def _nom(outil: dict[str, Any]) -> str:
    return str(cast(dict[str, Any], outil["function"])["name"])


class OutilsRelus:
    """Les outils vus par l'auteur : ceux du relais, dont les écritures passent par le relecteur."""

    def __init__(self, source: SourceAnnotee, relire: Callable[[str, dict[str, Any]], Awaitable[Verdict]]) -> None:
        self._source = source
        self._relire = relire
        self._a_relire: set[str] = set()

    async def lister(self) -> list[dict[str, Any]]:
        catalogue = await self._source.lister_annotes()
        self._a_relire = {_nom(outil) for outil, lecture in catalogue if lecture is not True}
        return [outil for outil, _ in catalogue]

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        if nom in self._a_relire:
            verdict = await self._relire(nom, arguments)
            if not verdict.accord:
                return f"renvoyé par le relecteur : {verdict.raison}", True
        return await self._source.appeler(nom, arguments)


class Lectures:
    """Les seuls outils en lecture seule, pour le relecteur ; tout autre appel est refusé sans partir."""

    def __init__(self, source: SourceAnnotee) -> None:
        self._source = source
        self._permis: set[str] = set()

    async def lister(self) -> list[dict[str, Any]]:
        catalogue = [outil for outil, lecture in await self._source.lister_annotes() if lecture is True]
        self._permis = {_nom(outil) for outil in catalogue}
        return catalogue

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        if nom not in self._permis:
            return f"outil non permis au relecteur, qui ne fait que lire : {nom}", True
        return await self._source.appeler(nom, arguments)


def _demande(enonce: str, nom: str, arguments: dict[str, Any]) -> str:
    action = json.dumps(arguments, ensure_ascii=False, indent=2)
    return f"Demande confiée à l'assistant :\n{enonce}\n\nAction qu'il propose :\n{nom}({action})"


def _suite(nom: str, arguments: dict[str, Any]) -> str:
    action = json.dumps(arguments, ensure_ascii=False, indent=2)
    return f"Nouvelle action que l'assistant propose, pour la même demande :\n{nom}({action})"


def _lire_verdict(appel: dict[str, Any]) -> Verdict | None:
    fonction = cast(dict[str, Any], appel.get("function") or {})
    if fonction.get("name") != "verdict":
        return None
    try:
        arguments: object = json.loads(fonction.get("arguments") or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(arguments, dict):
        return None
    valeurs = cast(dict[str, Any], arguments)
    accord, raison = valeurs.get("accord"), valeurs.get("raison")
    if not isinstance(accord, bool):
        return None
    return Verdict(accord, raison.strip() if isinstance(raison, str) and raison.strip() else "sans raison donnée")


async def relire(
    enonce: str,
    nom: str,
    arguments: dict[str, Any],
    lectures: Lectures,
    consigne: str,
    modele: Repondeur,
    configuration: ConfigurationModele,
    bilan: Bilan,
    raconter: Callable[[str], None],
    messages: list[dict[str, Any]] | None = None,
) -> Verdict:
    """Une relecture : le relecteur lit ce qu'il veut, puis rend son verdict sur l'action. messages
    est la conversation du relecteur, gardée d'une relecture à l'autre de la même exécution ; vide,
    elle commence par la consigne et la demande."""
    catalogue = [*await lectures.lister(), VERDICT]
    if messages is None:
        messages = []
    if messages:
        messages.append({"role": "user", "content": _suite(nom, arguments)})
    else:
        messages += [
            {"role": "system", "content": consigne},
            {"role": "user", "content": _demande(enonce, nom, arguments)},
        ]
    raconter(f"=== relecture de {nom} ===")
    for _ in range(TOURS_RELECTURE):
        reponse = await modele.repondre(messages, catalogue)
        bilan.compter(reponse)
        message = cast(dict[str, Any], reponse["choices"][0]["message"])
        appels = cast(list[dict[str, Any]], message.get("tool_calls") or [])
        pensee = raisonnement(message)
        raconter(recit(bilan.appels_modele, pensee, message.get("content"), appels, role="relecteur"))
        verdict = next((v for v in map(_lire_verdict, appels) if v is not None), None)
        tour: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
        if appels:
            tour["tool_calls"] = appels
        if configuration.raisonnement_renvoye and pensee:
            tour[configuration.raisonnement_renvoye] = pensee
        messages.append(tour)
        if verdict is not None:
            raconter(f"verdict : {'accordée' if verdict.accord else 'renvoyée'} ({verdict.raison})")
            # La conversation continue à la relecture suivante : chaque appel du tour reçoit sa réponse.
            for appel in appels:
                verdict_rendu = _lire_verdict(appel) is not None
                texte = "Verdict noté." if verdict_rendu else "Non lu : le verdict est rendu."
                messages.append({"role": "tool", "tool_call_id": appel.get("id", ""), "content": texte})
            return verdict
        if not appels:
            messages.append({"role": "user", "content": "Rends ton verdict avec l'outil verdict."})
        for appel in appels:
            if cast(dict[str, Any], appel.get("function") or {}).get("name") == "verdict":
                # Un verdict mal formé : le relecteur le refait, au lieu d'un refus d'outil trompeur.
                texte = "Erreur : verdict mal formé ; accord est vrai ou faux, raison un texte"
            else:
                texte = await executer_appel(appel, lectures)
            messages.append({"role": "tool", "tool_call_id": appel.get("id", ""), "content": texte})
    raconter(f"relecture sans verdict en {TOURS_RELECTURE} tours : l'action part")
    return Verdict(True, "relecture sans verdict", rendu=False)


@dataclass
class Bilans:
    """Ce que consomment l'auteur et le relecteur ; la fin est celle de l'auteur."""

    auteur: Bilan
    relecteur: Bilan

    def en_json(self) -> dict[str, Any]:
        sortie = self.auteur.en_json()
        relecteur = self.relecteur.en_json()
        sortie["appels_modele"] += relecteur["appels_modele"]
        sortie["consommation"] |= relecteur["consommation"]
        sortie["modeles_renvoyes"] |= relecteur["modeles_renvoyes"]
        return sortie


async def orchestrer(
    enonce: str,
    source: SourceAnnotee,
    lecture: SourceAnnotee,
    auteur: tuple[Repondeur, ConfigurationModele],
    relecteur: tuple[Repondeur, ConfigurationModele],
    noter: Callable[[Bilans], None],
    raconter: Callable[[str], None] = lambda texte: print(texte, flush=True),
) -> Bilans:
    """L'auteur travaille par source ; chacune de ses actions qui écrit ou envoie passe d'abord par le
    relecteur, qui ne lit que par lecture."""
    (modele_auteur, conf_auteur), (modele_relecteur, conf_relecteur) = auteur, relecteur
    bilans = Bilans(Bilan(role=conf_auteur.role), Bilan(role=conf_relecteur.role))
    consigne_relecteur = CONSIGNE_RELECTEUR.read_text(encoding="utf-8")
    lectures = Lectures(lecture)
    conversation: list[dict[str, Any]] = []

    async def relire_action(nom: str, arguments: dict[str, Any]) -> Verdict:
        verdict = await relire(
            enonce,
            nom,
            arguments,
            lectures,
            consigne_relecteur,
            modele_relecteur,
            conf_relecteur,
            bilans.relecteur,
            raconter,
            conversation,
        )
        noter(bilans)
        return verdict

    def noter_auteur(courant: Bilan) -> None:
        bilans.auteur = courant
        noter(bilans)

    await boucle(
        enonce,
        CONSIGNE_AUTEUR.read_text(encoding="utf-8"),
        OutilsRelus(source, relire_action),
        modele_auteur,
        conf_auteur,
        noter_auteur,
        raconter,
    )
    return bilans


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m orchestrations.auteur_relecteur")
    analyse.add_argument("--configuration", type=Path, required=True, help="le modèle de l'auteur")
    analyse.add_argument("--relecteur", type=Path, required=True, help="le modèle du relecteur")
    analyse.add_argument("--mcp", required=True)
    analyse.add_argument("--mcp-lecture", required=True, help="l'accès en lecture seule, pour le relecteur")
    analyse.add_argument("--enonce", type=Path, required=True)
    analyse.add_argument("--sortie", type=Path, required=True)
    options = analyse.parse_args(arguments)
    conf_auteur = replace(lire_configuration(options.configuration), role="auteur")
    conf_relecteur = replace(lire_configuration(options.relecteur), role="relecteur")
    bilans = Bilans(Bilan(role="auteur"), Bilan(role="relecteur"))

    def noter(courants: Bilans) -> None:
        nonlocal bilans
        bilans = courants
        ecrire_sortie_json(options.sortie, courants.en_json())

    async def executer() -> None:
        cle_auteur = cle_api(conf_auteur.cle_env, Path.cwd())
        cle_relecteur = cle_api(conf_relecteur.cle_env, Path.cwd())
        async with (
            Client(options.mcp, mode="legacy", cache=None) as client,
            Client(options.mcp_lecture, mode="legacy", cache=None) as client_lecture,
            Modele(conf_auteur, cle_auteur) as modele_auteur,
            Modele(conf_relecteur, cle_relecteur) as modele_relecteur,
        ):
            enonce = options.enonce.read_text(encoding="utf-8")
            await orchestrer(
                enonce,
                OutilsAnnotes(client),
                OutilsAnnotes(client_lecture),
                (modele_auteur, conf_auteur),
                (modele_relecteur, conf_relecteur),
                noter,
            )

    try:
        anyio.run(executer)
    except Exception as panne:  # rendue à EASE, qui la note en erreur technique
        bilans.auteur.fin, bilans.auteur.detail = "erreur", f"{type(panne).__name__} : {panne}"
        ecrire_sortie_json(options.sortie, bilans.en_json())
    if bilans.auteur.fin != "termine":
        print(f"auteur et relecteur, fin {bilans.auteur.fin} : {bilans.auteur.detail}", file=sys.stderr)
    return 1 if bilans.auteur.fin == "erreur" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
