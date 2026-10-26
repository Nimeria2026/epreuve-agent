"""EKE sur fr-bench-pdf2md, depuis la racine du dépôt :

    uv run --no-sync --all-packages python -m eke.banc_public telecharger
    uv run --no-sync --all-packages python -m eke.banc_public verifier
    uv run --no-sync --all-packages python -m eke.banc_public convertir
    uv run --no-sync --all-packages python -m eke.banc_public mesurer

`telecharger` range la version des scores publiés dans `99_local/bancs_documents/fr_bench_pdf2md/`
et écrit son manifeste ; relancé, il ne télécharge rien et vérifie le jeu contre le manifeste.
`verifier` fait seulement la vérification. `convertir` vérifie le jeu, puis écrit le Markdown
d'EKE pour chaque page, dans les trois ordres de lecture, sous `sorties/`. `mesurer` vérifie le
jeu, passe les tests du banc sur ces sorties et écrit la fiche de chaque lecture sous `mesures/`,
puis les écarts appariés entre les lectures.
Code de sortie 3 sur un écart du jeu, qui arrête tout ; 4 si les sorties ont été écrites par un
autre code de lecture que celui d'aujourd'hui (relancer `convertir`).
"""

from __future__ import annotations

import argparse
import hashlib
import sys

from eke.banc_public.conversion import VARIANTES, convertir_jeu
from eke.banc_public.jeu import charger
from eke.banc_public.mesure import Resultat, SortiesPerimees, ecrire_conversion, ecrire_ecarts, mesurer
from eke.banc_public.telechargement import DOSSIER, EcartJeu, chemin_manifeste, dossier_donnees, telecharger, verifier

PAIRES = (("lignes", "flux"), ("flux", "pdfium"), ("lignes", "pdfium"))
"""Les écarts appariés écrits après la mesure : la seconde lecture moins la première."""


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m eke.banc_public", description="EKE sur fr-bench-pdf2md.")
    commandes = analyse.add_subparsers(dest="commande", required=True)
    commandes.add_parser("telecharger", help="range le jeu et écrit son manifeste, ou le vérifie s'il existe")
    commandes.add_parser("verifier", help="compare le jeu rangé à son manifeste")
    commandes.add_parser("convertir", help="écrit le Markdown d'EKE de chaque page, dans les trois ordres")
    mesure = commandes.add_parser("mesurer", help="passe les tests du banc sur les sorties d'EKE")
    mesure.add_argument("--variante", choices=sorted(VARIANTES), action="append", help="par défaut, toutes")
    options = analyse.parse_args(arguments)
    try:
        manifeste = telecharger() if options.commande == "telecharger" else verifier()
    except EcartJeu as ecart:
        print(f"Écart, tout s'arrête : {ecart}", file=sys.stderr)
        return 3
    empreinte = hashlib.sha256(chemin_manifeste(DOSSIER).read_bytes()).hexdigest()
    print(f"{len(manifeste.fichiers)} fichiers conformes au manifeste, version {manifeste.revision}")
    print(f"manifeste {chemin_manifeste(DOSSIER)} : sha256 {empreinte}")
    if options.commande == "convertir":
        pages = charger(dossier_donnees(DOSSIER))
        durees = {variante: convertir_jeu(pages, variante, DOSSIER / "sorties") for variante in sorted(VARIANTES)}
        ecrire_conversion(durees)
    elif options.commande == "mesurer":
        mesures: dict[str, tuple[str, list[Resultat]]] = {}
        for variante in options.variante or sorted(VARIANTES):
            try:
                resume, resultats = mesurer(variante, empreinte)
            except SortiesPerimees as perimees:
                print(f"Sorties périmées : {perimees}", file=sys.stderr)
                return 4
            mesures[variante] = (variante, resultats)
            print(resume)
        for premiere, seconde in PAIRES:
            if premiere in mesures and seconde in mesures:
                print(ecrire_ecarts(mesures[premiere], mesures[seconde]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
