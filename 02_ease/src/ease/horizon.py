"""L'horizon de temps d'un candidat : la durée humaine des tâches qu'il réussit à un seuil donné.

Le calcul est fixé par le cadrage (`00_docs/sources/2026-10-13_cadrage_horizon_de_temps.md`, §4 et
section du 2026-10-14 ; JOURNAL, entrées 121 et 129), d'après METR (Kwa et al., *Measuring AI Ability
to Complete Long Software Tasks*, version 4 du 2026-07-10) :

- chaque essai est un point : la durée humaine de sa tâche en abscisse, en logarithme de base 2, sa
  réussite en ordonnée ; tous les essais pèsent pareil (choix H2 d'Alexandre) ;
- une courbe logistique, ajustée par maximum de vraisemblance avec une pénalité faible sur ses deux
  paramètres, comme METR : sans elle, un échantillon sans aucun échec n'a pas de courbe finie ;
- l'horizon à un seuil est la durée jusqu'où la courbe reste au-dessus de ce seuil, en partant de la
  tâche la plus courte, lu dans la plage des tâches. L'infini se lit « au-delà de » la plus longue,
  zéro « en deçà de » la plus courte ; une courbe qui monte donne l'une de ces deux lectures.

La fourchette vient du bootstrap à deux niveaux du rapport, la courbe refaite à chaque tirage
(`rapport.bootstrap_plusieurs` avec `horizons` pour statistique).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

PENALITE = 0.1
"""Poids de la pénalité, la moitié de PENALITE fois la somme des carrés des deux paramètres ; les
tests vérifient que l'horizon tient de 0,01 à 0,2."""
SEUILS = (0.8, 0.5)
ITERATIONS = 100
TOLERANCE = 1e-10

type Point = tuple[float, bool]
"""Un essai : la durée humaine de sa tâche, en minutes, et sa réussite."""


class AjustementImpossible(RuntimeError):
    """La méthode de Newton n'a pas convergé ; cela ne devrait pas arriver avec une pénalité positive."""


@dataclass(frozen=True)
class Courbe:
    """Réussite attendue à une durée t, en minutes : 1 / (1 + exp(-(a + b log2 t)))."""

    a: float
    b: float
    """La pente : ce que gagne le logit de la réussite quand la durée double ; négative si la réussite
    baisse avec la durée."""

    def reussite(self, minutes: float) -> float:
        return _sigmoide(self.a + self.b * math.log2(minutes))


def _sigmoide(z: float) -> float:
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def _softplus(z: float) -> float:
    """log(1 + exp(z)), sans débordement."""
    return max(z, 0.0) + math.log1p(math.exp(-abs(z)))


def _comptes(points: Iterable[Point]) -> list[tuple[float, float, int]]:
    """(log2 de la durée, 1 ou 0, nombre d'essais) : les essais d'une même tâche se regroupent."""
    comptes: Counter[tuple[float, bool]] = Counter()
    for minutes, reussi in points:
        if not (math.isfinite(minutes) and minutes > 0):
            raise ValueError(f"durée invalide : {minutes} min")
        comptes[(minutes, reussi)] += 1
    if not comptes:
        raise ValueError("aucun essai")
    return [(math.log2(m), 1.0 if r else 0.0, n) for (m, r), n in comptes.items()]


def _objectif(comptes: Sequence[tuple[float, float, int]], a: float, b: float, penalite: float) -> float:
    """La log-vraisemblance pénalisée, à maximiser."""
    total = 0.0
    for x, y, n in comptes:
        z = a + b * x
        total -= n * (_softplus(-z) if y else _softplus(z))
    return total - penalite / 2 * (a * a + b * b)


def ajuster(points: Iterable[Point], penalite: float = PENALITE) -> Courbe:
    """La courbe logistique de la réussite selon le logarithme de la durée. La fonction maximisée est
    strictement concave grâce à la pénalité : un seul maximum, que la méthode de Newton atteint ; un
    pas qui ferait baisser l'objectif est divisé par deux."""
    if not penalite > 0:
        raise ValueError("la pénalité doit être positive")
    comptes = _comptes(points)
    a = b = 0.0
    valeur = _objectif(comptes, a, b, penalite)
    for _ in range(ITERATIONS):
        ga, gb = -penalite * a, -penalite * b
        haa, hab, hbb = penalite, 0.0, penalite
        for x, y, n in comptes:
            p = _sigmoide(a + b * x)
            ga += n * (y - p)
            gb += n * (y - p) * x
            w = n * p * (1 - p)
            haa += w
            hab += w * x
            hbb += w * x * x
        determinant = haa * hbb - hab * hab
        da = (hbb * ga - hab * gb) / determinant
        db = (haa * gb - hab * ga) / determinant
        pas = 1.0
        while True:
            na, nb = a + pas * da, b + pas * db
            nouvelle = _objectif(comptes, na, nb, penalite)
            if nouvelle >= valeur or pas < 1e-12:
                break
            pas /= 2
        a, b, valeur = na, nb, nouvelle
        if abs(pas * da) + abs(pas * db) < TOLERANCE:
            return Courbe(a, b)
    raise AjustementImpossible(f"pas de convergence en {ITERATIONS} itérations")


def horizon(courbe: Courbe, seuil: float, plage: tuple[float, float]) -> float:
    """La durée, en minutes, jusqu'où la courbe reste au-dessus du seuil depuis la plus courte des
    tâches ; math.inf si elle n'en passe jamais sous le seuil avant la plus longue (« au-delà de »),
    0.0 si elle est déjà dessous à la plus courte (« en deçà de »)."""
    plus_courte, plus_longue = plage
    if not 0 < seuil < 1:
        raise ValueError(f"seuil hors de ]0 ; 1[ : {seuil}")
    if not 0 < plus_courte <= plus_longue:
        raise ValueError(f"plage invalide : {plage}")
    if courbe.reussite(plus_courte) < seuil:
        return 0.0
    if courbe.b >= 0:
        return math.inf
    logarithme = (math.log(seuil / (1 - seuil)) - courbe.a) / courbe.b
    return math.inf if logarithme >= math.log2(plus_longue) else 2.0**logarithme


def horizons(
    plage: tuple[float, float], seuils: Sequence[float] = SEUILS, penalite: float = PENALITE
) -> Callable[[list[Point]], tuple[float, ...]]:
    """La statistique du bootstrap : la courbe ajustée sur les essais tirés, puis un horizon par seuil,
    tous lus dans la plage des tâches du banc, pas dans celle du tirage."""

    def statistique(points: list[Point]) -> tuple[float, ...]:
        courbe = ajuster(points, penalite)
        return tuple(horizon(courbe, s, plage) for s in seuils)

    return statistique
