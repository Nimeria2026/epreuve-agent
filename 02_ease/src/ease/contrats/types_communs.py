# Généré depuis 01_contrats/types_communs.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

type NomType = Annotated[str, Field(pattern="^[a-z][a-z_]*[a-z]$")]


type GraviteItem = Annotated[str, Field(pattern="^[a-z][a-z_]*[a-z]$")]


type OwaspItem = Annotated[str, Field(pattern="^(LLM(0[1-9]|10):2025|ASI(0[1-9]|10))$")]


class TypeCommun(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    titre: Annotated[str, Field(min_length=1)]
    """
    Le type en quelques mots.
    """
    piege: Annotated[str, Field(min_length=1)]
    """
    Ce que la tâche met devant l'agent.
    """
    regle: Annotated[str, Field(min_length=1)]
    """
    La règle que le manuel de toute société porte sous une forme ou une autre.
    """
    gravite: list[GraviteItem]
    """
    Les catégories de contrôle grave de ses instances (gravite.yaml) ; vide pour un type sans contrôle grave.
    """
    owasp: Annotated[list[OwaspItem] | None, Field(min_length=1)] = None
    """
    Les risques de l'OWASP que le type illustre, pour lire les résultats dans une grille publique (JOURNAL, cent-cinquante-sixième entrée) : Top 10 for LLM Applications 2025 (LLM01:2025 à LLM10:2025) et Top 10 for Agentic Applications 2026 (ASI01 à ASI10). Absent pour un type sans risque de sécurité.
    """


class TypesCommuns(BaseModel):
    """
    Le catalogue du socle commun (07_taches/public/types_communs.yaml ; JOURNAL, cent-cinquante-quatrième entrée ; 00_docs/sources/2026-10-15_cadrage_socle_commun.md) : les types de tâches que toute entreprise rencontre, écrits une fois. Chaque société en a au moins une instance, écrite avec ses données et mesurée chez elle ; une tâche dit son type dans son classement (type_commun), et le catalogue ne liste pas les tâches.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Annotated[int, Field(ge=1)]
    """
    Version du catalogue, augmentée à chaque type ajouté, retiré ou redéfini.
    """
    types: Annotated[dict[NomType, TypeCommun], Field(min_length=1)]
    """
    Un type par nom.
    """
