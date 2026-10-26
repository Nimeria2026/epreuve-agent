"""Agent de reproduction pour τ²-bench : l'agent de Sierra, refait derrière le relais d'EASE.

Pour retrouver par EASE un score publié sur τ²-bench (règle 4 du BRIEF, étape 7), le modèle doit
voir ce que voit l'agent de τ²-bench 1.0.1 (`tau2.agent.llm_agent.LLMAgent`) : sa consigne et
la politique d'airline en message système, la conversation en messages de l'assistant et de
l'utilisateur, les 14 outils d'airline, et rien d'autre. EASE le lance comme l'agent seul :

    python -m orchestrations.reproduction_tau2 --configuration <fichier.yaml> \\
        --mcp <adresse du relais> --enonce <fichier> --sortie <fichier>

L'énoncé que rend le serveur de τ²-bench (`11_bancs_publics`) est la consigne de son agent,
puis « Conversation so far: » et le début de la conversation, une ligne par message. Cet agent
le redécoupe : la consigne devient le message système, le salut de l'agent et le premier message
du client redeviennent des messages. Il n'ajoute aucune consigne à lui.

Le serveur fait parler l'agent au client par un outil, `send_message_to_user` (journal τ²,
quatrième entrée). Cet agent le cache au modèle : quand le modèle répond par un texte, comme
l'agent de τ²-bench, l'agent porte ce texte au client par cet outil, et la réponse du client
revient au modèle comme un message de l'utilisateur. Quand le modèle appelle des outils, chacun
passe par le relais, et son résultat revient tel que τ²-bench le rend, erreur comprise, sans
préfixe. La conversation finit quand le client la clôt (`###STOP###`, `###TRANSFER###` ou
`###OUT-OF-SCOPE###` dans sa réponse), quand l'agent écrit `###STOP###`, ou quand τ²-bench
répond qu'elle est finie.

Trois écarts avec l'agent de τ²-bench, imposés par le passage d'un geste à la fois :
- un texte écrit en même temps que des appels d'outils n'atteint pas la conversation de
  τ²-bench (son agent l'y garde, sans le montrer au client) ; il reste dans l'historique du
  modèle et dans le journal du candidat ;
- plusieurs appels d'un même tour entrent dans la conversation de τ²-bench comme autant de
  messages de l'agent ;
- une réponse vide, sans texte ni appel, clôt la conversation (chez τ²-bench, l'historique
  devient invalide).
Le raisonnement du modèle est renvoyé si la configuration le demande (DeepSeek l'exige avec des
outils), ce que l'agent de τ²-bench ne fait pas.

Sortie au contrat sortie_candidat, réécrite après chaque appel de modèle, comme l'agent seul.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import anyio
from mcp import Client

from orchestrations.agent_seul import Bilan, Outils, OutilsMCP, Repondeur, ecrire_sortie, recit
from orchestrations.modele import ConfigurationModele, ErreurModele, Modele, cle_api, lire_configuration, raisonnement

DEBUT_CONVERSATION = "\n\nConversation so far:\n"
SALUT = "Hi! How can I help you today?"
"""Le premier message de l'agent de τ²-bench, écrit par son orchestrateur (DEFAULT_FIRST_AGENT_MESSAGE)."""
OUTIL_CLIENT = "send_message_to_user"
FINS_DU_CLIENT = ("###STOP###", "###TRANSFER###", "###OUT-OF-SCOPE###")
"""Les marques par lesquelles le simulateur de τ²-bench clôt la conversation (user_simulator_base)."""
FIN_DE_L_AGENT = "###STOP###"
"""La marque par laquelle l'agent de τ²-bench clôt la conversation (LLMAgent.STOP_TOKEN)."""
CONVERSATION_FINIE = "The conversation has ended."
"""Ce que rend le serveur de τ²-bench à un geste fait après la fin."""


class EnonceIllisible(ValueError):
    """L'énoncé n'a pas la forme de celui du serveur de τ²-bench."""


@dataclass(frozen=True)
class Depart:
    """L'énoncé redécoupé : la consigne de l'agent de τ²-bench et le début de la conversation."""

    consigne: str
    messages: list[dict[str, Any]]


def decouper(enonce: str) -> Depart:
    """Redécoupe l'énoncé du serveur de τ²-bench ; lève EnonceIllisible s'il a une autre forme."""
    consigne, separateur, debut = enonce.partition(DEBUT_CONVERSATION)
    if not separateur or not consigne.strip():
        raise EnonceIllisible("« Conversation so far: » introuvable après la consigne")
    salut, _, reste = debut.partition("\n")
    if salut != f"assistant: {SALUT}":
        raise EnonceIllisible(f"premier message inattendu : {salut[:80]!r}")
    if not reste.startswith("user: ") or not reste.removeprefix("user: ").strip():
        raise EnonceIllisible("le premier message du client manque")
    return Depart(
        consigne,
        [{"role": "assistant", "content": SALUT}, {"role": "user", "content": reste.removeprefix("user: ")}],
    )


def fin_du_client(reponse: str) -> bool:
    return any(marque in reponse for marque in FINS_DU_CLIENT)


async def appeler(appel: dict[str, Any], outils: Outils) -> str:
    """Le texte rendu au modèle pour un appel d'outil : celui de τ²-bench, erreur comprise."""
    fonction = cast(dict[str, Any], appel.get("function") or {})
    try:
        arguments: object = json.loads(fonction.get("arguments") or "{}")
    except json.JSONDecodeError:
        arguments = None
    if not isinstance(arguments, dict):
        return "Error: invalid arguments, a JSON object is expected"
    texte, _refus = await outils.appeler(str(fonction.get("name", "")), cast(dict[str, Any], arguments))
    return texte


async def converser(
    enonce: str,
    outils: Outils,
    modele: Repondeur,
    configuration: ConfigurationModele,
    noter: Callable[[Bilan], None],
    raconter: Callable[[str], None] = lambda texte: print(texte, flush=True),
) -> Bilan:
    """Joue la conversation de τ²-bench jusqu'à sa fin, ou jusqu'à la limite de tours."""
    bilan = Bilan(role=configuration.role)
    try:
        depart = decouper(enonce)
    except EnonceIllisible as ecart:
        bilan.fin, bilan.detail = "erreur", f"énoncé de τ²-bench illisible : {ecart}"
        noter(bilan)
        return bilan
    catalogue = await outils.lister()
    if not any(o["function"]["name"] == OUTIL_CLIENT for o in catalogue):
        bilan.fin, bilan.detail = "erreur", f"le relais ne présente pas {OUTIL_CLIENT}"
        noter(bilan)
        return bilan
    catalogue = [o for o in catalogue if o["function"]["name"] != OUTIL_CLIENT]
    messages: list[dict[str, Any]] = [{"role": "system", "content": depart.consigne}, *depart.messages]
    for _ in range(configuration.tours_max):
        try:
            reponse = await modele.repondre(messages, catalogue)
        except ErreurModele as panne:
            bilan.fin, bilan.detail = "erreur", str(panne)
            noter(bilan)
            return bilan
        bilan.compter(reponse)
        message = cast(dict[str, Any], reponse["choices"][0]["message"])
        appels = cast(list[dict[str, Any]], message.get("tool_calls") or [])
        contenu: object = message.get("content")
        texte = contenu if isinstance(contenu, str) else ""
        tour: dict[str, Any] = {"role": "assistant", "content": contenu}
        if appels:
            tour["tool_calls"] = appels
        pensee = raisonnement(message)
        if configuration.raisonnement_renvoye and pensee:
            tour[configuration.raisonnement_renvoye] = pensee
        messages.append(tour)
        raconter(recit(bilan.appels_modele, pensee, contenu, appels))
        noter(bilan)
        if appels:
            if texte.strip():
                raconter("(texte écrit avec des appels d'outils : gardé pour le modèle, non transmis au client)")
            for appel in appels:
                resultat = await appeler(appel, outils)
                messages.append({"role": "tool", "tool_call_id": appel.get("id", ""), "content": resultat})
                if resultat == CONVERSATION_FINIE:
                    return _clore(bilan, noter, "τ²-bench a clos la conversation")
            continue
        if not texte.strip():
            return _clore(bilan, noter, "réponse vide du modèle : conversation close par l'agent")
        reponse_client, refus = await outils.appeler(OUTIL_CLIENT, {"message": texte})
        raconter(f"client : {reponse_client}")
        if FIN_DE_L_AGENT in texte:
            return _clore(bilan, noter, "l'agent a clos la conversation")
        if reponse_client == CONVERSATION_FINIE or (refus and not reponse_client.strip()):
            return _clore(bilan, noter, "τ²-bench a clos la conversation")
        if refus:
            return _clore(bilan, noter, f"message refusé : {reponse_client}")
        messages.append({"role": "user", "content": reponse_client})
        if fin_du_client(reponse_client):
            return _clore(bilan, noter, None)
    bilan.fin, bilan.detail = "tours_max", f"{configuration.tours_max} tours sans fin de conversation"
    noter(bilan)
    return bilan


def _clore(bilan: Bilan, noter: Callable[[Bilan], None], detail: str | None) -> Bilan:
    bilan.fin, bilan.detail = "termine", detail
    noter(bilan)
    return bilan


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m orchestrations.reproduction_tau2")
    analyse.add_argument("--configuration", type=Path, required=True)
    analyse.add_argument("--mcp", required=True)
    analyse.add_argument("--enonce", type=Path, required=True)
    analyse.add_argument("--sortie", type=Path, required=True)
    options = analyse.parse_args(arguments)
    configuration = lire_configuration(options.configuration)
    bilan = Bilan(role=configuration.role)

    def noter(courant: Bilan) -> None:
        nonlocal bilan
        bilan = courant
        ecrire_sortie(options.sortie, courant)

    async def executer() -> None:
        cle = cle_api(configuration.cle_env, Path.cwd())
        async with Client(options.mcp, mode="legacy", cache=None) as client, Modele(configuration, cle) as modele:
            enonce = options.enonce.read_text(encoding="utf-8")
            await converser(enonce, OutilsMCP(client), modele, configuration, noter)

    try:
        anyio.run(executer)
    except Exception as panne:  # rendue à EASE, qui la note en erreur technique
        bilan.fin, bilan.detail = "erreur", f"{type(panne).__name__} : {panne}"
        ecrire_sortie(options.sortie, bilan)
    if bilan.fin != "termine":
        print(f"reproduction τ², fin {bilan.fin} : {bilan.detail}", file=sys.stderr)
    return 1 if bilan.fin == "erreur" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
