"""Lance le serveur MCP d'EKE en stdio, pour une personne de l'organigramme, sur un état de la PME.

Depuis la racine du dépôt :

    uv run --all-packages python -m eke --etat 05_pme/societes/calorelle/v3 --pour patrick.roux

Il attend un client MCP sur son entrée standard ; EASE, le gardien ou un agent le lancent comme
les serveurs de la PME. Code de sortie 2 si la personne n'est pas dans l'organigramme ou si le
dossier d'état n'a pas de dossiers partagés.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from eke.serveur import creer_serveur


async def _servir(serveur: Server[Any]) -> None:
    async with stdio_server() as (lecture, ecriture):
        await serveur.run(lecture, ecriture, serveur.create_initialization_options())


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m eke", description="Serveur MCP d'EKE, en stdio.")
    analyse.add_argument("--etat", type=Path, required=True, help="dossier d'état de la PME")
    analyse.add_argument("--pour", required=True, help="identifiant de la personne servie, par exemple patrick.roux")
    options = analyse.parse_args(arguments)
    try:
        serveur = creer_serveur(options.etat, options.pour)
    except (ValueError, FileNotFoundError) as erreur:
        print(f"EKE ne démarre pas : {erreur}", file=sys.stderr)
        return 2
    anyio.run(_servir, serveur)
    return 0


if __name__ == "__main__":
    sys.exit(main())
