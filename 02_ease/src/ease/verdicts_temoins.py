"""Verdicts du juge réel sur les textes des témoins : make verdicts-temoins.

    python -m ease.verdicts_temoins

Les témoins parfait, toujours faux et tricheurs écrivent des courriels connus d'avance. Le juge
réel (ease.juge) les tranche une fois, en heures creuses de DeepSeek ; ses verdicts vont dans
07_taches/public/etalon/verdicts_temoins.json, suivi par git, sans autre verdict que ceux servis.
Les tests et make temoins les rejouent ensuite sans appel à l'API (ease.temoins.juge_rejoue). À
relancer quand un texte de témoin, un critère du juge ou sa grille change.
"""

from __future__ import annotations

import sys

from ease.chargement import racine_depot
from ease.creneaux import refus_heures_creuses
from ease.executeur import ArretDuRun, maintenant
from ease.juge import JugeIndisponible, juge_du_banc, jugement
from ease.solutions_pme import TRICHEURS_PME
from ease.temoins import VERDICTS_TEMOINS, Temoin, TemoinParfait, TemoinToujoursFaux, passer, terrain_pme, tricheur_pme


def main(arguments: list[str] | None = None) -> int:
    del arguments
    refus = refus_heures_creuses(maintenant())
    if refus is not None:
        print(f"Juge non lancé : {refus}.", file=sys.stderr)
        return 4
    try:
        juge = juge_du_banc(racine_depot(), cache=VERDICTS_TEMOINS)
    except JugeIndisponible as erreur:
        print(f"Juge non lancé : {erreur}.", file=sys.stderr)
        return 2
    terrain = terrain_pme()
    temoins: list[Temoin] = [
        TemoinParfait(terrain),
        TemoinToujoursFaux(terrain),
        *(tricheur_pme(triche) for triche in TRICHEURS_PME),
    ]
    conforme = True
    try:
        for temoin in temoins:
            _, resume = passer(temoin, repetitions=1, juge=jugement(juge))
            accord = resume.taux == temoin.taux_attendu
            conforme &= accord
            print(
                f"{temoin.identifiant} : {resume.reussites}/{resume.executions} réussie(s), "
                f"attendu {temoin.taux_attendu:.0%} : {'conforme' if accord else 'ÉCART'}".replace("%", " %")
            )
    except ArretDuRun as arret:
        print(f"Arrêt : {arret}. Les verdicts déjà rendus restent gardés.", file=sys.stderr)
        return 4
    retires = juge.elaguer()
    cout = f"{juge.cout_dollars:.4f}".replace(".", ",")
    chemin = VERDICTS_TEMOINS.relative_to(racine_depot())
    print(f"\nVerdicts gardés dans {chemin} ({retires} retiré(s)) ; coût des appels : {cout} $")
    print("Témoins conformes avec le juge." if conforme else "ÉCART : un témoin ne donne pas le taux attendu.")
    return 0 if conforme else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
