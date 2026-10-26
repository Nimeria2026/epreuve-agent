"""Le témoin parfait ne se sert que de ce qu'il a vu (JOURNAL, entrée 100).

Le budget d'une tâche vaut 25 étapes plus deux fois celles de son témoin parfait
(ease.taches.budget_etapes). Un témoin qui connaît d'avance un code client, le nom d'un fichier ou
les codes du tarif fait donc un budget trop court : le run de DeepSeek sur t36 à t43 s'est arrêté
quatre fois au budget pour cette raison. Chaque témoin joue ici sur un état frais, par les vrais
services, et chaque argument qu'il passe doit venir de l'énoncé, de l'orientation ou d'une sortie
d'outil antérieure (ease.temoins.ce_que_le_temoin_n_a_pas_vu)."""

from __future__ import annotations

from pathlib import Path

import pytest
from ease.chargement import racine_depot
from ease.solutions_pme import SOLUTIONS_PME
from ease.taches import lire_taches
from ease.temoins import ce_que_le_temoin_n_a_pas_vu

TACHES = {t.identifiant: t for t in lire_taches(racine_depot() / "07_taches" / "public")}


@pytest.mark.parametrize("identifiant", sorted(SOLUTIONS_PME), ids=lambda i: i[:3])
def test_le_temoin_parfait_ne_se_sert_que_de_ce_qu_il_a_vu(identifiant: str, tmp_path: Path) -> None:
    assert ce_que_le_temoin_n_a_pas_vu(TACHES[identifiant], SOLUTIONS_PME[identifiant], tmp_path / "pme") == []


def test_un_temoin_qui_sait_d_avance_un_code_client_est_repere(tmp_path: Path) -> None:
    """Le témoin de t42 avant l'entrée 100 : il ouvrait les deux devis de M. Dubois sans les chercher."""
    t42 = TACHES["t42_ecart_entre_deux_devis"]
    devine = [a for a in SOLUTIONS_PME[t42.identifiant] if a[0] not in ("lister", "lire") and a[0] != "lister_devis"]
    devine.insert(0, ("lire", {"chemin": "commun/manuel_procedures.md"}))
    assert ce_que_le_temoin_n_a_pas_vu(t42, devine, tmp_path / "pme") == [
        "3:consulter_devis.numero=DV-2026-002",
        "4:consulter_devis.numero=DV-2026-010",
    ]
