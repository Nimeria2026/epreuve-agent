# Vérifier la métrique portée contre le code original de fr-bench-pdf2md

La métrique du banc est refaite en bibliothèque standard dans `eke.banc_public` : EKE n'ajoute
aucune dépendance. Les scripts de ce dossier comparent ce portage au code original, exécuté dans
un environnement jetable hors du dépôt, aux versions du `uv.lock` du banc. Décision d'Alexandre :
journal de l'étape 6, onzième entrée (`00_docs/sources/2026-10-08_journal_eke.md`).

Ils ne tournent pas sous pytest (leur nom ne commence pas par `test_`) et n'entrent pas dans
l'espace uv du dépôt.

## Préparer l'environnement jetable

Dans un terminal, depuis n'importe quel dossier hors du dépôt, par exemple `/tmp` :

    uv venv --no-config --python 3.12 /tmp/venv_banc
    uv pip install --no-config --python /tmp/venv_banc/bin/python rapidfuzz==3.14.3 unidecode==1.4.0 html-to-markdown==2.20.0 beautifulsoup4==4.14.3 numpy==2.4.1 lxml==6.0.2 pandas==2.3.3 pydantic==2.12.5 typing-extensions==4.15.0 devtools==0.12.2

Ce que ça produit : un Python isolé dans `/tmp/venv_banc`, sans effet sur `.venv/` ni sur
`uv.lock`. Vérifier : `/tmp/venv_banc/bin/python -c "import rapidfuzz; print(rapidfuzz.__version__)"`
affiche `3.14.3`. Pour défaire : `rm -r /tmp/venv_banc`.

## Lancer

Depuis la racine du dépôt, après `python -m eke.banc_public telecharger` puis `convertir` :

    /tmp/venv_banc/bin/python 04_eke/tests/original/verifier_contre_original.py comparer lignes pdfium
    /tmp/venv_banc/bin/python 04_eke/tests/original/verifier_contre_original.py table
    /tmp/venv_banc/bin/python 04_eke/tests/original/cas_de_reference.py

- `sources_originales.py` télécharge d'abord trois fichiers du banc et de vlmparse dans
  `99_local/bancs_documents/fr_bench_pdf2md/original/`, chacun vérifié par son sha256 ; un écart
  arrête tout.
- `comparer` passe les 2 335 tests et autant de tests de base par l'original et par le portage, sur
  chaque lecture, et compte les désaccords. Ce qu'on doit voir : `résultats en désaccord : 0` pour
  chaque lecture ; code de sortie 0.
- `table` relève ce qu'unidecode fait des caractères non ASCII lus. Ce qu'on doit voir :
  `absents de VERIFIES : 0 ; exceptions qui diffèrent du module : 0`.
- `cas_de_reference.py` réécrit `04_eke/tests/cas_fr_bench_pdf2md.json`, oracles des tests de
  `test_banc_reference_eke.py`.

À relancer après tout changement d'EKE qui change ses sorties : le portage de html-to-markdown
n'est exact que pour les textes sans balise HTML, et la table d'unidecode ne couvre que les
caractères déjà lus (`caracteres_non_verifies` de chaque fiche de mesure).
