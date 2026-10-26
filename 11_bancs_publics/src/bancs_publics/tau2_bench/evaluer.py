"""Réévalue une simulation écrite par le serveur, dans un processus neuf, avec l'évaluateur de τ²-bench.

Depuis la racine du dépôt :

    uv run --all-packages python -m bancs_publics.tau2_bench.evaluer --jeu sierra \\
        --simulation 99_local/tau2_travail/airline_14_r1/simulation.json

Rend sur la sortie standard la note au format de `evaluation.json`. Elle doit être identique à
celle que le serveur a écrite : la note ne dépend que de la conversation et de la tâche.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from bancs_publics.tau2_bench.donnees import JEUX, dossier_donnees, dossier_local, fichier_taches, verifier


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(
        prog="python -m bancs_publics.tau2_bench.evaluer",
        description="Réévalue une simulation écrite par le serveur, avec l'évaluateur de τ²-bench.",
    )
    analyse.add_argument("--jeu", choices=JEUX, required=True)
    analyse.add_argument("--simulation", type=Path, required=True, help="simulation.json écrite par le serveur")
    analyse.add_argument("--donnees", type=Path, default=None, help="dossier local des données (99_local/tau2)")
    options = analyse.parse_args(arguments)
    dossier: Path = options.donnees or dossier_local()
    if verifier(dossier):
        print(f"Données de τ²-bench absentes ou modifiées dans {dossier}", file=sys.stderr)
        return 2
    os.environ["TAU2_DATA_DIR"] = str(dossier_donnees(dossier))
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from loguru import logger

    from bancs_publics.tau2_bench import pont

    logger.remove()
    logger.add(sys.stderr, level="ERROR")
    simulation = json.loads(options.simulation.read_text(encoding="utf-8"))
    taches = pont.lire_taches(fichier_taches(dossier, options.jeu))
    note = pont.evaluer_fichier(options.simulation, taches[str(simulation["task_id"])], options.jeu)
    print(json.dumps(note, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
