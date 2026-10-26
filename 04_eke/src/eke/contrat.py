"""Le contrat de sortie d'EKE, lu dans `01_contrats/lecture_document.schema.json`.

`make contrats` génère le code des contrats dans EASE et la PME, pas dans EKE : EKE valide sa
sortie contre le schéma lui-même, et le déclare comme `outputSchema` de ses outils MCP (journal
de l'étape 6, troisième entrée). Le schéma reste la seule source de vérité.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

NOM = "lecture_document"


class SortieHorsContrat(Exception):
    """EKE allait rendre une sortie que son contrat refuse : une faute d'EKE, pas de l'agent."""


def racine_depot() -> Path:
    """Remonte depuis ce fichier jusqu'au dossier qui contient arborescence.toml."""
    for dossier in Path(__file__).resolve().parents:
        if (dossier / "arborescence.toml").is_file():
            return dossier
    raise FileNotFoundError("racine du dépôt introuvable (arborescence.toml absent)")


@cache
def schema() -> dict[str, Any]:
    chemin = racine_depot() / "01_contrats" / f"{NOM}.schema.json"
    contenu: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(contenu)
    return contenu


def ecarts(sortie: dict[str, Any]) -> list[str]:
    """Les écarts entre une sortie et le contrat ; liste vide si elle est conforme."""
    iterer: Callable[[Any], Iterator[Any]] = Draft202012Validator(schema()).iter_errors  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return [f"{'/'.join(str(p) for p in erreur.path) or '(racine)'} : {erreur.message}" for erreur in iterer(sortie)]


def verifier(sortie: dict[str, Any]) -> dict[str, Any]:
    """La sortie elle-même si elle est conforme ; SortieHorsContrat sinon."""
    trouves = ecarts(sortie)
    if trouves:
        raise SortieHorsContrat("sortie hors contrat : " + " ; ".join(trouves))
    return sortie
