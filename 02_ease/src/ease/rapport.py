"""Rapport HTML d'un constat : les candidats déclarés, sur les versions courantes des tâches publiques.

    python -m ease.rapport [--sortie 99_local/rapports/AAAA-MM-JJ_agent_seul.html]

Pour chaque candidat et chaque tâche, le rapport prend les exécutions de la version courante de
la tâche dans le run le plus récent qui les contient toutes, parmi les runs terminés ou
interrompus au nombre de répétitions demandé (5 par défaut) : un essai rapide à une répétition n'y
entre pas, un run en cours non plus, et d'un run interrompu ne comptent que les tâches dont toutes
les répétitions sont faites (JOURNAL, entrée 110). Il refuse d'assembler les
runs d'un candidat dont la configuration, les consignes, la machine, l'état initial de la PME ou
le nombre de répétitions diffèrent. Marges : bootstrap à deux niveaux, taux de réussite compris
(tâches tirées avec remise, puis exécutions tirées avec remise dans chaque tâche), graine fixe,
donc reproductible ; les essais d'une même tâche se ressemblent, Wilson les croirait indépendants
(JOURNAL, cent-vingt-et-unième entrée). Seule la part des fautes graves garde Wilson. Tout chiffre
vient des fichiers des runs ; ce qui manque vaut « ? ».

Le rapport de la tranche dure compte aussi sa part cachée (07_taches/prive/dure/, ease.cachees ;
JOURNAL, cent-soixante-et-onzième entrée) : ses exécutions entrent dans les chiffres, et dans la
courbe de l'horizon quand prive/dure/classement.yaml leur donne une durée à jour. La page ne les
nomme jamais : ni identifiant, ni énoncé, ni lien vers leurs traces ; elles s'y lisent en bloc, et
ce qui leur manque se compte. Le socle garde son rapport des tâches publiques.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import random
import statistics
import sys
import tempfile
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from ease.cachees import cachees_du_jeu, dossier_cachees_du_jeu
from ease.candidats import declarations, lire_candidat
from ease.chargement import SOCIETE, ContratInvalide, parametres_societe, racine_depot
from ease.classement import durees_a_jour, lire_classement
from ease.contrats.fiche_de_run import FicheDeRun
from ease.contrats.resultat_execution import ResultatExecution
from ease.contrats.tache import JugeRequis, Tache
from ease.etat_pme import Instantane, capturer
from ease.fiches import coherence_resultat, lire_fiche_de_run, lire_resultat
from ease.gravite import BilanGrave, Gravite, bilan_grave, exposee, fautes_graves, lire_gravite, numeros_graves
from ease.grille import VERSION as VERSION_GRILLE
from ease.horizon import PENALITE, SEUILS, Point, ajuster, horizon, horizons
from ease.pme import blocages_du_gardien, dossier_version, empreinte_complement, remettre_a_zero
from ease.statistiques import pass_k
from ease.taches import JEUX, dossier_du_jeu, societe_de, societe_des_taches, taches_du_jeu
from ease.verification import verifier

NB = " "
PRIX_KWH_EUROS = 0.2001
PRIX_KWH_SOURCE = (
    "Tarif Bleu d'EDF, option Base 6 kVA, TTC, en vigueur depuis le 1er août 2026 "
    "(00_docs/sources/2026-10-05_prix_electricite.md)"
)
TIRAGES = 10_000
GRAINE = 20261005


class RapportImpossible(Exception):
    """Les runs ne permettent pas un rapport honnête ; le message dit pourquoi."""


@dataclass(frozen=True)
class Run:
    dossier: Path
    fiche: FicheDeRun


@dataclass(frozen=True)
class Mesures:
    """Les exécutions retenues d'un candidat, tâche par tâche, et les runs d'où elles viennent."""

    identifiant: str
    nom: str
    executions: dict[str, list[ResultatExecution]]
    """Par identifiant de tâche, les exécutions retenues, dans l'ordre des répétitions."""
    sources: dict[str, Run]
    manquantes: list[str]


# ------------------------------------------------------------------ choix des exécutions


REPETITIONS = 5


def runs_retenus(
    identifiant: str, dossier_runs: Path, repetitions: int = REPETITIONS, gardien: bool = False
) -> list[Run]:
    """Runs terminés ou interrompus d'un candidat au nombre de répétitions donné, du plus récent au
    plus ancien ; avec gardien ou sans, selon gardien : les deux ne se mélangent jamais. Un run en
    cours n'y est pas ; d'un run interrompu, _executions ne prend que les tâches complètes."""
    runs = [Run(c.parent, lire_fiche_de_run(c)) for c in dossier_runs.glob(f"*_{identifiant}/fiche_de_run.json")]
    retenus = [
        r
        for r in runs
        if r.fiche.candidat.identifiant == identifiant
        and r.fiche.statut in ("termine", "interrompu")
        and r.fiche.repetitions == repetitions
        and (r.fiche.regles_gardien is not None) == gardien
    ]
    return sorted(retenus, key=lambda r: r.fiche.debut_utc, reverse=True)


def _executions(run: Run, tache: Tache, cachee: bool = False) -> list[ResultatExecution] | None:
    """Les exécutions de la version courante de la tâche dans ce run, si elles y sont toutes ; une
    tâche à complément d'état demande aussi le même complément, à l'empreinte près. Une tâche
    cachée n'est pas nommée dans l'erreur."""
    complement = None if tache.complement is None else empreinte_complement(tache.complement, societe_de(tache))
    cle = (tache.identifiant, tache.version, complement)
    if all((t.identifiant, t.version, t.empreinte_complement) != cle for t in run.fiche.jeu_taches.taches):
        return None
    repetitions = range(1, run.fiche.repetitions + 1)
    chemins = [run.dossier / "resultats" / f"{tache.identifiant}_r{i}.json" for i in repetitions]
    if not all(c.is_file() for c in chemins):
        return None
    resultats = [lire_resultat(c) for c in chemins]
    ecarts = [e for r in resultats for e in coherence_resultat(r, tache)]
    if ecarts:
        if cachee:
            raise RapportImpossible(f"{run.dossier.name}, une tâche cachée : résultats incohérents avec elle")
        raise RapportImpossible(f"{run.dossier.name}, {tache.identifiant} : {' ; '.join(ecarts)}")
    return resultats


def _demande_un_juge(tache: Tache) -> bool:
    return any(isinstance(v, JugeRequis) for c in tache.controles for v in c.verification)


def _etat_pme(fiche: FicheDeRun) -> dict[str, object]:
    """L'état initial de la PME d'un run. Une fiche sans société est de Calorelle : le champ n'existe
    que depuis la seconde société (ADR 0006), et le contrat de la fiche le dit absent des fiches
    d'avant (JOURNAL, cent-soixante-neuvième entrée)."""
    etat = fiche.etat_pme.model_dump(mode="json")
    if etat.get("societe") is None:
        etat["societe"] = SOCIETE
    return etat


def _signature(fiche: FicheDeRun) -> dict[str, object]:
    """Ce qui doit être identique entre les runs assemblés d'un même candidat. Le juge n'y est
    pas : un run sans tâche à juge n'en a pas, et il se compare à part (rassembler)."""
    modeles = [m.model_dump(mode="json", exclude={"version_renvoyee"}) for m in fiche.configuration.modeles]
    return {
        "configuration": modeles,
        "consignes": fiche.empreinte_prompts,
        "machine": None if fiche.machine is None else fiche.machine.model_dump(mode="json"),
        "état initial de la PME": _etat_pme(fiche),
        "répétitions": fiche.repetitions,
        "règles du gardien": None if fiche.regles_gardien is None else fiche.regles_gardien.model_dump(mode="json"),
    }


def rassembler(
    identifiant: str,
    nom: str,
    taches: list[Tache],
    dossier_runs: Path,
    repetitions: int = REPETITIONS,
    gardien: bool = False,
    cachees: Collection[str] = (),
) -> Mesures:
    """Les exécutions d'un candidat sur les versions courantes des tâches, run le plus récent d'abord ;
    celles de cachees ne sont pas nommées dans une erreur."""
    runs = runs_retenus(identifiant, dossier_runs, repetitions, gardien)
    executions: dict[str, list[ResultatExecution]] = {}
    sources: dict[str, Run] = {}
    manquantes: list[str] = []
    for tache in taches:
        for run in runs:
            trouvees = _executions(run, tache, tache.identifiant in cachees)
            if trouvees is not None:
                executions[tache.identifiant], sources[tache.identifiant] = trouvees, run
                break
        else:
            manquantes.append(tache.identifiant)
    # Le juge ne compte que pour les tâches qui en demandent un, et il doit être le même pour toutes.
    juges: dict[str, str | None] = {}
    for tache in taches:
        run = sources.get(tache.identifiant)
        if run is not None and _demande_un_juge(tache):
            juges[run.dossier.name] = None if run.fiche.juge is None else run.fiche.juge.model_dump_json()
    if len(set(juges.values())) > 1:
        raise RapportImpossible(
            f"{identifiant} : les runs {', '.join(sorted(juges))} n'ont pas le même juge ; "
            "leurs exécutions ne s'assemblent pas"
        )
    signatures = {run.dossier.name: _signature(run.fiche) for run in sources.values()}
    if signatures:
        premier, reference = next(iter(signatures.items()))
        for nom_run, signature in signatures.items():
            ecarts = [cle for cle, valeur in signature.items() if valeur != reference[cle]]
            if ecarts:
                raise RapportImpossible(
                    f"{identifiant} : les runs {premier} et {nom_run} diffèrent ({', '.join(ecarts)}) ; "
                    "leurs exécutions ne s'assemblent pas"
                )
    return Mesures(identifiant, nom, executions, sources, manquantes)


def notes_de_l_inaction(taches: list[Tache]) -> dict[str, list[tuple[float, str | None]]]:
    """Tâche par tâche, les notes des contrôles appliqués à l'état initial laissé intact."""
    resultat: dict[str, list[tuple[float, str | None]]] = {}
    with tempfile.TemporaryDirectory() as temporaire:
        etats: dict[tuple[str, str | None, str], Instantane] = {}
        for tache in taches:
            cle = (tache.etat_initial, tache.complement, societe_de(tache))
            if cle not in etats:
                dossier = Path(temporaire) / f"{cle[2]}_{cle[0]}_{cle[1] or 'seul'}"
                remettre_a_zero(dossier, *cle)
                etats[cle] = capturer(dossier)
            resultat[tache.identifiant] = verifier(tache, etats[cle], etats[cle])
    return resultat


def planchers(taches: list[Tache]) -> dict[str, float]:
    """Score de l'inertie, tâche par tâche : les contrôles appliqués à l'état initial laissé intact."""
    notes = notes_de_l_inaction(taches)
    return {
        t.identifiant: math.fsum(
            c.poids * score for c, (score, _) in zip(t.controles, notes[t.identifiant], strict=True)
        )
        for t in taches
    }


# ------------------------------------------------------------------------- statistiques


def quantile(valeurs: Sequence[float], q: float) -> float:
    """Quantile par interpolation linéaire ; une borne infinie reste infinie."""
    tries = sorted(valeurs)
    position = q * (len(tries) - 1)
    bas, haut = math.floor(position), math.ceil(position)
    if bas == haut or math.isinf(tries[bas]) or math.isinf(tries[haut]):
        return tries[haut]
    return tries[bas] + (tries[haut] - tries[bas]) * (position - bas)


def _tirage[T](groupes: Sequence[Sequence[T]], indices: Sequence[int], hasard: random.Random) -> list[T]:
    return [hasard.choice(groupes[i]) for i in indices for _ in groupes[i]]


def bootstrap[T](
    groupes: Sequence[Sequence[T]],
    statistique: Callable[[list[T]], float],
    tirages: int = TIRAGES,
    graine: int = GRAINE,
) -> tuple[float, float]:
    """Intervalle à 95 % : tâches tirées avec remise, puis exécutions tirées avec remise dans chacune."""
    return bootstrap_plusieurs(groupes, lambda tirees: (statistique(tirees),), tirages, graine)[0]


def bootstrap_plusieurs[T](
    groupes: Sequence[Sequence[T]],
    statistiques: Callable[[list[T]], Sequence[float]],
    tirages: int = TIRAGES,
    graine: int = GRAINE,
) -> list[tuple[float, float]]:
    """Comme bootstrap, pour plusieurs statistiques calculées sur les mêmes tirages : l'horizon à 80 %
    et à 50 % sortent d'une même courbe, ajustée une fois par tirage."""
    hasard = random.Random(graine)
    n = len(groupes)
    valeurs = [statistiques(_tirage(groupes, [hasard.randrange(n) for _ in range(n)], hasard)) for _ in range(tirages)]
    return [(quantile(v, 0.025), quantile(v, 0.975)) for v in zip(*valeurs, strict=True)]


def bootstrap_ecart[T](
    a: Sequence[Sequence[T]],
    b: Sequence[Sequence[T]],
    statistique: Callable[[list[T]], float],
    tirages: int = TIRAGES,
    graine: int = GRAINE,
) -> tuple[float, float]:
    """Intervalle à 95 % de statistique(a) moins statistique(b) ; les mêmes tâches sont tirées pour les deux."""
    if len(a) != len(b):
        raise ValueError("a et b doivent porter sur les mêmes tâches")
    hasard = random.Random(graine)
    n = len(a)
    valeurs: list[float] = []
    for _ in range(tirages):
        indices = [hasard.randrange(n) for _ in range(n)]
        valeurs.append(statistique(_tirage(a, indices, hasard)) - statistique(_tirage(b, indices, hasard)))
    return quantile(valeurs, 0.025), quantile(valeurs, 0.975)


def taux(resultats: list[ResultatExecution]) -> float:
    return sum(r.reussie for r in resultats) / len(resultats)


def score_moyen(resultats: list[ResultatExecution]) -> float:
    return math.fsum(r.score for r in resultats) / len(resultats)


def _par_reussite(montants: list[float | None], resultats: list[ResultatExecution]) -> float:
    if any(m is None for m in montants):
        return math.nan
    reussites = sum(r.reussie for r in resultats)
    return math.inf if reussites == 0 else math.fsum(m for m in montants if m is not None) / reussites


def _dollars(resultat: ResultatExecution) -> float | None:
    return None if isinstance(resultat.cout_dollars, str) else resultat.cout_dollars


def _euros(resultat: ResultatExecution) -> float | None:
    energie = resultat.energie_wh
    return None if energie is None or isinstance(energie, str) else energie / 1000 * PRIX_KWH_EUROS


def dollars_par_reussite(resultats: list[ResultatExecution]) -> float:
    return _par_reussite([_dollars(r) for r in resultats], resultats)


def euros_par_reussite(resultats: list[ResultatExecution]) -> float:
    return _par_reussite([_euros(r) for r in resultats], resultats)


@dataclass(frozen=True)
class Bilan:
    """Les chiffres d'un candidat sur les tâches communes à tous les candidats."""

    executions: int
    erreurs_techniques: int
    reussites: int
    taux_ic: tuple[float, float]
    """Fourchette à 95 % du taux de réussite, par le bootstrap à deux niveaux (entrée 121)."""
    score: float
    score_ic: tuple[float, float]
    plancher: float
    pass_k: dict[int, float]
    dollars: float | None
    dollars_par_reussite: tuple[float, tuple[float, float]] | None
    energie_wh: float | None
    euros_par_reussite: tuple[float, tuple[float, float]] | None
    duree_secondes: float
    duree_mediane_secondes: float
    etapes_moyennes: float
    refus_gardien: int | None = None
    """Refus du gardien dans les exécutions retenues ; None pour des runs sans gardien."""
    graves: BilanGrave | None = None
    """Fautes graves parmi les exécutions des tâches à contrôle grave ; None sans marquage."""
    lectures: tuple[float, int] | None = None
    """Lectures du relecteur par exécution, en moyenne, et refus de son accès en tout ; None sans relecteur."""
    contextes_depasses: int = 0
    """Exécutions arrêtées par un contexte du modèle dépassé : des échecs de l'agent, dans le taux
    (cadrage du 2026-10-14, choix T3)."""
    delais_depasses: int = 0
    """Exécutions arrêtées par un délai dépassé, du candidat ou d'un appel au modèle : des échecs de
    l'agent, dans le taux (cadrage du générateur des images, choix D1)."""
    energie_mesuree: tuple[float, int] | None = None
    """Quand l'électricité manque pour une partie des exécutions : celle des exécutions mesurées, en Wh,
    et le nombre d'exécutions sans mesure. None quand elle est complète, ou absente partout. Elle ne
    donne qu'un minimum, sans marge (JOURNAL, cent-douzième entrée)."""


ORCHESTRATIONS = {frozenset({"agent"}): "agent seul", frozenset({"auteur", "relecteur"}): "auteur et relecteur"}


def orchestration(mesures: Mesures) -> str:
    """L'orchestration d'un candidat, lue dans les rôles de ses modèles (fiche de run)."""
    roles = frozenset(m.role for run in mesures.sources.values() for m in run.fiche.configuration.modeles)
    if not roles:
        return "non déclarée"
    return ORCHESTRATIONS.get(roles, ", ".join(sorted(roles)))


def _a_un_relecteur(mesures: Mesures) -> bool:
    return any(m.role == "relecteur" for run in mesures.sources.values() for m in run.fiche.configuration.modeles)


def lectures(run: Run, resultat: ResultatExecution) -> tuple[int, int]:
    """Lectures faites par l'accès en lecture seule pendant une exécution, et refus de cet accès
    (journal <tâche>_r<k>_lectures.jsonl ; relecture de la tranche 5, B6 et B7)."""
    chemin = run.dossier / "journaux" / f"{Path(resultat.journal).stem}_lectures.jsonl"
    if not chemin.is_file():
        return 0, 0
    lignes = [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne.strip()]
    faites = sum(1 for ligne in lignes if ligne.get("lecture") is not None)
    return faites, len(lignes) - faites


def _retenus(resultats: list[ResultatExecution]) -> list[ResultatExecution]:
    return [r for r in resultats if r.arret != "erreur_technique"]


def _total(montants: list[float | None]) -> float | None:
    return None if any(m is None for m in montants) else math.fsum(m for m in montants if m is not None)


def faire_bilan(
    mesures: Mesures,
    communes: list[str],
    plancher_par_tache: dict[str, float],
    taches: list[Tache] | None = None,
    gravite: Gravite | None = None,
) -> Bilan:
    """Les chiffres d'un candidat ; avec les tâches et leur marquage, ses fautes graves en plus."""
    groupes = [mesures.executions[t] for t in communes]
    toutes = [r for g in groupes for r in g]
    retenus = [_retenus(g) for g in groupes]
    retenus = [g for g in retenus if g]
    a_plat = [r for g in retenus for r in g]
    if not a_plat:
        raise RapportImpossible(f"{mesures.identifiant} : aucune exécution retenue")
    comptes = [(sum(r.reussie for r in g), len(g)) for g in retenus]
    k_max = min(n for _, n in comptes)
    dollars = _total([_dollars(r) for r in toutes])
    energies = [r.energie_wh for r in toutes]
    sans_energie = all(e is None for e in energies)
    energie = (
        None
        if sans_energie or any(isinstance(e, str) or e is None for e in energies)
        else math.fsum(e for e in energies if not isinstance(e, str) and e is not None)
    )
    mesurees = [float(e) for e in energies if isinstance(e, (int, float))]
    energie_mesuree = (
        (math.fsum(mesurees), len(energies) - len(mesurees)) if mesurees and len(mesurees) < len(energies) else None
    )
    return Bilan(
        executions=len(a_plat),
        erreurs_techniques=len(toutes) - len(a_plat),
        contextes_depasses=sum(r.arret == "contexte_depasse" for r in a_plat),
        delais_depasses=sum(r.arret == "delai_depasse" for r in a_plat),
        reussites=sum(r.reussie for r in a_plat),
        taux_ic=bootstrap(retenus, taux),
        score=score_moyen(a_plat),
        score_ic=bootstrap(retenus, score_moyen),
        plancher=math.fsum(plancher_par_tache[t] for t in communes) / len(communes),
        pass_k={k: pass_k(comptes, k) for k in range(1, k_max + 1)},
        dollars=dollars,
        dollars_par_reussite=None
        if dollars is None
        else (dollars_par_reussite(toutes), bootstrap(groupes, dollars_par_reussite)),
        energie_wh=energie,
        energie_mesuree=energie_mesuree,
        euros_par_reussite=None
        if energie is None
        else (euros_par_reussite(toutes), bootstrap(groupes, euros_par_reussite)),
        duree_secondes=math.fsum(r.duree_secondes for r in toutes),
        duree_mediane_secondes=statistics.median(r.duree_secondes for r in toutes),
        etapes_moyennes=statistics.fmean(r.etapes for r in toutes),
        refus_gardien=None
        if any(mesures.sources[t].fiche.regles_gardien is None for t in communes)
        else sum(
            len(blocages_du_gardien(mesures.sources[t].dossier / r.journal))
            for t in communes
            for r in mesures.executions[t]
        ),
        lectures=None
        if not _a_un_relecteur(mesures)
        else (
            statistics.fmean(lectures(mesures.sources[t], r)[0] for t in communes for r in mesures.executions[t]),
            sum(lectures(mesures.sources[t], r)[1] for t in communes for r in mesures.executions[t]),
        ),
        graves=None
        if taches is None or gravite is None
        else bilan_grave(
            [(r, t) for t in taches if t.identifiant in communes for r in mesures.executions[t.identifiant]],
            gravite,
        ),
    )


# ------------------------------------------------------------------------------ écriture


def _nombre(valeur: float, decimales: int) -> str:
    return f"{valeur:,.{decimales}f}".replace(",", NB).replace(".", ",")


def _pourcent(valeur: float) -> str:
    return _nombre(100 * valeur, 1).removesuffix(",0") + f"{NB}%"


def _borne(valeur: float, ecrire: Callable[[float], str]) -> str:
    return "?" if math.isnan(valeur) else "non bornée" if math.isinf(valeur) else ecrire(valeur)


def _ic(intervalle: tuple[float, float], ecrire: Callable[[float], str]) -> str:
    return f"IC 95{NB}% de {_borne(intervalle[0], ecrire)} à {_borne(intervalle[1], ecrire)}"


def _dollar(valeur: float) -> str:
    return f"{_nombre(valeur, 4)}{NB}$"


def _euro(valeur: float) -> str:
    return f"{_nombre(valeur, 4)}{NB}€"


def _electricite_partielle(bilan: Bilan, sans_objet: str) -> str:
    """L'électricité quand une partie des exécutions n'a pas de mesure : un minimum, sans marge,
    avec le nombre d'exécutions manquantes ; sans objet quand rien n'est mesuré."""
    if bilan.energie_mesuree is None:
        return sans_objet
    mesuree, manquantes = bilan.energie_mesuree
    euros = mesuree / 1000 * PRIX_KWH_EUROS
    par_reussite = f"<br>au moins {_euro(euros / bilan.reussites)} par tâche réussie" if bilan.reussites else ""
    return (
        f"au moins {_nombre(mesuree, 1)}{NB}Wh, soit au moins {_euro(euros)}{par_reussite}"
        f'<br><span class="doux petit">{manquantes} exécution(s) sans mesure, pas de marge</span>'
    )


def _points(valeur: float) -> str:
    return _nombre(100 * valeur, 1).removesuffix(",0")


def conclusion(mesures: list[Mesures], communes: list[str]) -> str:
    """Une phrase : qui réussit le plus, et si l'écart est établi à 95 %."""
    if len(mesures) != 2:
        return "Le rapport ne compare que deux candidats à la fois."
    groupes = {m.identifiant: [_retenus(m.executions[t]) for t in communes] for m in mesures}
    taux_de = {m.identifiant: taux([r for g in groupes[m.identifiant] for r in g]) for m in mesures}
    premier, second = sorted(mesures, key=lambda m: taux_de[m.identifiant], reverse=True)
    a, b = groupes[premier.identifiant], groupes[second.identifiant]
    ka, na = sum(r.reussie for g in a for r in g), sum(len(g) for g in a)
    kb, nb = sum(r.reussie for g in b for r in g), sum(len(g) for g in b)
    bas, haut = bootstrap_ecart(a, b, taux)
    ecart = _points(taux_de[premier.identifiant] - taux_de[second.identifiant])
    marge = f"de {_points(bas)} à {_points(haut)} points"
    if bas > 0:
        return (
            f"{premier.nom} réussit plus souvent que {second.nom} : {ka} exécutions sur {na} contre {kb} "
            f"sur {nb}, un écart de {ecart} points établi à 95{NB}% ({marge})."
        )
    return (
        f"{premier.nom} réussit {ka} exécutions sur {na}, {second.nom} {kb} sur {nb} : l'écart de {ecart} "
        f"points n'est pas établi à 95{NB}% ({marge})."
    )


def _fautives(resultats: list[bool]) -> float:
    return sum(resultats) / len(resultats)


def conclusion_graves(mesures: list[Mesures], taches: list[Tache], communes: list[str], gravite: Gravite) -> str:
    """Une phrase sur les fautes graves, à côté de la conclusion sur la réussite, jamais mêlée à elle."""
    exposees = [t for t in taches if t.identifiant in communes and exposee(t, gravite)]
    if len(mesures) != 2 or not exposees:
        return ""
    groupes = {
        m.identifiant: [
            [bool(fautes_graves(r, t, gravite)) for r in _retenus(m.executions[t.identifiant])] for t in exposees
        ]
        for m in mesures
    }
    comptes = {i: (sum(sum(g) for g in liste), sum(len(g) for g in liste)) for i, liste in groupes.items()}
    if any(n == 0 for _, n in comptes.values()):
        return ""
    premier, second = sorted(mesures, key=lambda m: comptes[m.identifiant][0] / comptes[m.identifiant][1])
    a, b = groupes[premier.identifiant], groupes[second.identifiant]
    (ka, na), (kb, nb) = comptes[premier.identifiant], comptes[second.identifiant]
    debut = (
        "Exécutions avec une faute grave, parmi celles des tâches à contrôle grave : "
        f"{premier.nom} {ka} sur {na}, {second.nom} {kb} sur {nb}"
    )
    if ka == kb == 0:
        return f"{debut}."
    bas, haut = bootstrap_ecart(b, a, _fautives)
    ecart = _points(kb / nb - ka / na)
    marge = f"de {_points(bas)} à {_points(haut)} points"
    if bas > 0:
        return f"{debut} ; {premier.nom} en commet moins, un écart de {ecart} points établi à 95{NB}% ({marge})."
    return f"{debut} ; l'écart de {ecart} points n'est pas établi à 95{NB}% ({marge})."


STYLE = """
:root { --fond: #fbfaf7; --texte: #1d1d1b; --doux: #5f5e5a; --trait: #dcd9d0; --carte: #ffffff;
  --ok: #1f7a4d; --ko: #b3261e; --accent: #2b4c7e; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --fond: #161615;
  --texte: #ecebe6; --doux: #a8a69e; --trait: #3a3935; --carte: #1f1f1d; --ok: #5cc28f;
  --ko: #f08a80; --accent: #8fb0e3; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--fond); color: var(--texte);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 1.6rem; line-height: 1.25; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 40px 0 12px; }
h3 { font-size: 1rem; margin: 28px 0 6px; }
.doux { color: var(--doux); }
.petit { font-size: .9rem; }
.encadre { background: var(--carte); border: 1px solid var(--trait); border-left: 4px solid var(--accent);
  padding: 14px 18px; font-size: 1.1rem; margin: 24px 0; }
.encadre.alerte { border-left-color: var(--ko); font-size: 1rem; }
.tableau { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; background: var(--carte); font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--trait); vertical-align: top; }
th { font-weight: 600; }
.ok { color: var(--ok); }
.ko { color: var(--ko); }
a { color: var(--accent); }
.executions a { margin-right: 8px; text-decoration: none; white-space: nowrap; }
details { margin: 0 0 10px; }
summary { cursor: pointer; color: var(--doux); }
ul { padding-left: 20px; }
li { margin: 4px 0; }
"""


def _e(texte: object) -> str:
    return html.escape(str(texte))


def _lien(cible: Path, depuis: Path, texte: str, titre: str = "", classe: str = "") -> str:
    relatif = Path(os.path.relpath(cible, depuis)).as_posix()
    attributs = f' title="{_e(titre)}"' if titre else ""
    attributs += f' class="{classe}"' if classe else ""
    return f'<a href="{_e(relatif)}"{attributs}>{_e(texte)}</a>'


def _modele(mesures: Mesures) -> str:
    vus = sorted({str(m.version_renvoyee) for run in mesures.sources.values() for m in run.fiche.configuration.modeles})
    run = next(iter(mesures.sources.values()))
    plusieurs = len(run.fiche.configuration.modeles) > 1
    modeles = ", ".join(
        f"{m.role + ' : ' if plusieurs else ''}{m.nom} ({m.fournisseur})" for m in run.fiche.configuration.modeles
    )
    machine = run.fiche.machine
    if not run.fiche.configuration.modeles:
        return '<span class="doux">aucun modèle déclaré</span>'
    lieu = "API du fournisseur" if machine is None else f"{machine.carte_graphique}, {machine.service_modele}"
    return f'{_e(modeles)}<br><span class="doux petit">renvoyé : {_e(", ".join(vus))} ; {_e(lieu)}</span>'


def _cellule_graves(graves: BilanGrave) -> str:
    if graves.exposees == 0 or graves.wilson is None:
        return '<span class="doux">aucune tâche à contrôle grave</span>'
    detail = ", ".join(f"{c} {n}" for c, n in graves.par_categorie.items() if n)
    return (
        f"<strong>{graves.fautives} sur {graves.exposees}</strong> ({_pourcent(graves.fautives / graves.exposees)})"
        f'<br><span class="doux petit">exécutions des tâches à contrôle grave ; {_ic(graves.wilson, _pourcent)}'
        + (f" ; {_e(detail)}" if detail else "")
        + "</span>"
    )


def _tableau_chiffres(mesures: list[Mesures], bilans: list[Bilan]) -> list[str]:
    def ligne(titre: str, cellules: list[str]) -> str:
        return f"<tr><th>{titre}</th>" + "".join(f"<td>{c}</td>" for c in cellules) + "</tr>"

    sans_objet = '<span class="doux">sans objet</span>'
    lignes = ['<div class="tableau"><table><thead><tr><th></th>']
    lignes += [f"<th>{_e(m.nom)}</th>" for m in mesures]
    lignes.append("</tr></thead><tbody>")
    lignes.append(
        ligne(
            "Réussite",
            [
                f"<strong>{b.reussites} sur {b.executions}</strong> ({_pourcent(b.reussites / b.executions)})"
                f'<br><span class="doux petit">{_ic(b.taux_ic, _pourcent)}</span>'
                for b in bilans
            ],
        )
    )
    if all(b.graves is not None for b in bilans):
        lignes.append(ligne("Fautes graves", [_cellule_graves(b.graves) for b in bilans if b.graves is not None]))
    k = min(max(b.pass_k) for b in bilans)
    lignes.append(
        ligne(
            f"Régularité (pass<sup>{k}</sup>)",
            [
                f'{_pourcent(b.pass_k[k])}<br><span class="doux petit">chance qu\'une tâche réussisse ses {k} '
                "essais</span>"
                for b in bilans
            ],
        )
    )
    lignes.append(
        ligne(
            "Score moyen",
            [
                f'{_nombre(b.score, 2)}<br><span class="doux petit">{_ic(b.score_ic, lambda v: _nombre(v, 2))} ; '
                f"ne rien faire vaut {_nombre(b.plancher, 2)}</span>"
                for b in bilans
            ],
        )
    )
    lignes.append(
        ligne(
            "Coût des appels au modèle",
            [
                sans_objet
                if b.dollars_par_reussite is None or b.dollars is None
                else f"{_dollar(b.dollars)} en tout<br>{_dollar(b.dollars_par_reussite[0])} par tâche réussie"
                f'<br><span class="doux petit">{_ic(b.dollars_par_reussite[1], _dollar)}</span>'
                for b in bilans
            ],
        )
    )
    lignes.append(
        ligne(
            "Électricité de la carte graphique",
            [
                _electricite_partielle(b, sans_objet)
                if b.euros_par_reussite is None or b.energie_wh is None
                else f"{_nombre(b.energie_wh, 1)}{NB}Wh, soit {_euro(b.energie_wh / 1000 * PRIX_KWH_EUROS)}"
                f"<br>{_euro(b.euros_par_reussite[0])} par tâche réussie"
                f'<br><span class="doux petit">{_ic(b.euros_par_reussite[1], _euro)}</span>'
                for b in bilans
            ],
        )
    )
    lignes.append(
        ligne(
            "Durée",
            [
                f'{_nombre(b.duree_secondes / 60, 1)}{NB}min en tout<br><span class="doux petit">'
                f"{_nombre(b.duree_mediane_secondes, 0)}{NB}s par exécution (médiane)</span>"
                for b in bilans
            ],
        )
    )
    lignes.append(ligne("Étapes par exécution", [_nombre(b.etapes_moyennes, 1) for b in bilans]))
    if any(b.lectures is not None for b in bilans):
        lignes.append(
            ligne(
                "Lectures du relecteur",
                [
                    sans_objet
                    if b.lectures is None
                    else f'{_nombre(b.lectures[0], 1)} par exécution<br><span class="doux petit">hors du budget '
                    f"d'étapes ; refus de l'accès en lecture : {b.lectures[1]}</span>"
                    for b in bilans
                ],
            )
        )
    lignes.append(ligne("Erreurs techniques", [str(b.erreurs_techniques) for b in bilans]))
    if any(b.contextes_depasses for b in bilans):
        lignes.append(ligne("Contextes dépassés, comptés en échecs", [str(b.contextes_depasses) for b in bilans]))
    if any(b.delais_depasses for b in bilans):
        lignes.append(ligne("Délais dépassés, comptés en échecs", [str(b.delais_depasses) for b in bilans]))
    if any(b.refus_gardien is not None for b in bilans):
        lignes.append(
            ligne(
                "Refus du gardien",
                [sans_objet if b.refus_gardien is None else str(b.refus_gardien) for b in bilans],
            )
        )
    lignes.append(ligne("Orchestration", [_e(orchestration(m)) for m in mesures]))
    lignes.append(ligne("Modèle", [_modele(m) for m in mesures]))
    lignes.append("</tbody></table></div>")
    return lignes


# ------------------------------------------------------------------------- horizon de temps


@dataclass(frozen=True)
class BilanHorizon:
    """L'horizon d'un candidat, aux SEUILS, sur les tâches de la courbe."""

    taches: int
    essais: int
    estimations: tuple[float, ...]
    """Par seuil, en minutes ; math.inf se lit « au-delà de » la plus longue tâche, 0.0 « en deçà de » la
    plus courte (ease.horizon)."""
    fourchettes: list[tuple[float, float]]
    pente: float


def bilan_horizon(
    mesures: Mesures, taches: Sequence[Tache], minutes: dict[str, float], plage: tuple[float, float]
) -> BilanHorizon:
    """La courbe sur tous les essais retenus des tâches données, puis sa fourchette par le bootstrap à
    deux niveaux, la courbe refaite à chaque tirage."""
    groupes: list[list[Point]] = [
        [(minutes[t.identifiant], r.reussie) for r in _retenus(mesures.executions[t.identifiant])] for t in taches
    ]
    groupes = [g for g in groupes if g]
    if not groupes:
        raise RapportImpossible(f"{mesures.nom} : aucun essai sans erreur technique pour l'horizon")
    points = [p for g in groupes for p in g]
    courbe = ajuster(points)
    estimations = tuple(horizon(courbe, s, plage) for s in SEUILS)
    return BilanHorizon(len(groupes), len(points), estimations, bootstrap_plusieurs(groupes, horizons(plage)), courbe.b)


def _minutes(valeur: float) -> str:
    """Une durée donnée en minutes ; sous deux minutes, en secondes."""
    return f"{_nombre(valeur * 60, 0)}{NB}s" if valeur < 2 else f"{_nombre(valeur, 1)}{NB}min"


def lecture_horizon(valeur: float, plage: tuple[float, float]) -> str:
    if math.isinf(valeur):
        return f"au-delà de {_minutes(plage[1])}"
    if valeur == 0:
        return f"en deçà de {_minutes(plage[0])}"
    return _minutes(valeur)


def _ic_horizon(intervalle: tuple[float, float], plage: tuple[float, float]) -> str:
    bas, haut = intervalle
    if math.isinf(bas) or haut == 0:
        return f"IC 95{NB}% tout entier {lecture_horizon(bas, plage)}"
    debut = f"moins de {_minutes(plage[0])}" if bas == 0 else _minutes(bas)
    fin = f"plus de {_minutes(plage[1])}" if math.isinf(haut) else _minutes(haut)
    return f"IC 95{NB}% de {debut} à {fin}"


def sans_noms(identifiants: Sequence[str], cachees: Collection[str]) -> str:
    """Des tâches nommées, sauf les cachées, comptées à la fin sans leurs noms."""
    noms = [i for i in identifiants if i not in cachees]
    n = len(identifiants) - len(noms)
    if n:
        noms.append(f"{n} tâche{'s' if n > 1 else ''} cachée{'s' if n > 1 else ''}")
    return ", ".join(noms)


def _section_horizon(
    mesures: list[Mesures],
    taches: list[Tache],
    communes: list[str],
    gravite: Gravite,
    durees: dict[str, float],
    cachees: Collection[str] = (),
) -> list[str]:
    """L'horizon de temps (cadrage du 2026-10-13, section du 2026-10-14 ; JOURNAL, entrée 129), sur
    les tâches communes sans contrôle grave dont la durée estimée par la grille est à jour ; les
    cachées y entrent comme les autres, et celles qui en restent hors se comptent sans leurs noms."""
    retenues = [t for t in taches if t.identifiant in communes and not exposee(t, gravite)]
    dans = [t for t in retenues if t.identifiant in durees]
    hors = [t.identifiant for t in retenues if t.identifiant not in durees]
    lignes = ["<h2>L'horizon de temps</h2>"]
    if not dans:
        lignes.append(
            "<p class=\"doux\">Aucune tâche sans contrôle grave n'a de durée estimée à jour : pas d'horizon.</p>"
        )
        return lignes
    minutes = {t.identifiant: durees[t.identifiant] / 60 for t in dans}
    plage = (min(minutes.values()), max(minutes.values()))
    bilans = [bilan_horizon(m, dans, minutes, plage) for m in mesures]
    lignes.append(
        f"<p>Sur {len(dans)} tâches sans contrôle grave, dont la durée humaine est estimée par la grille "
        f"{_e(VERSION_GRILLE)}, de {_minutes(plage[0])} à {_minutes(plage[1])}. L'horizon à un seuil est la "
        "durée de tâche jusqu'où la courbe de réussite reste au-dessus de ce seuil, depuis la tâche la plus "
        "courte. Les durées de la grille sont des bornes basses : l'horizon se lit en minutes de la grille, "
        "pas en minutes chronométrées.</p>"
    )

    def ligne(titre: str, cellules: list[str]) -> str:
        return f"<tr><th>{titre}</th>" + "".join(f"<td>{c}</td>" for c in cellules) + "</tr>"

    tableau = ['<div class="tableau"><table><thead><tr><th></th>']
    tableau += [f"<th>{_e(m.nom)}</th>" for m in mesures]
    tableau.append("</tr></thead><tbody>")
    for i, seuil in enumerate(SEUILS):
        tableau.append(
            ligne(
                f"Horizon à {_pourcent(seuil)}",
                [
                    f"<strong>{lecture_horizon(b.estimations[i], plage)}</strong>"
                    f'<br><span class="doux petit">{_ic_horizon(b.fourchettes[i], plage)}</span>'
                    for b in bilans
                ],
            )
        )
    tableau.append(
        ligne("La courbe", ["monte avec la durée" if b.pente >= 0 else "descend avec la durée" for b in bilans])
    )
    tableau.append(ligne("Dans la courbe", [f"{b.taches} tâches, {b.essais} essais" for b in bilans]))
    tableau.append("</tbody></table></div>")
    lignes += tableau
    plus_haut = SEUILS.index(max(SEUILS))
    if all(math.isinf(b.estimations[plus_haut]) for b in bilans):
        lignes.append(
            f"<p>Pour chaque candidat, la courbe reste au-dessus de {_pourcent(SEUILS[plus_haut])} sur toute la "
            "plage : ces tâches ne départagent pas les candidats par leur durée.</p>"
        )
    if hors:
        caches = " (CACHEES=1 pour les cachées, dans une séance qui peut les lire)" if set(hors) & set(cachees) else ""
        lignes.append(
            '<p class="doux petit">Hors de la courbe, faute de durée estimée à jour : '
            f"{_e(sans_noms(hors, cachees))} ; make classement ESTIMER=1 la recalcule{caches}.</p>"
        )
    lignes.append(
        '<p class="doux petit">Une courbe logistique par candidat, de la réussite de chaque essai selon le '
        "logarithme de la durée, tous les essais au même poids, pénalité "
        f"{_nombre(PENALITE, 1)} sur ses deux paramètres ; fourchettes par le bootstrap à deux niveaux, la "
        "courbe refaite à chaque tirage ; d'après METR (00_docs/sources/2026-10-13_cadrage_horizon_de_temps.md). "
        "Les tâches à contrôle grave sont hors de la courbe : leurs manques se lisent dans les fautes "
        "graves.</p>"
    )
    return lignes


def _echecs(resultat: ResultatExecution, tache: Tache, gravite: Gravite | None = None) -> str:
    """Pourquoi l'exécution a échoué, en clair : l'étape manquée, puis le détail technique, en petit."""
    if resultat.arret == "erreur_technique":
        return f"erreur technique : {_e(resultat.detail_arret or '?')}"
    raisons: list[str] = []
    if resultat.arret == "budget_etapes":
        raisons.append("budget d'étapes épuisé")
    if resultat.arret == "contexte_depasse":
        raisons.append("contexte du modèle dépassé")
    if resultat.arret == "delai_depasse":
        raisons.append(f"délai dépassé ({_e(resultat.detail_arret or '?')})")
    categorie = {} if gravite is None else numeros_graves(tache, gravite)
    for c in resultat.controles:
        if c.score < 1:
            detail = c.detail or "?"
            detail = detail if len(detail) <= 200 else detail[:199] + "…"
            etape = tache.controles[c.numero - 1].etape
            grave = (
                f'<strong class="ko">faute grave ({_e(categorie[c.numero])})</strong>, '
                if c.numero in categorie
                else ""
            )
            raisons.append(f'{grave}manqué, « {_e(etape)} » <span class="doux">({_e(detail)})</span>')
    return " ; ".join(raisons)


def _section_tache(tache: Tache, mesures: list[Mesures], depuis: Path, gravite: Gravite | None = None) -> list[str]:
    lignes = [f'<h3>{_e(tache.identifiant)} <span class="doux petit">version {tache.version}</span></h3>']
    lignes.append(
        "<details><summary>Énoncé de la tâche</summary>"
        '<p class="doux petit">Depuis le 2026-10-08 (JOURNAL, entrée 97), l\'agent le reçoit après la date et '
        "l'heure de la PME.</p>"
        f"<p>{_e(tache.enonce)}</p></details>"
    )
    lignes.append(
        '<div class="tableau"><table><thead><tr><th>Modèle</th><th>Réussites</th><th>Score moyen</th>'
        "<th>Étapes</th><th>Durée</th><th>Exécutions (récit de l'agent)</th></tr></thead><tbody>"
    )
    defauts: list[str] = []
    for m in mesures:
        resultats = m.executions.get(tache.identifiant)
        if resultats is None:
            lignes.append(f'<tr><td>{_e(m.nom)}</td><td colspan="5" class="doux">non mesurée</td></tr>')
            continue
        run = m.sources[tache.identifiant]
        liens: list[str] = []
        for r in resultats:
            nom = Path(r.journal).stem
            cible = run.dossier / "journaux" / f"{nom}_candidat.log"
            if not cible.is_file():
                cible = run.dossier / r.journal
            marque, classe, titre = ("✓", "ok", "réussie") if r.reussie else ("✗", "ko", "échouée")
            liens.append(_lien(cible, depuis, f"r{r.repetition}{NB}{marque}", titre, classe))
            if not r.reussie:
                defauts.append(f"<li><strong>{_e(m.nom)}, r{r.repetition}</strong> : {_echecs(r, tache, gravite)}</li>")
        lignes.append(
            f"<tr><td>{_e(m.nom)}</td><td>{sum(r.reussie for r in resultats)} sur {len(resultats)}</td>"
            f"<td>{_nombre(score_moyen(resultats), 2)}</td>"
            f"<td>{_nombre(statistics.fmean(r.etapes for r in resultats), 1)}</td>"
            f"<td>{_nombre(statistics.fmean(r.duree_secondes for r in resultats), 0)}{NB}s</td>"
            f'<td class="executions">{"".join(liens)}</td></tr>'
        )
    lignes.append("</tbody></table></div>")
    if defauts:
        lignes.append('<ul class="petit">' + "".join(defauts) + "</ul>")
    return lignes


def _section_cachees(cachees: list[Tache], mesures: list[Mesures]) -> list[str]:
    """Les tâches cachées en bloc : ni leurs noms, ni leurs énoncés, ni lien vers leurs traces, ni le
    détail de leurs échecs ; leurs exécutions comptent déjà dans les chiffres et dans la courbe."""
    pluriel = "s" if len(cachees) > 1 else ""
    lignes = [
        f'<h3>Tâche{pluriel} cachée{pluriel} <span class="doux petit">{len(cachees)}, ensemble</span></h3>',
        '<p class="doux petit">Rangées hors git (07_taches/prive/), pour que personne ne règle une orchestration '
        "sur elles : la page ne donne ni leurs noms, ni leurs énoncés, ni leurs traces.</p>",
        '<div class="tableau"><table><thead><tr><th>Modèle</th><th>Tâches mesurées</th><th>Réussites</th>'
        "<th>Score moyen</th><th>Étapes</th><th>Durée</th></tr></thead><tbody>",
    ]
    for m in mesures:
        resultats = [r for t in cachees for r in m.executions.get(t.identifiant, [])]
        if not resultats:
            lignes.append(f'<tr><td>{_e(m.nom)}</td><td colspan="5" class="doux">non mesurées</td></tr>')
            continue
        mesurees = sum(1 for t in cachees if t.identifiant in m.executions)
        lignes.append(
            f"<tr><td>{_e(m.nom)}</td><td>{mesurees} sur {len(cachees)}</td>"
            f"<td>{sum(r.reussie for r in resultats)} sur {len(resultats)}</td>"
            f"<td>{_nombre(score_moyen(resultats), 2)}</td>"
            f"<td>{_nombre(statistics.fmean(r.etapes for r in resultats), 1)}</td>"
            f"<td>{_nombre(statistics.fmean(r.duree_secondes for r in resultats), 0)}{NB}s</td></tr>"
        )
    lignes.append("</tbody></table></div>")
    return lignes


CORRIGEES_DU_SOCLE = ("t01", "t02", "t04", "t05", "t08", "t09")
"""Les tâches du socle de Calorelle dont les contrôles ont été corrigés après relecture des traces
(JOURNAL, entrées 29 à 31 et 62) : la limite qui le dit ne vaut que pour un rapport qui les porte."""


def nom_court(identifiant: str) -> str:
    """Le code d'une tâche, avant son premier « _ » : t01, h03, dv04, dvh11."""
    return identifiant.split("_", 1)[0]


def nom_de_la_pme(taches: list[Tache]) -> str:
    """Le nom de la PME fictive des tâches, celui que déclare leur état (entreprise/societe.yaml ;
    ADR 0006) : Calorelle, Domivelle, Négovelle, ou l'entreprise d'une campagne sur le gabarit."""
    societe = societe_des_taches(taches)
    etat = dossier_version(min(t.etat_initial for t in taches), societe) if taches else None
    if etat is None or not etat.is_dir():
        return societe.capitalize()
    return parametres_societe(etat).nom


def _section_methode(
    mesures: list[Mesures],
    taches: list[Tache],
    gravite: Gravite | None = None,
    cachees: Collection[str] = (),
    marquage: str | None = None,
) -> list[str]:
    """marquage : le fichier où les contrôles graves du jeu sont marqués, quand ce n'est pas
    07_taches/public/gravite.yaml, qui garde les catégories."""
    lignes = ["<h2>Méthode et limites</h2><ul>"]
    versions = ", ".join(f"{t.identifiant} v{t.version}" for t in taches if t.identifiant not in cachees)
    nombre = sum(1 for t in taches if t.identifiant in cachees)
    if nombre:
        versions += f", et {nombre} tâche{'s' if nombre > 1 else ''} cachée{'s' if nombre > 1 else ''}"
    lignes.append(
        f"<li>Tâches de la PME fictive {_e(nom_de_la_pme(taches))}, dans leur version courante : {_e(versions)}.</li>"
    )
    regles = next((r.fiche.regles_gardien for m in mesures for r in m.sources.values()), None)
    if regles is None:
        lignes.append("<li>Sans gardien : l'agent atteint les services de la PME directement.</li>")
    else:
        lignes.append(
            f"<li>Avec le gardien entre l'agent et la PME : règles version {_e(regles.version)}, empreinte "
            f"{_e(regles.empreinte[:15])}.</li>"
        )
    lignes.append(
        "<li>Taux de réussite, autres marges et écart entre candidats : bootstrap à deux niveaux, "
        f"{_nombre(TIRAGES, 0)} tirages, graine {GRAINE} ; les tâches sont tirées avec remise, puis les "
        "exécutions dans chaque tâche, parce que les essais d'une même tâche se ressemblent.</li>"
    )
    if gravite is not None:
        marques = sum(len(e) for t, e in gravite.graves.items() if any(x.identifiant == t for x in taches))
        exposees = sum(exposee(t, gravite) for t in taches)
        categories = " ; ".join(f"{n}, {d}" for n, d in gravite.categories.items())
        ou = (
            f"07_taches/public/gravite.yaml, version {gravite.version}"
            if marquage is None
            else f"{marquage}, avec les catégories de 07_taches/public/gravite.yaml, version {gravite.version}"
        )
        lignes.append(
            f"<li>Fautes graves : {marques} contrôles, sur {exposees} tâches, sont marqués graves dans "
            f"{_e(ou)} ({_e(categories)}). Une exécution "
            "commet une faute grave quand elle en manque un. La part des exécutions fautives se compte parmi "
            "celles des tâches à contrôle grave, intervalle de Wilson à 95 %, et ne se mêle jamais au score "
            "ni à la réussite. Chaque contrôle grave est une interdiction : ne rien faire le tient.</li>"
        )
    if any(_a_un_relecteur(m) for m in mesures):
        lignes.append(
            "<li>Auteur et relecteur : chaque action qui écrit ou envoie est relue avant de partir. Le "
            "relecteur lit par un accès en lecture seule, hors du budget d'étapes de la tâche, avec un plafond de "
            "trois lectures par étape du budget ; « Étapes » ne compte que l'auteur, les lectures sont comptées à "
            "part, refus de l'accès compris (JOURNAL, entrées 93 et 94).</li>"
        )
    lignes.append(
        "<li>« Ne rien faire vaut » : le score d'un agent qui ne touche à rien, contrôles appliqués à "
        "l'état initial intact.</li>"
    )
    lignes.append(
        f"<li>Électricité : relevé de la carte graphique seule par nvidia-smi, toutes les 500 ms, donc un "
        f"minimum ; prix de {_nombre(PRIX_KWH_EUROS, 4)}{NB}€ le kilowattheure, {_e(PRIX_KWH_SOURCE)}.</li>"
    )
    vus: set[str] = set()
    for m in mesures:
        run = next(iter(m.sources.values()))
        for modele in run.fiche.configuration.modeles:
            cle = f"{modele.nom}|{None if modele.tarif is None else modele.tarif.model_dump_json()}"
            if modele.tarif is not None and cle not in vus:
                vus.add(cle)
                t = modele.tarif
                lignes.append(
                    f"<li>Prix de {_e(modele.nom)} : {_nombre(t.entree_dollars_par_million, 3)}{NB}$ le million "
                    f"de jetons d'entrée, {_e(t.entree_en_cache_dollars_par_million)}{NB}$ lus en cache, "
                    f"{_nombre(t.sortie_dollars_par_million, 3)}{NB}$ en sortie ; {_e(t.source)}, relevé le "
                    f"{_e(t.releve_le)}.</li>"
                )
    corrigees = (
        " ; contrôles de t01, t02, t04 et t05 corrigés après relecture des traces (JOURNAL, entrées 29 à 31), "
        "de t08 et t09 aussi (entrée 62), avant ce rapport"
        if any(nom_court(t.identifiant) in CORRIGEES_DU_SOCLE for t in taches)
        else ""
    )
    lignes.append(
        f"<li>Limites : {len(taches)} tâches seulement ; {_e(_orchestrations(mesures))} ; PME fictive seulement, "
        f"sans banc public dans ce rapport, donc aucun classement d'orchestration (règle 11){corrigees}.</li></ul>"
    )
    lignes.append(
        '<h3>Runs utilisés</h3><div class="tableau"><table class="petit"><thead><tr><th>Candidat</th>'
        "<th>Tâches</th><th>Run</th><th>Début (UTC)</th><th>Code</th></tr></thead><tbody>"
    )
    for m in mesures:
        par_run: dict[str, list[str]] = {}
        for tache, run in m.sources.items():
            par_run.setdefault(run.dossier.name, []).append(tache)
        for nom_run, identifiants in par_run.items():
            liste = sans_noms([nom_court(i) if i not in cachees else i for i in identifiants], cachees)
            run = next(r for r in m.sources.values() if r.dossier.name == nom_run)
            code = run.fiche.code
            etat = " avec modifications non commitées" if code.modifications_non_commitees else ""
            if run.fiche.statut == "interrompu":
                etat += f" ; run interrompu ({run.fiche.raison_interruption or '?'}), tâches complètes seules"
            lignes.append(
                f"<tr><td>{_e(m.nom)}</td><td>{_e(liste)}</td><td>{_e(nom_run)}</td>"
                f"<td>{run.fiche.debut_utc:%Y-%m-%d %H:%M}</td><td>{_e(code.commit[:8])}{_e(etat)}</td></tr>"
            )
    lignes.append("</tbody></table></div>")
    return lignes


def _orchestrations(mesures: list[Mesures]) -> str:
    noms = {orchestration(m) for m in mesures}
    if len(noms) == 1:
        return f"même orchestration ({noms.pop()}) pour {'les deux candidats' if len(mesures) == 2 else 'tous'}"
    return "orchestrations : " + ", ".join(f"{m.nom}, {orchestration(m)}" for m in mesures)


def noms_courts(noms: list[str]) -> tuple[str, list[str]]:
    """Le début commun des noms, à la frontière d'un mot, et ce qui reste de chacun."""
    mots = [nom.split(" ") for nom in noms]
    commun = 0
    while all(len(m) > commun + 1 for m in mots) and len({m[commun] for m in mots}) == 1:
        commun += 1
    if len(noms) < 2 or commun == 0:
        return "", noms
    return " ".join(mots[0][:commun]), [" ".join(m[commun:]) for m in mots]


def produire(
    mesures: list[Mesures],
    taches: list[Tache],
    plancher_par_tache: dict[str, float],
    depuis: Path,
    gravite: Gravite | None = None,
    durees: dict[str, float] | None = None,
    cachees: Collection[str] = (),
    marquage: str | None = None,
) -> str:
    """Le rapport HTML complet ; depuis est le dossier où il sera écrit (liens relatifs vers les traces).
    Avec la gravité et les durées estimées à jour (en secondes, par tâche), il donne l'horizon de temps.
    Les tâches de cachees comptent partout, sans jamais être nommées. marquage : voir _section_methode."""
    debut, courts = noms_courts([m.nom for m in mesures])
    mesures = [replace(m, nom=court) for m, court in zip(mesures, courts, strict=True)]
    debut = debut.removesuffix(" sur").removesuffix(" avec")
    titre = (f"{debut} : " if debut else "") + " contre ".join(m.nom for m in mesures)
    communes = [t.identifiant for t in taches if all(t.identifiant in m.executions for m in mesures)]
    if not communes:
        raise RapportImpossible("aucune tâche mesurée pour tous les candidats")
    bilans = [faire_bilan(m, communes, plancher_par_tache, taches, gravite) for m in mesures]
    manquantes = [f"{m.nom} : {sans_noms(m.manquantes, cachees)}" for m in mesures if m.manquantes]
    noms = " et ".join(m.nom for m in mesures)
    communes_cachees = sum(1 for t in communes if t in cachees)
    dont = f", dont {communes_cachees} cachée{'s' if communes_cachees > 1 else ''}" if communes_cachees else ""
    corps = [
        "<main>",
        f"<h1>{_e(titre)}</h1>",
        f'<p class="doux">{_e(noms)}, sur {len(communes)} tâches de la PME fictive {_e(nom_de_la_pme(taches))}'
        f"{dont}. "
        f"Rapport produit le {datetime.now(UTC):%Y-%m-%d à %H:%M} UTC depuis les fichiers des runs.</p>",
    ]
    if manquantes:
        corps.append(
            '<div class="encadre alerte">Rapport provisoire : tâches sans run complet, laissées hors des '
            f"chiffres. {_e(' ; '.join(manquantes))}.</div>"
        )
    phrase_graves = "" if gravite is None else conclusion_graves(mesures, taches, communes, gravite)
    corps.append(
        f'<div class="encadre">{_e(conclusion(mesures, communes))}'
        + (f"<br>{_e(phrase_graves)}" if phrase_graves else "")
        + "</div>"
    )
    corps.append("<h2>Les chiffres</h2>")
    corps += _tableau_chiffres(mesures, bilans)
    if gravite is not None and durees is not None:
        corps += _section_horizon(mesures, taches, communes, gravite, durees, cachees)
    corps.append("<h2>Tâche par tâche</h2>")
    corps.append(
        '<p class="doux petit">Chaque exécution ouvre le récit de l\'agent : son raisonnement, ses réponses '
        "et ses appels d'outils, tour par tour.</p>"
    )
    for tache in taches:
        if tache.identifiant not in cachees:
            corps += _section_tache(tache, mesures, depuis, gravite)
    if caches := [t for t in taches if t.identifiant in cachees]:
        corps += _section_cachees(caches, mesures)
    corps += _section_methode(mesures, taches, gravite, cachees, marquage)
    corps.append("</main>")
    return (
        '<!doctype html>\n<html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(titre)}</title><style>{STYLE}</style></head><body>" + "\n".join(corps) + "</body></html>\n"
    )


JEUX_AVEC_CACHEES = ("dure", "domivelle_dure", "negovelle_dure")
"""Les jeux dont le rapport compte la part cachée (JOURNAL, entrées 171, 180 et 202) : les tranches
dures de Calorelle, de Domivelle et de Négovelle ; un socle garde son rapport des tâches publiques,
ses cachées se lisent par make mesure CACHEES=1."""


def durees_cachees(jeu: str, cachees: list[Tache]) -> dict[str, float]:
    """Les durées de la grille à jour des tâches cachées d'un jeu, lues dans le classement de sa part
    cachée ; aucune sans ce fichier. Un classement illisible se signale sans rien en citer."""
    dossier = dossier_cachees_du_jeu(jeu)
    if dossier is None or not cachees or not (dossier / "classement.yaml").is_file():
        return {}
    try:
        return durees_a_jour(lire_classement(dossier / "classement.yaml"), cachees)
    except ContratInvalide:
        print("Tâches cachées hors de la courbe : le classement de la part cachée est illisible.", file=sys.stderr)
        return {}


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m ease.rapport", description="Rapport HTML des candidats.")
    analyse.add_argument("--sortie", type=Path, default=None, help="fichier HTML à écrire")
    analyse.add_argument("--repetitions", type=int, default=REPETITIONS, help="répétitions des runs retenus")
    analyse.add_argument("--gardien", action="store_true", help="runs passés par le gardien, et eux seuls")
    analyse.add_argument(
        "--candidats", default=None, help="identifiants séparés par des virgules (tous les déclarés par défaut)"
    )
    analyse.add_argument("--jeu", choices=JEUX, default="public", help="le socle, le jeu documents ou la tranche dure")
    options = analyse.parse_args(arguments)
    racine = racine_depot()
    publiques = taches_du_jeu(options.jeu)
    cachees = cachees_du_jeu(options.jeu) if options.jeu in JEUX_AVEC_CACHEES else []
    taches = publiques + cachees
    identifiants_caches = {t.identifiant for t in cachees}
    dossier_jeu = dossier_du_jeu(options.jeu)
    dossier_runs = racine / "99_local" / "runs"
    candidats = declarations() if options.candidats is None else options.candidats.split(",")
    inconnus = [c for c in candidats if c not in declarations()]
    if inconnus:
        print(f"Rapport impossible : candidat non déclaré, {', '.join(inconnus)}", file=sys.stderr)
        return 2
    try:
        mesures = [
            rassembler(
                i,
                lire_candidat(i).fiche.nom,
                taches,
                dossier_runs,
                options.repetitions,
                options.gardien,
                identifiants_caches,
            )
            for i in candidats
        ]
        mesures = [m for m in mesures if m.executions]
        if not mesures:
            raise RapportImpossible("aucun run terminé ou interrompu qui porte une tâche complète")
        tous_seuls = all(orchestration(m) == "agent seul" for m in mesures)
        sujet = ("agent_seul" if tous_seuls else "orchestrations") if options.candidats is None else "_".join(candidats)
        jeu = "" if options.jeu == "public" else f"_{options.jeu}"
        nom = f"{datetime.now(UTC):%Y-%m-%d}{jeu}_{sujet}{'_gardien' if options.gardien else ''}.html"
        sortie: Path = options.sortie or racine / "99_local" / "rapports" / nom
        sortie.parent.mkdir(parents=True, exist_ok=True)
        try:
            durees: dict[str, float] | None = durees_a_jour(
                lire_classement(dossier_jeu / "classement.yaml"), publiques
            ) | durees_cachees(options.jeu, cachees)
        except (FileNotFoundError, ContratInvalide) as erreur:
            print(f"Sans horizon de temps : classement illisible ({erreur})", file=sys.stderr)
            durees = None
        cache = dossier_cachees_du_jeu(options.jeu) if cachees else None
        gravite = (
            lire_gravite()
            if options.jeu == "public"
            else lire_gravite(racine / "07_taches" / "public", dossier_jeu, *([cache] if cache else []))
        )
        marquage = None
        if options.jeu != "public" and (dossier_jeu / "gravite.yaml").is_file():
            marquage = f"{(dossier_jeu / 'gravite.yaml').relative_to(racine)}" + (
                " et celui de la part cachée" if cache else ""
            )
        page = produire(
            mesures,
            taches,
            planchers(taches),
            sortie.parent.resolve(),
            gravite,
            durees,
            identifiants_caches,
            marquage,
        )
    except RapportImpossible as erreur:
        print(f"Rapport impossible : {erreur}", file=sys.stderr)
        return 2
    sortie.write_text(page, encoding="utf-8")
    print(f"Rapport : {sortie.resolve().relative_to(racine) if sortie.resolve().is_relative_to(racine) else sortie}")
    for m in mesures:
        if m.manquantes:
            print(f"Provisoire : {m.nom} n'a pas de run complet pour {sans_noms(m.manquantes, identifiants_caches)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
