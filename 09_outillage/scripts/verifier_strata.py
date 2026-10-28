"""Vérifie que Strata servira Flash-Next comme le dit sa fiche officielle (JOURNAL, entrée 296) :
la version du programme, et le préréglage « flash-next » tel que Strata l'exporte, comparé à sa copie
du dépôt, 02_ease/src/ease/moteurs/strata_flash_next.json. Lancé par make strata avant tout plan.

    python3 09_outillage/scripts/verifier_strata.py

Seuls comptent les champs qui changent ce que le moteur fait : l'identité du préréglage, ses choix,
ses réglages, l'issue de son réglage, le moteur et le modèle (leurs empreintes). Les chemins du
dossier personnel s'écrivent « ~ » des deux côtés. Un écart arrête make strata : un préréglage
modifié ou un Strata mis à jour demande une fiche nouvelle, et ses runs ne s'assemblent pas avec les
anciens (le préréglage est dans l'empreinte des deux déclarations de Flash-Next).

Bibliothèque standard seule.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

RACINE = Path(__file__).resolve().parents[2]
REFERENCE = RACINE / "02_ease" / "src" / "ease" / "moteurs" / "strata_flash_next.json"
PRESET = "flash-next"
VERSION = "0.2.4.2"
CHAMPS = (
    ("id",),
    ("name",),
    ("schema",),
    ("choices",),
    ("settings",),
    ("tuner", "mode"),
    ("tuner", "outcome"),
    ("identity", "engine", "version"),
    ("identity", "engine", "build_id"),
    ("identity", "engine", "sha256"),
    ("identity", "model", "bytes"),
    ("identity", "model", "sha256_shard1"),
)
"""Ce que la comparaison regarde ; le reste (mesures, dates de vérification, état actif) varie seul."""


class StrataNonConforme(Exception):
    """Strata ne sert pas Flash-Next comme le dit sa fiche ; le message dit en quoi."""


def normaliser(valeur: object, maison: str = str(Path.home())) -> object:
    """Les chemins du dossier personnel, écrits « ~ », à toute profondeur."""
    if isinstance(valeur, str):
        return "~" + valeur[len(maison) :] if valeur.startswith(maison + "/") else valeur
    if isinstance(valeur, dict):
        return {k: normaliser(v, maison) for k, v in cast(dict[str, object], valeur).items()}
    if isinstance(valeur, list):
        return [normaliser(v, maison) for v in cast(list[object], valeur)]
    return valeur


def _champ(preset: dict[str, Any], chemin: tuple[str, ...]) -> object:
    valeur: object = preset
    for cle in chemin:
        valeur = cast(dict[str, object], valeur).get(cle) if isinstance(valeur, dict) else None
    return valeur


def ecarts(reference: dict[str, Any], vivant: dict[str, Any], maison: str = str(Path.home())) -> list[str]:
    """Les champs qui diffèrent entre la copie du dépôt et le préréglage de Strata."""
    ref, viv = normaliser(reference, maison), normaliser(vivant, maison)
    return [
        ".".join(chemin)
        for chemin in CHAMPS
        if _champ(cast(dict[str, Any], ref), chemin) != _champ(cast(dict[str, Any], viv), chemin)
    ]


def deballer(donnees: object) -> dict[str, Any]:
    """Le préréglage, qu'il soit rendu tel quel ou enveloppé dans un seul champ."""
    if isinstance(donnees, dict):
        dico = cast(dict[str, Any], donnees)
        if "name" not in dico and len(dico) == 1:
            seul = next(iter(dico.values()))
            if isinstance(seul, dict):
                return cast(dict[str, Any], seul)
        return dico
    raise StrataNonConforme("Strata n'a pas rendu de préréglage lisible")


def verifier(strata: str = "strata") -> None:
    sortie = subprocess.run([strata, "--version"], capture_output=True, text=True, check=False)
    mots = sortie.stdout.split()
    version = mots[1] if len(mots) > 1 and mots[0] == "strata" else "?"
    if version != VERSION:
        raise StrataNonConforme(f"Strata {version}, la fiche dit {VERSION}")
    export = subprocess.run(
        [strata, "presets", "export", PRESET, "--output", "json"], capture_output=True, text=True, check=False
    )
    if export.returncode != 0:
        raise StrataNonConforme(f"le préréglage {PRESET} ne s'exporte pas : {export.stderr.strip()}")
    try:
        vivant = deballer(json.loads(export.stdout))
    except json.JSONDecodeError as erreur:
        raise StrataNonConforme(f"l'export du préréglage {PRESET} n'est pas du JSON ({erreur})") from erreur
    reference = cast(dict[str, Any], json.loads(REFERENCE.read_text(encoding="utf-8")))
    differents = ecarts(reference, vivant)
    if differents:
        raise StrataNonConforme(f"le préréglage {PRESET} diffère de sa fiche : {', '.join(differents)}")


def main() -> int:
    try:
        verifier()
    except (StrataNonConforme, OSError) as erreur:
        print(f"REFUS : {erreur}. Fiche : 02_ease/src/ease/moteurs/strata_flash_next.md.", file=sys.stderr)
        return 6
    print(f"Strata {VERSION} et le préréglage {PRESET} : conformes à la fiche.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
