"""Auteur et relecteur sur τ²-bench airline : l'orchestration auteur et relecteur 0.2.0 de la PME
(`auteur_relecteur`), branchée sur la conversation de τ²-bench (étape 7, décision d'Alexandre du
2026-10-11). EASE la lance comme l'auteur et relecteur de la PME :

    python -m orchestrations.auteur_relecteur_tau2 --configuration <auteur.yaml> \\
        --relecteur <relecteur.yaml> --mcp <adresse du relais> --mcp-lecture <adresse> \\
        --enonce <fichier> --sortie <fichier>

L'auteur est l'agent de reproduction de τ²-bench (`reproduction_tau2.converser`), celui du bras
agent seul : même consigne de τ²-bench, mêmes outils, mêmes réglages. Comme `auteur.md` sur la
PME ajoute à la consigne de l'agent seul une phrase sur la relecture, la consigne de l'auteur est
celle de τ²-bench, intacte, suivie de cette phrase traduite (consignes/relecture_auteur_en.md).

Le relecteur suit la même logique que sur la PME, dans les termes de τ²-bench :
- relu : chaque appel d'outil que τ²-bench ne déclare pas en lecture seule (annotation MCP
  readOnlyHint), les outils génériques compris (`calculate`, `transfer_to_human_agents`) ; un
  outil qui ne déclare rien est relu, comme sur la PME ;
- non relu : les messages de l'auteur au client (`send_message_to_user`, que l'auteur ne voit
  pas : il répond en texte), comme les réponses en texte sur la PME ;
- ce qu'il voit : la politique d'airline de τ²-bench à la place du manuel de Calorelle, la
  conversation avec le client jusqu'à l'action (messages de l'auteur au client et réponses du
  client), puis l'action ; ni les gestes de l'auteur, ni leurs résultats, ni son raisonnement ;
- ce qu'il peut faire : lire par les seuls outils en lecture seule, par l'accès en lecture seule
  du relais (--mcp-lecture), compté à part par EASE ; puis accorder ou renvoyer avec sa raison,
  par l'outil « verdict » ;
- une seule conversation pour toute l'exécution : à chaque nouvelle action, il reçoit la suite
  de la conversation avec le client depuis l'action précédente, puis l'action.
Sa consigne est la traduction fidèle de consignes/relecteur.md, sans règle ajoutée ni retirée
(consignes/relecteur_en.md), avec les messages de l'orchestration en anglais, comme la politique
et la conversation (choix d'Alexandre du 2026-10-11). Le reste vient de `auteur_relecteur`, sans
le modifier : le décompte des deux rôles (Bilans), la lecture des annotations (OutilsAnnotes), le
plafond de TOURS_RELECTURE tours par relecture, au-delà duquel l'action part.

Une action renvoyée revient à l'auteur comme une erreur d'outil de τ²-bench : « Error: sent back
by the reviewer: <raison> ». Les lectures du relecteur passent par le serveur de τ²-bench comme
les gestes de l'auteur : elles entrent dans la conversation de τ²-bench, sans effet sur sa base,
et comptent dans ses limites de 200 messages et de 10 erreurs d'outil.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import anyio
from mcp import Client

from orchestrations.agent_seul import Bilan, Repondeur, ecrire_sortie_json, outil_openai, recit
from orchestrations.auteur_relecteur import TOURS_RELECTURE, Bilans, OutilsAnnotes, SourceAnnotee, Verdict
from orchestrations.modele import ConfigurationModele, ErreurModele, Modele, cle_api, lire_configuration, raisonnement
from orchestrations.reproduction_tau2 import (
    CONVERSATION_FINIE,
    DEBUT_CONVERSATION,
    OUTIL_CLIENT,
    EnonceIllisible,
    appeler,
    converser,
    decouper,
)

CONSIGNES = Path(__file__).parent / "consignes"
CONSIGNE_RELECTEUR = CONSIGNES / "relecteur_en.md"
"""Traduction fidèle de consignes/relecteur.md."""
RELECTURE_AUTEUR = CONSIGNES / "relecture_auteur_en.md"
"""Traduction fidèle de la phrase sur la relecture de consignes/auteur.md."""

VERDICT = outil_openai(
    "verdict",
    "Gives the verdict on the proposed action: approved as is, or sent back to the assistant with the reason.",
    {
        "type": "object",
        "properties": {
            "approved": {"type": "boolean", "description": "true if the action can go out as is"},
            "reason": {"type": "string", "description": "why; the assistant will read it if the action is sent back"},
        },
        "required": ["approved", "reason"],
        "additionalProperties": False,
    },
)
RENVOI = "Error: sent back by the reviewer: "
"""Ce que lit l'auteur avant la raison d'un renvoi, au format d'une erreur d'outil de τ²-bench."""
RELANCE = "Give your verdict with the verdict tool."
VERDICT_NOTE = "Verdict recorded."
NON_LU = "Not read: the verdict is given."
VERDICT_MAL_FORME = "Error: malformed verdict; approved is true or false, reason is a text"


def politique(consigne: str) -> str:
    """La politique d'airline, prise dans la consigne de l'agent de τ²-bench (`<policy>`)."""
    _, ouverture, reste = consigne.partition("<policy>\n")
    texte, fermeture, _ = reste.partition("\n</policy>")
    if not ouverture or not fermeture or not texte.strip():
        raise EnonceIllisible("politique introuvable dans la consigne de τ²-bench")
    return texte


def enonce_de_l_auteur(enonce: str, phrase: str) -> str:
    """L'énoncé de τ²-bench, la phrase sur la relecture ajoutée à la fin de sa consigne."""
    consigne, separateur, debut = enonce.partition(DEBUT_CONVERSATION)
    if not separateur:
        return enonce  # converser le refusera comme illisible
    return f"{consigne}\n\n{phrase.strip()}{separateur}{debut}"


@dataclass
class Conversation:
    """La conversation avec le client, au format de l'énoncé de τ²-bench, une ligne par message ;
    vues compte les lignes déjà montrées au relecteur."""

    lignes: list[str] = field(default_factory=lambda: list[str]())
    vues: int = 0

    def ajouter(self, role: str, texte: str) -> None:
        self.lignes.append(f"{role}: {texte}")

    def nouvelles(self) -> str:
        """Les lignes que le relecteur n'a pas encore vues, désormais vues."""
        texte = "\n".join(self.lignes[self.vues :])
        self.vues = len(self.lignes)
        return texte


def _action(nom: str, arguments: dict[str, Any]) -> str:
    return f"{nom}({json.dumps(arguments, ensure_ascii=False, indent=2)})"


def _demande(regles: str, conversation: str, nom: str, arguments: dict[str, Any]) -> str:
    return (
        f"Request entrusted to the assistant:\nCompany policy:\n{regles}\n\n"
        f"Conversation with the customer so far:\n{conversation}\n\n"
        f"Action it proposes:\n{_action(nom, arguments)}"
    )


def _suite(conversation: str, nom: str, arguments: dict[str, Any]) -> str:
    debut = f"Conversation with the customer since the previous action:\n{conversation}\n\n" if conversation else ""
    return f"{debut}New action that the assistant proposes, for the same request:\n{_action(nom, arguments)}"


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
    accord, raison = valeurs.get("approved"), valeurs.get("reason")
    if not isinstance(accord, bool):
        return None
    return Verdict(accord, raison.strip() if isinstance(raison, str) and raison.strip() else "no reason given")


class Lectures:
    """Les seuls outils de τ²-bench en lecture seule, pour le relecteur ; tout autre appel est
    refusé sans partir."""

    def __init__(self, source: SourceAnnotee) -> None:
        self._source = source
        self._permis: set[str] = set()

    async def lister(self) -> list[dict[str, Any]]:
        catalogue = [outil for outil, lecture in await self._source.lister_annotes() if lecture is True]
        self._permis = {str(outil["function"]["name"]) for outil in catalogue}
        return catalogue

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        if nom not in self._permis:
            return f"Error: tool not allowed to the reviewer, who only reads: {nom}", True
        return await self._source.appeler(nom, arguments)


async def relire(
    regles: str,
    conversation: Conversation,
    nom: str,
    arguments: dict[str, Any],
    lectures: Lectures,
    consigne: str,
    modele: Repondeur,
    configuration: ConfigurationModele,
    bilan: Bilan,
    raconter: Callable[[str], None],
    messages: list[dict[str, Any]],
) -> Verdict:
    """Une relecture, comme auteur_relecteur.relire : le relecteur lit ce qu'il veut, puis rend
    son verdict. messages est sa conversation, gardée d'une relecture à l'autre ; vide, elle
    commence par la consigne, la politique et la conversation avec le client."""
    catalogue = [*await lectures.lister(), VERDICT]
    if messages:
        messages.append({"role": "user", "content": _suite(conversation.nouvelles(), nom, arguments)})
    else:
        messages += [
            {"role": "system", "content": consigne},
            {"role": "user", "content": _demande(regles, conversation.nouvelles(), nom, arguments)},
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
                texte = VERDICT_NOTE if _lire_verdict(appel) is not None else NON_LU
                messages.append({"role": "tool", "tool_call_id": appel.get("id", ""), "content": texte})
            return verdict
        if not appels:
            messages.append({"role": "user", "content": RELANCE})
        for appel in appels:
            if cast(dict[str, Any], appel.get("function") or {}).get("name") == "verdict":
                texte = VERDICT_MAL_FORME
            else:
                texte = await appeler(appel, lectures)
            messages.append({"role": "tool", "tool_call_id": appel.get("id", ""), "content": texte})
    raconter(f"relecture sans verdict en {TOURS_RELECTURE} tours : l'action part")
    return Verdict(True, "relecture sans verdict", rendu=False)


class OutilsRelus:
    """Les outils vus par l'auteur : ceux du relais ; les gestes qui ne sont pas déclarés en
    lecture seule passent par le relecteur, et les messages au client nourrissent la conversation
    qu'il lit, sans passer par lui."""

    def __init__(
        self,
        source: SourceAnnotee,
        relire: Callable[[str, dict[str, Any]], Awaitable[Verdict]],
        conversation: Conversation,
    ) -> None:
        self._source = source
        self._relire = relire
        self._conversation = conversation
        self._a_relire: set[str] = set()

    async def lister(self) -> list[dict[str, Any]]:
        catalogue = await self._source.lister_annotes()
        self._a_relire = {
            str(outil["function"]["name"])
            for outil, lecture in catalogue
            if lecture is not True and outil["function"]["name"] != OUTIL_CLIENT
        }
        return [outil for outil, _ in catalogue]

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        if nom == OUTIL_CLIENT:
            texte, refus = await self._source.appeler(nom, arguments)
            if not refus:
                self._conversation.ajouter("assistant", str(arguments.get("message", "")))
                if texte != CONVERSATION_FINIE:
                    self._conversation.ajouter("user", texte)
            return texte, refus
        if nom in self._a_relire:
            verdict = await self._relire(nom, arguments)
            if not verdict.accord:
                return f"{RENVOI}{verdict.raison}", True
        return await self._source.appeler(nom, arguments)


async def orchestrer(
    enonce: str,
    source: SourceAnnotee,
    lecture: SourceAnnotee,
    auteur: tuple[Repondeur, ConfigurationModele],
    relecteur: tuple[Repondeur, ConfigurationModele],
    noter: Callable[[Bilans], None],
    raconter: Callable[[str], None] = lambda texte: print(texte, flush=True),
) -> Bilans:
    """L'auteur joue la conversation de τ²-bench par source ; chacun de ses gestes qui n'est pas
    déclaré en lecture seule passe d'abord par le relecteur, qui ne lit que par lecture."""
    (modele_auteur, conf_auteur), (modele_relecteur, conf_relecteur) = auteur, relecteur
    bilans = Bilans(Bilan(role=conf_auteur.role), Bilan(role=conf_relecteur.role))
    try:
        depart = decouper(enonce)
        regles = politique(depart.consigne)
    except EnonceIllisible as ecart:
        bilans.auteur.fin, bilans.auteur.detail = "erreur", f"énoncé de τ²-bench illisible : {ecart}"
        noter(bilans)
        return bilans
    conversation = Conversation()
    for message in depart.messages:
        conversation.ajouter(str(message["role"]), str(message["content"]))
    consigne_relecteur = CONSIGNE_RELECTEUR.read_text(encoding="utf-8")
    lectures = Lectures(lecture)
    messages_relecteur: list[dict[str, Any]] = []

    async def relire_action(nom: str, arguments: dict[str, Any]) -> Verdict:
        try:
            verdict = await relire(
                regles,
                conversation,
                nom,
                arguments,
                lectures,
                consigne_relecteur,
                modele_relecteur,
                conf_relecteur,
                bilans.relecteur,
                raconter,
                messages_relecteur,
            )
        finally:
            noter(bilans)
        return verdict

    def noter_auteur(courant: Bilan) -> None:
        bilans.auteur = courant
        noter(bilans)

    try:
        await converser(
            enonce_de_l_auteur(enonce, RELECTURE_AUTEUR.read_text(encoding="utf-8")),
            OutilsRelus(source, relire_action, conversation),
            modele_auteur,
            conf_auteur,
            noter_auteur,
            raconter,
        )
    except ErreurModele as panne:  # une panne du modèle du relecteur ; celle de l'auteur, converser la note
        bilans.auteur.fin, bilans.auteur.detail = "erreur", f"relecteur : {panne}"
        noter(bilans)
    return bilans


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m orchestrations.auteur_relecteur_tau2")
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
        print(f"auteur et relecteur τ², fin {bilans.auteur.fin} : {bilans.auteur.detail}", file=sys.stderr)
    return 1 if bilans.auteur.fin == "erreur" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
