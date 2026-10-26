"""Lecture des fichiers de données et contrôle par les schémas de 01_contrats/.

Chaque contrat se vérifie en trois temps : le schéma JSON (source de vérité), le modèle Pydantic
généré depuis lui, puis les règles que JSON Schema ne sait pas exprimer, propres à chaque
contrat (modules taches et fiches).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from pydantic import BaseModel
from pydantic import ValidationError as ErreurPydantic

from ease.contrats.parametres_societe import ParametresSociete


class ContratInvalide(ValueError):
    """Un fichier ne respecte pas son contrat. Porte la liste complète des écarts."""

    def __init__(self, chemin: Path, erreurs: list[str]) -> None:
        self.chemin = chemin
        self.erreurs = erreurs
        detail = "\n".join(f"  - {erreur}" for erreur in erreurs)
        super().__init__(f"contrat non respecté : {chemin.name}\n{detail}")


def racine_depot() -> Path:
    """Remonte depuis ce fichier jusqu'au dossier qui contient arborescence.toml."""
    for dossier in Path(__file__).resolve().parents:
        if (dossier / "arborescence.toml").is_file():
            return dossier
    raise FileNotFoundError("racine du dépôt introuvable (arborescence.toml absent)")


SOCIETE = "calorelle"
"""La société fictive par défaut : Calorelle, la seule du banc avant la seconde (ADR 0006)."""


def dossier_societe(societe: str = SOCIETE, racine: Path | None = None) -> Path:
    """Dossier des données d'une société fictive, 05_pme/societes/<société>/ (ADR 0006) : ses
    états initiaux (v1, v2, v3) et ses compléments d'état. Seul endroit où s'écrit ce chemin."""
    return (racine or racine_depot()) / "05_pme" / "societes" / societe


def dossier_complements_caches(societe: str = SOCIETE, racine: Path | None = None) -> Path:
    """Dossier des compléments d'état des tâches cachées d'une société, hors git : ceux de
    Calorelle à la racine de 07_taches/prive/complements/, ceux d'une autre société dans un
    sous-dossier à son nom (ADR 0006). Seul endroit où s'écrit ce chemin."""
    base = (racine or racine_depot()) / "07_taches" / "prive" / "complements"
    return base if societe == SOCIETE else base / societe


class _ChargeurSansDates(yaml.SafeLoader):
    """Chargeur YAML qui laisse les dates en texte, comme en JSON : le schéma les vérifie."""


_ChargeurSansDates.yaml_implicit_resolvers = {
    premier: [(etiquette, motif) for etiquette, motif in resolveurs if etiquette != "tag:yaml.org,2002:timestamp"]
    for premier, resolveurs in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def lire_donnees(chemin: Path) -> Any:
    """Lit un fichier JSON ou YAML."""
    texte = chemin.read_text(encoding="utf-8")
    if chemin.suffix == ".json":
        return json.loads(texte)
    return yaml.load(texte, Loader=_ChargeurSansDates)


@cache
def validateur(contrat: str) -> Draft202012Validator:
    """Validateur du schéma 01_contrats/<contrat>.schema.json."""
    chemin = racine_depot() / "01_contrats" / f"{contrat}.schema.json"
    schema = json.loads(chemin.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def ecarts_schema(contrat: str, donnees: Any) -> list[str]:
    """Écarts entre des données et le schéma d'un contrat, triés par emplacement."""
    # Les annotations de jsonschema laissent iter_errors partiellement inconnu : on le type ici.
    iterer: Callable[[Any], Iterator[Any]] = validateur(contrat).iter_errors  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    erreurs: list[ValidationError] = sorted(iterer(donnees), key=lambda e: str(list(e.absolute_path)))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(racine)'} : {e.message}" for e in erreurs]


def ecarts_utc(**horodatages: datetime | None) -> list[str]:
    """Signale les dates qui ne sont pas en UTC."""
    return [
        f"{nom} : {valeur.isoformat()} n'est pas en UTC"
        for nom, valeur in horodatages.items()
        if valeur is not None and valeur.utcoffset() != timedelta(0)
    ]


def valider_modele[M: BaseModel](chemin: Path, modele: type[M], donnees: Any) -> M:
    """Construit le modèle Pydantic ; un refus de Pydantic devient un ContratInvalide détaillé.

    Le schéma JSON est le premier filtre ; celui-ci rattrape ce qu'il laisserait passer.
    """
    try:
        return modele.model_validate(donnees)
    except ErreurPydantic as erreur:
        details = [f"{'/'.join(str(p) for p in e['loc']) or '(racine)'} : {e['msg']}" for e in erreur.errors()]
        raise ContratInvalide(chemin, details) from erreur


FICHIER_PARAMETRES_SOCIETE = Path("entreprise") / "societe.yaml"
"""Paramètres d'une société pour les services communs, relatif à son état (contrat
parametres_societe) ; un état sans ce fichier est celui de Calorelle."""

PARAMETRES_CALORELLE = ParametresSociete(
    nom="Calorelle", domaine="calorelle.example", dossier_fiches_fournisseurs="administration/fournisseurs"
)
"""Les paramètres d'un état sans entreprise/societe.yaml : ceux de Calorelle, dont les états
n'ont pas ce fichier (ADR 0006). Les services TypeScript gardent les mêmes valeurs
(05_pme/commun/src/societe.ts)."""


def parametres_societe(etat: Path) -> ParametresSociete:
    """Les paramètres de la société d'un état : entreprise/societe.yaml, contrôlé par son
    contrat, ou ceux de Calorelle si le fichier manque."""
    chemin = etat / FICHIER_PARAMETRES_SOCIETE
    if not chemin.is_file():
        return PARAMETRES_CALORELLE
    donnees = lire_donnees(chemin)
    erreurs = ecarts_schema("parametres_societe", donnees)
    if erreurs:
        raise ContratInvalide(chemin, erreurs)
    return valider_modele(chemin, ParametresSociete, donnees)
