"""Les tâches cachées du banc (étape 5, JOURNAL, entrées 80 et 95), rangées hors git dans
07_taches/prive/ :

    07_taches/prive/c01_<nom>.yaml, c02_…        les tâches, au même contrat que les publiques
    07_taches/prive/complements/<nom>/           leurs compléments d'état, au même format
    07_taches/prive/temoins.yaml                 pour chaque tâche, les gestes du témoin parfait
                                                 (solution) et du toujours faux (erreur)
    07_taches/prive/gravite.yaml                 leurs contrôles graves (ease.gravite)

La tranche dure a sa part cachée, à part, dans prive/dure/ (cadrage du 2026-10-14, T6 ; JOURNAL,
cent-soixante-et-onzième entrée), au même format :

    07_taches/prive/dure/hc01_<nom>.yaml, …    une tâche par palier de la grille
    07_taches/prive/dure/temoins.yaml          leurs témoins
    07_taches/prive/dure/gravite.yaml          leurs contrôles graves, s'il y en a
    07_taches/prive/dure/classement.yaml       leur classement, durées de la grille comprises

Leurs compléments d'état vont avec les autres, dans prive/complements/ (ease.chargement).

Domivelle, seconde société (ADR 0006), a ses deux parts cachées dans prive/domivelle/ (cadrage du
2026-10-15, sections 5 et 8 ; JOURNAL, cent-quatre-vingtième entrée), au même format :

    07_taches/prive/domivelle/dvc01_<nom>.yaml, …        le socle, ses témoins, ses contrôles graves
    07_taches/prive/domivelle/dure/dvhc01_<nom>.yaml, …  la tranche longue, deux par palier, ses
                                                         témoins et son classement

Leurs compléments vont dans prive/complements/domivelle/<tâche>/, le sous-dossier de la société
(ease.pme.dossier_complement).

Négovelle, troisième société, a de même ses deux parts cachées dans prive/negovelle/ (cadrage du
2026-10-17, sections 5 et 8 ; JOURNAL, deux-cent-deuxième entrée) :

    07_taches/prive/negovelle/ngc01_<nom>.yaml, …         le socle, ses témoins, ses contrôles graves
    07_taches/prive/negovelle/dure/nghc01_<nom>.yaml, …   la tranche longue, deux par palier, ses
                                                          témoins et son classement

et leurs compléments dans prive/complements/negovelle/<tâche>/.

Claude les écrit dans des séances dédiées, et ne rouvre pas prive/ quand il conçoit une
orchestration. Elles se vérifient par les tests seuls (test_taches_cachees.py), dont les messages
ne citent que des identifiants : aucun contenu ne remonte dans la séance qui lance les tests.
Elles n'ont pas de vérification juge_requis : l'étalonnage du juge demande de lire les textes.

Ce module ne connaît que la forme de ces fichiers, rien de leur contenu.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from ease.chargement import racine_depot
from ease.contrats.tache import Tache
from ease.jouet import Actions
from ease.taches import lire_taches

MOTIF = "c[0-9]*.yaml"
MOTIF_DURE = "hc[0-9]*.yaml"
MOTIF_DOMIVELLE = "dvc[0-9]*.yaml"
MOTIF_DOMIVELLE_DURE = "dvhc[0-9]*.yaml"
MOTIF_NEGOVELLE = "ngc[0-9]*.yaml"
MOTIF_NEGOVELLE_DURE = "nghc[0-9]*.yaml"

PARTS_CACHEES: dict[str, tuple[str, str]] = {
    "public": ("", MOTIF),
    "dure": ("dure", MOTIF_DURE),
    "domivelle": ("domivelle", MOTIF_DOMIVELLE),
    "domivelle_dure": ("domivelle/dure", MOTIF_DOMIVELLE_DURE),
    "negovelle": ("negovelle", MOTIF_NEGOVELLE),
    "negovelle_dure": ("negovelle/dure", MOTIF_NEGOVELLE_DURE),
}
"""Les jeux qui ont une part cachée : son sous-dossier de prive/ et le motif de ses fichiers. Les
autres jeux n'en ont pas."""


def dossier_prive() -> Path:
    return racine_depot() / "07_taches" / "prive"


def dossier_prive_dure() -> Path:
    return dossier_prive() / PARTS_CACHEES["dure"][0]


def taches_cachees(dossier: Path | None = None, motif: str = MOTIF) -> list[Tache]:
    """Les tâches cachées, dans l'ordre de leurs noms ; aucune si prive/ n'existe pas."""
    dossier = dossier or dossier_prive()
    return lire_taches(dossier, motif) if dossier.is_dir() else []


def taches_cachees_dure() -> list[Tache]:
    """La part cachée de la tranche dure ; aucune tant que prive/dure/ n'existe pas."""
    return taches_cachees(dossier_prive_dure(), MOTIF_DURE)


def dossier_cachees_du_jeu(jeu: str) -> Path | None:
    """Le dossier de la part cachée d'un jeu, avec ses témoins et ses contrôles graves ; None pour
    un jeu qui n'en a pas."""
    part = PARTS_CACHEES.get(jeu)
    return None if part is None else dossier_prive() / part[0]


def cachees_du_jeu(jeu: str) -> list[Tache]:
    """Les tâches cachées d'un jeu : celles du socle pour public, celles de la tranche pour dure, et
    de même pour domivelle, domivelle_dure, negovelle et negovelle_dure ; aucune pour un autre jeu."""
    dossier = dossier_cachees_du_jeu(jeu)
    return [] if dossier is None else taches_cachees(dossier, PARTS_CACHEES[jeu][1])


def _actions(valeur: object, ou: str) -> Actions:
    if not isinstance(valeur, list):
        raise ValueError(f"{ou} : une liste de [outil, arguments] est attendue")
    actions: Actions = []
    for rang, geste in enumerate(cast(list[Any], valeur), start=1):
        if not (isinstance(geste, list) and len(cast(list[Any], geste)) == 2):
            raise ValueError(f"{ou}, geste {rang} : [outil, arguments] attendu")
        nom, arguments = cast(list[Any], geste)
        if not isinstance(nom, str) or not isinstance(arguments, dict):
            raise ValueError(f"{ou}, geste {rang} : un nom d'outil et un dictionnaire d'arguments")
        actions.append((nom, cast(dict[str, Any], arguments)))
    return actions


def temoins_caches(dossier: Path | None = None) -> tuple[dict[str, Actions], dict[str, Actions]]:
    """(solutions, erreurs) des tâches cachées, lues dans le temoins.yaml du dossier (prive/ par
    défaut, prive/dure/ pour la tranche) ; vides sans fichier."""
    chemin = (dossier or dossier_prive()) / "temoins.yaml"
    if not chemin.is_file():
        return {}, {}
    donnees: object = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    if not isinstance(donnees, dict):
        raise ValueError("temoins.yaml : un dictionnaire par identifiant de tâche est attendu")
    solutions: dict[str, Actions] = {}
    erreurs: dict[str, Actions] = {}
    for identifiant, gestes in cast(dict[str, Any], donnees).items():
        if not isinstance(gestes, dict) or set(cast(dict[str, Any], gestes)) != {"solution", "erreur"}:
            raise ValueError(f"temoins.yaml, {identifiant} : les clés solution et erreur sont attendues")
        valeurs = cast(dict[str, Any], gestes)
        solutions[identifiant] = _actions(valeurs["solution"], f"temoins.yaml, {identifiant}, solution")
        erreurs[identifiant] = _actions(valeurs["erreur"], f"temoins.yaml, {identifiant}, erreur")
    return solutions, erreurs
