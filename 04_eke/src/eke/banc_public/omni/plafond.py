"""Le plafond de lecture d'EKE sur un document : la part des valeurs de la vérité que son texte
contient (décision d'Alexandre, journal de l'étape 6, vingt et unième entrée).

Une valeur de la vérité est trouvée si une suite de m mots consécutifs du texte d'EKE a la même
clé canonique qu'elle (`valeurs.cle`), telle quelle ou privée des signes qui la bordent (ni lettre
ni chiffre, à ses deux bouts : « +/-678 » donne aussi « 678 »), m allant de t - 1 à t + 1, où t
est le nombre de mots de la valeur écrite (au moins 1) ; une date ou une heure se cherche aussi
dans des suites de 1 à 3 mots, la plus longue de ses formes écrites (« Oct 31, 2024 » pour
« 2024-10-31 »). Les mots sont les morceaux du texte
séparés par des blancs ; une suite peut passer d'une ligne ou d'une page à la suivante. Retirer
les bords peut faire trouver 678 dans « -678 » : un signe perdu, rare, compté comme trouvé.

C'est le score qu'aurait, à la métrique du banc, un extracteur parfait limité à ce texte : il
rendrait chaque valeur trouvée à sa bonne adresse et rien d'autre, sans rien inventer, et son
`accuracy` serait la part des valeurs trouvées. Une valeur calculée par le
schéma (un nombre de lignes, un booléen, une différence) ou écrite dans une image n'est pas
trouvée, sauf si elle figure telle quelle dans le texte.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from eke.banc_public.omni.valeurs import cle, cle_texte
from eke.banc_public.omni.verite import Adresse

ECART_DE_MOTS = 1
"""Une valeur de t mots se cherche dans des suites de t - 1 à t + 1 mots du texte."""


@dataclass(frozen=True)
class Valeur:
    adresse: Adresse
    type: str
    """Type JSON de la valeur dans la vérité : str, int, float ou bool."""
    cle: str
    mots: int
    trouvee: bool


def sans_bords(texte: str) -> str:
    """Le texte privé, à ses deux bouts, de ce qui n'est ni lettre ni chiffre ; vide s'il n'a
    ni lettre ni chiffre."""
    debut, fin = 0, len(texte)
    while debut < fin and not texte[debut].isalnum():
        debut += 1
    while fin > debut and not texte[fin - 1].isalnum():
        fin -= 1
    return texte[debut:fin]


def mots_de(valeur: Any) -> int:
    return max(1, len(str(valeur).split()))


MOTS_D_UNE_DATE = 3
"""Les formats de date du banc s'écrivent en trois mots au plus (« %B %d, %Y »)."""


def tailles(mots: int, cle_: str = "") -> range:
    """Les longueurs des suites de mots où chercher une valeur de `mots` mots et de clé `cle_`."""
    bas, haut = max(1, mots - ECART_DE_MOTS), mots + ECART_DE_MOTS
    if cle_.startswith(("#d", "#t")):
        bas, haut = 1, max(haut, MOTS_D_UNE_DATE)
    return range(bas, haut + 1)


def chercher(texte: str, valeurs: Mapping[Adresse, Any]) -> list[Valeur]:
    """Chaque valeur de la vérité, trouvée ou non dans le texte."""
    mots = texte.split()
    attendues: dict[int, set[str]] = defaultdict(set)
    preparees: list[tuple[Adresse, Any, str, int]] = []
    for adresse, valeur in valeurs.items():
        k, n = cle(valeur), mots_de(valeur)
        preparees.append((adresse, valeur, k, n))
        for m in tailles(n, k):
            attendues[m].add(k)
    trouvees: dict[int, set[str]] = defaultdict(set)
    for m, cles in attendues.items():
        restantes = set(cles)
        for debut in range(len(mots) - m + 1):
            suite = " ".join(mots[debut : debut + m])
            for k in (cle_texte(suite), cle_texte(sans_bords(suite))):
                if k in restantes:
                    trouvees[m].add(k)
                    restantes.discard(k)
            if not restantes:
                break
    return [
        Valeur(adresse, type(valeur).__name__, k, n, any(k in trouvees[m] for m in tailles(n, k)))
        for adresse, valeur, k, n in preparees
    ]
