"""Intervalle de Wilson, pass^k et résumé d'un run."""

from __future__ import annotations

import pytest
from ease.statistiques import intervalle_wilson, pass_k


def test_wilson_retrouve_l_exemple_du_brief() -> None:
    bas, haut = intervalle_wilson(38, 40)
    assert (round(bas * 100, 1), round(haut * 100, 1)) == (83.5, 98.6)


def test_wilson_reste_entre_0_et_1_aux_extremes() -> None:
    assert intervalle_wilson(0, 8)[0] == 0.0
    assert intervalle_wilson(8, 8)[1] == 1.0
    assert round(intervalle_wilson(8, 8)[0], 3) == 0.676


def test_wilson_refuse_les_comptes_impossibles() -> None:
    with pytest.raises(ValueError):
        intervalle_wilson(5, 4)
    with pytest.raises(ValueError):
        intervalle_wilson(0, 0)


def test_pass_k_suit_l_estimateur_de_tau_bench() -> None:
    assert pass_k([(2, 4)], 1) == 0.5
    assert pass_k([(2, 4)], 2) == pytest.approx(1 / 6)
    assert pass_k([(2, 4)], 4) == 0.0
    assert pass_k([(4, 4), (0, 4)], 4) == 0.5


def test_pass_k_refuse_k_superieur_aux_essais() -> None:
    with pytest.raises(ValueError):
        pass_k([(2, 4)], 5)
