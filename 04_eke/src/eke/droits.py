"""Ce qu'une personne de la PME peut ouvrir par EKE : ce qu'elle ouvre dans les dossiers partagés.

Mêmes règles que les services TypeScript de la PME (`05_pme/commun/src/droits.ts`, `dossiers.ts`
et `chemins.ts`), relues en Python parce qu'EKE ne les importe pas : la personne vient de
`entreprise/organigramme.yaml`, les droits requis par dossier de premier niveau de
`entreprise/acces_dossiers.yaml` ; un dossier absent de cette liste n'est ouvert à personne ; le
mot réservé « tous » l'ouvre à toute personne de l'organigramme. Un chemin donné par l'agent ne
sort jamais des dossiers partagés : ni chemin absolu, ni « .. », ni lien vers l'extérieur.

Le format est celui de la PME du banc, pas de Calorelle : une autre PME écrite sur le même
modèle se lirait de même.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import yaml

TOUT_LE_PERSONNEL = "tous"


class RefusEke(Exception):
    """Un refus à rendre à l'agent tel quel, comme une erreur d'outil MCP."""


@dataclass(frozen=True)
class Personne:
    id: str
    nom: str
    droits: frozenset[str]


def _yaml(chemin: Path) -> Any:
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def _textes(valeur: Any) -> list[str]:
    if not isinstance(valeur, list):
        return []
    return [v for v in cast(list[Any], valeur) if isinstance(v, str)]


def charger_personne(etat: Path, ident: str) -> Personne:
    """La personne de l'organigramme ; ValueError si elle n'y est pas."""
    organigramme = _yaml(etat / "entreprise" / "organigramme.yaml")
    personnes: Any = cast(dict[str, Any], organigramme).get("personnes", []) if isinstance(organigramme, dict) else []
    for personne in cast(list[Any], personnes if isinstance(personnes, list) else []):
        if isinstance(personne, dict):
            fiche = cast(dict[str, Any], personne)
            if fiche.get("id") == ident:
                nom = fiche.get("nom")
                return Personne(ident, nom if isinstance(nom, str) else ident, frozenset(_textes(fiche.get("droits"))))
    raise ValueError(f"personne inconnue dans l'organigramme : {ident}")


def charger_acces(etat: Path) -> dict[str, frozenset[str]]:
    """Droits requis pour chaque dossier de premier niveau."""
    contenu = _yaml(etat / "entreprise" / "acces_dossiers.yaml")
    if not isinstance(contenu, dict):
        return {}
    return {str(dossier): frozenset(_textes(droits)) for dossier, droits in cast(dict[Any, Any], contenu).items()}


@dataclass(frozen=True)
class Dossiers:
    """Les dossiers partagés de l'état de la PME, vus par une personne."""

    racine: Path
    personne: Personne
    acces: dict[str, frozenset[str]]

    @classmethod
    def pour(cls, etat: Path, ident: str) -> Dossiers:
        return cls((etat / "dossiers").resolve(strict=True), charger_personne(etat, ident), charger_acces(etat))

    def ouvre(self, dossier_racine: str) -> bool:
        """Vrai si la personne a au moins un des droits requis ; fermé par défaut."""
        requis = self.acces.get(dossier_racine)
        if requis is None:
            return False
        return TOUT_LE_PERSONNEL in requis or not requis.isdisjoint(self.personne.droits)

    def fichier(self, relatif: str) -> Path:
        """Le chemin absolu d'un fichier donné par l'agent, après le confinement et les droits.

        Le dossier de premier niveau se lit sur le chemin donné, normalisé, et sur celui où mène
        un lien : un lien de `commun/` vers `direction/` n'ouvre pas `direction/`.
        """
        if "\0" in relatif:
            raise RefusEke("chemin invalide")
        if PurePosixPath(relatif).is_absolute() or Path(relatif).is_absolute():
            raise RefusEke(f"chemin absolu refusé : {relatif}")
        lexical = Path(os.path.normpath(self.racine / relatif))
        reel = lexical.resolve()
        for candidat in (lexical, reel):
            if candidat != self.racine and self.racine not in candidat.parents:
                raise RefusEke(f"chemin hors des dossiers partagés : {relatif}")
        for candidat in (lexical, reel):
            parties = candidat.relative_to(self.racine).parts
            if parties and not self.ouvre(parties[0]):
                raise RefusEke(f"accès refusé à {parties[0]}/ pour {self.personne.nom}")
        if not reel.is_file():
            raise RefusEke(f"fichier introuvable : {relatif}")
        return reel
