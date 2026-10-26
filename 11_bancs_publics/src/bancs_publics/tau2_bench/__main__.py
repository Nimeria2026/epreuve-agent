"""Lance le serveur MCP de τ²-bench en stdio, sur un jeu de tâches d'airline.

Depuis la racine du dépôt, après `python -m bancs_publics.tau2_bench.donnees` :

    uv run --all-packages python -m bancs_publics.tau2_bench --jeu sierra

Il attend un client MCP sur son entrée standard : EASE le lance pour un run et lui parle comme
aux serveurs de la PME. `--utilisateur` vaut `ecrit_d_avance` (aucun modèle, pour les témoins et
les tests), `rejoue:<agent>` (aucun modèle : l'utilisateur redit les messages des conversations
publiées par Sierra pour cet agent, avec `--jeu publie`), ou le nom d'un modèle de simulateur au
format de litellm (runs de reproduction : clé et budget à part). Code de sortie 2 si les données
manquent ou ont changé, ou si l'agent rejoué est inconnu.

Le serveur ne fait aucun appel réseau à son lancement : litellm lit sa table de prix locale
(`LITELLM_LOCAL_MODEL_COST_MAP`), et seul le simulateur d'utilisateur, s'il est un modèle, appelle
une API (règle 12 du BRIEF).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from bancs_publics.tau2_bench.donnees import (
    JEUX,
    PUBLIES,
    dossier_donnees,
    dossier_local,
    fichier_publie,
    fichier_taches,
    verifier,
)


async def _servir(serveur: Server[Any]) -> None:
    async with stdio_server() as (lecture, ecriture):
        # La sortie standard du processus porte MCP. Ce qu'une bibliothèque y imprime pendant le
        # run va sur la sortie d'erreur : sinon, gardé en tampon, il partirait au client à l'arrêt
        # du serveur, comme un message illisible (essai du 2026-10-10, journal τ², 18e entrée).
        sortie, sys.stdout = sys.stdout, sys.stderr
        try:
            await serveur.run(lecture, ecriture, serveur.create_initialization_options())
        finally:
            sys.stdout = sortie


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(
        prog="python -m bancs_publics.tau2_bench", description="Serveur MCP de τ²-bench, airline, en stdio."
    )
    analyse.add_argument("--jeu", choices=JEUX, required=True, help="jeu de tâches d'airline : sierra ou verified")
    analyse.add_argument("--donnees", type=Path, default=None, help="dossier local des données (99_local/tau2)")
    analyse.add_argument(
        "--travail", type=Path, default=None, help="où écrire simulations et notes (99_local/tau2_travail)"
    )
    analyse.add_argument(
        "--utilisateur", default="ecrit_d_avance", help="ecrit_d_avance, rejoue:<agent>, ou un modèle de litellm"
    )
    options = analyse.parse_args(arguments)
    dossier: Path = options.donnees or dossier_local()
    manquants = verifier(dossier)
    if manquants:
        print(
            f"Données de τ²-bench absentes ou modifiées dans {dossier} : {', '.join(manquants)}. "
            "Lancer : uv run --all-packages python -m bancs_publics.tau2_bench.donnees",
            file=sys.stderr,
        )
        return 2
    publiees = None
    if options.utilisateur.startswith("rejoue:"):
        agent = options.utilisateur.removeprefix("rejoue:")
        if agent not in PUBLIES:
            print(f"Agent rejoué inconnu : {agent} (connus : {', '.join(PUBLIES)})", file=sys.stderr)
            return 2
        publiees = fichier_publie(dossier, agent)
    os.environ["TAU2_DATA_DIR"] = str(dossier_donnees(dossier))
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    # Rien de τ²-bench ne doit écrire sur la sortie standard, réservée à MCP.
    with contextlib.redirect_stdout(sys.stderr):
        from loguru import logger

        from bancs_publics.tau2_bench.serveur import Pont, creer_serveur

        logger.remove()
        logger.add(sys.stderr, level="WARNING")
        travail: Path = options.travail or dossier.with_name("tau2_travail")
        etat = Pont(options.jeu, fichier_taches(dossier, options.jeu), travail, options.utilisateur, publiees)
        serveur = creer_serveur(etat)
    anyio.run(_servir, serveur)
    return 0


if __name__ == "__main__":
    sys.exit(main())
