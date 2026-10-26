"""Énergie électrique de la carte graphique pendant une exécution, relevée par nvidia-smi.

Un modèle local n'a pas de prix par jeton : son coût est l'électricité. Le wattmètre lance
nvidia-smi en boucle (une mesure de puissance toutes les 500 ms), et additionne puissance fois
durée entre deux mesures. Il ne voit que la carte graphique : le processeur, la mémoire et
l'alimentation consomment en plus, et le chiffre est donc un minimum. Sans nvidia-smi, ou sans
aucune mesure, l'énergie vaut « ? ».
"""

from __future__ import annotations

import subprocess
import threading
import time
from types import TracebackType
from typing import Literal

COMMANDE = ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits", "-lms", "500", "-i", "0"]


class Wattmetre:
    """Ouvert par `with Wattmetre() as wattmetre:` autour d'une exécution ; lire ensuite energie_wh."""

    def __init__(self, commande: list[str] | None = None) -> None:
        self._commande = commande or COMMANDE
        self._processus: subprocess.Popen[str] | None = None
        self._fil: threading.Thread | None = None
        self._debut = 0.0
        self._joules = 0.0
        self._derniere: tuple[float, float] | None = None
        """(instant, puissance en watts) de la dernière mesure lue."""
        self._mesures = 0

    def __enter__(self) -> Wattmetre:
        self._debut = time.monotonic()
        try:
            self._processus = subprocess.Popen(
                self._commande, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
        except OSError:
            return self  # pas de nvidia-smi : l'énergie restera inconnue
        self._fil = threading.Thread(target=self._lire, daemon=True, name="wattmetre")
        self._fil.start()
        return self

    def _lire(self) -> None:
        assert self._processus is not None and self._processus.stdout is not None
        for ligne in self._processus.stdout:
            try:
                watts = float(ligne.strip())
            except ValueError:
                continue
            instant = time.monotonic()
            if self._derniere is None:
                # Avant la première mesure, on suppose la même puissance depuis le début.
                self._joules += watts * (instant - self._debut)
            else:
                self._joules += self._derniere[1] * (instant - self._derniere[0])
            self._derniere = (instant, watts)
            self._mesures += 1

    def __exit__(
        self, type_: type[BaseException] | None, erreur: BaseException | None, trace: TracebackType | None
    ) -> None:
        fin = time.monotonic()
        if self._processus is not None:
            self._processus.terminate()
            self._processus.wait()
        if self._fil is not None:
            self._fil.join(5)
        if self._derniere is not None:
            self._joules += self._derniere[1] * (fin - self._derniere[0])

    @property
    def energie_wh(self) -> float | Literal["?"]:
        """Énergie de la carte pendant l'exécution, en wattheures ; « ? » sans aucune mesure."""
        return self._joules / 3600 if self._mesures else "?"
