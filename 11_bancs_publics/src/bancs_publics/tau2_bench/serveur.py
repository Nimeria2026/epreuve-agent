"""Le serveur MCP de τ²-bench : les outils d'airline et le client, pour un agent ; l'ouverture et
la clôture des exécutions, pour EASE.

Un seul processus sert tout un run : chaque exécution s'ouvre sur une tâche neuve, avec une base
neuve, et se clôt par la note de τ²-bench, écrite sur le disque. L'agent voit les 14 outils
d'airline tels que τ²-bench les présente au sien (nom, description, schéma), chacun annoncé en
lecture seule ou non selon son type chez τ²-bench (annotation MCP readOnlyHint ; un outil
générique, `calculate` ou `transfer_to_human_agents`, n'annonce rien), et un quinzième,
`send_message_to_user`, qui porte son message au client et rend la réponse du client.

Deux outils de plus servent à EASE seul : `poa_ouvrir` et `poa_cloturer`. Le serveur les annonce,
pour que le client MCP connaisse chacun de ses outils ; l'environnement d'EASE les retire de ce
qu'il présente à l'agent et les lui refuse (règle 5 du BRIEF : l'agent ne voit ni les contrôles ni
les solutions). Ce serveur ne se branche donc jamais directement sur un agent.

Avec l'utilisateur rejoué (`--utilisateur rejoue:<agent>`), `poa_ouvrir` reçoit aussi `essai`, le
numéro de l'essai publié (0 à 3) : l'utilisateur redit les messages de cette conversation-là, et
la note dit si la conversation rejouée en a divergé (`divergence`).

Une panne du pont (une réponse de τ²-bench qu'il n'a pas su lire) revient en erreur marquée
`{"panne": true}` : EASE la compte comme une erreur technique, jamais comme une faute de l'agent.

Clôture d'une exécution : `<travail>/<execution>/simulation.json` (la conversation au format de
τ²-bench, réévaluable) et `<travail>/<execution>/evaluation.json` (la note mise à plat), lus par
EASE sur le disque, comme l'état final de la PME.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import anyio.to_thread
from mcp import types
from mcp.server import ServerRequestContext
from mcp.server.lowlevel import Server

from bancs_publics.tau2_bench import pont

VERSION = "0.1.0"
OUVRIR = "poa_ouvrir"
CLOTURER = "poa_cloturer"
NOM_EXECUTION = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
"""Un nom de dossier sans point ni barre : rien ne sort du dossier de travail."""

DESCRIPTION_CLIENT = (
    "Send a message to the user (the customer) and get the user's reply. This is the only way to talk to the user. "
    "When the user ends the conversation, the reply says so and no further action is possible."
)


def ecrire_json(chemin: Path, donnees: Any) -> None:
    """Écrit un JSON d'un seul geste : un lecteur ne voit jamais un fichier à moitié écrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    texte = json.dumps(donnees, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=chemin.parent, delete=False) as provisoire:
        provisoire.write(texte)
    Path(provisoire.name).replace(chemin)


class RefusPont(Exception):
    """Un appel que le serveur refuse : il revient à l'appelant comme une erreur d'outil."""


def _resultat(texte: str, erreur: bool = False, structure: dict[str, Any] | None = None) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=texte)], is_error=erreur, structured_content=structure
    )


def outils_mcp(outils: list[pont.Outil]) -> list[types.Tool]:
    """Les outils annoncés : ceux d'airline, le client, puis les deux d'EASE."""
    annonces: list[types.Tool] = []
    for outil in outils:
        lecture = {"lecture": True, "ecriture": False}.get(outil.type)
        annonces.append(
            types.Tool(
                name=outil.nom,
                description=outil.description,
                input_schema=outil.schema,
                annotations=None if lecture is None else types.ToolAnnotations(read_only_hint=lecture),
            )
        )
    annonces.append(
        types.Tool(
            name=pont.OUTIL_CLIENT,
            description=DESCRIPTION_CLIENT,
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string", "description": "The message to send to the user."}},
                "required": ["message"],
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(read_only_hint=False),
        )
    )
    annonces += [
        types.Tool(
            name=OUVRIR,
            description="Réservé à EASE : ouvre une exécution sur une tâche du jeu, rend l'énoncé.",
            input_schema={
                "type": "object",
                "properties": {
                    "tache": {"type": "string"},
                    "execution": {"type": "string"},
                    "essai": {"type": "integer", "minimum": 0},
                },
                "required": ["tache", "execution"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name=CLOTURER,
            description="Réservé à EASE : clôt l'exécution ouverte, écrit la simulation et la note de τ²-bench.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
    ]
    return annonces


class Pont:
    """L'état du serveur : le jeu de tâches, l'exécution ouverte, le dossier de travail."""

    def __init__(
        self, jeu: str, fichier_taches: Path, travail: Path, utilisateur: str, publiees: Path | None = None
    ) -> None:
        """publiees : les conversations publiées que redit l'utilisateur rejoué (`rejoue:<agent>`)."""
        self.jeu = jeu
        self.taches = pont.lire_taches(fichier_taches)
        self.travail = travail
        self.utilisateur = utilisateur
        if utilisateur.startswith(pont.REJOUE) and publiees is None:
            raise ValueError("utilisateur rejoué sans fichier de conversations publiées")
        self.rejouees = None if publiees is None else pont.lire_publiees(publiees)
        self.outils = pont.outils_airline()
        self._noms = {o.nom for o in self.outils}
        self._conversation: pont.Conversation | None = None
        self._execution: str | None = None

    def ouvrir(self, tache: str, execution: str, essai: int | None = None) -> dict[str, Any]:
        if tache not in self.taches:
            raise RefusPont(f"tâche inconnue dans le jeu {self.jeu} : {tache}")
        if not NOM_EXECUTION.match(execution):
            raise RefusPont(f"nom d'exécution invalide : {execution}")
        publiee = None
        if self.rejouees is not None:
            if essai is None or (tache, essai) not in self.rejouees:
                raise RefusPont(f"aucune conversation publiée pour la tâche {tache}, essai {essai}")
            publiee = self.rejouees[(tache, essai)]
        conversation = pont.Conversation(self.taches[tache], self.jeu, self.utilisateur, publiee)
        enonce = conversation.ouvrir()
        self._conversation, self._execution = conversation, execution
        return {"enonce": enonce}

    def cloturer(self) -> dict[str, Any]:
        if self._conversation is None or self._execution is None:
            raise RefusPont("aucune exécution ouverte")
        conversation, execution = self._conversation, self._execution
        self._conversation, self._execution = None, None
        simulation, evaluation = conversation.cloturer()
        dossier = self.travail / execution
        ecrire_json(dossier / "simulation.json", simulation)
        ecrire_json(dossier / "evaluation.json", evaluation)
        return {"evaluation": str(dossier / "evaluation.json"), "simulation": str(dossier / "simulation.json")}

    def geste(self, nom: str, arguments: dict[str, Any]) -> pont.Reponse:
        """Un geste de l'agent : un outil d'airline ou un message au client."""
        if self._conversation is None:
            raise RefusPont("aucune exécution ouverte")
        if nom == pont.OUTIL_CLIENT:
            message = arguments.get("message")
            if not isinstance(message, str) or not message.strip():
                raise RefusPont("send_message_to_user expects a non-empty 'message' string.")
            return self._conversation.message(message)
        if nom not in self._noms:
            raise RefusPont(f"Unknown tool: {nom}")
        return self._conversation.outil(nom, arguments)

    def appeler(self, nom: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            if nom == OUVRIR:
                essai = arguments.get("essai")
                ouverture = self.ouvrir(
                    str(arguments.get("tache")),
                    str(arguments.get("execution")),
                    essai if isinstance(essai, int) else None,
                )
                return _resultat(json.dumps(ouverture))
            if nom == CLOTURER:
                return _resultat(json.dumps(self.cloturer()))
            reponse = self.geste(nom, arguments)
        except (RefusPont, pont.ConversationTerminee) as refus:
            return _resultat(str(refus), erreur=True)
        except pont.PanneDuPont as panne:
            return _resultat(str(panne), erreur=True, structure={"panne": True})
        return _resultat(reponse.texte, reponse.erreur, {"conversation_terminee": reponse.terminee})


def creer_serveur(etat: Pont) -> Server[Any]:
    async def lister(
        contexte: ServerRequestContext[Any], parametres: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        del contexte, parametres
        return types.ListToolsResult(tools=outils_mcp(etat.outils))

    async def executer(
        contexte: ServerRequestContext[Any], parametres: types.CallToolRequestParams
    ) -> types.CallToolResult:
        del contexte
        arguments: dict[str, Any] = dict(parametres.arguments or {})
        return await anyio.to_thread.run_sync(etat.appeler, parametres.name, arguments)

    return Server("tau2_bench", version=VERSION, on_list_tools=lister, on_call_tool=executer)
