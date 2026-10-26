"""Wattmètre : énergie de la carte relevée par une commande qui imite nvidia-smi."""

from __future__ import annotations

import sys
import time

from ease.energie import Wattmetre


def _imitation(*lignes: str) -> list[str]:
    """Commande qui écrit une ligne toutes les 50 ms, puis attend qu'on l'arrête, comme nvidia-smi -lms."""
    script = f"import time\nfor l in {list(lignes)!r}:\n    print(l, flush=True)\n    time.sleep(0.05)\ntime.sleep(30)"
    return [sys.executable, "-c", script]


def test_une_puissance_constante_donne_puissance_fois_duree() -> None:
    debut = time.monotonic()
    with Wattmetre(_imitation("100.00", "100.00", "100.00")) as wattmetre:
        time.sleep(0.5)
    duree = time.monotonic() - debut
    energie = wattmetre.energie_wh
    assert not isinstance(energie, str)
    joules = energie * 3600
    # Le wattmètre compte de son entrée à sa sortie, un peu moins que la durée vue d'ici.
    assert 100 * (duree - 0.1) < joules <= 100 * duree


def test_sans_commande_l_energie_est_inconnue() -> None:
    with Wattmetre(["commande-absente-du-systeme"]) as wattmetre:
        pass
    assert wattmetre.energie_wh == "?"


def test_une_carte_qui_ne_donne_pas_sa_puissance_laisse_l_energie_inconnue() -> None:
    with Wattmetre(_imitation("[N/A]", "[N/A]")) as wattmetre:
        time.sleep(0.3)
    assert wattmetre.energie_wh == "?"
