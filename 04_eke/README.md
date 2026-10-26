# 04_eke

L'outil documentaire de la PME, exposé aux agents comme un serveur MCP. Langage : Python.

Il lit un document PDF des dossiers partagés (facture, devis, contrat, courrier) et rend chaque
texte et chaque valeur avec sa provenance : la page et la zone d'où ils viennent. Il sera aussi
mesuré sur un banc public de documents (règle 11 du BRIEF), fr-bench-pdf2md d'abord.

Entrées permises : `README.md`, `pyproject.toml`, `src/`, `tests/`.
Ouvert à l'étape 6, le 2026-10-08 ; décisions dans `00_docs/sources/2026-10-08_journal_eke.md`.

## Lancer

Depuis la racine du dépôt, après `make installer` :

    uv run --all-packages python -m eke --etat 05_pme/societes/calorelle/v3 --pour patrick.roux

Le serveur attend un client MCP sur son entrée standard, comme les services de la PME ; il ne
garde rien en mémoire et relit le fichier à chaque appel. Code de sortie 2 si la personne n'est
pas dans l'organigramme.

Dans la PME, EASE ou le gardien lancent EKE ainsi pour les seules tâches qui déclarent le service
`eke`, celles du jeu « documents » (`07_taches/public/documents/`) ; les tâches du banc ne le
voient pas (décision d'Alexandre du 2026-10-10, journal de l'étape 6, vingt-quatrième entrée).

## Outils

Trois outils, tous en lecture seule (annotation MCP `readOnlyHint`), qui déclarent le contrat
`01_contrats/lecture_document.schema.json` comme `outputSchema` :

- `lire_document(chemin)` : le texte, morceau de ligne par morceau de ligne, dans l'ordre du
  flux de PDFium, qui suit les colonnes d'un texte suivi, chaque morceau avec sa page et sa zone ;
- `extraire_valeurs(chemin)` : les paires étiquette-valeur (« Total TTC : 512,40 € »), chaque
  valeur typée (montant, date, iban, pourcentage, texte), normalisée (`512.40`, `2026-10-17`) et
  citée ;
- `citer(chemin, texte)` : chaque endroit où le texte apparaît, ou aucun.

Zones en points PDF, origine en haut à gauche de la page telle qu'elle s'affiche, y vers le bas.
Une personne ouvre par EKE ce qu'elle ouvre dans les dossiers partagés (`organigramme.yaml`,
`acces_dossiers.yaml`), et rien hors d'eux.

## Ce qui est générique, ce qui est propre à Calorelle

Rien dans `src/eke/` ne connaît Calorelle. Le code se range en couches :

- `pdfium.py` : le seul module qui parle à pypdfium2 ; caractères, boîtes, rendu ;
- `geometrie.py` : zones, et passage de l'espace PDF à la page affichée (boîte, rotation) ;
- `mise_en_page.py` : des caractères aux morceaux de ligne, seuils en hauteur de ligne ;
- `valeurs.py` : paires étiquette-valeur d'un document en français (montants en euros, dates
  françaises) ; aucune étiquette attendue ;
- `droits.py` : le format des droits de la PME du banc, pas ceux de Calorelle ;
- `lecture.py`, `contrat.py`, `serveur.py` : assemblage, contrat, MCP.

Ce qui est propre à Calorelle vit dans les tests, comme oracles : l'échéancier du comptable, les
fiches JSON des devis, les étiquettes « Total TTC » ou « Date de facture ». Les PDF construits par
`tests/fabrique_pdf.py` (tableaux, page tournée, boîte décalée, crénage) ne ressemblent pas à
ceux de Calorelle, exprès.

## Tests

    uv run --all-packages pytest -q 04_eke/tests

Quatre vérités extérieures à EKE : le texte que trace chaque PDF de v2 et v3, la relecture de
chaque zone citée par PDFium, l'image de la page rendue (toute encre tombe dans une zone), et les
données de la PME (échéancier, devis). La conversion de coordonnées est comparée à celle de
PDFium pour les quatre rotations.

## Banc public : fr-bench-pdf2md

EKE est aussi mesuré sur un banc public de documents (règle 11 du BRIEF), sans modèle : sa
couche de lecture rendue en Markdown simple, notée par les tests unitaires du banc. Faits et
licence : `00_docs/sources/2026-10-09_faits_fr_bench_pdf2md.md` ; décisions et résultats :
journal de l'étape 6, entrées 8 et suivantes. Depuis la racine du dépôt :

    uv run --no-sync --all-packages python -m eke.banc_public telecharger
    uv run --no-sync --all-packages python -m eke.banc_public convertir
    uv run --no-sync --all-packages python -m eke.banc_public mesurer

`telecharger` range la version des scores publiés (727 pages, 360 Mo) dans
`99_local/bancs_documents/fr_bench_pdf2md/`, hors git, et écrit son manifeste (source, version,
taille et sha256 de chaque fichier) ; relancé, il vérifie le jeu contre le manifeste, et un écart
arrête tout (code 3). `convertir` écrit le Markdown de chaque page sous `sorties/`, dans trois
ordres de lecture : `flux` (l'ordre de `lire_document`, le score d'EKE), `lignes` (les lignes
visuelles, que garde `extraire_valeurs`) et `pdfium` (l'ordre brut du moteur). `mesurer` passe les 2 335 tests sur chaque lecture et écrit sous
`mesures/` une fiche JSON par lecture (scores par catégorie, intervalle à 95 % par bootstrap sur
les pages, jeu, manifeste, code, moteur, machine), le résultat de chaque test en JSONL, et les
écarts appariés entre lectures. Il refuse (code 4) des sorties écrites par un autre code de
lecture que celui d'aujourd'hui : relancer `convertir`.

La métrique est refaite en bibliothèque standard (`banc_public/metrique.py` et ses trois
portages : `flou` pour rapidfuzz, `translitteration` pour unidecode, `html_markdown` pour
html-to-markdown). Elle est comparée au code original, test par test, par les scripts de
`tests/original/` (mode d'emploi dans leur `README.md`).

## Banc public : OmniExtractBench

Second banc public de documents (règle 11 du BRIEF) : 620 documents de quatre suites, chacun
avec un schéma JSON et sa vérité (Datalab, faits et licences :
`00_docs/sources/2026-10-10_faits_omniextractbench.md`). Le banc note une extraction guidée par un
schéma, qu'EKE sans modèle ne fait pas : la mesure, décidée par Alexandre (journal de l'étape 6,
vingt et unième entrée), est le plafond de lecture, la part des valeurs de la vérité que contient
le texte de `lire_document`, à la forme canonique du banc. Depuis la racine du dépôt :

    uv run --no-sync --all-packages python -m eke.banc_public.omni telecharger
    uv run --no-config --no-project --with pyarrow python 04_eke/tests/original/omni/lire_manifeste.py
    uv run --no-sync --all-packages python -m eke.banc_public.omni convertir
    uv run --no-sync --all-packages python -m eke.banc_public.omni mesurer

`telecharger` range la version `725aaa6` (1 247 fichiers, 877 Mo) dans
`99_local/bancs_documents/omniextractbench/` et son manifeste, comme pour fr-bench-pdf2md.
`lire_manifeste.py` recopie en JSON le manifeste Parquet du banc, que la bibliothèque standard ne
lit pas, dans un environnement éphémère qui ne touche ni `.venv/` ni `uv.lock`. `convertir` écrit
le texte d'EKE de chaque document sous `sorties/flux/` ; `mesurer` y cherche chaque valeur et
écrit la fiche sous `mesures/` (plafond par suite, moyenne des documents, moyenne des suites,
intervalles à 95 % par bootstrap sur les documents). La forme canonique et l'aplatissement de la
vérité sont refaits en bibliothèque standard (`banc_public/omni/valeurs.py` et `verite.py`) et
comparés à l'original par les scripts de `tests/original/omni/`.

## Limites connues

- `extraire_valeurs` et `citer` travaillent par ligne visuelle : une page en deux colonnes de
  texte suivi s'y lit d'une colonne à l'autre (`lire_document` suit le flux, qui garde les
  colonnes ; journal de l'étape 6, dix-neuvième entrée).
- Un texte tourné (étiquette d'axe verticale d'un graphique) se coupe en un caractère par
  morceau : « T W h » au lieu de « TWh ».
- Une citation coupée par un changement de ligne n'est pas trouvée par `citer`.
- Pas d'OCR : un PDF scanné, sans couche de texte, ne rend rien.
- PDFium lit l'espace insécable de WinAnsi (octet 0xA0) comme une espace simple.
- Un IBAN se reconnaît à sa forme ; sa clé n'est pas vérifiée (ceux de la PME sont fictifs et
  ne la respectent pas).
- Dans l'état v3, 10 des 18 factures fournisseurs rangées portent un IBAN qui n'est pas celui de
  la fiche de leur fournisseur : un défaut des données, invisible tant qu'aucun outil ne lisait
  les PDF, sans effet sur les tâches du banc (journal de l'étape 6, vingt-cinquième entrée).
- `lire_document`, `extraire_valeurs` et `citer` rangent d'abord toute la page en lignes
  visuelles, en un temps quadratique en nombre de morceaux : 7 ms par PDF de Calorelle, mais une
  page dense d'OmniExtractBench (27 612 morceaux) ne se range pas en deux minutes. La mesure du
  banc ne lit que le flux.
