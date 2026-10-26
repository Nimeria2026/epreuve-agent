# Généré depuis 01_contrats/technicien.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

type Competence = Annotated[
    Literal[
        "chaudiere_gaz",
        "chaudiere_fioul",
        "pompe_a_chaleur",
        "climatisation",
        "ventilation",
    ],
    Field(title="Competence"),
]


class Periode(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    debut: AwareDatetime
    fin: AwareDatetime


class Technicien(BaseModel):
    """
    Un technicien de la PME vu par le service de planning (étape 5) : ses compétences, s'il est apprenti, ses périodes d'indisponibilité, sans motif. Une personne de l'organigramme. Données fictives.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(pattern="^[a-z]+\\.[a-z]+$")]
    """
    Identifiant de la personne dans l'organigramme, par exemple thomas.girard.
    """
    nom: Annotated[str, Field(min_length=1)]
    competences: Annotated[list[Competence], Field(min_length=1)]
    apprenti: bool
    """
    Vrai pour un apprenti. Le logiciel le planifie comme les autres ; le manuel dit ce qu'il peut faire seul.
    """
    indisponibilites: list[Periode]
    """
    Périodes où le technicien ne peut pas être planifié, sans motif : congés, arrêts et formations restent au dossier RH.
    """
