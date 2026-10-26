"""Données de τ²-bench pour les tests du pont, récupérées dès le chargement des tests (le réseau
sert la première fois seulement, puis 99_local/tau2/ suffit), et TAU2_DATA_DIR posé avant tout
import de tau2 : τ²-bench lit ce dossier à son premier import, celui de `pont` par les tests."""

from __future__ import annotations

import fcntl
import os

from bancs_publics.tau2_bench.donnees import dossier_donnees, dossier_local, recuperer

# Les tests tournent en parallèle (make tests, pytest-xdist) : chaque processus charge ce fichier,
# et un seul à la fois vérifie ou télécharge les données, pour qu'un clone neuf ne les écrive pas
# à plusieurs (JOURNAL, entrée 258).
dossier_local().mkdir(parents=True, exist_ok=True)
with (dossier_local() / ".verrou_tests").open("w", encoding="utf-8") as verrou:
    fcntl.flock(verrou, fcntl.LOCK_EX)
    DONNEES = recuperer()
os.environ["TAU2_DATA_DIR"] = str(dossier_donnees(DONNEES))
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
