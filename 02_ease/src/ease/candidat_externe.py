"""Candidat lancé dans son propre processus et branché par le relais MCP d'EASE (règle 6).

Pour chaque exécution, EASE ouvre un relais sur les outils, écrit l'énoncé dans un fichier, et
lance la commande du candidat avec trois arguments de plus :

    --mcp <adresse du relais> --enonce <fichier de l'énoncé> --sortie <fichier de sortie>

Un candidat déclaré avec un accès en lecture seule reçoit en plus `--mcp-lecture <adresse>` : ses
appels y passent hors du budget de la tâche, dans journaux/<tâche>_r<k>_lectures.jsonl.

Le candidat agit par le relais, puis écrit sa sortie (contrat sortie_candidat), qu'il réécrit
après chaque appel de modèle. EASE l'arrête s'il dépasse son délai, ou dès que le budget
d'étapes est épuisé. Ce que le candidat écrit sur ses sorties standard va dans
journaux/<tâche>_r<k>_candidat.log, à côté du journal des appels.

Pour un modèle local, un wattmètre relève l'énergie de la carte graphique pendant l'exécution
(ease.energie). Pour un modèle payé au tarif des heures creuses, le run s'arrête avant une
exécution qui risquerait de déborder sur les heures pleines (ease.creneaux).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ease.chargement import ContratInvalide, racine_depot
from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import Configuration, Machine
from ease.contrats.resultat_execution import Jetons
from ease.contrats.sortie_candidat import SortieCandidat
from ease.creneaux import refus_heures_creuses
from ease.energie import Wattmetre
from ease.executeur import ArretDuRun, Consommation, ContexteDepasse, DelaiDepasse, Outils, maintenant
from ease.fiches import lire_sortie_candidat
from ease.relais import Relais

ARRET_SECONDES = 5.0
"""Après une demande d'arrêt, temps laissé au candidat avant de le tuer."""

type Interruption = Literal["delai", "budget"]
type Creneau = Literal["heures_creuses_deepseek"]


@dataclass(frozen=True)
class Lancement:
    """Comment lancer le candidat : sa commande, son délai, son dossier et ses variables."""

    commande: list[str]
    delai_secondes: float = 1800.0
    repertoire: Path | None = None
    """Dossier de travail ; la racine du dépôt par défaut."""
    variables: Mapping[str, str] = field(default_factory=lambda: {})
    sonde: str | None = None
    """Adresse à interroger avant un run : le serveur d'un modèle local doit y répondre."""
    contexte_serveur: int | None = None
    """Le contexte, en jetons, que le serveur du modèle local doit annoncer : deux candidats sur le même
    modèle, à des contextes différents, ne peuvent pas se confondre (cadrage du second Qwen local)."""
    creneau: Creneau | None = None
    """Heures autorisées par le tarif noté dans la configuration ; None si toutes le sont."""
    wattmetre: list[str] | None = None
    """Commande qui relève la puissance de la carte d'un modèle local (ease.energie) ; None sinon."""
    acces_lecture: bool = False
    """Vrai : le candidat reçoit aussi --mcp-lecture, l'adresse d'un accès en lecture seule dont les
    appels se comptent hors du budget de la tâche (relais, Outils.lire_avec)."""


def _arreter(processus: subprocess.Popen[bytes]) -> None:
    processus.terminate()
    try:
        processus.wait(ARRET_SECONDES)
    except subprocess.TimeoutExpired:
        processus.kill()
        processus.wait()


def _attendre(processus: subprocess.Popen[bytes], outils: Outils, delai: float) -> Interruption | None:
    """Attend la fin du candidat ; l'arrête au-delà du délai ou dès que le budget est épuisé."""
    limite = time.monotonic() + delai
    while processus.poll() is None:
        if outils.budget_atteint:
            _arreter(processus)
            return "budget"
        if time.monotonic() > limite:
            _arreter(processus)
            return "delai"
        time.sleep(0.05)
    return None


class CandidatExterne:
    """Un candidat d'un autre processus : orchestration de 03_orchestrations, ou témoin externe."""

    def __init__(
        self,
        fiche: FicheCandidat,
        configuration: Configuration,
        lancement: Lancement,
        empreinte_prompts: str | None = None,
        machine: Machine | None = None,
    ) -> None:
        self._fiche = fiche
        self._configuration = configuration
        self._lancement = lancement
        self._empreinte_prompts = empreinte_prompts
        self._machine = machine
        self._modeles_vus: dict[str, set[str]] = {}

    @property
    def fiche(self) -> FicheCandidat:
        return self._fiche

    @property
    def configuration(self) -> Configuration:
        """La configuration déclarée, avec le modèle que les API ont annoncé, s'il est connu."""
        modeles = [
            m.model_copy(update={"version_renvoyee": ", ".join(sorted(self._modeles_vus[m.role]))})
            if self._modeles_vus.get(m.role)
            else m
            for m in self._configuration.modeles
        ]
        return self._configuration.model_copy(update={"modeles": modeles})

    @property
    def empreinte_prompts(self) -> str | None:
        return self._empreinte_prompts

    @property
    def machine(self) -> Machine | None:
        return self._machine

    @property
    def lancement(self) -> Lancement:
        return self._lancement

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        lancement = self._lancement
        if lancement.creneau == "heures_creuses_deepseek":
            refus = refus_heures_creuses(maintenant())
            if refus is not None:
                raise ArretDuRun(f"run arrêté avant cette exécution : {refus}")
        log = outils.journal.with_name(f"{outils.journal.stem}_candidat.log")
        wattmetre = None if lancement.wattmetre is None else Wattmetre(lancement.wattmetre)
        with ExitStack() as pile:
            if wattmetre is not None:
                pile.enter_context(wattmetre)
            interruption, processus, sortie, relais = self._lancer(enonce, outils, log)
        energie = None if wattmetre is None else wattmetre.energie_wh
        if relais.panne is not None:
            raise RuntimeError(f"panne de l'environnement : {relais.panne}") from relais.panne
        if interruption == "delai":
            # Un échec de l'agent, plus une panne (choix D1) : la consommation est celle que sa
            # sortie, réécrite pendant l'exécution, disait au moment de l'arrêt.
            raise DelaiDepasse(
                f"candidat arrêté après {lancement.delai_secondes:.0f} s ; voir {log.name}",
                self._consommation(sortie, energie),
            )
        if sortie is not None and sortie.fin == "erreur":
            raise RuntimeError(f"le candidat signale une panne : {sortie.detail}")
        if interruption is None and processus.returncode != 0:
            raise RuntimeError(f"le candidat s'est arrêté avec le code {processus.returncode} ; voir {log.name}")
        if sortie is not None and sortie.fin == "contexte_depasse":
            raise ContexteDepasse(f"contexte du modèle dépassé : {sortie.detail}", self._consommation(sortie, energie))
        if sortie is not None and sortie.fin == "delai_depasse":
            raise DelaiDepasse(
                f"délai d'un appel au modèle dépassé : {sortie.detail}", self._consommation(sortie, energie)
            )
        return self._consommation(sortie, energie)

    def _lancer(
        self, enonce: str, outils: Outils, log: Path
    ) -> tuple[Interruption | None, subprocess.Popen[bytes], SortieCandidat | None, Relais]:
        """Lance le candidat avec son relais, attend sa fin, et lit sa sortie."""
        lancement = self._lancement
        with (
            tempfile.TemporaryDirectory(prefix="poa-candidat-") as dossier,
            Relais(outils, lecture=lancement.acces_lecture) as relais,
        ):
            fichier_enonce, fichier_sortie = Path(dossier) / "enonce.txt", Path(dossier) / "sortie.json"
            fichier_enonce.write_text(enonce, encoding="utf-8")
            commande = [
                *lancement.commande,
                *("--mcp", relais.url, "--enonce", str(fichier_enonce), "--sortie", str(fichier_sortie)),
                *(("--mcp-lecture", relais.url_lecture) if lancement.acces_lecture else ()),
            ]
            with log.open("wb") as flux:
                processus = subprocess.Popen(
                    commande,
                    cwd=lancement.repertoire or racine_depot(),
                    stdout=flux,
                    stderr=subprocess.STDOUT,
                    env=os.environ | dict(lancement.variables),
                )
                interruption = _attendre(processus, outils, lancement.delai_secondes)
            sortie = self._lire_sortie(fichier_sortie)
        return interruption, processus, sortie, relais

    def _lire_sortie(self, chemin: Path) -> SortieCandidat | None:
        if not chemin.exists():
            return None
        try:
            return lire_sortie_candidat(chemin)
        except ContratInvalide:
            return None

    def _consommation(self, sortie: SortieCandidat | None, energie: float | Literal["?"] | None) -> Consommation:
        """Les jetons rendus par le candidat ; « ? » pour chaque rôle déclaré s'il n'a rien rendu."""
        if sortie is None:
            inconnu = Jetons(entree="?", entree_en_cache="?", sortie="?")
            return Consommation({m.role: inconnu for m in self._configuration.modeles}, energie)
        for role, nom in sortie.modeles_renvoyes.items():
            self._modeles_vus.setdefault(role, set()).add(nom)
        jetons = {role: Jetons.model_validate(j.model_dump()) for role, j in sortie.consommation.items()}
        return Consommation(jetons, energie, sortie.duree_chronometree_secondes)
