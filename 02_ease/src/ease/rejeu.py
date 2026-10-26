"""Le rejeu d'un run : les gestes d'un agent, relus dans les journaux d'un run passé, rejoués sans
modèle devant les tâches telles qu'elles sont aujourd'hui (JOURNAL, cent-soixante-septième entrée).

Après un run, une tâche se corrige souvent : un contrôle trop étroit, un manque du manuel. Le rejeu
dit, sans rien payer, ce que la correction change aux verdicts des exécutions déjà faites. Chaque
appel d'outil réussi du journal est refait, dans l'ordre, sur l'état remis à zéro, lectures
comprises (lire un courriel le marque lu) ; puis les contrôles de la version courante de la tâche
notent l'état final. Une tâche dont seuls les contrôles ont changé se juge ainsi entièrement. Une
tâche dont l'énoncé, le complément ou le manuel ont changé, non : l'agent les aurait lus autrement,
et le rejeu ne le dit pas ; la ligne signale le changement de version, le JOURNAL dit lequel.

Les appels refusés pendant le run (outil en erreur, gardien, budget) ne se refont pas : ils n'ont
rien changé. Le gardien n'est donc pas rejoué. Un appel qui réussissait et que l'état d'aujourd'hui
refuse est compté comme divergence. Les lectures de l'accès en lecture seule, sans effet, restent
dans leur journal à part. Le juge n'est appelé qu'avec --juge : il demande la clé de .env, et
coûte, sauf pour un texte déjà jugé sous la même consigne et le même contexte, dont il garde le
verdict. Sans lui, la part jugée d'un contrôle n'est pas évaluée, et la ligne le dit.

Rien ne s'écrit dans 99_local/runs : l'état et les journaux du rejeu vivent dans un dossier
temporaire, et seuls les verdicts s'affichent. Ce ne sont pas des mesures : aucune fiche de run,
et aucun chiffre du rejeu ne va dans un rapport. Les tâches qui ne sont dans aucun jeu public, les
cachées d'abord, ne sont ni ouvertes ni rejouées, seulement comptées.

Depuis la racine du dépôt :

    make rejouer-run CHEMIN=99_local/runs/2026-10-15_204407_agent_seul_deepseek_flash
    make rejouer-run CHEMIN=99_local/runs/<run> TACHES=dvh03,dvh07 JUGE=1
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ease.chargement import racine_depot
from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import Configuration, FicheDeRun, Machine
from ease.contrats.tache import JugeRequis, Tache
from ease.executeur import ArretDuRun, Consommation, Controleur, Environnement, ErreurOutil, Outils, executer_une_fois
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.jouet import Actions
from ease.juge import JugeIndisponible, juge_du_banc, jugement
from ease.pme import EnvironnementPME, etat_des_taches
from ease.taches import JEUX, societe_des_taches, taches_du_jeu
from ease.temoins import fiche_temoin
from ease.verification import verifier

DETAIL_MAX = 220
"""Longueur gardée du détail d'un contrôle manqué, à l'affichage."""


def gestes_du_journal(chemin: Path) -> Actions:
    """Les appels réussis d'un journal d'exécution, dans l'ordre : (outil, arguments)."""
    gestes: Actions = []
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if not ligne.strip():
            continue
        entree: dict[str, Any] = json.loads(ligne)
        if not entree.get("erreur"):
            gestes.append((str(entree["outil"]), dict(entree.get("arguments") or {})))
    return gestes


class Rejoueur:
    """Un candidat sans modèle, qui refait les gestes qu'on lui donne avant chaque exécution."""

    def __init__(self) -> None:
        self.gestes: Actions = []
        self.divergences = 0
        """Appels réussis pendant le run et refusés au rejeu, pour l'exécution en cours."""

    @property
    def fiche(self) -> FicheCandidat:
        return fiche_temoin("rejeu", "Rejeu d'un run passé")

    @property
    def configuration(self) -> Configuration:
        return Configuration(modeles=[])

    @property
    def empreinte_prompts(self) -> str | None:
        return None

    @property
    def machine(self) -> Machine | None:
        return None

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        self.divergences = 0
        for nom, arguments in self.gestes:
            try:
                outils.appeler_avec(nom, arguments)
            except ErreurOutil:
                self.divergences += 1
        return Consommation()


@dataclass(frozen=True)
class Rejouee:
    """Une exécution du run, avant et après le rejeu."""

    tache: str
    repetition: int
    version_run: int
    version_courante: int
    reussie_avant: bool | None
    """None si le run n'a pas gardé le résultat de cette exécution."""
    score_avant: float | None
    reussie_apres: bool
    score_apres: float
    arret_apres: str
    rates: tuple[tuple[int, float, str], ...]
    """Contrôles manqués au rejeu : numéro, score, détail."""
    divergences: int
    juge_absent: bool
    """Vrai si la tâche a une part jugée et que le juge n'a pas été appelé."""

    @property
    def change(self) -> bool:
        return self.reussie_avant is not None and self.reussie_avant != self.reussie_apres


def taches_publiques(racine: Path | None = None) -> dict[str, Tache]:
    """Les tâches de tous les jeux publics, par identifiant, dans leur version courante."""
    taches: dict[str, Tache] = {}
    for jeu in JEUX:
        for tache in taches_du_jeu(jeu, racine):
            ancienne = taches.get(tache.identifiant)
            if ancienne is not None and ancienne != tache:
                raise ValueError(f"deux tâches publiques portent l'identifiant {tache.identifiant}")
            taches[tache.identifiant] = tache
    return taches


def a_un_juge(tache: Tache) -> bool:
    return any(isinstance(v, JugeRequis) for c in tache.controles for v in c.verification)


def taches_rejouables(
    fiche: FicheDeRun, publiques: dict[str, Tache], prefixes: Sequence[str] = ()
) -> tuple[list[tuple[Tache, int]], int]:
    """Les tâches du run qu'un jeu public porte encore, avec leur version au run, et le nombre de
    celles qu'aucun ne porte : cachées ou retirées, elles ne sont pas ouvertes."""
    retenues: list[tuple[Tache, int]] = []
    hors_jeu = 0
    for tache_du_run in fiche.jeu_taches.taches:
        if prefixes and not any(tache_du_run.identifiant.startswith(p) for p in prefixes):
            continue
        tache = publiques.get(tache_du_run.identifiant)
        if tache is None:
            hors_jeu += 1
        else:
            retenues.append((tache, tache_du_run.version))
    return retenues, hors_jeu


def rejouer(
    dossier_run: Path,
    taches: Sequence[tuple[Tache, int]],
    repetitions: int,
    environnement: Environnement,
    controleur: Controleur,
    juge_appele: bool,
) -> list[Rejouee]:
    """Rejoue chaque exécution gardée du run, tâche par tâche puis essai par essai."""
    rejoueur = Rejoueur()
    identifiant_run = dossier_run.name
    lignes: list[Rejouee] = []
    with tempfile.TemporaryDirectory(prefix="rejeu_") as temporaire:
        dossier = Path(temporaire)
        (dossier / "journaux").mkdir()
        for tache, version_run in taches:
            for repetition in range(1, repetitions + 1):
                journal = dossier_run / "journaux" / f"{tache.identifiant}_r{repetition}.jsonl"
                if not journal.is_file():
                    continue
                rejoueur.gestes = gestes_du_journal(journal)
                resultat = executer_une_fois(
                    rejoueur, environnement, tache, controleur, identifiant_run, repetition, dossier
                )
                chemin_avant = dossier_run / "resultats" / f"{tache.identifiant}_r{repetition}.json"
                avant = lire_resultat(chemin_avant) if chemin_avant.is_file() else None
                lignes.append(
                    Rejouee(
                        tache=tache.identifiant,
                        repetition=repetition,
                        version_run=version_run,
                        version_courante=tache.version,
                        reussie_avant=None if avant is None else avant.reussie,
                        score_avant=None if avant is None else avant.score,
                        reussie_apres=resultat.reussie,
                        score_apres=resultat.score,
                        arret_apres=resultat.arret,
                        rates=tuple(
                            (c.numero, c.score, (c.detail or "")[:DETAIL_MAX])
                            for c in resultat.controles
                            if c.score < 1
                        ),
                        divergences=rejoueur.divergences,
                        juge_absent=a_un_juge(tache) and not juge_appele,
                    )
                )
    return lignes


def _verdict(reussie: bool | None, score: float | None) -> str:
    if reussie is None or score is None:
        return "?"
    return f"{'réussite' if reussie else 'échec'} {score:.2f}".replace(".", ",")


def afficher(lignes: Sequence[Rejouee], hors_jeu: int) -> str:
    """Le compte rendu du rejeu, en texte : une ligne par exécution, puis le bilan."""
    sortie: list[str] = []
    for ligne in lignes:
        version = (
            f"v{ligne.version_courante}"
            if ligne.version_run == ligne.version_courante
            else f"v{ligne.version_run} → v{ligne.version_courante}"
        )
        marque = ("CHANGE?" if ligne.juge_absent else "CHANGE ") if ligne.change else "       "
        suite = [
            f"{marque}{ligne.tache} r{ligne.repetition} {version} : "
            f"{_verdict(ligne.reussie_avant, ligne.score_avant)} → "
            f"{_verdict(ligne.reussie_apres, ligne.score_apres)}"
        ]
        if ligne.arret_apres != "termine":
            suite.append(f", arrêt {ligne.arret_apres}")
        if ligne.divergences:
            suite.append(f", {ligne.divergences} appel(s) refusé(s) au rejeu")
        if ligne.juge_absent:
            suite.append(", part jugée non évaluée")
        sortie.append("".join(suite))
        for numero, score, detail in ligne.rates:
            sortie.append(f"           contrôle {numero}, score {score:.2f} : {detail}".replace(".", ",", 1))
    avant = sum(1 for ligne in lignes if ligne.reussie_avant)
    apres = sum(1 for ligne in lignes if ligne.reussie_apres)
    changees = sorted({ligne.tache for ligne in lignes if ligne.change})
    changes = sum(1 for ligne in lignes if ligne.change)
    sans_juge = sorted({ligne.tache for ligne in lignes if ligne.change and ligne.juge_absent})
    sortie.append("")
    sortie.append(
        f"Rejoué : {len(lignes)} exécution(s) de {len({ligne.tache for ligne in lignes})} tâche(s) ; "
        f"réussites {avant} au run, {apres} au rejeu ; verdicts changés : {changes}"
        + (f", dans {len(changees)} tâche(s) ({', '.join(changees)})" if changees else "")
    )
    if any(ligne.juge_absent for ligne in lignes):
        sortie.append("Sans juge : la part jugée des contrôles n'est pas évaluée (JUGE=1 pour l'appeler).")
    if sans_juge:
        sortie.append(f"CHANGE? : verdict changé sans le juge, à confirmer avec JUGE=1 ({', '.join(sans_juge)}).")
    if hors_jeu:
        sortie.append(f"{hors_jeu} tâche(s) du run hors de tout jeu public, ni ouvertes ni rejouées.")
    sortie.append("Pas une mesure : ces verdicts ne vont dans aucun rapport.")
    return "\n".join(sortie)


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(
        prog="python -m ease.rejeu",
        description="Rejoue les gestes d'un run passé devant les tâches telles qu'elles sont aujourd'hui.",
    )
    analyse.add_argument("chemin", type=Path, help="dossier du run, par exemple 99_local/runs/<run>")
    analyse.add_argument("--taches", default="", help="préfixes séparés par des virgules, par exemple dvh03,dvh07")
    analyse.add_argument("--juge", action="store_true", help="appelle le juge du banc (clé dans .env)")
    options = analyse.parse_args(arguments)
    dossier_run: Path = options.chemin.resolve()
    chemin_fiche = dossier_run / "fiche_de_run.json"
    if not chemin_fiche.is_file():
        print(f"Rejeu impossible : {chemin_fiche} introuvable.", file=sys.stderr)
        return 2
    fiche = lire_fiche_de_run(chemin_fiche)
    prefixes = [p for p in options.taches.split(",") if p]
    taches, hors_jeu = taches_rejouables(fiche, taches_publiques(), prefixes)
    if not taches:
        print("Rejeu impossible : aucune tâche du run n'est dans un jeu public.", file=sys.stderr)
        return 2
    seules = [t for t, _ in taches]
    try:
        societe = societe_des_taches(seules)
        version = etat_des_taches(seules)
    except ValueError as erreur:
        print(f"Rejeu impossible : {erreur}.", file=sys.stderr)
        return 2
    controleur: Controleur = verifier
    juge_appele = False
    if options.juge and any(a_un_juge(t) for t in seules):
        try:
            controleur = functools.partial(verifier, juge=jugement(juge_du_banc(racine_depot())))
        except JugeIndisponible as erreur:
            print(f"Rejeu impossible : juge indisponible, {erreur}.", file=sys.stderr)
            return 2
        juge_appele = True
    with tempfile.TemporaryDirectory(prefix="rejeu_pme_") as etat:
        environnement = EnvironnementPME(version, Path(etat) / "pme", societe=societe)
        print(
            f"Rejeu de {fiche.identifiant} : {len(taches)} tâche(s), {fiche.repetitions} essai(s) chacune", flush=True
        )
        try:
            lignes = rejouer(dossier_run, taches, fiche.repetitions, environnement, controleur, juge_appele)
        except ArretDuRun as arret:
            print(f"Rejeu interrompu : {arret}.", file=sys.stderr)
            return 4
    print(afficher(lignes, hors_jeu))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
