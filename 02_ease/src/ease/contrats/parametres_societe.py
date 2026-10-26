# Généré depuis 01_contrats/parametres_societe.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ParametresSociete(BaseModel):
    """
    Paramètres d'une société fictive pour les services communs de la PME (ADR 0006), lus dans entreprise/societe.yaml de son état. Un état sans ce fichier est celui de Calorelle : nom Calorelle, domaine calorelle.example, fiches fournisseurs dans administration/fournisseurs, valeurs que gardent les services et EASE quand le fichier manque.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    nom: Annotated[str, Field(min_length=1)]
    """
    Nom de la société, par exemple Domivelle.
    """
    domaine: Annotated[str, Field(pattern="^[a-z0-9-]+(\\.[a-z0-9-]+)*\\.example$")]
    """
    Domaine des adresses du personnel et des boîtes partagées, toujours en .example (RFC 2606) : un courriel vers ce domaine reste dans la société.
    """
    dossier_fiches_fournisseurs: Annotated[
        str, Field(pattern="^[a-z0-9_]+(/[a-z0-9_]+)*$")
    ]
    """
    Dossier, relatif aux dossiers partagés, des fiches que lit et modifie le service des achats : <dossier>/<fournisseur>/fiche_fournisseur.yaml.
    """
