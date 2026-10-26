"""Comparaisons approchées de rapidfuzz 3.14.3, refaites en bibliothèque standard.

Le banc appelle `fuzz.partial_ratio`, `fuzz.ratio`, `Levenshtein.distance` et
`process.extractOne`. À l'exécution, rapidfuzz passe par son code C++ (rapidfuzz-cpp, fichier
`rapidfuzz/fuzz_impl.hpp` de l'archive source 3.14.3, sha256 `24919371...4b5814b7b5f`), dont
`partial_ratio` diffère du repli en Python (`fuzz_py.py`) : c'est le C++ qui est porté ici, y
compris l'ordre dans lequel il évalue les fenêtres, dont dépend ce qu'il élague. rapidfuzz est
sous licence MIT (Max Bachmann).

Les calculs en virgule flottante suivent ceux du C++, opération par opération : le banc compare
ces scores à des seuils par `>=`, et un dernier bit peut changer un test.
"""

from __future__ import annotations

from collections.abc import Sequence

TAILLE_MAX = 2**64 - 1
"""`std::numeric_limits<size_t>::max()` : la distance « pas encore trouvée » du C++."""


def _masques(s1: str) -> dict[str, int]:
    """Pour chaque caractère de s1, le masque des positions où il apparaît."""
    masques: dict[str, int] = {}
    bit = 1
    for caractere in s1:
        masques[caractere] = masques.get(caractere, 0) | bit
        bit <<= 1
    return masques


def _lcs(masques: dict[str, int], longueur1: int, s2: str) -> int:
    """Longueur de la plus longue sous-suite commune, par vecteurs de bits (Hyyrö, 2004)."""
    if longueur1 == 0:
        return 0
    tous = (1 << longueur1) - 1
    v = tous
    for caractere in s2:
        u = v & masques.get(caractere, 0)
        v = ((v + u) | (v - u)) & tous
    return longueur1 - v.bit_count()


def distance_indel(s1: str, s2: str) -> int:
    """Insertions et suppressions pour passer de s1 à s2 : len1 + len2 - 2 LCS."""
    return len(s1) + len(s2) - 2 * _lcs(_masques(s1), len(s1), s2)


def _similarite(distance: int, maximum: int) -> float:
    """`normalized_similarity * 100` du C++ : 1 - distance / maximum, puis fois 100."""
    distance_normee = distance / maximum if maximum != 0 else 0.0
    return (1.0 - distance_normee) * 100


def ratio(s1: str, s2: str) -> float:
    """`fuzz.ratio` : similarité Indel normalisée, de 0 à 100 ; 100 pour deux chaînes vides."""
    return _similarite(distance_indel(s1, s2), len(s1) + len(s2))


def _partial_ratio_impl(s1: str, s2: str) -> float:
    """`fuzz_detail::partial_ratio_impl`, sans seuil (score_cutoff à 0) ; len(s1) <= len(s2)."""
    longueur1, longueur2 = len(s1), len(s2)
    masques = _masques(s1)
    meilleur = 0.0
    seuil = 0.0

    def indel(debut: int, fin: int) -> int:
        return longueur1 + (fin - debut) - 2 * _lcs(masques, longueur1, s2[debut:fin])

    if longueur2 > longueur1:
        maximum = longueur1 * 2
        # NormSim_to_NormDist(0) vaut min(1, 1 - 0 + 1e-5) = 1 : la distance seuil est le maximum.
        distance_seuil = maximum
        meilleure_distance = TAILLE_MAX
        scores: list[int | None] = [None] * (longueur2 - longueur1)
        fenetres: list[tuple[int, int]] = [(0, longueur2 - longueur1 - 1)]
        while fenetres:
            nouvelles: list[tuple[int, int]] = []
            for premiere, seconde in fenetres:
                for position in (premiere, seconde):
                    if scores[position] is None:
                        trouve = indel(position, position + longueur1)
                        scores[position] = trouve
                        if trouve < distance_seuil:
                            distance_seuil = meilleure_distance = trouve
                            if meilleure_distance == 0:
                                return 100.0
                ecart = seconde - premiere
                if ecart == 1:
                    continue
                a, b = scores[premiere], scores[seconde]
                assert a is not None and b is not None
                # Deux fenêtres voisines diffèrent d'au plus 2 : connus // 2 <= ecart, pas de
                # dépassement par le bas des entiers non signés du C++.
                connus = abs(a - b)
                amelioration = (ecart - connus // 2) // 2 * 2
                if min(a, b) - amelioration < distance_seuil:
                    centre = ecart // 2
                    nouvelles.append((premiere, premiere + centre))
                    nouvelles.append((premiere + centre, seconde))
            fenetres = nouvelles
        if meilleure_distance != TAILLE_MAX:
            score = 1.0 - meilleure_distance / maximum
            score *= 100
            if score >= seuil:
                seuil = meilleur = score

    ensemble = set(s1)
    for i in range(1, longueur1):
        if s2[i - 1] not in ensemble:
            continue
        candidat = _similarite(indel(0, i), longueur1 + i)
        if candidat >= seuil and candidat > meilleur:
            seuil = meilleur = candidat
            if meilleur == 100.0:
                return meilleur
    for i in range(longueur2 - longueur1, longueur2):
        if s2[i] not in ensemble:
            continue
        candidat = _similarite(indel(i, longueur2), longueur1 + longueur2 - i)
        if candidat >= seuil and candidat > meilleur:
            seuil = meilleur = candidat
            if meilleur == 100.0:
                return meilleur
    return meilleur


def partial_ratio(s1: str, s2: str) -> float:
    """`fuzz.partial_ratio` : la meilleure fenêtre de la plus longue chaîne pour la plus courte."""
    if len(s1) > len(s2):
        s1, s2 = s2, s1
    if not s1 or not s2:
        return 100.0 if len(s1) == len(s2) else 0.0
    score = _partial_ratio_impl(s1, s2)
    if score != 100 and len(s1) == len(s2):
        score = max(score, _partial_ratio_impl(s2, s1))
    return score


def levenshtein(s1: str, s2: str, plafond: int | None = None) -> int:
    """`Levenshtein.distance`, poids 1 ; au-delà du plafond, rend plafond + 1."""
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    if plafond is not None and len(s1) - len(s2) > plafond:
        return plafond + 1
    precedente = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1, 1):
        courante = [i]
        for j, c2 in enumerate(s2, 1):
            courante.append(min(precedente[j] + 1, courante[j - 1] + 1, precedente[j - 1] + (c1 != c2)))
        if plafond is not None and min(courante) > plafond:
            return plafond + 1
        precedente = courante
    return precedente[-1]


def premier_meilleur(motif: str, morceaux: Sequence[str], plafond: int) -> tuple[int, int] | None:
    """`process.extractOne(motif, morceaux, scorer=Levenshtein.distance)`, réduit à ce que le banc
    en garde : l'indice et la distance du premier morceau le plus proche, si elle est au plus le
    plafond ; None sinon (le banc écarte alors la correspondance)."""
    meilleur: tuple[int, int] | None = None
    for indice, morceau in enumerate(morceaux):
        distance = levenshtein(motif, morceau, plafond)
        if distance <= plafond and (meilleur is None or distance < meilleur[1]):
            meilleur = (indice, distance)
            if distance == 0:
                break
    return meilleur
