"""EKE mesuré sur OmniExtractBench (Datalab), second banc public de documents (règle 11 du BRIEF).

Sans modèle : le plafond de lecture, la part des valeurs de la vérité que contient le texte que
`lire_document` rend aux agents, à la forme canonique du banc. Décisions d'Alexandre : journal de
l'étape 6, vingt et unième entrée (`00_docs/sources/2026-10-08_journal_eke.md`) ; faits :
`00_docs/sources/2026-10-10_faits_omniextractbench.md`.

- `jeu` : la version des 620 documents, rangée comme fr-bench-pdf2md, et son manifeste lu ;
- `valeurs` : la forme canonique des valeurs du banc, refaite en bibliothèque standard ;
- `verite` : les valeurs notées d'un document, comme le correcteur du banc les tire ;
- `conversion` : le texte d'EKE de chaque document ;
- `plafond`, `mesure` : les valeurs trouvées, les plafonds par suite et leurs marges.
"""
