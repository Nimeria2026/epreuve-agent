"""EKE mesuré sur un banc public de documents (règle 11 du BRIEF) : fr-bench-pdf2md d'abord.

Sans modèle : la couche de lecture d'EKE (PDFium et sa mise en page) rendue en Markdown simple,
puis la métrique du banc refaite en bibliothèque standard, à l'identique de son code publié.

- `telechargement` : le jeu, fichier par fichier, sous manifeste (source, version, taille, sha256) ;
- `jeu` : les pages et leurs tests, comme le banc les charge ;
- `conversion` : le Markdown simple d'EKE, en deux ordres de lecture ;
- `flou`, `translitteration`, `html_markdown`, `metrique` : la métrique du banc ;
- `mesure` : les scores par catégorie, leur marge, la fiche de la mesure.

Faits et sources : `00_docs/sources/2026-10-09_faits_fr_bench_pdf2md.md` ; décisions : journal de
l'étape 6, `00_docs/sources/2026-10-08_journal_eke.md`, entrées 8 et suivantes.
"""
