"""Heures pleines de DeepSeek : un run au tarif des heures creuses refuse de commencer trop près d'elles.

Le 2026-10-05 est un lundi, le 2026-10-10 un samedi.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from ease.creneaux import en_heures_pleines, refus_heures_creuses


def _utc(jour: int, heure: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, jour, heure, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("instant", "attendu"),
    [
        (_utc(5, 1), True),  # début inclus
        (_utc(5, 3, 59), True),
        (_utc(5, 4), False),  # fin exclue
        (_utc(5, 5, 59), False),
        (_utc(5, 6), True),
        (_utc(5, 9, 59), True),
        (_utc(5, 10), False),
        (_utc(10, 2), False),  # samedi
        (_utc(11, 7), False),  # dimanche
    ],
)
def test_les_heures_pleines_sont_1h_4h_et_6h_10h_utc_en_semaine(instant: datetime, attendu: bool) -> None:
    assert en_heures_pleines(instant) is attendu


def test_l_heure_de_paris_est_convertie_en_utc() -> None:
    # 8 h à Paris en octobre (heure d'été, UTC+2) : 6 h UTC, heures pleines.
    assert en_heures_pleines(datetime(2026, 10, 5, 8, 0, tzinfo=ZoneInfo("Europe/Paris")))
    assert not en_heures_pleines(datetime(2026, 10, 5, 7, 59, tzinfo=ZoneInfo("Europe/Paris")))


def test_un_lancement_en_heures_creuses_loin_des_heures_pleines_est_accepte() -> None:
    assert refus_heures_creuses(_utc(5, 12)) is None
    assert refus_heures_creuses(_utc(5, 5, 44)) is None  # 6 h dans 16 minutes


def test_un_lancement_moins_de_15_minutes_avant_les_heures_pleines_est_refuse() -> None:
    refus = refus_heures_creuses(_utc(5, 5, 50))
    assert refus is not None and "à 06:00 UTC" in refus
    refus = refus_heures_creuses(_utc(5, 0, 50))
    assert refus is not None and "à 01:00 UTC" in refus


def test_un_lancement_en_heures_pleines_est_refuse() -> None:
    refus = refus_heures_creuses(_utc(5, 2))
    assert refus is not None and "maintenant" in refus


def test_la_nuit_du_vendredi_au_samedi_reste_creuse() -> None:
    assert refus_heures_creuses(_utc(9, 23, 55)) is None
    assert refus_heures_creuses(_utc(10, 0, 50)) is None
