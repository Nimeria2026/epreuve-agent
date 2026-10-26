"""Témoin externe : un témoin qui agit depuis son propre processus, par le relais MCP d'EASE.

Il emprunte le chemin d'un vrai candidat (processus séparé, relais, fichier de sortie) avec un
comportement connu d'avance : parfait, toujours faux ou inerte. Si ses taux s'écartent de ceux
du même témoin joué dans le processus d'EASE, c'est le chemin qui se trompe. Comme les autres
témoins, il appartient au banc et reconnaît la tâche à son énoncé (règle 5).

    python -m ease.temoin_externe --terrain pme --comportement parfait \\
        --mcp <adresse> --enonce <fichier> --sortie <fichier>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

import anyio
from mcp import Client

from ease.jouet import Actions

type Comportement = Literal["parfait", "toujours_faux", "inerte"]
COMPORTEMENTS: tuple[Comportement, ...] = ("parfait", "toujours_faux", "inerte")


async def jouer(adresse: str, actions: Actions) -> None:
    """Joue les gestes dans l'ordre ; s'arrête au premier refus, comme le témoin du processus d'EASE."""
    async with Client(adresse, mode="legacy", cache=None) as client:
        for nom, arguments in actions:
            resultat = await client.call_tool(nom, dict(arguments))
            if resultat.is_error:
                return


def main(arguments: list[str] | None = None) -> int:
    from ease.temoins import TERRAINS  # import tardif : temoins importe ce module

    analyse = argparse.ArgumentParser(prog="python -m ease.temoin_externe")
    analyse.add_argument("--terrain", choices=sorted(TERRAINS), required=True)
    analyse.add_argument("--comportement", choices=COMPORTEMENTS, required=True)
    analyse.add_argument("--mcp", required=True)
    analyse.add_argument("--enonce", type=Path, required=True)
    analyse.add_argument("--sortie", type=Path, required=True)
    options = analyse.parse_args(arguments)
    terrain = TERRAINS[options.terrain]()
    tache = terrain.tache(options.enonce.read_text(encoding="utf-8"))
    actions: Actions = {
        "parfait": terrain.solutions[tache],
        "toujours_faux": terrain.erreurs[tache],
        "inerte": [],
    }[options.comportement]
    anyio.run(jouer, options.mcp, actions)
    sortie: dict[str, Any] = {
        "fin": "termine",
        "detail": None,
        "appels_modele": 0,
        "consommation": {},
        "modeles_renvoyes": {},
    }
    options.sortie.write_text(json.dumps(sortie) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
