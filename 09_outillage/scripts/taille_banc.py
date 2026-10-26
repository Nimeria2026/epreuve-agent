"""Nombre de tâches pour établir un écart de réussite entre deux candidats mesurés sur les mêmes tâches.

    python 09_outillage/scripts/taille_banc.py

Approximation normale du test apparié (McNemar) : risque 5 % bilatéral, puissance 80 %, une
exécution par tâche. Deux cas : réussites des deux candidats indépendantes, ou corrélées
(corrélation 0,4 : les tâches dures le sont pour les deux). Chaque taille est vérifiée par
simulation. Résultats notés au JOURNAL le 2026-10-05 (trente-neuvième entrée).
"""

from __future__ import annotations

import math
import random

Z = 1.959964 + 0.841621
"""Quantiles normaux : 95 % bilatéral, puis puissance 80 %."""


def _jointes(pa: float, pb: float, rho: float) -> tuple[float, float]:
    """Probabilités que seul A réussisse, puis que seul B réussisse."""
    p11 = pa * pb + rho * math.sqrt(pa * (1 - pa) * pb * (1 - pb))
    return pa - p11, pb - p11


def taches_necessaires(pa: float, pb: float, rho: float) -> int:
    p10, p01 = _jointes(pa, pb, rho)
    ecart = pa - pb
    return math.ceil(Z * Z * (p10 + p01 - ecart * ecart) / (ecart * ecart))


def puissance_simulee(n: int, pa: float, pb: float, rho: float, essais: int = 4000, graine: int = 1) -> float:
    hasard = random.Random(graine)
    p10, p01 = _jointes(pa, pb, rho)
    etablis = 0
    for _ in range(essais):
        seul_a = seul_b = 0
        for _ in range(n):
            u = hasard.random()
            if u < p10:
                seul_a += 1
            elif u < p10 + p01:
                seul_b += 1
        ecart = (seul_a - seul_b) / n
        variance = (seul_a + seul_b) / n - ecart * ecart
        if variance > 0 and ecart / math.sqrt(variance / n) > 1.959964:
            etablis += 1
    return etablis / essais


def main() -> None:
    for pa, pb in ((0.90, 0.80), (0.85, 0.65), (0.80, 0.50)):
        for rho in (0.0, 0.4):
            n = taches_necessaires(pa, pb, rho)
            puissance = puissance_simulee(n, pa, pb, rho)
            print(f"{pa:.0%} contre {pb:.0%}, corrélation {rho} : {n} tâches, puissance simulée {puissance:.2f}")


if __name__ == "__main__":
    main()
