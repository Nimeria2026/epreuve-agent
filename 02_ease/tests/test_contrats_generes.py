"""Le code généré depuis 01_contrats/ est à jour : un schéma modifié sans make contrats échoue ici."""

from __future__ import annotations

import subprocess
import sys

from ease.taches import racine_depot


def test_le_code_des_contrats_est_a_jour() -> None:
    racine = racine_depot()
    resultat = subprocess.run(
        [sys.executable, str(racine / "09_outillage" / "scripts" / "generer_contrats.py"), "--verifier"],
        capture_output=True,
        text=True,
        cwd=racine,
    )
    assert resultat.returncode == 0, resultat.stderr
