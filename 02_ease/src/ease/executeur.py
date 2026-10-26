"""Exécuteur minimal d'EASE : lance un candidat sur un jeu de tâches, k fois, et écrit le run.

Dossier d'un run, dans 99_local/runs/ par défaut :

    fiche_de_run.json               écrite au début (en cours), réécrite à la fin
    resultats/<tache>_r<k>.json     un résultat d'exécution par tâche et par répétition
    journaux/<tache>_r<k>.jsonl     chaque appel d'outil, dans l'ordre

Le candidat ne reçoit que l'énoncé et les outils (règle 5 du BRIEF). Il n'agit sur
l'environnement qu'à travers Outils, qui compte les étapes, applique le budget et tient le
journal. Chaque fichier est contrôlé contre son contrat avant d'être écrit : le banc ne publie
rien qu'il ne saurait relire.

L'environnement est le jouet de l'étape 1 ou la PME (ease.pme), dont les services sont des
serveurs MCP lancés pour la durée d'une exécution. À l'étape 3, un candidat lancé dans un
processus séparé prendra la même interface Candidat.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from ease.chargement import ecarts_schema, racine_depot
from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import (
    Code,
    Configuration,
    EtatPME,
    FicheDeRun,
    JeuDeTaches,
    JugeDuRun,
    Machine,
    ReferenceCandidat,
    ReglesGardien,
    TacheDuJeu,
)
from ease.contrats.resultat_execution import Jetons, ReferenceTache, ResultatControle, ResultatExecution
from ease.contrats.tache import Tache
from ease.empreintes import empreinte_json
from ease.etat_pme import Instantane
from ease.fiches import regles_fiche_de_run, regles_resultat
from ease.taches import donnees_empreinte, societe_des_taches

type Inconnu = Literal["?"]
type Arret = Literal["termine", "budget_etapes", "budget_cout", "erreur_technique", "contexte_depasse", "delai_depasse"]


class ErreurOutil(Exception):
    """Appel refusé par l'environnement (outil inconnu, argument manquant, fichier absent).

    L'erreur revient à l'agent, comme une réponse d'outil en erreur dans MCP ; l'appel compte
    quand même comme une étape.
    """


class BudgetEtapesDepasse(Exception):
    """Le candidat a tenté un appel d'outil au-delà du budget d'étapes de la tâche."""


class ContexteDepasse(Exception):
    """Le serveur du modèle a refusé une conversation plus longue que son contexte : un échec de
    l'agent, sous un arrêt à part, compté dans le taux (cadrage du 2026-10-14, choix T3). Porte
    la consommation rendue par le candidat jusque-là."""

    def __init__(self, message: str, consommation: Consommation) -> None:
        super().__init__(message)
        self.consommation = consommation


class DelaiDepasse(Exception):
    """Le candidat a dépassé son délai, ou un appel au modèle le sien : un échec de l'agent, sous un
    arrêt à part, compté dans le taux comme le contexte dépassé (cadrage du générateur des images,
    choix D1 ; cadrage du second Qwen local, choix S1). Porte la consommation connue jusque-là."""

    def __init__(self, message: str, consommation: Consommation) -> None:
        super().__init__(message)
        self.consommation = consommation


class ArretDuRun(Exception):
    """Le run entier doit s'arrêter avant l'exécution suivante (heures pleines, par exemple).

    Ce n'est ni un échec de l'agent ni une panne d'une exécution : la fiche de run est notée
    interrompue, avec la raison.
    """


@dataclass(frozen=True)
class DescriptionOutil:
    """Ce que l'agent sait d'un outil : son nom, son rôle, et le schéma JSON de ses arguments."""

    nom: str
    description: str
    schema: Mapping[str, Any]
    lecture_seule: bool | None = None
    """Ce que le service déclare (annotation MCP readOnlyHint) : vrai si l'outil ne fait que lire,
    faux s'il écrit ou envoie, None s'il ne dit rien. Une orchestration s'en sert pour savoir quoi
    faire relire, sans connaître les noms des outils d'une PME."""

    @property
    def parametres(self) -> list[str]:
        """Noms des arguments, dans l'ordre du schéma."""
        proprietes: Mapping[str, Any] = self.schema.get("properties", {})
        return list(proprietes)


class Environnement(Protocol):
    """Le monde où agit le candidat : l'environnement jouet de l'étape 1, ou la PME."""

    @property
    def version(self) -> str: ...

    def empreinte(self) -> str: ...

    @property
    def regles_gardien(self) -> ReglesGardien | None:
        """Les règles du gardien placé devant l'environnement ; None sans gardien."""
        ...

    def empreinte_complement(self, tache: Tache) -> str | None:
        """Empreinte du complément d'état propre à la tâche ; None si elle n'en a pas."""
        ...

    def ouvrir(self, tache: Tache) -> None:
        """Remet l'état à zéro et prépare les services de la tâche, pour la personne servie."""
        ...

    def fermer(self) -> None:
        """Arrête les services ouverts par ouvrir ; sans effet si rien n'est ouvert."""
        ...

    def preambule(self) -> str | None:
        """Ce que l'agent sait avant l'énoncé, lu dans l'état ouvert : la date et l'heure de la
        PME, comme tout employé les connaît. None si l'environnement n'a pas d'horloge."""
        ...

    def outils(self) -> list[DescriptionOutil]: ...

    def appeler(self, nom: str, arguments: Mapping[str, Any], lecture_seule: bool = False) -> Any:
        """lecture_seule : l'appel vient de l'accès en lecture seule ; un service qui a un effet de
        bord en lisant (un courriel marqué lu) s'en abstient alors (MARQUE_LECTURE_SEULE)."""
        ...

    def etat(self) -> Instantane:
        """Instantané de l'état, lu sans passer par les outils de l'agent (règle 3)."""
        ...


class AccesOutils(Protocol):
    """Ce dont Outils a besoin d'un environnement : ses outils et leur appel. Un terrain dont les
    tâches ne suivent pas le contrat de tâche de la PME, comme τ²-bench (ease.terrain_tau2), s'en
    contente ; tout Environnement le fournit."""

    def outils(self) -> list[DescriptionOutil]: ...

    def appeler(self, nom: str, arguments: Mapping[str, Any], lecture_seule: bool = False) -> Any: ...


MARQUE_LECTURE_SEULE = "poa/lecture_seule"
"""Clé posée dans le _meta MCP d'un appel fait par l'accès en lecture seule : le relecteur regarde
sans rien changer, pas même l'indicateur « lu » d'un courriel (JOURNAL, entrée 95)."""

LECTURES_PAR_ETAPE = 3
"""Plafond de l'accès en lecture seule : tant de lectures par étape du budget de la tâche. Un garde-fou
contre une boucle sans fin, pas un budget mesuré (JOURNAL, entrée 94)."""


class Outils:
    """Accès du candidat à l'environnement : compte les étapes, applique le budget, tient le journal.

    Un candidat qui le demande a aussi un accès en lecture seule (lire_avec) : seuls les outils que
    leur service déclare en lecture seule y passent ; ses lectures se comptent à part, hors du
    budget de la tâche, et vont dans un journal à part (<journal>_lectures.jsonl). C'est l'accès du
    relecteur d'auteur et relecteur (JOURNAL, entrée 94)."""

    def __init__(self, environnement: AccesOutils, etapes_max: int, journal: Path) -> None:
        self._environnement = environnement
        self._etapes_max = etapes_max
        self.journal = journal
        self.journal_lectures = journal.with_name(f"{journal.stem}_lectures.jsonl")
        self.etapes = 0
        self.lectures = 0
        self.budget_atteint = False
        """Vrai dès qu'un appel a été refusé faute d'étapes : l'exécution finit en budget_etapes."""

    def lister(self) -> list[DescriptionOutil]:
        """Description des outils disponibles. Ne compte pas comme une étape."""
        return self._environnement.outils()

    def appeler(self, nom: str, **arguments: Any) -> Any:
        """Appelle un outil. Lève BudgetEtapesDepasse au-delà du budget, ErreurOutil si l'appel est refusé."""
        return self.appeler_avec(nom, arguments)

    def appeler_avec(self, nom: str, arguments: Mapping[str, Any]) -> Any:
        """Comme appeler, avec les arguments en dictionnaire : un argument peut alors s'appeler nom."""
        if self.etapes >= self._etapes_max:
            self.budget_atteint = True
            raise BudgetEtapesDepasse(f"budget de {self._etapes_max} étapes atteint")
        self.etapes += 1
        arguments = dict(arguments)
        ligne: dict[str, Any] = {
            "etape": self.etapes,
            "horodatage_utc": maintenant().isoformat().replace("+00:00", "Z"),
            "outil": nom,
            "arguments": arguments,
        }
        try:
            resultat = self._environnement.appeler(nom, arguments)
        except ErreurOutil as erreur:
            self._ecrire(ligne | {"resultat": None, "erreur": str(erreur)})
            raise
        self._ecrire(ligne | {"resultat": resultat, "erreur": None})
        return resultat

    def lister_lectures(self) -> list[DescriptionOutil]:
        """Les seuls outils déclarés en lecture seule. Ne compte pas comme une lecture."""
        return [o for o in self._environnement.outils() if o.lecture_seule is True]

    def lire_avec(self, nom: str, arguments: Mapping[str, Any]) -> Any:
        """Appel par l'accès en lecture seule : refusé pour un outil qui écrit, compté à part. Un
        refus de l'accès (outil qui écrit, plafond atteint) s'écrit aussi au journal des lectures,
        sans numéro de lecture (relecture de la tranche 5, B7)."""
        arguments = dict(arguments)
        ligne: dict[str, Any] = {
            "lecture": None,
            "horodatage_utc": maintenant().isoformat().replace("+00:00", "Z"),
            "outil": nom,
            "arguments": arguments,
        }
        plafond = LECTURES_PAR_ETAPE * self._etapes_max
        refus = (
            f"outil hors de l'accès en lecture seule : {nom}"
            if nom not in {o.nom for o in self.lister_lectures()}
            else f"plafond de {plafond} lectures atteint"
            if self.lectures >= plafond
            else None
        )
        if refus is not None:
            self._ecrire(ligne | {"resultat": None, "erreur": refus}, self.journal_lectures)
            raise ErreurOutil(refus)
        self.lectures += 1
        ligne["lecture"] = self.lectures
        try:
            resultat = self._environnement.appeler(nom, arguments, lecture_seule=True)
        except ErreurOutil as erreur:
            self._ecrire(ligne | {"resultat": None, "erreur": str(erreur)}, self.journal_lectures)
            raise
        self._ecrire(ligne | {"resultat": resultat, "erreur": None}, self.journal_lectures)
        return resultat

    def _ecrire(self, ligne: dict[str, Any], journal: Path | None = None) -> None:
        with (journal or self.journal).open("a", encoding="utf-8") as fichier:
            fichier.write(json.dumps(ligne, ensure_ascii=False, default=str) + "\n")


@dataclass(frozen=True)
class Consommation:
    """Jetons consommés pendant une exécution, par rôle de modèle, par exemple agent ou superviseur.

    Un candidat qui n'appelle aucun modèle, comme un témoin, rend une consommation vide.
    """

    par_role: Mapping[str, Jetons] = field(default_factory=lambda: {})
    energie_wh: float | Inconnu | None = None
    """Énergie de la carte graphique d'un modèle local (ease.energie) ; None sans modèle local."""
    duree_chronometree_secondes: float | None = None
    """Durée chronométrée par un poste humain, de « Commencer » à « J'ai fini » ; None pour un agent."""


class Candidat(Protocol):
    """Ce que l'exécuteur attend d'un candidat."""

    @property
    def fiche(self) -> FicheCandidat: ...

    @property
    def configuration(self) -> Configuration: ...

    @property
    def empreinte_prompts(self) -> str | None: ...

    @property
    def machine(self) -> Machine | None: ...

    def executer(self, enonce: str, outils: Outils) -> Consommation: ...


type Controleur = Callable[[Tache, Instantane, Instantane], list[tuple[float, str | None]]]
"""(tâche, état initial, état final) donne un couple (score, détail) par contrôle de la tâche."""


def enonce_donne(enonce: str, preambule: str | None) -> str:
    """L'énoncé tel que le candidat le reçoit : le préambule de l'environnement, une ligne vide,
    puis l'énoncé de la tâche (JOURNAL, entrée 97)."""
    return enonce if preambule is None else f"{preambule}\n\n{enonce}"


def maintenant() -> datetime:
    """Date et heure courantes, en UTC."""
    return datetime.now(UTC)


def version_code(racine: Path) -> Code:
    """Commit courant et présence de modifications non commitées (fichiers ignorés exclus).

    GIT_OPTIONAL_LOCKS=0 : `git status` ne prend pas le verrou de l'index. Un run lancé pendant un
    commit ne le fait pas échouer, et un processus coupé net ne laisse pas de `.git/index.lock`
    (JOURNAL, soixante-sixième entrée).

    Dans l'image du banc (étape 8), il n'y a pas de dépôt git : le commit vient de
    POA_COMMIT_IMAGE, fixé à la construction, et l'image est faite de l'archive git de ce commit
    (JOURNAL, cent-seizième entrée).
    """
    commit_image = os.environ.get("POA_COMMIT_IMAGE")
    if commit_image and not (racine / ".git").exists():
        return Code(commit=commit_image, modifications_non_commitees=False)
    environnement = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments], cwd=racine, capture_output=True, text=True, check=True, env=environnement
        ).stdout.strip()

    return Code(commit=git("rev-parse", "HEAD"), modifications_non_commitees=bool(git("status", "--porcelain")))


def _jetons_totaux(consommation: Consommation) -> Jetons:
    def somme(valeurs: list[int | Inconnu]) -> int | Inconnu:
        entiers = [v for v in valeurs if isinstance(v, int)]
        return "?" if len(entiers) != len(valeurs) else sum(entiers)

    jetons = list(consommation.par_role.values())
    return Jetons(
        entree=somme([j.entree for j in jetons]),
        entree_en_cache=somme([j.entree_en_cache for j in jetons]),
        sortie=somme([j.sortie for j in jetons]),
    )


def cout_dollars(consommation: Consommation, configuration: Configuration) -> float | Inconnu:
    """Coût d'une exécution aux prix de la fiche de run ; « ? » dès qu'un élément manque, sauf la
    part lue en cache quand elle se paie au prix de l'entrée.

    Un modèle local n'a pas de tarif : son coût reste « ? » tant que l'électricité n'est pas
    mesurée.
    """
    tarifs = {modele.role: modele.tarif for modele in configuration.modeles}
    total = 0.0
    for role, jetons in consommation.par_role.items():
        tarif = tarifs.get(role)
        if tarif is None:
            return "?"
        entree, cache, sortie = jetons.entree, jetons.entree_en_cache, jetons.sortie
        prix_cache = tarif.entree_en_cache_dollars_par_million
        if cache == "?" and prix_cache == tarif.entree_dollars_par_million:
            cache = 0  # sans remise sur le cache, sa part ne change rien au coût (DeepInfra, entrée 120)
        if entree == "?" or cache == "?" or sortie == "?" or (cache > 0 and prix_cache == "?"):
            return "?"
        prix_cache_connu = 0.0 if prix_cache == "?" else prix_cache
        total += (
            (entree - cache) * tarif.entree_dollars_par_million
            + cache * prix_cache_connu
            + sortie * tarif.sortie_dollars_par_million
        ) / 1e6
    return total


def _ecrire_contrat[M: BaseModel](chemin: Path, contrat: str, objet: M, regles: Callable[[M], list[str]]) -> None:
    donnees = objet.model_dump(mode="json")
    erreurs = ecarts_schema(contrat, donnees) + regles(objet)
    if erreurs:
        raise ValueError(f"EASE allait écrire {chemin.name} hors de son contrat : {erreurs}")
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def executer_une_fois(
    candidat: Candidat,
    environnement: Environnement,
    tache: Tache,
    controleur: Controleur,
    run: str,
    repetition: int,
    dossier_run: Path,
) -> ResultatExecution:
    """Une exécution : remise à zéro, passage du candidat, contrôles sur l'état final.

    Les services sont arrêtés avant la lecture de l'état final : plus rien ne peut l'écrire.
    """
    nom = f"{tache.identifiant}_r{repetition}"
    journal = dossier_run / "journaux" / f"{nom}.jsonl"
    journal.touch()
    environnement.ouvrir(tache)
    try:
        etat_initial = environnement.etat()
        outils = Outils(environnement, tache.budget.etapes_max, journal)
        debut, chrono = maintenant(), time.monotonic()
        consommation = Consommation()
        arret: Arret = "termine"
        detail: str | None = None
        try:
            consommation = candidat.executer(enonce_donne(tache.enonce, environnement.preambule()), outils)
        except ArretDuRun:
            raise
        except BudgetEtapesDepasse as erreur:
            arret, detail = "budget_etapes", str(erreur)
        except ContexteDepasse as erreur:
            arret, detail, consommation = "contexte_depasse", str(erreur), erreur.consommation
        except DelaiDepasse as erreur:
            arret, detail, consommation = "delai_depasse", str(erreur), erreur.consommation
        except ErreurOutil as erreur:
            detail = f"l'agent s'est arrêté sur une erreur d'outil : {erreur}"
        except Exception as erreur:  # une panne, pas un échec de l'agent (BRIEF, JOURNAL du 2026-10-05)
            arret, detail = "erreur_technique", f"{type(erreur).__name__} : {erreur}"
        if arret == "termine" and outils.budget_atteint:
            # Un candidat externe ne voit le refus que comme une erreur d'outil ; le relais le note.
            arret, detail = "budget_etapes", f"budget de {tache.budget.etapes_max} étapes atteint"
        duree, fin = time.monotonic() - chrono, maintenant()
    finally:
        environnement.fermer()

    cout = cout_dollars(consommation, candidat.configuration)
    if arret == "termine" and cout != "?" and cout > tache.budget.cout_max_dollars:
        arret, detail = "budget_cout", f"{cout:.6f} $ pour un budget de {tache.budget.cout_max_dollars} $"

    scores = controleur(tache, etat_initial, environnement.etat())
    if len(scores) != len(tache.controles):
        raise ValueError(f"le contrôleur rend {len(scores)} scores pour {len(tache.controles)} contrôles")
    controles = [
        ResultatControle(numero=numero, famille=controle.famille, poids=controle.poids, score=score, detail=texte)
        for numero, (controle, (score, texte)) in enumerate(zip(tache.controles, scores, strict=True), start=1)
    ]
    return ResultatExecution(
        run=run,
        tache=ReferenceTache(identifiant=tache.identifiant, version=tache.version),
        repetition=repetition,
        debut_utc=debut,
        fin_utc=fin,
        arret=arret,
        detail_arret=detail,
        controles=controles,
        score=math.fsum(c.poids * c.score for c in controles),
        reussie=arret == "termine" and all(c.score == 1 for c in controles),
        etapes=outils.etapes,
        jetons=_jetons_totaux(consommation),
        cout_dollars=cout,
        energie_wh=consommation.energie_wh,
        duree_secondes=duree,
        duree_chronometree_secondes=consommation.duree_chronometree_secondes,
        journal=f"journaux/{nom}.jsonl",
    )


def nouveau_dossier_de_run(dossier_runs: Path, candidat: str) -> tuple[datetime, str, Path]:
    """Début, identifiant et dossier d'un run neuf. Le nom tient à la seconde : un second run du
    même candidat lancé dans la même seconde attend la suivante (vu le 2026-10-06 sur une machine
    rapide, deux témoins parfaits enchaînés)."""
    dossier_runs.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        debut = maintenant()
        identifiant = f"{debut:%Y-%m-%d_%H%M%S}_{candidat}"
        dossier = dossier_runs / identifiant
        try:
            dossier.mkdir()
        except FileExistsError:
            time.sleep(1.01 - debut.microsecond / 1_000_000)
            continue
        return debut, identifiant, dossier
    raise RuntimeError(f"aucun nom de run libre pour {candidat} dans {dossier_runs}")


def lancer_run(
    *,
    candidat: Candidat,
    environnement: Environnement,
    taches: list[Tache],
    controleur: Controleur,
    repetitions: int,
    nom_jeu: str,
    dossier_runs: Path | None = None,
    juge: JugeDuRun | None = None,
) -> Path:
    """Lance le candidat sur chaque tâche, repetitions fois, et renvoie le dossier du run.

    juge : le juge que le contrôleur consulte, noté dans la fiche de run ; None sans juge."""
    racine = racine_depot()
    debut, identifiant, dossier = nouveau_dossier_de_run(
        dossier_runs or racine / "99_local" / "runs", candidat.fiche.identifiant
    )
    (dossier / "resultats").mkdir()
    (dossier / "journaux").mkdir()

    fiche = FicheDeRun(
        identifiant=identifiant,
        debut_utc=debut,
        fin_utc=None,
        statut="en_cours",
        raison_interruption=None,
        code=version_code(racine),
        candidat=ReferenceCandidat(identifiant=candidat.fiche.identifiant, version=candidat.fiche.version),
        configuration=candidat.configuration,
        empreinte_prompts=candidat.empreinte_prompts,
        jeu_taches=JeuDeTaches(
            nom=nom_jeu,
            taches=[
                TacheDuJeu(
                    identifiant=t.identifiant,
                    version=t.version,
                    empreinte_complement=environnement.empreinte_complement(t),
                )
                for t in taches
            ],
            empreinte=empreinte_json([donnees_empreinte(t) for t in taches]),
        ),
        etat_pme=EtatPME(
            version=environnement.version,
            empreinte=environnement.empreinte(),
            societe=societe_des_taches(taches),
        ),
        regles_gardien=environnement.regles_gardien,
        repetitions=repetitions,
        machine=candidat.machine,
        juge=juge,
    )
    chemin_fiche = dossier / "fiche_de_run.json"
    _ecrire_contrat(chemin_fiche, "fiche_de_run", fiche, regles_fiche_de_run)
    try:
        for tache in taches:
            for repetition in range(1, repetitions + 1):
                resultat = executer_une_fois(
                    candidat, environnement, tache, controleur, identifiant, repetition, dossier
                )
                chemin = dossier / "resultats" / f"{tache.identifiant}_r{repetition}.json"
                _ecrire_contrat(chemin, "resultat_execution", resultat, regles_resultat)
    except BaseException as interruption:
        raison = f"{type(interruption).__name__} : {interruption}".rstrip(" :")
        fiche = fiche.model_copy(
            update={"statut": "interrompu", "fin_utc": maintenant(), "raison_interruption": raison}
        )
        _ecrire_contrat(chemin_fiche, "fiche_de_run", fiche, regles_fiche_de_run)
        raise
    # La configuration est relue : un candidat externe y note le modèle que l'API a annoncé.
    fiche = fiche.model_copy(
        update={"statut": "termine", "fin_utc": maintenant(), "configuration": candidat.configuration}
    )
    _ecrire_contrat(chemin_fiche, "fiche_de_run", fiche, regles_fiche_de_run)
    return dossier
