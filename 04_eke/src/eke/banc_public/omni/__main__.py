"""EKE sur OmniExtractBench, depuis la racine du dépôt :

    uv run --no-sync --all-packages python -m eke.banc_public.omni telecharger
    (puis, une fois, lire_manifeste.py dans un environnement jetable : 04_eke/tests/original/omni)
    uv run --no-sync --all-packages python -m eke.banc_public.omni convertir
    uv run --no-sync --all-packages python -m eke.banc_public.omni mesurer

`telecharger` range la version 725aaa6 dans `99_local/bancs_documents/omniextractbench/` et
écrit son manifeste ; relancé, il vérifie le jeu contre lui. `verifier` fait seulement la
vérification. `convertir` écrit le texte d'EKE de chaque document sous `sorties/flux/`.
`mesurer` cherche chaque valeur de la vérité dans ces textes et écrit la fiche sous `mesures/`.
Code de sortie 3 sur un écart du jeu, qui arrête tout ; 4 si les textes ont été écrits par un
autre code de lecture que celui d'aujourd'hui (relancer `convertir`).
"""

from __future__ import annotations

import argparse
import sys

from eke.banc_public.omni.conversion import convertir, ecrire_note, empreinte_lecture
from eke.banc_public.omni.jeu import DEPOT, DOSSIER, REVISION, charger, garder
from eke.banc_public.omni.mesure import SortiesPerimees, mesurer
from eke.banc_public.telechargement import EcartJeu, telecharger, verifier


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m eke.banc_public.omni", description="EKE sur OmniExtractBench.")
    commandes = analyse.add_subparsers(dest="commande", required=True)
    commandes.add_parser("telecharger", help="range le jeu et écrit son manifeste, ou le vérifie s'il existe")
    commandes.add_parser("verifier", help="compare le jeu rangé à son manifeste")
    commandes.add_parser("convertir", help="écrit le texte d'EKE de chaque document")
    commandes.add_parser("mesurer", help="cherche les valeurs de la vérité dans les textes d'EKE")
    options = analyse.parse_args(arguments)
    try:
        if options.commande == "telecharger":
            manifeste = telecharger(DOSSIER, revision=REVISION, depot=DEPOT, garder=garder)
        else:
            manifeste = verifier(DOSSIER, REVISION)
        print(f"{len(manifeste.fichiers)} fichiers conformes au manifeste, version {manifeste.revision}")
        if options.commande in ("convertir", "mesurer"):
            documents = charger()
            if options.commande == "convertir":
                empreinte = empreinte_lecture()
                ecrire_note(convertir(documents), empreinte)
            else:
                resume, _ = mesurer(documents)
                print(resume)
    except EcartJeu as ecart:
        print(f"Écart, tout s'arrête : {ecart}", file=sys.stderr)
        return 3
    except SortiesPerimees as perimees:
        print(f"Textes périmés : {perimees}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
