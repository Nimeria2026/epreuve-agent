# Vérifier le portage d'OmniExtractBench contre le correcteur original

La forme canonique des valeurs et l'aplatissement de la vérité d'OmniExtractBench sont refaits
en bibliothèque standard dans `eke.banc_public.omni` : EKE n'ajoute aucune dépendance. Décision
d'Alexandre : journal de l'étape 6, vingt et unième entrée (`00_docs/sources/2026-10-08_journal_eke.md`).
Ces scripts ne tournent pas sous pytest et n'entrent pas dans l'espace uv du dépôt.

## Préparer l'environnement jetable

Dans un terminal, depuis n'importe quel dossier hors du dépôt, par exemple `/tmp` :

    uv venv --no-config --python 3.12 /tmp/venv_omni
    uv pip install --no-config --python /tmp/venv_omni/bin/python omni-extract-bench==0.1.7 pyarrow

Ce que ça produit : un Python isolé dans `/tmp/venv_omni`, avec le correcteur du banc (et scipy,
sa seule dépendance) et pyarrow, sans effet sur `.venv/` ni sur `uv.lock`. Vérifier :
`/tmp/venv_omni/bin/python -c "import omni_extract_bench; print(omni_extract_bench.__version__)"`
affiche `0.1.7`. Pour défaire : `rm -r /tmp/venv_omni`.

## Lancer

Depuis la racine du dépôt :

    /tmp/venv_omni/bin/python 04_eke/tests/original/omni/lire_manifeste.py
    /tmp/venv_omni/bin/python 04_eke/tests/original/omni/cas_de_reference.py
    /tmp/venv_omni/bin/python 04_eke/tests/original/omni/verifier_contre_original.py

- `lire_manifeste.py`, après `python -m eke.banc_public.omni telecharger` : recopie
  `manifest.parquet` en `manifeste_lu_725aaa6.json`, avec le sha256 du Parquet lu. Ce qu'on doit
  voir : `620 documents recopiés`.
- `cas_de_reference.py` réécrit `04_eke/tests/cas_omniextractbench.json` (3 819 valeurs
  synthétiques et leur clé, quatre vérités synthétiques aplaties), oracles de
  `test_banc_omni_reference_eke.py` ; aucun texte du jeu n'y entre.
- `verifier_contre_original.py`, après `convertir` : sur les 620 documents, compare l'aplatissement
  de chaque vérité, la clé de chaque valeur distincte et de chaque suite de un à trois mots des
  textes d'EKE, puis chaque valeur trouvée ou non, par le portage et par l'original. Ce qu'on doit
  voir : `désaccords : 0` sur les quatre lignes ; code de sortie 0. Deux à trois heures sur un
  cœur ; `--part 1/2` et `--part 2/2`, dans deux terminaux, se partagent les documents.
