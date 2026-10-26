"""Courriels de la messagerie de la PME : lecture et règles hors schéma.

Le serveur messagerie (TypeScript) écrit les courriels dans l'état de la PME ; EASE les relit
pour ses contrôles. Le contrat commun est 01_contrats/courriel.schema.json.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ease.chargement import ContratInvalide, ecarts_schema, lire_donnees, valider_modele
from ease.contrats.courriel import Courriel


def regles_courriel(courriel: Courriel) -> list[str]:
    """Règles que le schéma du courriel ne sait pas exprimer."""
    erreurs: list[str] = []
    for champ, valeur in (("en_reponse_a", courriel.en_reponse_a), ("transfere_de", courriel.transfere_de)):
        if valeur == courriel.identifiant:
            erreurs.append(f"{champ} : un courriel ne peut pas se citer lui-même")
    prefixe = f"pieces/{courriel.identifiant}/"
    for piece in courriel.pieces_jointes:
        if not piece.fichier.startswith(prefixe):
            erreurs.append(f"pieces_jointes : {piece.fichier} doit être rangé sous {prefixe}")
    return erreurs


def lire_courriel(chemin: Path) -> Courriel:
    """Lit un courriel, ou lève ContratInvalide avec tous les écarts."""
    donnees: Any = lire_donnees(chemin)
    erreurs = ecarts_schema("courriel", donnees)
    if erreurs:
        raise ContratInvalide(chemin, erreurs)
    courriel = valider_modele(chemin, Courriel, donnees)
    erreurs = regles_courriel(courriel)
    if erreurs:
        raise ContratInvalide(chemin, erreurs)
    return courriel
