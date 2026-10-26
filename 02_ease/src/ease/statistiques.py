"""Statistiques d'un run : taux de réussite et sa marge, régularité (pass^k), score moyen.

Règle 2 du BRIEF : pas de conclusion sans marge d'erreur. Les erreurs techniques (API en panne,
coupure) ne sont pas des échecs de l'agent : elles sortent du calcul et sont comptées à part.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from statistics import NormalDist

from ease.contrats.resultat_execution import ResultatExecution


def intervalle_wilson(succes: int, n: int, confiance: float = 0.95) -> tuple[float, float]:
    """Intervalle de confiance de Wilson pour une proportion de succes réussites sur n."""
    if n <= 0:
        raise ValueError("n doit être strictement positif")
    if not 0 <= succes <= n:
        raise ValueError("le nombre de réussites doit être compris entre 0 et n")
    z = NormalDist().inv_cdf(1 - (1 - confiance) / 2)
    p = succes / n
    denominateur = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominateur
    marge = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominateur
    return max(0.0, centre - marge), min(1.0, centre + marge)


def pass_k(comptes: list[tuple[int, int]], k: int) -> float:
    """pass^k de τ-bench : chance qu'une tâche réussisse k essais sur k, moyennée sur les tâches.

    comptes donne, pour chaque tâche, (réussites, essais). Estimateur sans biais :
    C(réussites, k) / C(essais, k).
    """
    if not comptes:
        raise ValueError("aucune tâche")
    valeurs: list[float] = []
    for succes, essais in comptes:
        if not 1 <= k <= essais:
            raise ValueError(f"k = {k} doit être compris entre 1 et le nombre d'essais ({essais})")
        valeurs.append(math.comb(succes, k) / math.comb(essais, k))
    return math.fsum(valeurs) / len(valeurs)


@dataclass(frozen=True)
class Resume:
    """Résumé des exécutions d'un run."""

    executions: int
    erreurs_techniques: int
    reussites: int
    taux: float
    intervalle: tuple[float, float]
    score_moyen: float
    pass_k: dict[int, float]


def resumer(resultats: list[ResultatExecution]) -> Resume:
    """Résume les exécutions d'un run, erreurs techniques mises à part."""
    retenus = [r for r in resultats if r.arret != "erreur_technique"]
    if not retenus:
        raise ValueError("aucune exécution retenue : rien à résumer")
    reussites = sum(1 for r in retenus if r.reussie)
    par_tache: dict[tuple[str, int], list[bool]] = defaultdict(list)
    for resultat in retenus:
        par_tache[(resultat.tache.identifiant, resultat.tache.version)].append(resultat.reussie)
    comptes = [(sum(essais), len(essais)) for essais in par_tache.values()]
    k_max = min(essais for _, essais in comptes)
    return Resume(
        executions=len(retenus),
        erreurs_techniques=len(resultats) - len(retenus),
        reussites=reussites,
        taux=reussites / len(retenus),
        intervalle=intervalle_wilson(reussites, len(retenus)),
        score_moyen=math.fsum(r.score for r in retenus) / len(retenus),
        pass_k={k: pass_k(comptes, k) for k in range(1, k_max + 1)},
    )
