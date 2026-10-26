"""Empreintes sha256 des données d'un run : jeu de tâches, état initial, prompts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def empreinte_texte(texte: str) -> str:
    """Empreinte d'un texte, au format « sha256:<64 chiffres hexadécimaux> »."""
    return "sha256:" + hashlib.sha256(texte.encode("utf-8")).hexdigest()


def empreinte_json(donnees: Any) -> str:
    """Empreinte d'une donnée JSON, indépendante de l'ordre des clés et de la mise en forme."""
    return empreinte_texte(json.dumps(donnees, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
