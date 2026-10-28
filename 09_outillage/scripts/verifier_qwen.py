"""Vérifie que make qwen servira Qwen 3.8 27B comme le dit sa fiche officielle
(02_ease/src/ease/moteurs/vllm_qwen_27b.md ; JOURNAL, entrée 301) : les versions des paquets de
l'environnement de vLLM et le modèle, comparés à 02_ease/src/ease/moteurs/vllm_qwen_27b.json.
Lancé par servir_qwen.sh avant de démarrer vLLM.

    python3 09_outillage/scripts/verifier_qwen.py --modele <dossier> --venv <dossier> [--empreintes]

Le modèle : la révision de Hugging Face notée au téléchargement, la taille de chaque fichier, et le
contenu des petits fichiers (configuration, modèle de conversation, jetons), recalculé à chaque
fois. Le contenu des poids (18 Gio) ne se recalcule qu'avec --empreintes, quelques minutes.
L'environnement de vLLM est aussi celui du serveur de Nimeria : une mise à jour faite pour lui
arrête make qwen, jusqu'à une fiche nouvelle.

Bibliothèque standard seule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

RACINE = Path(__file__).resolve().parents[2]
REFERENCE = RACINE / "02_ease" / "src" / "ease" / "moteurs" / "vllm_qwen_27b.json"
POIDS = ".safetensors"
LIRE_VERSIONS = (
    "import importlib.metadata as m, json, sys\n"
    "v = {}\n"
    "for p in sys.argv[1:]:\n"
    "    try:\n"
    "        v[p] = m.version(p)\n"
    "    except m.PackageNotFoundError:\n"
    "        v[p] = None\n"
    "print(json.dumps(v))\n"
)


class QwenNonConforme(Exception):
    """make qwen ne servirait pas Qwen comme le dit sa fiche ; le message dit en quoi."""


def versions_du_venv(venv: Path, paquets: list[str]) -> dict[str, str | None]:
    """Les versions installées dans l'environnement de vLLM, lues sans importer torch."""
    sortie = subprocess.run(
        [str(venv / "bin" / "python"), "-c", LIRE_VERSIONS, *paquets],
        capture_output=True,
        text=True,
        check=False,
    )
    if sortie.returncode != 0:
        raise QwenNonConforme(f"l'environnement {venv} ne dit pas ses versions ({sortie.stderr.strip()})")
    return cast(dict[str, str | None], json.loads(sortie.stdout))


def ecarts_paquets(attendus: dict[str, str], installes: dict[str, str | None]) -> list[str]:
    return [f"{p} {installes.get(p) or 'absent'} (fiche : {v})" for p, v in attendus.items() if installes.get(p) != v]


def _sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _git_sha1(chemin: Path) -> str:
    contenu = chemin.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(contenu) + contenu, usedforsecurity=False).hexdigest()


def ecarts_modele(attendu: dict[str, Any], dossier: Path, empreintes: bool = False) -> list[str]:
    """Ce qui, dans le dossier du modèle, diffère de la fiche."""
    ecarts: list[str] = []
    fichiers = cast(dict[str, dict[str, Any]], attendu["fichiers"])
    for nom, fiche in fichiers.items():
        chemin = dossier / nom
        if not chemin.is_file():
            ecarts.append(f"{nom} absent")
            continue
        meta = dossier / ".cache" / "huggingface" / "download" / f"{nom}.metadata"
        lignes = meta.read_text(encoding="utf-8").split() if meta.is_file() else []
        if not lignes or lignes[0] != attendu["revision"]:
            revision = lignes[0][:8] if lignes else "?"
            ecarts.append(f"{nom} : révision {revision}, la fiche dit {attendu['revision'][:8]}")
        if chemin.stat().st_size != fiche["octets"]:
            ecarts.append(f"{nom} : {chemin.stat().st_size} octets, la fiche en dit {fiche['octets']}")
            continue
        if "git_sha1" in fiche:
            modifie = _git_sha1(chemin) != fiche["git_sha1"]
        else:
            modifie = (empreintes or not nom.endswith(POIDS)) and _sha256(chemin) != fiche["sha256"]
        if modifie:
            ecarts.append(f"{nom} : contenu modifié")
    return ecarts


def verifier(modele: Path, venv: Path, empreintes: bool = False) -> None:
    reference = cast(dict[str, Any], json.loads(REFERENCE.read_text(encoding="utf-8")))
    paquets = cast(dict[str, str], reference["paquets"])
    differents = ecarts_paquets(paquets, versions_du_venv(venv, list(paquets)))
    differents += ecarts_modele(cast(dict[str, Any], reference["modele"]), modele, empreintes)
    if differents:
        raise QwenNonConforme("diffère de sa fiche : " + " ; ".join(differents))


def main(arguments: list[str] | None = None) -> int:
    lecteur = argparse.ArgumentParser(description="Qwen 3.8 27B sous vLLM, comparé à sa fiche.")
    lecteur.add_argument("--modele", type=Path, required=True)
    lecteur.add_argument("--venv", type=Path, required=True)
    lecteur.add_argument("--empreintes", action="store_true", help="recalcule aussi les poids")
    args = lecteur.parse_args(arguments)
    try:
        verifier(args.modele, args.venv, args.empreintes)
    except (QwenNonConforme, OSError, ValueError) as erreur:
        print(f"REFUS : {erreur}. Fiche : 02_ease/src/ease/moteurs/vllm_qwen_27b.md.", file=sys.stderr)
        return 6
    poids = "poids recalculés" if args.empreintes else "poids comparés par leur taille"
    print(f"vLLM et Qwen 3.8 27B : conformes à la fiche ({poids}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
