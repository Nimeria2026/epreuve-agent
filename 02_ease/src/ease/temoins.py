"""Les quatre témoins du banc (règle 4 du BRIEF) et la commande make temoins.

Chaque témoin a un comportement connu d'avance, donc un taux de réussite attendu : parfait
100 %, toujours faux 0 %, une fois sur deux 50 %, inerte 0 %. Si le banc mesure autre chose,
c'est le banc qui se trompe.

Les témoins passent sur le jouet de l'étape 1 et sur la PME, où ils agissent par les outils MCP de
ses serveurs comme le ferait un agent : ses tâches publiques, ses tâches cachées, le jeu
« documents » de l'étape 6, dont les tâches déclarent EKE, la tranche dure et sa part cachée. Ils
appartiennent au banc : le parfait et le toujours faux connaissent les gestes de chaque tâche, ce
qu'aucun vrai candidat ne peut faire (règle 5). Ils reconnaissent la tâche à son énoncé, seule
information qu'un candidat reçoit.

Sur la PME, les vérifications juge_requis sont tranchées par le juge rejoué : les verdicts du
juge réel sur les textes des témoins, enregistrés une fois par make verdicts-temoins
(ease.verdicts_temoins) dans 07_taches/public/etalon/verdicts_temoins.json. Aucun appel à l'API.
Tant que ce fichier n'existe pas, ces points sont signalés et ne comptent pas au score.
"""

from __future__ import annotations

import contextlib
import functools
import re
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ease.cachees import (
    cachees_du_jeu,
    dossier_cachees_du_jeu,
    dossier_prive_dure,
    taches_cachees,
    taches_cachees_dure,
    temoins_caches,
)
from ease.candidat_externe import CandidatExterne, Lancement
from ease.chargement import racine_depot
from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import Configuration, Machine
from ease.contrats.tache import Tache
from ease.executeur import Candidat, Consommation, Environnement, Outils, enonce_donne, lancer_run
from ease.fiches import lire_resultat
from ease.jouet import ERREURS_JOUET, SOLUTIONS_JOUET, TACHES_JOUET, Actions, ClasseurJouet
from ease.juge import DU_RUN, Juge, JugeIndisponible, jugement
from ease.pme import EnvironnementPME, etat_des_taches
from ease.solutions_documents import ERREURS_DOCUMENTS, SOLUTIONS_DOCUMENTS
from ease.solutions_domivelle import ERREURS_DOMIVELLE, SOLUTIONS_DOMIVELLE
from ease.solutions_domivelle_dure import ERREURS_DOMIVELLE_DURE, SOLUTIONS_DOMIVELLE_DURE
from ease.solutions_dure import ERREURS_DURE, SOLUTIONS_DURE
from ease.solutions_gabarit import ERREURS_GABARIT, SOLUTIONS_GABARIT
from ease.solutions_negovelle import ERREURS_NEGOVELLE, SOLUTIONS_NEGOVELLE
from ease.solutions_negovelle_dure import ERREURS_NEGOVELLE_DURE, SOLUTIONS_NEGOVELLE_DURE
from ease.solutions_pme import ERREURS_PME, SOLUTIONS_PME, TRICHEURS_PME
from ease.statistiques import Resume, resumer
from ease.taches import (
    lire_taches,
    societe_de,
    taches_documents,
    taches_domivelle,
    taches_domivelle_dure,
    taches_domivelle_dure_v2,
    taches_dure,
    taches_dure_v2,
    taches_gabarit,
    taches_negovelle,
    taches_negovelle_dure,
    taches_negovelle_dure_v2,
)
from ease.temoin_externe import Comportement
from ease.verification import Jugement, verifier

REPETITIONS = 4
"""Nombre pair : le témoin une fois sur deux réussit alors exactement la moitié des exécutions."""

VERDICTS_TEMOINS = racine_depot() / "07_taches" / "public" / "etalon" / "verdicts_temoins.json"
"""Verdicts du juge réel sur les textes des témoins, suivis par git (make verdicts-temoins)."""


def _refuser(_corps: dict[str, Any]) -> dict[str, Any]:
    raise JugeIndisponible(f"verdict absent de {VERDICTS_TEMOINS.name} : relancer make verdicts-temoins")


def juge_rejoue(chemin: Path = VERDICTS_TEMOINS) -> Jugement | None:
    """Le juge rejoué depuis les verdicts gardés des témoins, sans appel à l'API ; None tant que le
    fichier n'existe pas. Un texte sans verdict gardé arrête le run."""
    if not chemin.is_file():
        return None
    return jugement(Juge(_refuser, chemin, (0.0, 0.0, 0.0)))


@dataclass(frozen=True)
class Terrain:
    """Où passent les témoins : un jeu de tâches, son environnement, et les gestes connus d'avance."""

    nom: str
    taches: list[Tache]
    environnement: Callable[[], Environnement]
    solutions: Mapping[str, Actions]
    erreurs: Mapping[str, Actions]

    def __post_init__(self) -> None:
        identifiants = [t.identifiant for t in self.taches]
        if len({t.enonce for t in self.taches}) != len(self.taches):
            raise ValueError(f"terrain {self.nom} : deux tâches ont le même énoncé")
        for table, nom in ((self.solutions, "solution"), (self.erreurs, "erreur")):
            if sorted(table) != sorted(identifiants):
                raise ValueError(f"terrain {self.nom} : une {nom} par tâche, ni plus ni moins")

    def tache(self, enonce: str) -> str:
        """Identifiant de la tâche dont c'est l'énoncé, reçu seul ou après le préambule de
        l'environnement (executeur.enonce_donne)."""
        return next(t.identifiant for t in self.taches if enonce == t.enonce or enonce.endswith(f"\n\n{t.enonce}"))


def terrain_jouet() -> Terrain:
    return Terrain("jouet", TACHES_JOUET, ClasseurJouet, SOLUTIONS_JOUET, ERREURS_JOUET)


def terrain_pme(dossier: Path | None = None, gardien: Path | None = None, version: str = "v3") -> Terrain:
    """La PME dans un état initial et les tâches publiques qui en partent ; l'état de travail va
    dans dossier (99_local/travail/pme sinon). gardien : fichier de règles, pour placer le gardien entre
    les témoins et la PME. Un terrain ne mélange jamais deux états."""
    taches = [t for t in lire_taches(racine_depot() / "07_taches" / "public") if t.etat_initial == version]
    identifiants = {t.identifiant for t in taches}
    solutions = {k: v for k, v in SOLUTIONS_PME.items() if k in identifiants}
    erreurs = {k: v for k, v in ERREURS_PME.items() if k in identifiants}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien)
    return Terrain(f"pme_{version}", taches, environnement, solutions, erreurs)


def terrain_cachees(dossier: Path | None = None, version: str | None = None, gardien: Path | None = None) -> Terrain:
    """Les tâches cachées (ease.cachees) et leurs témoins, rangés hors git, dans l'état de ces tâches
    s'il n'est pas donné ; un terrain vide s'il n'y en a pas. Leurs vérifications n'ont pas de juge.
    gardien : fichier de règles, pour placer le gardien entre les témoins et la PME."""
    cachees = taches_cachees()
    if version is None:
        version = etat_des_taches(cachees) if cachees else "v3"
    taches = [t for t in cachees if t.etat_initial == version]
    solutions, erreurs = temoins_caches()
    identifiants = {t.identifiant for t in taches}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien)
    return Terrain(
        f"pme_cachees_{version}",
        taches,
        environnement,
        {k: v for k, v in solutions.items() if k in identifiants},
        {k: v for k, v in erreurs.items() if k in identifiants},
    )


def terrain_documents(dossier: Path | None = None, gardien: Path | None = None, version: str = "v3") -> Terrain:
    """Le jeu « documents » (étape 6) dans un état initial : ses tâches déclarent EKE, que la PME
    lance pour elles seules."""
    taches = [t for t in taches_documents() if t.etat_initial == version]
    identifiants = {t.identifiant for t in taches}
    solutions = {k: v for k, v in SOLUTIONS_DOCUMENTS.items() if k in identifiants}
    erreurs = {k: v for k, v in ERREURS_DOCUMENTS.items() if k in identifiants}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien)
    return Terrain(f"documents_{version}", taches, environnement, solutions, erreurs)


def _terrain_tranche(
    nom: str, toutes: list[Tache], dossier: Path | None, gardien: Path | None, version: str
) -> Terrain:
    taches = [t for t in toutes if t.etat_initial == version]
    identifiants = {t.identifiant for t in taches}
    solutions = {k: v for k, v in SOLUTIONS_DURE.items() if k in identifiants}
    erreurs = {k: v for k, v in ERREURS_DURE.items() if k in identifiants}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien)
    return Terrain(f"{nom}_{version}", taches, environnement, solutions, erreurs)


def terrain_dure(dossier: Path | None = None, gardien: Path | None = None, version: str = "v3") -> Terrain:
    """La tranche dure dans un état initial (JOURNAL, cent-trentième entrée) : le témoin parfait y
    prouve chaque tâche faisable, et son run donne les durées de la grille."""
    return _terrain_tranche("dure", taches_dure(), dossier, gardien, version)


def terrain_dure_v2(dossier: Path | None = None, gardien: Path | None = None, version: str = "v3") -> Terrain:
    """La tranche longue de la v2 (ease.taches.taches_dure_v2), hors de la v1 : ses gestes sont avec
    ceux de la tranche dure (ease.solutions_dure), et ses témoins tournent dans make tests pour
    qu'elle reste juste jusqu'à la v2 (JOURNAL, entrée 256)."""
    return _terrain_tranche("dure_v2", taches_dure_v2(), dossier, gardien, version)


def terrain_dure_cachees(
    dossier: Path | None = None, version: str | None = None, gardien: Path | None = None
) -> Terrain:
    """La part cachée de la tranche dure (ease.cachees, prive/dure/ ; JOURNAL,
    cent-soixante-et-onzième entrée) et ses témoins, comme terrain_cachees : le témoin parfait y
    prouve chaque tâche faisable, et son run donne leurs durées de la grille (make classement
    JEU=dure CACHEES=1 ESTIMER=1)."""
    cachees = taches_cachees_dure()
    if version is None:
        version = etat_des_taches(cachees) if cachees else "v3"
    taches = [t for t in cachees if t.etat_initial == version]
    solutions, erreurs = temoins_caches(dossier_prive_dure())
    identifiants = {t.identifiant for t in taches}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien)
    return Terrain(
        f"dure_cachees_{version}",
        taches,
        environnement,
        {k: v for k, v in solutions.items() if k in identifiants},
        {k: v for k, v in erreurs.items() if k in identifiants},
    )


def terrain_domivelle(dossier: Path | None = None, gardien: Path | None = None, version: str = "v1") -> Terrain:
    """Le socle de Domivelle, seconde société fictive (ADR 0006 ; JOURNAL, cent-cinquante-cinquième
    entrée), dans son état initial."""
    taches = [t for t in taches_domivelle() if t.etat_initial == version]
    identifiants = {t.identifiant for t in taches}
    solutions = {k: v for k, v in SOLUTIONS_DOMIVELLE.items() if k in identifiants}
    erreurs = {k: v for k, v in ERREURS_DOMIVELLE.items() if k in identifiants}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien, societe="domivelle")
    return Terrain(f"domivelle_{version}", taches, environnement, solutions, erreurs)


def _terrain_tranche_domivelle(
    nom: str, toutes: list[Tache], dossier: Path | None, gardien: Path | None, version: str
) -> Terrain:
    taches = [t for t in toutes if t.etat_initial == version]
    identifiants = {t.identifiant for t in taches}
    solutions = {k: v for k, v in SOLUTIONS_DOMIVELLE_DURE.items() if k in identifiants}
    erreurs = {k: v for k, v in ERREURS_DOMIVELLE_DURE.items() if k in identifiants}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien, societe="domivelle")
    return Terrain(f"{nom}_{version}", taches, environnement, solutions, erreurs)


def terrain_domivelle_dure(dossier: Path | None = None, gardien: Path | None = None, version: str = "v1") -> Terrain:
    """La tranche longue de Domivelle (cadrage du 2026-10-15, section 8) : le témoin parfait y prouve
    chaque tâche faisable, et son run donne les durées de la grille."""
    return _terrain_tranche_domivelle("domivelle_dure", taches_domivelle_dure(), dossier, gardien, version)


def terrain_domivelle_dure_v2(dossier: Path | None = None, gardien: Path | None = None, version: str = "v1") -> Terrain:
    """La tranche longue de la v2 de Domivelle (ease.taches.taches_domivelle_dure_v2), hors de la
    v1 : ses gestes sont avec ceux de sa tranche longue (ease.solutions_domivelle_dure), et ses
    témoins tournent dans make tests pour qu'elle reste juste jusqu'à la v2."""
    return _terrain_tranche_domivelle("domivelle_dure_v2", taches_domivelle_dure_v2(), dossier, gardien, version)


def _terrain_part_cachee(
    jeu: str, societe: str, dossier: Path | None, version: str | None, gardien: Path | None
) -> Terrain:
    """Une part cachée d'une autre société que Calorelle (ease.cachees : domivelle, domivelle_dure,
    negovelle ou negovelle_dure) et ses témoins, comme terrain_cachees ; un terrain vide s'il n'y en
    a pas."""
    cachees = cachees_du_jeu(jeu)
    if version is None:
        version = etat_des_taches(cachees) if cachees else "v1"
    taches = [t for t in cachees if t.etat_initial == version]
    solutions, erreurs = temoins_caches(dossier_cachees_du_jeu(jeu))
    identifiants = {t.identifiant for t in taches}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien, societe=societe)
    return Terrain(
        f"{jeu}_cachees_{version}",
        taches,
        environnement,
        {k: v for k, v in solutions.items() if k in identifiants},
        {k: v for k, v in erreurs.items() if k in identifiants},
    )


def terrain_domivelle_cachees(
    dossier: Path | None = None, version: str | None = None, gardien: Path | None = None
) -> Terrain:
    """La part cachée du socle de Domivelle (prive/domivelle/ ; JOURNAL, cent-quatre-vingtième
    entrée)."""
    return _terrain_part_cachee("domivelle", "domivelle", dossier, version, gardien)


def terrain_domivelle_dure_cachees(
    dossier: Path | None = None, version: str | None = None, gardien: Path | None = None
) -> Terrain:
    """La part cachée de la tranche longue de Domivelle (prive/domivelle/dure/) : son témoin
    parfait donne leurs durées de la grille (make classement JEU=domivelle_dure CACHEES=1
    ESTIMER=1)."""
    return _terrain_part_cachee("domivelle_dure", "domivelle", dossier, version, gardien)


def terrain_negovelle(dossier: Path | None = None, gardien: Path | None = None, version: str = "v1") -> Terrain:
    """Le socle de Négovelle, troisième société fictive (cadrage du 2026-10-17, négoce de gros), dans
    son état initial."""
    taches = [t for t in taches_negovelle() if t.etat_initial == version]
    identifiants = {t.identifiant for t in taches}
    solutions = {k: v for k, v in SOLUTIONS_NEGOVELLE.items() if k in identifiants}
    erreurs = {k: v for k, v in ERREURS_NEGOVELLE.items() if k in identifiants}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien, societe="negovelle")
    return Terrain(f"negovelle_{version}", taches, environnement, solutions, erreurs)


def _terrain_tranche_negovelle(
    nom: str, toutes: list[Tache], dossier: Path | None, gardien: Path | None, version: str
) -> Terrain:
    taches = [t for t in toutes if t.etat_initial == version]
    identifiants = {t.identifiant for t in taches}
    solutions = {k: v for k, v in SOLUTIONS_NEGOVELLE_DURE.items() if k in identifiants}
    erreurs = {k: v for k, v in ERREURS_NEGOVELLE_DURE.items() if k in identifiants}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien, societe="negovelle")
    return Terrain(f"{nom}_{version}", taches, environnement, solutions, erreurs)


def terrain_negovelle_dure(dossier: Path | None = None, gardien: Path | None = None, version: str = "v1") -> Terrain:
    """La tranche longue de Négovelle (cadrage du 2026-10-17, section 8) : le témoin parfait y prouve
    chaque tâche faisable, et son run donne les durées de la grille."""
    return _terrain_tranche_negovelle("negovelle_dure", taches_negovelle_dure(), dossier, gardien, version)


def terrain_negovelle_dure_v2(dossier: Path | None = None, gardien: Path | None = None, version: str = "v1") -> Terrain:
    """La tranche longue de la v2 de Négovelle (ease.taches.taches_negovelle_dure_v2), hors de la
    v1 : ses gestes sont avec ceux de sa tranche longue (ease.solutions_negovelle_dure), et ses
    témoins tournent dans make tests pour qu'elle reste juste jusqu'à la v2."""
    return _terrain_tranche_negovelle("negovelle_dure_v2", taches_negovelle_dure_v2(), dossier, gardien, version)


def terrain_negovelle_cachees(
    dossier: Path | None = None, version: str | None = None, gardien: Path | None = None
) -> Terrain:
    """La part cachée du socle de Négovelle (prive/negovelle/ ; JOURNAL, deux-cent-deuxième entrée)."""
    return _terrain_part_cachee("negovelle", "negovelle", dossier, version, gardien)


def terrain_negovelle_dure_cachees(
    dossier: Path | None = None, version: str | None = None, gardien: Path | None = None
) -> Terrain:
    """La part cachée de la tranche longue de Négovelle (prive/negovelle/dure/) : son témoin parfait
    donne leurs durées de la grille (make classement JEU=negovelle_dure CACHEES=1 ESTIMER=1)."""
    return _terrain_part_cachee("negovelle_dure", "negovelle", dossier, version, gardien)


def terrain_gabarit(dossier: Path | None = None, gardien: Path | None = None, version: str = "v1") -> Terrain:
    """La société gabarit, base des campagnes (cadrage des interventions, section 11) : ses dix
    tâches communes, et celles du métier qu'une campagne ajoute, sur l'état que régénèrent ses
    variables (make gabarit)."""
    taches = [t for t in taches_gabarit() if t.etat_initial == version]
    identifiants = {t.identifiant for t in taches}
    solutions = {k: v for k, v in SOLUTIONS_GABARIT.items() if k in identifiants}
    erreurs = {k: v for k, v in ERREURS_GABARIT.items() if k in identifiants}
    environnement = functools.partial(EnvironnementPME, version, dossier, gardien, societe="gabarit")
    return Terrain(f"gabarit_{version}", taches, environnement, solutions, erreurs)


TERRAINS: dict[str, Callable[[], Terrain]] = {
    "jouet": terrain_jouet,
    "pme": terrain_pme,
    "pme_cachees": terrain_cachees,
    "documents": terrain_documents,
    "dure": terrain_dure,
    "dure_v2": terrain_dure_v2,
    "dure_cachees": terrain_dure_cachees,
    "domivelle": terrain_domivelle,
    "domivelle_dure": terrain_domivelle_dure,
    "domivelle_dure_v2": terrain_domivelle_dure_v2,
    "domivelle_cachees": terrain_domivelle_cachees,
    "domivelle_dure_cachees": terrain_domivelle_dure_cachees,
    "negovelle": terrain_negovelle,
    "negovelle_dure": terrain_negovelle_dure,
    "negovelle_dure_v2": terrain_negovelle_dure_v2,
    "negovelle_cachees": terrain_negovelle_cachees,
    "negovelle_dure_cachees": terrain_negovelle_dure_cachees,
    "gabarit": terrain_gabarit,
}


LIBRES = frozenset({"texte", "commentaire", "objet"})
"""Ce que l'agent écrit de lui-même : le texte d'un courriel, d'un commentaire, un objet."""
CONSTRUITS = frozenset(
    {"du", "au", "debut", "competence", "nature", "statut", "reponse", "nom_fichier", "motif", "etat"}
)
"""Ce que l'agent construit par une règle (une date, le nom d'une facture selon le manuel) ou choisit
dans une liste fermée que décrit l'outil (une compétence, un statut, l'état d'un article retourné)."""
ECRITURES = frozenset({"enregistrer_piece_jointe", "deplacer", "copier"})
"""Les outils dont le dossier est une destination, que le manuel ou le témoin fixe."""
LISTES_FERMEES = frozenset({("lister_courriels", "dossier")})
"""Les arguments qu'un outil choisit dans une liste fermée sous une clé que d'autres outils emploient
autrement : les envoyés ou la réception d'une boîte (ngh13, JOURNAL, entrée 199)."""


def _atomes(valeur: object, cle: str | None = None) -> list[tuple[str | None, str]]:
    """Les valeurs textuelles d'arguments, avec leur clé, hors du texte libre."""
    if isinstance(valeur, dict):
        elements = cast(dict[object, object], valeur)
        return [a for k, v in elements.items() if k not in LIBRES for a in _atomes(v, str(k))]
    if isinstance(valeur, list):
        return [a for v in cast(list[object], valeur) for a in _atomes(v, cle)]
    return [(cle, valeur)] if isinstance(valeur, str) else []


def ce_que_le_temoin_n_a_pas_vu(tache: Tache, actions: Actions, dossier: Path) -> list[str]:
    """Les arguments du témoin parfait que ni l'énoncé ni une sortie d'outil antérieure ne lui ont
    montrés (JOURNAL, entrée 100). Le budget d'une tâche suit les étapes de son témoin : un témoin
    qui sait d'avance un code client, un nom de fichier ou un code du tarif fait un budget trop court.

    L'orientation est donnée d'avance, comme la base de 25 étapes du budget la couvre : la racine des
    dossiers, commun/ et l'annuaire, les boîtes et leurs courriels. Un chemin est vu quand chacune de
    ses parties l'a été. Les nombres (quantités, taux, durées) ne sont pas regardés : trop courts
    pour être cherchés dans les sorties (relecture de la tranche 5, B1). Le témoin joue sur un état
    frais, dans dossier."""
    environnement = EnvironnementPME(tache.etat_initial, dossier, societe=societe_de(tache))
    manquants: list[str] = []
    try:
        environnement.ouvrir(tache)
        vu = enonce_donne(tache.enonce, environnement.preambule())
        orientation: list[tuple[str, dict[str, object]]] = [
            ("lister", {}),
            ("lister", {"dossier": "commun"}),
            ("lire", {"chemin": "commun/annuaire.md"}),
        ]
        if "messagerie" in tache.services:
            boites = str(environnement.appeler("lister_boites", {}))
            orientation += [("lister_courriels", {})]
            orientation += [
                ("lister_courriels", {"boite": b}) for b in re.findall(r"[\w.+-]+@[\w.-]+\.example", boites)
            ]
        for outil, arguments in orientation:
            with contextlib.suppress(Exception):
                vu += "\n" + str(environnement.appeler(outil, arguments))
        for rang, (outil, arguments) in enumerate(actions, start=1):
            for cle, valeur in _atomes(arguments):
                if (
                    cle in CONSTRUITS
                    or cle == "boite"
                    or (cle == "dossier" and outil in ECRITURES)
                    or (outil, cle) in LISTES_FERMEES
                ):
                    continue
                parties = [p for p in valeur.split("/") if p]
                if valeur not in vu and not ("/" in valeur and all(p in vu for p in parties)):
                    manquants.append(f"{rang}:{outil}.{cle}={valeur}")
            vu += "\n" + str(environnement.appeler(outil, arguments))
    finally:
        environnement.fermer()
    return manquants


def fiche_temoin(identifiant: str, nom: str) -> FicheCandidat:
    """Fiche d'un témoin : aucun modèle, jamais classé."""
    return FicheCandidat(
        identifiant=identifiant,
        nom=nom,
        version="1",
        origine="temoin",
        division=None,
        branchement="mcp",
        editeur="Épreuve d'agent",
        url=None,
        modeles=[],
        cout_mesurable=True,
        conditions_utilisation=None,
    )


class Temoin(ABC):
    """Socle commun des témoins : aucun modèle, aucun prompt, aucune machine."""

    identifiant = ""
    nom = ""
    taux_attendu = 0.0

    def __init__(self, terrain: Terrain) -> None:
        self.terrain = terrain

    def _jouer(self, table: Mapping[str, Actions], enonce: str, outils: Outils) -> Consommation:
        for nom, arguments in table[self.terrain.tache(enonce)]:
            outils.appeler(nom, **arguments)
        return Consommation()

    @property
    def fiche(self) -> FicheCandidat:
        return fiche_temoin(self.identifiant, self.nom)

    @property
    def configuration(self) -> Configuration:
        return Configuration(modeles=[])

    @property
    def empreinte_prompts(self) -> str | None:
        return None

    @property
    def machine(self) -> Machine | None:
        return None

    @abstractmethod
    def executer(self, enonce: str, outils: Outils) -> Consommation:
        """Comportement connu du témoin."""


class TemoinParfait(Temoin):
    """Exécute la solution écrite à la main. Attendu : 100 %."""

    identifiant, nom, taux_attendu = "temoin_parfait", "Témoin parfait", 1.0

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        return self._jouer(self.terrain.solutions, enonce, outils)


class TemoinToujoursFaux(Temoin):
    """Joue l'erreur écrite à la main : mauvaise cible, piège où il tombe. Attendu : 0 %."""

    identifiant, nom, taux_attendu = "temoin_toujours_faux", "Témoin toujours faux", 0.0

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        return self._jouer(self.terrain.erreurs, enonce, outils)


class TemoinUneFoisSurDeux(Temoin):
    """Joue la solution à un appel sur deux et ne fait rien à l'autre. Attendu : 50 %."""

    identifiant, nom, taux_attendu = "temoin_une_fois_sur_deux", "Témoin une fois sur deux", 0.5

    def __init__(self, terrain: Terrain) -> None:
        super().__init__(terrain)
        self._appels = 0

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        self._appels += 1
        if self._appels % 2 == 1:
            return self._jouer(self.terrain.solutions, enonce, outils)
        return Consommation()


class TemoinInerte(Temoin):
    """Ne fait rien. Attendu : 0 %, avec un score partiel, puisque rien n'est abîmé."""

    identifiant, nom, taux_attendu = "temoin_inerte", "Témoin inerte", 0.0

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        return Consommation()


class TemoinTricheur(Temoin):
    """Joue une triche écrite à la main (solutions_pme.TRICHEURS_PME). Attendu : 0 %."""

    taux_attendu = 0.0

    def __init__(self, terrain: Terrain, triche: str, table: Mapping[str, Actions]) -> None:
        super().__init__(terrain)
        self.identifiant = f"temoin_tricheur_{triche}"
        self.nom = f"Témoin tricheur ({triche})"
        self._table = table

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        return self._jouer(self._table, enonce, outils)


def tricheur_pme(triche: str, dossier: Path | None = None) -> TemoinTricheur:
    """Un tricheur sur la PME, limité aux tâches que sa triche vise."""
    table = TRICHEURS_PME[triche]
    complet = terrain_pme(dossier)
    taches = [t for t in complet.taches if t.identifiant in table]
    solutions = {t.identifiant: complet.solutions[t.identifiant] for t in taches}
    erreurs = {t.identifiant: complet.erreurs[t.identifiant] for t in taches}
    terrain = Terrain(complet.nom, taches, complet.environnement, solutions, erreurs)
    return TemoinTricheur(terrain, triche, table)


def temoins(terrain: Terrain) -> list[Temoin]:
    return [TemoinParfait(terrain), TemoinToujoursFaux(terrain), TemoinUneFoisSurDeux(terrain), TemoinInerte(terrain)]


def temoin_externe(terrain: str, comportement: Comportement) -> CandidatExterne:
    """Le même témoin, joué depuis un processus séparé par le relais MCP (ease.temoin_externe)."""
    commande = [sys.executable, "-m", "ease.temoin_externe", "--terrain", terrain, "--comportement", comportement]
    return CandidatExterne(
        fiche=fiche_temoin(
            f"temoin_{comportement}_externe", f"Témoin {comportement.replace('_', ' ')}, processus séparé"
        ),
        configuration=Configuration(modeles=[]),
        lancement=Lancement(commande, delai_secondes=120),
    )


def mesurer(
    candidat: Candidat,
    terrain: Terrain,
    dossier_runs: Path | None = None,
    repetitions: int = REPETITIONS,
    juge: Jugement | None = None,
) -> tuple[Path, Resume]:
    """Lance un candidat sur les tâches d'un terrain, puis relit ses résultats depuis le disque."""
    dossier = lancer_run(
        candidat=candidat,
        environnement=terrain.environnement(),
        taches=terrain.taches,
        controleur=verifier if juge is None else functools.partial(verifier, juge=juge),
        repetitions=repetitions,
        nom_jeu=terrain.nom,
        dossier_runs=dossier_runs,
        juge=None if juge is None else DU_RUN,
    )
    resultats = [lire_resultat(chemin) for chemin in sorted((dossier / "resultats").glob("*.json"))]
    return dossier, resumer(resultats)


def passer(
    temoin: Temoin, dossier_runs: Path | None = None, repetitions: int = REPETITIONS, juge: Jugement | None = None
) -> tuple[Path, Resume]:
    """Lance un témoin sur les tâches de son terrain."""
    return mesurer(temoin, temoin.terrain, dossier_runs, repetitions, juge)


def passer_terrain(
    terrain: Terrain, juge: Jugement | None = None, dossier_runs: Path | None = None
) -> list[tuple[Temoin, Path, Resume]]:
    """Passe les témoins d'un terrain ; rend chacun avec le dossier de son run et son résumé."""
    passages: list[tuple[Temoin, Path, Resume]] = []
    for temoin in temoins(terrain):
        dossier, resume = passer(temoin, dossier_runs, juge=juge)
        passages.append((temoin, dossier, resume))
    return passages


def conforme(temoin: Temoin, resume: Resume) -> bool:
    """Si le témoin a le taux qu'on attend de lui : sinon, c'est le banc qui se trompe."""
    return resume.taux == temoin.taux_attendu


def passage_complet(dossier_runs: Path | None = None) -> list[tuple[Temoin, Path, Resume]]:
    """Les témoins sur tous les terrains qui ont des tâches, le juge rejoué sur la PME, comme
    make temoins sans argument : le passage que liste le manifeste d'une publication (cadrage du
    dépôt public et de l'organisation, section 8, règle 3)."""
    juge = juge_rejoue()
    passages: list[tuple[Temoin, Path, Resume]] = []
    for nom, fabrique in TERRAINS.items():
        terrain = fabrique()
        if terrain.taches:
            passages += passer_terrain(terrain, juge if nom == "pme" else None, dossier_runs)
    return passages


def _pourcent(valeur: float) -> str:
    return f"{valeur * 100:.1f}".replace(".", ",").removesuffix(",0") + " %"


def _tableau(terrain: Terrain, juge: Jugement | None = None) -> bool:
    """Passe les quatre témoins sur un terrain et imprime leurs résultats. Vrai si tout est conforme."""
    lignes: list[list[Any]] = []
    tout_conforme = True
    for temoin, dossier, resume in passer_terrain(terrain, juge):
        bas, haut = resume.intervalle
        verdict = "conforme" if conforme(temoin, resume) else "ÉCART"
        tout_conforme &= verdict == "conforme"
        lignes.append(
            [
                temoin.identifiant,
                f"{resume.reussites}/{resume.executions}",
                _pourcent(resume.taux),
                f"{_pourcent(bas)} à {_pourcent(haut)}",
                f"{resume.score_moyen:.2f}".replace(".", ","),
                _pourcent(resume.pass_k[REPETITIONS]),
                _pourcent(temoin.taux_attendu),
                verdict,
                dossier.name,
            ]
        )
    entetes = [
        "témoin",
        "réussites",
        "taux",
        "IC 95 %",
        "score moyen",
        f"pass^{REPETITIONS}",
        "attendu",
        "verdict",
        "dossier du run",
    ]
    largeurs = [max(len(str(ligne[i])) for ligne in [entetes, *lignes]) for i in range(len(entetes))]
    print(f"Terrain {terrain.nom} : {len(terrain.taches)} tâches, {REPETITIONS} répétitions\n")
    for ligne in [entetes, *lignes]:
        print("  ".join(str(cellule).ljust(largeur) for cellule, largeur in zip(ligne, largeurs, strict=True)).rstrip())
    print()
    return tout_conforme


def main(arguments: list[str] | None = None) -> int:
    """Passe les témoins sur les terrains demandés (tous par défaut). Code 1 si un écart."""
    noms = arguments or list(TERRAINS)
    inconnus = [nom for nom in noms if nom not in TERRAINS]
    if inconnus:
        print(f"terrain inconnu : {', '.join(inconnus)} (connus : {', '.join(TERRAINS)})", file=sys.stderr)
        return 2
    print("Témoins du banc, runs dans 99_local/runs/\n")
    juge = juge_rejoue()
    if "pme" in noms:
        print(
            f"Juge sur la PME : rejoué depuis {VERDICTS_TEMOINS.relative_to(racine_depot())}\n"
            if juge is not None
            else "Juge sur la PME : aucun, verdicts des témoins pas encore enregistrés (make verdicts-temoins)\n"
        )
    # Chaque terrain passe, même après un écart. Un terrain sans tâche (pas de tâche cachée) est
    # sauté quand on passe tous les terrains, et compte comme un écart quand on l'a demandé.
    terrains = {nom: TERRAINS[nom]() for nom in noms}
    vides = [n for n, t in terrains.items() if not t.taches]
    for nom in vides:
        print(f"Terrain {nom} : aucune tâche{', sauté' if not arguments else ''}.\n")
    verdicts = [_tableau(t, juge if nom == "pme" else None) for nom, t in terrains.items() if t.taches]
    if arguments and vides:
        verdicts.append(False)
    conforme = all(verdicts)
    print("Le banc mesure ce qu'il doit." if conforme else "ÉCART : le banc ne retrouve pas les taux attendus.")
    return 0 if conforme else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
