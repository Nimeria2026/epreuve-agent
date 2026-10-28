"""Classement des tâches : ce qui les décrit, pour lire les résultats, jamais pour les noter.

    python -m ease.classement            # le tableau des tâches publiques
    python -m ease.classement --verser   # verse d'abord les durées des runs du poste humain
    python -m ease.classement --estimer  # calcule d'abord les durées estimées par la grille
    python -m ease.classement --jeu dure --cachees --estimer   # la part cachée de la tranche

Cadrage : 00_docs/sources/2026-10-13_cadrage_horizon_de_temps.md, §6 (JOURNAL, cent-vingt-et-unième
entrée). Une fiche par tâche réunit deux sortes d'attributs :

- calculés depuis la tâche, jamais écrits : le métier (famille), les services, plusieurs services
  (trois ou plus), le contrôle grave (gravite.yaml) et les étapes du témoin parfait ;
- écrits dans 07_taches/public/classement.yaml (contrat classement) : les étiquettes de
  difficulté, le type commun d'une tâche du socle commun, la fiche ROME de France Travail et les
  sections du manuel dont la tâche se sert, à la main ; les durées humaines mesurées, que seul
  ce module verse depuis les runs du poste humain (candidats humain_pN), essais réussis
  seulement ; la durée estimée par la grille (ease.grille), que seul ce module calcule depuis un
  run du témoin parfait.

La durée humaine mesurée d'une tâche est la moyenne géométrique de ses durées pour sa version
courante, comme METR le fait pour son horizon de temps. Le poste humain étant en pause, la durée
estimée la remplace en attendant (JOURNAL, cent-vingt-cinquième entrée) : une borne basse, toujours
dite estimée. Le fichier est réécrit d'un bloc à chaque versement ou calcul : ses commentaires ne
sont pas gardés, sauf l'en-tête, que ce module écrit.

Le socle commun (JOURNAL, cent-cinquante-quatrième entrée ; 00_docs/sources/
2026-10-15_cadrage_socle_commun.md) : 07_taches/public/types_communs.yaml (contrat types_communs)
décrit les types de tâches que toute entreprise rencontre ; une tâche du socle d'une société dit
son type dans son classement (type_commun), et chaque type a au moins une tâche dans le socle de
chaque société (SOCLES).

Avec --cachees, le classement de la part cachée d'un jeu (ease.cachees) : prive/classement.yaml
pour le socle, prive/dure/classement.yaml pour la tranche dure, dont le rapport lit les durées
(JOURNAL, cent-soixante-et-onzième entrée), et de même prive/domivelle/ et prive/domivelle/dure/
pour Domivelle (entrée 180), prive/negovelle/ et prive/negovelle/dure/ pour Négovelle (entrée 202).
Sa sortie nomme ces tâches : elle est réservée à une séance qui peut les lire.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from ease.cachees import cachees_du_jeu, dossier_cachees_du_jeu, temoins_caches
from ease.chargement import SOCIETE, ContratInvalide, ecarts_schema, lire_donnees, racine_depot, valider_modele
from ease.contrats.classement import Classement, DureeEstimee, DureeHumaine, FicheRome
from ease.contrats.tache import Tache
from ease.contrats.types_communs import TypesCommuns
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.gravite import Gravite, exposee, lire_gravite
from ease.grille import MANUEL, Appel, estimer
from ease.grille import VERSION as VERSION_GRILLE
from ease.jouet import Actions
from ease.pme import dossier_complement, dossier_version, empreinte_complement
from ease.solutions_dure import SOLUTIONS_DURE
from ease.solutions_pme import SOLUTIONS_PME
from ease.taches import dossier_du_jeu, societe_de, taches_du_jeu

PUBLIC = racine_depot() / "07_taches" / "public"
FICHIER = PUBLIC / "classement.yaml"
RUNS = racine_depot() / "99_local" / "runs"
PREFIXE_HUMAIN = "humain_"
TEMOIN = "temoin_parfait"
SERVICES_POUR_PLUSIEURS = 3

EN_TETE = """\
# Classement des tâches publiques (contrat 01_contrats/classement.schema.json ; JOURNAL, entrées 121,
# 125 et 154). Écrit par ease.classement : make classement VERSER=1 ou ESTIMER=1 réécrit ce fichier
# d'un bloc, sans garder d'autres commentaires que celui-ci. Les étiquettes, le type commun d'une
# tâche du socle commun (07_taches/public/types_communs.yaml), la fiche ROME et les sections du
# manuel s'écrivent à la main ; les durées, jamais : les mesurées viennent des runs du poste
# humain, l'estimée de la grille (ease.grille) sur un run du témoin parfait. Le métier, les
# services, le contrôle grave et les étapes du témoin se calculent depuis la tâche (make classement).
# Fiches ROME : France Travail, ROME 4.0, Licence Ouverte ; on cite le code et l'intitulé.
"""

EN_TETE_CACHEES = """\
# Classement des tâches cachées d'un jeu (contrat 01_contrats/classement.schema.json ; JOURNAL,
# entrées 121, 125 et 171). Hors git, comme elles. Écrit par ease.classement : make classement
# CACHEES=1 VERSER=1 ou ESTIMER=1 réécrit ce fichier d'un bloc, sans garder d'autres commentaires
# que celui-ci. Les étiquettes, la fiche ROME et les sections du manuel s'écrivent à la main ; les
# durées, jamais. Le métier, les services, le contrôle grave et les étapes du témoin se calculent
# depuis la tâche. Fiches ROME : France Travail, ROME 4.0, Licence Ouverte.
"""


def lire_classement(chemin: Path = FICHIER) -> Classement:
    """Lit un classement, ou lève ContratInvalide avec ses écarts."""
    donnees = lire_donnees(chemin)
    erreurs = ecarts_schema("classement", donnees)
    if erreurs:
        raise ContratInvalide(chemin, erreurs)
    return valider_modele(chemin, Classement, donnees)


def ecrire_classement(classement: Classement, chemin: Path = FICHIER, en_tete: str = EN_TETE) -> None:
    """Écrit un classement d'un bloc, après l'avoir vérifié contre son contrat."""
    donnees = classement.model_dump(mode="json", exclude_none=True)
    erreurs = ecarts_schema("classement", donnees)
    if erreurs:
        raise ValueError(f"classement hors de son contrat : {erreurs}")
    texte = yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False, width=100, default_flow_style=None)
    chemin.write_text(en_tete + texte, encoding="utf-8")


def ecarts_classement(classement: Classement, taches: Sequence[Tache]) -> list[str]:
    """Ce qui ne va pas entre un classement et les tâches de son jeu ; liste vide s'il les suit."""
    erreurs: list[str] = []
    versions = {t.identifiant: t.version for t in taches}
    for identifiant in versions.keys() - classement.taches.keys():
        erreurs.append(f"{identifiant} : pas de fiche de classement")
    for identifiant, fiche in sorted(classement.taches.items()):
        if identifiant not in versions:
            erreurs.append(f"{identifiant} : fiche d'une tâche inconnue")
        elif fiche.version_tache != versions[identifiant]:
            erreurs.append(
                f"{identifiant} : fiche de la version {fiche.version_tache}, tâche en version "
                f"{versions[identifiant]} ; relire ses étiquettes, puis noter la version"
            )
        for duree in fiche.durees:
            if duree.personne not in classement.personnes:
                erreurs.append(f"{identifiant} : durée d'une personne non déclarée, {duree.personne}")
        estimee = fiche.duree_estimee
        if identifiant in versions and estimee is not None and not _a_jour(estimee, versions[identifiant]):
            erreurs.append(f"{identifiant} : durée estimée périmée ; make classement ESTIMER=1")
    return sorted(erreurs)


TYPES_COMMUNS = PUBLIC / "types_communs.yaml"

SOCLES: dict[str, Path] = {
    SOCIETE: PUBLIC,
    "domivelle": PUBLIC / "domivelle",
    "negovelle": PUBLIC / "negovelle",
    "gabarit": PUBLIC / "gabarit",
}
"""Le dossier du socle de chaque société, avec son classement.yaml et son gravite.yaml : les
instances des types communs s'y lisent. Une société neuve y ajoute le sien (JOURNAL,
cent-cinquante-quatrième entrée)."""


def lire_types_communs(chemin: Path = TYPES_COMMUNS) -> TypesCommuns:
    """Lit le catalogue du socle commun, ou lève ContratInvalide avec ses écarts."""
    donnees = lire_donnees(chemin)
    erreurs = ecarts_schema("types_communs", donnees)
    if erreurs:
        raise ContratInvalide(chemin, erreurs)
    return valider_modele(chemin, TypesCommuns, donnees)


def socles() -> dict[str, tuple[Classement, Gravite]]:
    """Le classement et les contrôles graves publics du socle de chaque société."""
    # Les catégories de gravité ne se définissent que dans le gravite.yaml de public/ ; le dossier
    # d'une autre société n'apporte que ses contrôles graves.
    return {
        societe: (
            lire_classement(d / "classement.yaml"),
            lire_gravite(PUBLIC) if d == PUBLIC else lire_gravite(PUBLIC, d),
        )
        for societe, d in SOCLES.items()
    }


def instances_des_types(classement: Classement) -> dict[str, list[str]]:
    """Les tâches d'un socle par type commun, d'après leur classement ; une tâche du métier n'a
    pas de type."""
    instances: dict[str, list[str]] = {}
    for identifiant, fiche in sorted(classement.taches.items()):
        if fiche.type_commun is not None:
            instances.setdefault(fiche.type_commun, []).append(identifiant)
    return instances


def ecarts_types_communs(types: TypesCommuns, socles: Mapping[str, tuple[Classement, Gravite]]) -> list[str]:
    """Ce qui ne va pas entre le catalogue et le socle de chaque société ; liste vide si tout
    suit. Un type de catalogue a des catégories de gravité connues et au moins une instance dans
    chaque société ; une instance porte un type du catalogue, et ses contrôles graves restent dans
    les catégories de son type."""
    erreurs: list[str] = []
    for societe, (classement, gravite) in sorted(socles.items()):
        for nom, type_commun in sorted(types.types.items()):
            for categorie in type_commun.gravite:
                if categorie not in gravite.categories:
                    erreurs.append(f"{societe}, {nom} : catégorie de gravité inconnue, {categorie}")
        instances = instances_des_types(classement)
        for nom in sorted(types.types.keys() - instances.keys()):
            erreurs.append(f"{societe}, {nom} : aucune tâche de ce type")
        for nom, identifiants in sorted(instances.items()):
            if nom not in types.types:
                erreurs.append(f"{societe}, {', '.join(identifiants)} : type commun inconnu, {nom}")
                continue
            for identifiant in identifiants:
                hors = sorted(set(gravite.graves.get(identifiant, {}).values()) - set(types.types[nom].gravite))
                if hors:
                    erreurs.append(
                        f"{societe}, {identifiant} : contrôle grave hors de son type {nom}, {', '.join(hors)}"
                    )
    return erreurs


def _a_jour(estimee: DureeEstimee, version_tache: int) -> bool:
    return estimee.version_tache == version_tache and estimee.grille == VERSION_GRILLE


def durees_a_jour(classement: Classement, taches: Sequence[Tache]) -> dict[str, float]:
    """Les durées estimées par la grille, en secondes, des seules tâches dont l'estimation vaut pour
    leur version courante et pour la grille courante ; c'est ce que lit l'horizon de temps."""
    durees: dict[str, float] = {}
    for tache in taches:
        fiche = classement.taches.get(tache.identifiant)
        if fiche is not None and fiche.duree_estimee is not None and _a_jour(fiche.duree_estimee, tache.version):
            durees[tache.identifiant] = fiche.duree_estimee.secondes
    return durees


def moyenne_geometrique(valeurs: Sequence[float]) -> float:
    return math.exp(math.fsum(math.log(v) for v in valeurs) / len(valeurs))


@dataclass(frozen=True)
class FicheComplete:
    """Les attributs d'une tâche, calculés et écrits réunis."""

    identifiant: str
    version: int
    metier: str
    services: tuple[str, ...]
    plusieurs_services: bool
    controle_grave: bool
    etapes_temoin: int | None
    etiquettes: tuple[str, ...]
    rome: FicheRome
    durees_courantes: tuple[float, ...]
    """Les durées, en secondes, des essais réussis sur la version courante de la tâche."""
    duree_estimee_secondes: float | None = None
    """La durée estimée par la grille courante sur la version courante ; None sinon."""

    @property
    def duree_humaine_secondes(self) -> float | None:
        return moyenne_geometrique(self.durees_courantes) if self.durees_courantes else None


def fiches_completes(
    classement: Classement, taches: Sequence[Tache], gravite: Gravite, solutions: Mapping[str, Actions] | None = None
) -> list[FicheComplete]:
    """Une fiche complète par tâche classée, dans l'ordre des tâches ; les étapes du témoin se lisent
    dans solutions (celles des tâches cachées), sinon dans les solutions du socle et de la tranche."""
    fiches: list[FicheComplete] = []
    for tache in taches:
        fiche = classement.taches.get(tache.identifiant)
        if fiche is None:
            continue
        solution = (
            solutions.get(tache.identifiant)
            if solutions is not None
            else SOLUTIONS_PME.get(tache.identifiant) or SOLUTIONS_DURE.get(tache.identifiant)
        )
        fiches.append(
            FicheComplete(
                identifiant=tache.identifiant,
                version=tache.version,
                metier=tache.famille,
                services=tuple(tache.services),
                plusieurs_services=len(tache.services) >= SERVICES_POUR_PLUSIEURS,
                controle_grave=exposee(tache, gravite),
                etapes_temoin=None if solution is None else len(solution),
                etiquettes=tuple(fiche.etiquettes),
                rome=fiche.rome,
                durees_courantes=tuple(d.secondes for d in fiche.durees if d.version_tache == tache.version),
                duree_estimee_secondes=None
                if fiche.duree_estimee is None or not _a_jour(fiche.duree_estimee, tache.version)
                else fiche.duree_estimee.secondes,
            )
        )
    return fiches


def durees_des_runs(dossier_runs: Path, taches: Sequence[Tache]) -> list[tuple[str, DureeHumaine]]:
    """Les essais réussis du poste humain sur les tâches données, avec leur durée chronométrée."""
    connues = {t.identifiant for t in taches}
    mesures: list[tuple[str, DureeHumaine]] = []
    for dossier in sorted(dossier_runs.glob(f"*_{PREFIXE_HUMAIN}p*")):
        fiche = dossier / "fiche_de_run.json"
        if not fiche.is_file():
            continue
        candidat = str(json.loads(fiche.read_text(encoding="utf-8"))["candidat"]["identifiant"])
        if not candidat.startswith(PREFIXE_HUMAIN):
            continue
        personne = candidat.removeprefix(PREFIXE_HUMAIN)
        for chemin in sorted((dossier / "resultats").glob("*.json")):
            resultat = lire_resultat(chemin)
            secondes = resultat.duree_chronometree_secondes
            if not resultat.reussie or secondes is None or resultat.tache.identifiant not in connues:
                continue
            mesures.append(
                (
                    resultat.tache.identifiant,
                    DureeHumaine(
                        personne=personne,
                        secondes=secondes,
                        run=resultat.run,
                        repetition=resultat.repetition,
                        version_tache=resultat.tache.version,
                    ),
                )
            )
    return mesures


def verser(classement: Classement, mesures: Iterable[tuple[str, DureeHumaine]]) -> tuple[Classement, int]:
    """Le classement avec les durées qu'il n'a pas encore ; une durée se reconnaît à sa tâche, son
    run et sa répétition. Une tâche sans fiche est refusée : on la classe d'abord."""
    nouveau = classement.model_copy(deep=True)
    ajoutees = 0
    for identifiant, duree in mesures:
        fiche = nouveau.taches.get(identifiant)
        if fiche is None:
            raise ValueError(f"{identifiant} : pas de fiche de classement où verser sa durée")
        if any((d.run, d.repetition) == (duree.run, duree.repetition) for d in fiche.durees):
            continue
        fiche.durees.append(duree)
        ajoutees += 1
    return nouveau, ajoutees


def texte_du_manuel(tache: Tache) -> str:
    """Le manuel que voit la tâche : celui de son complément s'il en porte un, sinon celui de son
    état initial."""
    societe = societe_de(tache)
    chemins = [dossier_version(tache.etat_initial, societe) / "dossiers" / MANUEL]
    if tache.complement is not None:
        chemins.insert(0, dossier_complement(tache.complement, societe) / "dossiers" / MANUEL)
    return next(c for c in chemins if c.is_file()).read_text(encoding="utf-8")


def chemins_du_temoin(dossier_runs: Path, taches: Sequence[Tache]) -> dict[str, tuple[str, Path]]:
    """Pour chaque tâche, le run du témoin parfait le plus récent qui l'a jouée dans sa version
    courante, avec son complément courant, et le journal de sa première répétition."""
    runs = sorted(dossier_runs.glob(f"*_{TEMOIN}/fiche_de_run.json"), reverse=True)
    trouves: dict[str, tuple[str, Path]] = {}
    for tache in taches:
        complement = None if tache.complement is None else empreinte_complement(tache.complement, societe_de(tache))
        cle = (tache.identifiant, tache.version, complement)
        for chemin_fiche in runs:
            fiche = lire_fiche_de_run(chemin_fiche)
            journal = chemin_fiche.parent / "journaux" / f"{tache.identifiant}_r1.jsonl"
            jouees = {(t.identifiant, t.version, t.empreinte_complement) for t in fiche.jeu_taches.taches}
            if (
                fiche.candidat.identifiant == TEMOIN
                and fiche.statut == "termine"
                and cle in jouees
                and journal.is_file()
            ):
                trouves[tache.identifiant] = (chemin_fiche.parent.name, journal)
                break
    return trouves


def appels_du_journal(journal: Path) -> list[Appel]:
    lignes = [json.loads(ligne) for ligne in journal.read_text(encoding="utf-8").splitlines() if ligne.strip()]
    return [Appel(str(d["outil"]), d.get("arguments") or {}, str(d.get("resultat") or "")) for d in lignes]


def estimer_durees(classement: Classement, taches: Sequence[Tache], dossier_runs: Path) -> tuple[Classement, list[str]]:
    """Le classement avec la durée estimée de chaque tâche qu'un run du témoin parfait couvre, et
    les tâches qu'aucun ne couvre."""
    nouveau = classement.model_copy(deep=True)
    chemins = chemins_du_temoin(dossier_runs, taches)
    manquantes: list[str] = []
    for tache in taches:
        fiche = nouveau.taches.get(tache.identifiant)
        if fiche is None:
            raise ValueError(f"{tache.identifiant} : pas de fiche de classement où écrire sa durée estimée")
        if tache.identifiant not in chemins:
            manquantes.append(tache.identifiant)
            continue
        run, journal = chemins[tache.identifiant]
        parts = estimer(appels_du_journal(journal), texte_du_manuel(tache), fiche.sections_manuel)
        fiche.duree_estimee = DureeEstimee(
            secondes=round(parts.total, 1),
            grille=VERSION_GRILLE,
            version_tache=tache.version,
            run=run,
            lire=round(parts.lire, 1),
            chercher=round(parts.chercher, 1),
            ecrire=round(parts.ecrire, 1),
            agir=round(parts.agir, 1),
        )
    return nouveau, manquantes


def _minutes(secondes: float | None) -> str:
    return "?" if secondes is None else f"{secondes / 60:.1f}".replace(".", ",")


def tableau(fiches: Sequence[FicheComplete]) -> list[str]:
    """Le tableau des fiches, une ligne par tâche, puis les totaux."""
    lignes = [
        "tâche | métier | services | grave | étapes du témoin | étiquettes | ROME | durée humaine, min (essais)"
        " | durée estimée, min"
    ]
    for f in fiches:
        etiquettes = [*f.etiquettes, *(["plusieurs_services"] if f.plusieurs_services else [])]
        lignes.append(
            f"{f.identifiant} | {f.metier} | {len(f.services)} | {'oui' if f.controle_grave else 'non'} | "
            f"{'?' if f.etapes_temoin is None else f.etapes_temoin} | {', '.join(etiquettes) or '-'} | "
            f"{f.rome.code} | {_minutes(f.duree_humaine_secondes)} ({len(f.durees_courantes)})"
            f" | {_minutes(f.duree_estimee_secondes)}"
        )
    mesurees = sum(1 for f in fiches if f.durees_courantes)
    graves = sum(1 for f in fiches if f.controle_grave)
    estimees = sum(1 for f in fiches if f.duree_estimee_secondes is not None)
    lignes.append(
        f"{len(fiches)} tâches, dont {graves} à contrôle grave ; durée humaine mesurée pour {mesurees}, "
        f"estimée par la grille {VERSION_GRILLE} pour {estimees}"
    )
    return lignes


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(
        prog="python -m ease.classement",
        description="Classement des tâches publiques, socle ou tranche dure, par société.",
    )
    analyse.add_argument("--verser", action="store_true", help="verse d'abord les durées des runs du poste humain")
    analyse.add_argument(
        "--estimer",
        action="store_true",
        help="calcule d'abord les durées estimées par la grille, sur le témoin parfait",
    )
    analyse.add_argument(
        "--jeu",
        choices=(
            "public",
            "dure",
            "dure_v2",
            "domivelle",
            "domivelle_dure",
            "domivelle_dure_v2",
            "negovelle",
            "negovelle_dure",
            "negovelle_dure_v2",
            "gabarit",
        ),
        default="public",
        help="le socle de Calorelle, sa tranche dure, ceux de Domivelle, le socle de Négovelle ou la société gabarit, "
        "chacun avec son classement ; les tranches longues de la v2 (dure_v2, domivelle_dure_v2, negovelle_dure_v2) "
        "à part",
    )
    analyse.add_argument(
        "--cachees",
        action="store_true",
        help="la part cachée du jeu (07_taches/prive/), pour une séance qui peut lire ses tâches",
    )
    options = analyse.parse_args(arguments)
    solutions: dict[str, Actions] | None = None
    en_tete = EN_TETE
    if options.cachees:
        cache = dossier_cachees_du_jeu(options.jeu)
        if cache is None:
            print(f"Le jeu {options.jeu} n'a pas de tâches cachées.", file=sys.stderr)
            return 2
        dossier, taches, en_tete = cache, cachees_du_jeu(options.jeu), EN_TETE_CACHEES
        solutions = temoins_caches(cache)[0]
    else:
        dossier, taches = dossier_du_jeu(options.jeu), taches_du_jeu(options.jeu)
    fichier = dossier / "classement.yaml"
    if not fichier.is_file():
        print(
            f"Aucun classement : {fichier.relative_to(racine_depot())} est à écrire, une fiche par tâche.",
            file=sys.stderr,
        )
        return 1
    classement = lire_classement(fichier)
    if options.verser:
        classement, ajoutees = verser(classement, durees_des_runs(RUNS, taches))
        if ajoutees:
            ecrire_classement(classement, fichier, en_tete)
        print(f"Durées versées : {ajoutees} nouvelle(s), depuis {RUNS.relative_to(racine_depot())}.")
    if options.estimer:
        classement, manquantes = estimer_durees(classement, taches, RUNS)
        ecrire_classement(classement, fichier, en_tete)
        print(f"Durées estimées par la grille {VERSION_GRILLE} : {len(taches) - len(manquantes)} tâche(s).")
        if manquantes:
            terrain = ("pme" if options.jeu == "public" else options.jeu) + ("_cachees" if options.cachees else "")
            print(
                f"Sans run du témoin parfait à leur version courante (make temoins TERRAIN={terrain}) : "
                + ", ".join(manquantes),
                file=sys.stderr,
            )
    erreurs = ecarts_classement(classement, taches)
    gravite = lire_gravite(PUBLIC) if dossier == PUBLIC else lire_gravite(PUBLIC, dossier)
    print("\n".join(tableau(fiches_completes(classement, taches, gravite, solutions))))
    if erreurs:
        print("\nÀ reprendre :\n" + "\n".join(f"- {e}" for e in erreurs), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
