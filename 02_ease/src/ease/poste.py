"""Le poste de mesure, seul endroit d'où part un run (cadrage du dépôt public et de l'organisation,
section 10 ; JOURNAL, entrée 285).

    <dépôt>_postes/api      les modèles par API : DeepSeek, MiMo, τ²-bench
    <dépôt>_postes/local    les modèles sur la carte : Qwen, Strata

Un poste est un worktree de l'atelier figé sur un commit, posé par make poste-mesure POSTE=api ou
POSTE=local (09_outillage/scripts/poste_de_mesure.py, qui tient la même liste). Ses runs s'écrivent
dans le 99_local de l'atelier, par un lien. make mesure et make mesure-tau2 refusent un run lancé
d'ailleurs, l'atelier compris, d'un poste modifié, ou d'un commit qui n'est pas dans main.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

POSTES = ("api", "local")
"""Les deux postes : plusieurs runs tournent sur le même poste quand ils partagent un commit (le
verrou est par candidat) ; le second sert quand l'API et la carte ont besoin de deux commits."""


def _git(*arguments: str, dans: Path) -> subprocess.CompletedProcess[str]:
    environnement = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"GIT_OPTIONAL_LOCKS": "0"}
    return subprocess.run(["git", *arguments], cwd=dans, capture_output=True, text=True, env=environnement, check=False)


def postes_de(principal: Path) -> Path:
    """Le dossier des postes d'un atelier : à côté de lui, jamais dedans, où ses tests et ses outils
    le reliraient."""
    return principal.parent / f"{principal.name}_postes"


def refus_hors_poste(racine: Path) -> str | None:
    """Pourquoi un run ne peut pas partir de racine, ou None s'il le peut."""
    commun = _git("rev-parse", "--path-format=absolute", "--git-common-dir", dans=racine)
    if commun.returncode != 0:
        return f"{racine} n'est pas dans un dépôt git"
    principal = Path(commun.stdout.strip()).parent.resolve()
    dossier = racine.resolve()
    if dossier.parent != postes_de(principal).resolve() or dossier.name not in POSTES:
        return (
            f"{dossier} n'est pas un poste de mesure ; un run part de {postes_de(principal)}/api ou /local, "
            "préparé par make poste-mesure POSTE=api ou POSTE=local"
        )
    if _git("status", "--porcelain", dans=dossier).stdout.strip():
        return f"le poste {dossier.name} a des modifications ; un poste ne se modifie pas"
    if _git("merge-base", "--is-ancestor", "HEAD", "main", dans=dossier).returncode != 0:
        commit = _git("rev-parse", "--short", "HEAD", dans=dossier).stdout.strip()
        return f"le commit {commit} du poste {dossier.name} n'est pas dans main"
    return None
