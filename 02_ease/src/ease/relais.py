"""Relais MCP d'EASE : les outils de l'environnement offerts à un candidat externe, en HTTP local.

Un candidat lancé dans son propre processus (règle 6) n'a aucun accès aux objets d'EASE. Le
relais lui présente les outils de l'environnement, jouet ou PME, comme un serveur MCP en HTTP,
sur 127.0.0.1 et un port choisi par le système, le temps d'une exécution. Chaque appel passe par
Outils : il compte une étape, respecte le budget, entre au journal, puis atteint
l'environnement. Un refus revient au candidat comme une erreur d'outil MCP ; un budget épuisé
aussi, et Outils le note pour l'exécuteur. Une panne de l'environnement est gardée et relevée à
la fin : c'est une erreur technique, pas une faute de l'agent.

Avec le gardien (étape 4), l'environnement PME lui passe chaque appel : il le juge avant la PME.

Un candidat qui le demande (`acces_lecture` dans sa déclaration) a un second serveur, à
l'adresse url_lecture : il ne présente que les outils déclarés en lecture seule, et ses appels se
comptent à part, hors du budget de la tâche (Outils.lire_avec ; JOURNAL, entrée 94).
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Callable
from types import TracebackType
from typing import Any

import anyio.to_thread
import uvicorn
from mcp import types
from mcp.server import ServerRequestContext
from mcp.server.lowlevel import Server

from ease.executeur import BudgetEtapesDepasse, DescriptionOutil, ErreurOutil, Outils

HOTE = "127.0.0.1"
DEMARRAGE_MAX_SECONDES = 10.0


def _texte(texte: str, erreur: bool = False) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=texte)], is_error=erreur)


class Relais:
    """Serveur MCP local, ouvert par `with Relais(outils) as relais:`, à l'adresse relais.url ;
    avec lecture=True, un second serveur en lecture seule, à l'adresse relais.url_lecture."""

    def __init__(self, outils: Outils, lecture: bool = False) -> None:
        self._outils = outils
        self._lecture = lecture
        self.url = ""
        self.url_lecture = ""
        self.panne: BaseException | None = None
        """Première panne de l'environnement pendant l'exécution, à relever par l'appelant."""
        self._serveurs: list[tuple[uvicorn.Server, threading.Thread]] = []

    def __enter__(self) -> Relais:
        self.url = self._demarrer(
            Server("ease-relais", version="0.1.0", on_list_tools=self._lister, on_call_tool=self._appeler)
        )
        if self._lecture:
            self.url_lecture = self._demarrer(
                Server(
                    "ease-relais-lecture", version="0.1.0", on_list_tools=self._lister_lectures, on_call_tool=self._lire
                )
            )
        return self

    def _demarrer(self, mcp: Server[Any]) -> str:
        application = mcp.streamable_http_app(json_response=True, host=HOTE)
        prise = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        prise.bind((HOTE, 0))
        port = prise.getsockname()[1]
        serveur = uvicorn.Server(uvicorn.Config(application, log_level="warning", lifespan="on"))
        fil = threading.Thread(target=serveur.run, kwargs={"sockets": [prise]}, daemon=True, name="relais-mcp")
        fil.start()
        self._serveurs.append((serveur, fil))
        limite = time.monotonic() + DEMARRAGE_MAX_SECONDES
        while not serveur.started:
            if not fil.is_alive() or time.monotonic() > limite:
                self._arreter()
                raise RuntimeError("le relais MCP n'a pas démarré")
            time.sleep(0.01)
        return f"http://{HOTE}:{port}/mcp"

    def __exit__(
        self, type_: type[BaseException] | None, erreur: BaseException | None, trace: TracebackType | None
    ) -> None:
        self._arreter()

    def _arreter(self) -> None:
        for serveur, _ in self._serveurs:
            serveur.should_exit = True
        for _, fil in self._serveurs:
            fil.join(DEMARRAGE_MAX_SECONDES)

    async def _lister(
        self, contexte: ServerRequestContext[Any], parametres: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        del contexte, parametres
        return self._decrire(self._outils.lister())

    async def _lister_lectures(
        self, contexte: ServerRequestContext[Any], parametres: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        del contexte, parametres
        return self._decrire(self._outils.lister_lectures())

    def _decrire(self, descriptions: list[DescriptionOutil]) -> types.ListToolsResult:
        outils = [
            types.Tool(
                name=o.nom,
                description=o.description,
                input_schema=dict(o.schema),
                annotations=None if o.lecture_seule is None else types.ToolAnnotations(read_only_hint=o.lecture_seule),
            )
            for o in descriptions
        ]
        return types.ListToolsResult(tools=outils)

    async def _appeler(
        self, contexte: ServerRequestContext[Any], parametres: types.CallToolRequestParams
    ) -> types.CallToolResult:
        del contexte
        return await self._transmettre(self._outils.appeler_avec, parametres)

    async def _lire(
        self, contexte: ServerRequestContext[Any], parametres: types.CallToolRequestParams
    ) -> types.CallToolResult:
        del contexte
        return await self._transmettre(self._outils.lire_avec, parametres)

    async def _transmettre(
        self, appeler: Callable[[str, dict[str, Any]], Any], parametres: types.CallToolRequestParams
    ) -> types.CallToolResult:
        arguments: dict[str, Any] = dict(parametres.arguments or {})
        try:
            resultat = await anyio.to_thread.run_sync(appeler, parametres.name, arguments)
        except (ErreurOutil, BudgetEtapesDepasse) as refus:
            return _texte(str(refus), erreur=True)
        except Exception as panne:  # l'environnement, pas l'agent
            if self.panne is None:
                self.panne = panne
            return _texte("panne de l'environnement : l'exécution sera notée en erreur technique", erreur=True)
        return _texte(resultat if isinstance(resultat, str) else json.dumps(resultat, ensure_ascii=False))
