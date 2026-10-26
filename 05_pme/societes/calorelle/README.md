# Calorelle

Les données initiales de Calorelle, la PME fictive du banc depuis l'étape 2 : son état de départ,
rechargé avant chaque exécution d'une tâche. Versionné : une tâche indique la version d'état
qu'elle attend. Ce dossier s'appelait `05_pme/donnees_initiales/` jusqu'au 2026-10-15 (ADR 0006).

Contenu : `v1/`, l'état des treize tâches des étapes 2 à 4 jusqu'au 2026-10-08, gardé pour
relire leurs runs ; `v2/`, v1 et les ajouts de l'étape 5 (techniciens, planning, échéancier,
règles du manuel), l'état de tout le banc depuis l'entrée 90 du JOURNAL ; `v3/`, v2 et la
tranche 5 (tarif et devis dans la facturation, règles des devis, des frais et de l'arrivée d'un
salarié, zone d'intervention), où passeront les 45 tâches (entrée 91) ; et `complements/`, un dossier par tâche qui en a
besoin (t06 à t13, puis celles de l'étape 5) posé sur l'état de sa tâche au départ de chacune de ses exécutions, et d'elles seules : ses
fichiers s'ajoutent, ou remplacent ceux de même chemin. Un état ne change donc pas pour les
tâches sans complément. Un run ne mélange jamais deux états. Les
compléments sont écrits par `09_outillage/scripts/generer_complements.py` (`make complements`).
Un complément ne contient que `entreprise/`, `dossiers/`, `messagerie/`, `facturation/` et un
`README.md` qui décrit le piège. Les dossiers partagés et la messagerie de v1 sont produits par
`09_outillage/scripts/generer_donnees_v1.py`, ceux de v2 et son planning par
`09_outillage/scripts/generer_donnees_v2.py`, qui part de v1, ceux de v3 et sa facturation par
`09_outillage/scripts/generer_donnees_v3.py`, qui part de v2 (`make donnees`) ; le dossier
`entreprise/` de chaque état est écrit à la main. Sous ce dossier, les noms de fichiers sont libres (ADR 0003) :
une boîte porte le nom de son adresse, une pièce jointe garde le nom de son expéditeur.
