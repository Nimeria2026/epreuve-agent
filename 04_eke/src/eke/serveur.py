"""Le serveur MCP d'EKE : trois outils en lecture seule sur les PDF des dossiers partagés.

Comme les services de la PME, il se lance en stdio pour une personne de l'organigramme, sur un
dossier d'état (`python -m eke --etat <dossier> --pour <personne>`), et ne garde rien en
mémoire : chaque appel relit le fichier demandé. Une personne lit par EKE ce qu'elle ouvre dans
les dossiers partagés (`droits`). Chaque outil déclare le contrat `lecture_document` comme
`outputSchema`, rend la sortie structurée, et la même en JSON dans un texte, pour un client qui
ne lit que le texte.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio.to_thread
from mcp import types
from mcp.server import ServerRequestContext
from mcp.server.lowlevel import Server

from eke import VERSION
from eke.contrat import schema
from eke.droits import Dossiers, RefusEke
from eke.lecture import lire, sortie_citations, sortie_lignes, sortie_valeurs
from eke.pdfium import DocumentIllisible

CHEMIN = {
    "type": "string",
    "minLength": 1,
    "description": "chemin du PDF dans les dossiers partagés, par exemple commercial/devis/2026/dv-2026-004.pdf",
}
TEXTE = {"type": "string", "minLength": 1, "description": "le texte à trouver, tel qu'il se lit dans le document"}


def _entree(**proprietes: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": proprietes, "required": list(proprietes), "additionalProperties": False}


def outils() -> list[types.Tool]:
    """Les trois outils d'EKE, tous en lecture seule (annotation MCP readOnlyHint)."""
    lecture_seule = types.ToolAnnotations(read_only_hint=True)
    return [
        types.Tool(
            name="lire_document",
            title="Lire un PDF",
            description=(
                "Rend le texte d'un PDF des dossiers partagés, morceau de ligne par morceau de ligne, dans l'ordre "
                "de lecture du PDF : une colonne de texte après l'autre. Chaque morceau porte sa page et sa zone : "
                "rectangle en points, origine en haut à gauche de la page."
            ),
            input_schema=_entree(chemin=CHEMIN),
            output_schema=schema(),
            annotations=lecture_seule,
        ),
        types.Tool(
            name="extraire_valeurs",
            title="Extraire les valeurs d'un PDF",
            description=(
                "Rend les paires étiquette-valeur d'un PDF des dossiers partagés (« Total TTC : 512,40 € »). Chaque "
                "valeur est typée (montant, date, iban, pourcentage, texte), normalisée (512.40, 2026-10-17), et "
                "citée avec sa page et sa zone."
            ),
            input_schema=_entree(chemin=CHEMIN),
            output_schema=schema(),
            annotations=lecture_seule,
        ),
        types.Tool(
            name="citer",
            title="Citer un texte d'un PDF",
            description=(
                "Cherche un texte dans un PDF des dossiers partagés et rend chaque endroit où il apparaît, avec sa "
                "page et sa zone ; aucune citation s'il n'y est pas. Les blancs comptent comme une espace, la casse "
                "et les accents à l'identique."
            ),
            input_schema=_entree(chemin=CHEMIN, texte=TEXTE),
            output_schema=schema(),
            annotations=lecture_seule,
        ),
    ]


def _refus(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=message)], is_error=True)


def _argument(arguments: dict[str, Any], nom: str) -> str:
    valeur = arguments.get(nom)
    if not isinstance(valeur, str) or not valeur.strip():
        raise RefusEke(f"argument manquant ou vide : {nom}")
    return valeur


def appeler(dossiers: Dossiers, nom: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Un appel d'outil, sans MCP autour : la sortie au contrat, ou RefusEke."""
    if nom not in {"lire_document", "extraire_valeurs", "citer"}:
        raise RefusEke(f"outil inconnu : {nom}")
    chemin = _argument(arguments, "chemin")
    recherche = _argument(arguments, "texte") if nom == "citer" else ""
    absolu = dossiers.fichier(chemin)
    lecture = lire(absolu.relative_to(dossiers.racine).as_posix(), absolu.read_bytes())
    if nom == "lire_document":
        return sortie_lignes(lecture)
    if nom == "extraire_valeurs":
        return sortie_valeurs(lecture)
    return sortie_citations(lecture, recherche)


def creer_serveur(etat: Path, pour: str) -> Server[Any]:
    """Le serveur d'EKE pour cette personne ; ValueError si elle n'est pas dans l'organigramme."""
    dossiers = Dossiers.pour(etat, pour)

    async def lister(
        contexte: ServerRequestContext[Any], parametres: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        del contexte, parametres
        return types.ListToolsResult(tools=outils())

    async def executer(
        contexte: ServerRequestContext[Any], parametres: types.CallToolRequestParams
    ) -> types.CallToolResult:
        del contexte
        arguments: dict[str, Any] = dict(parametres.arguments or {})
        try:
            sortie = await anyio.to_thread.run_sync(appeler, dossiers, parametres.name, arguments)
        except (RefusEke, DocumentIllisible) as refus:
            return _refus(str(refus))
        texte = json.dumps(sortie, ensure_ascii=False, separators=(",", ":"))
        return types.CallToolResult(content=[types.TextContent(type="text", text=texte)], structured_content=sortie)

    return Server("eke", version=VERSION, on_list_tools=lister, on_call_tool=executer)
