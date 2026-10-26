"""Heures pleines de DeepSeek : un run payé au tarif des heures creuses ne doit pas y déborder.

D'après la page des prix de DeepSeek, consultée le 2026-10-05 : heures pleines de 1 h à 4 h et
de 6 h à 10 h UTC, du lundi au vendredi, hors jours fériés chinois. Les jours fériés ne sont pas
connus ici : ils sont traités comme des jours ordinaires, ce qui peut refuser un run à tort mais
jamais en accepter un qui serait facturé plus cher. Source et prix :
00_docs/sources/2026-10-05_reglages_des_modeles.md.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

HEURES_PLEINES_UTC = ((1, 4), (6, 10))
MARGE = timedelta(minutes=15)
"""Une exécution ne commence pas si les heures pleines arrivent avant ce délai."""


def en_heures_pleines(instant: datetime) -> bool:
    """Vrai si l'instant tombe dans les heures pleines de DeepSeek."""
    utc = instant.astimezone(UTC)
    return utc.weekday() < 5 and any(debut <= utc.hour < fin for debut, fin in HEURES_PLEINES_UTC)


def refus_heures_creuses(instant: datetime, marge: timedelta = MARGE) -> str | None:
    """La raison de ne pas lancer une exécution maintenant, ou None si les heures creuses le permettent."""
    pas = timedelta(minutes=1)
    moment = instant
    while moment <= instant + marge:
        if en_heures_pleines(moment):
            debut = "maintenant" if moment == instant else f"à {moment.astimezone(UTC):%H:%M} UTC"
            return f"heures pleines de DeepSeek {debut} (1 h-4 h et 6 h-10 h UTC, lundi à vendredi)"
        moment += pas
    return None
