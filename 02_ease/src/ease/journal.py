"""Lecture d'un journal d'exécution dans un terminal : make journal CHEMIN=<fichier ou run>.

Un journal (journaux/<tâche>_r<k>.jsonl) garde chaque appel d'outil de l'agent, une ligne JSON
par appel : complet pour une machine, pénible à lire. Cette commande l'affiche étape par étape,
avec les arguments, le résultat ou le refus, et coupe les résultats longs (--complet pour tout
voir). Avec un dossier de run, elle affiche les journaux dont le nom commence par le motif donné,
par exemple t05, et indique le fichier où un candidat externe a raconté ses tours. Les lectures
faites par l'accès en lecture seule, hors budget (<tâche>_r<k>_lectures.jsonl, le relecteur
d'auteur et relecteur), s'affichent à la suite du journal de leur exécution.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

LIGNES_MAX = 6
"""Lignes de résultat gardées par étape, hors --complet."""

LARGEUR_MAX = 110
"""Caractères gardés par ligne de résultat, hors --complet."""


def _arguments(arguments: Mapping[str, Any]) -> str:
    return ", ".join(f"{cle}={json.dumps(valeur, ensure_ascii=False)}" for cle, valeur in arguments.items())


def _resultat(resultat: Any, complet: bool) -> list[str]:
    texte = resultat if isinstance(resultat, str) else json.dumps(resultat, ensure_ascii=False)
    lignes = texte.splitlines() or ["(vide)"]
    if complet:
        return lignes
    gardees = [ligne if len(ligne) <= LARGEUR_MAX else ligne[:LARGEUR_MAX] + " [coupé]" for ligne in lignes]
    if len(lignes) > LIGNES_MAX:
        gardees = [*gardees[:LIGNES_MAX], f"[{len(lignes) - LIGNES_MAX} lignes de plus, --complet pour tout voir]"]
    return gardees


def lire(chemin: Path, complet: bool = False) -> list[str]:
    """Les lignes à afficher pour un journal, étape par étape."""
    sortie = [f"== {chemin.name}"]
    appels = [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne.strip()]
    if not appels:
        return [*sortie, "aucun appel d'outil : l'agent n'a rien fait", ""]
    for appel in appels:
        if "etape" in appel:
            rang = f"Étape {appel['etape']}"
        else:
            rang = "Lecture refusée" if appel["lecture"] is None else f"Lecture {appel['lecture']}"
        sortie.append(f"{rang}  {appel['outil']}({_arguments(appel['arguments'])})")
        if appel["erreur"] is not None:
            sortie.append(f"  refusé : {appel['erreur']}")
        else:
            premiere, *suite = _resultat(appel["resultat"], complet)
            sortie += [f"  → {premiere}", *(f"    {ligne}" for ligne in suite)]
    return [*sortie, ""]


def journaux(chemin: Path, motif: str = "") -> list[Path]:
    """Un fichier de journal, ou ceux d'un dossier de run dont le nom commence par motif."""
    if chemin.is_file():
        return [chemin]
    dossier = chemin / "journaux" if (chemin / "journaux").is_dir() else chemin
    return sorted(p for p in dossier.glob(f"{motif}*.jsonl") if not p.name.endswith("_lectures.jsonl"))


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m ease.journal", description="Affiche un journal d'exécution.")
    analyse.add_argument("chemin", type=Path, help="fichier .jsonl, ou dossier d'un run")
    analyse.add_argument("motif", nargs="?", default="", help="début du nom des journaux, par exemple t05")
    analyse.add_argument("--complet", action="store_true", help="résultats en entier")
    options = analyse.parse_args(arguments)
    trouves = journaux(options.chemin, options.motif)
    if not trouves:
        print(f"aucun journal trouvé dans {options.chemin} pour « {options.motif} »", file=sys.stderr)
        return 2
    for chemin in trouves:
        print("\n".join(lire(chemin, options.complet)))
        lectures = chemin.with_name(f"{chemin.stem}_lectures.jsonl")
        if lectures.is_file():
            print("Lectures hors budget, par l'accès en lecture seule :")
            print("\n".join(lire(lectures, options.complet)))
        recit = chemin.with_name(f"{chemin.stem}_candidat.log")
        if recit.is_file() and recit.stat().st_size:
            print(f"Ce que le candidat a écrit (raisonnement du modèle compris) : {recit}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
