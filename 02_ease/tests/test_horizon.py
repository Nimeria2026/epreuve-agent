"""L'horizon de temps (ease.horizon ; cadrage du 2026-10-13, section du 2026-10-14 ; JOURNAL, entrée 129)."""

from __future__ import annotations

import math

import pytest
from ease.horizon import Courbe, Point, ajuster, horizon, horizons
from ease.rapport import bootstrap, bootstrap_plusieurs

PLAGE = (1.0, 64.0)


def _points(a: float, b: float, essais: int = 2000) -> list[Point]:
    """Des essais aux durées 1, 2, 4… 64 minutes, réussis dans la proportion exacte d'une courbe connue."""
    points: list[Point] = []
    for x in range(7):
        reussis = round(essais * Courbe(a, b).reussite(2.0**x))
        points += [(2.0**x, True)] * reussis + [(2.0**x, False)] * (essais - reussis)
    return points


def test_la_courbe_connue_est_retrouvee_et_son_horizon_avec() -> None:
    """Réussite 1 / (1 + exp(-(3 - log2 t))) : la moitié à 8 minutes, 80 % à 2^(3 - ln 4) minutes."""
    courbe = ajuster(_points(3.0, -1.0))
    assert courbe.a == pytest.approx(3.0, abs=0.02) and courbe.b == pytest.approx(-1.0, abs=0.01)
    assert horizon(courbe, 0.5, PLAGE) == pytest.approx(8.0, rel=0.02)
    assert horizon(courbe, 0.8, PLAGE) == pytest.approx(2 ** (3 - math.log(4)), rel=0.02)


@pytest.mark.parametrize("penalite", [0.01, 0.2])
def test_l_horizon_tient_quand_la_penalite_change(penalite: float) -> None:
    points = _points(3.0, -1.0, essais=50)
    reference = horizon(ajuster(points), 0.5, PLAGE)
    assert horizon(ajuster(points, penalite), 0.5, PLAGE) == pytest.approx(reference, rel=0.01)


def test_sans_aucun_echec_l_horizon_est_au_dela_de_la_plus_longue_tache() -> None:
    """La pénalité garde une courbe finie ; elle reste au-dessus de tout seuil sur la plage."""
    courbe = ajuster([(m, True) for m in (1.0, 4.0, 64.0) for _ in range(5)])
    assert math.isfinite(courbe.a) and math.isfinite(courbe.b)
    assert horizon(courbe, 0.8, PLAGE) == math.inf and horizon(courbe, 0.5, PLAGE) == math.inf


def test_sans_aucune_reussite_l_horizon_est_en_deca_de_la_plus_courte() -> None:
    courbe = ajuster([(m, False) for m in (1.0, 4.0, 64.0) for _ in range(5)])
    assert horizon(courbe, 0.5, PLAGE) == 0.0


def test_une_courbe_qui_monte_ne_donne_jamais_une_duree() -> None:
    """Manquer les tâches courtes et réussir les longues n'est pas une limite de durée."""
    montante = Courbe(-2.0, 1.0)  # 12 % à 1 minute, 98 % à 64 minutes
    assert horizon(montante, 0.5, PLAGE) == 0.0
    assert horizon(Courbe(3.0, 0.2), 0.8, PLAGE) == math.inf


def test_la_lecture_reste_dans_la_plage_des_taches() -> None:
    courbe = Courbe(3.0, -1.0)  # la moitié à 8 minutes
    assert horizon(courbe, 0.5, (1.0, 4.0)) == math.inf
    assert horizon(courbe, 0.5, (16.0, 64.0)) == 0.0
    assert horizon(courbe, 0.5, (1.0, 8.0)) == math.inf  # la courbe touche le seuil au bout, sans passer dessous


def test_les_entrees_invalides_sont_refusees() -> None:
    with pytest.raises(ValueError, match="aucun essai"):
        ajuster([])
    with pytest.raises(ValueError, match="durée invalide"):
        ajuster([(0.0, True)])
    with pytest.raises(ValueError, match="pénalité"):
        ajuster([(1.0, True)], penalite=0.0)
    with pytest.raises(ValueError, match="seuil"):
        horizon(Courbe(0.0, -1.0), 1.0, PLAGE)
    with pytest.raises(ValueError, match="plage"):
        horizon(Courbe(0.0, -1.0), 0.5, (4.0, 1.0))


def _part(essais: list[bool]) -> float:
    return sum(essais) / len(essais)


def test_le_bootstrap_a_plusieurs_statistiques_rend_ce_que_rend_le_bootstrap_simple() -> None:
    """Mêmes tirages, mêmes bornes : les fourchettes déjà publiées ne changent pas."""
    groupes = [[True, True, False], [True, False, False], [True, True, True], [False, False, True]]
    simple = bootstrap(groupes, _part, tirages=500)
    assert bootstrap_plusieurs(groupes, lambda tirees: (_part(tirees),), tirages=500) == [simple]


def test_la_fourchette_de_l_horizon_peut_avoir_une_borne_au_dela_de_la_plage() -> None:
    """Un candidat qui manque peu : sa fourchette va jusqu'à l'infini, lu « au-delà »."""
    groupes: list[list[Point]] = [
        [(1.0, True)] * 5,
        [(2.0, True)] * 5,
        [(4.0, True)] * 4 + [(4.0, False)],
        [(8.0, True)] * 5,
        [(16.0, True)] * 4 + [(16.0, False)],
    ]
    plage = (1.0, 16.0)
    (bas80, haut80), (bas50, haut50) = bootstrap_plusieurs(groupes, horizons(plage), tirages=300)
    assert haut80 == math.inf and haut50 == math.inf
    assert bas50 >= bas80
