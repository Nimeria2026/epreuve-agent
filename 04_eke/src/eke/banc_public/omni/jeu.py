"""OmniExtractBench dans `99_local/`, et ses documents tels que le banc les décrit.

Le jeu vit sur Hugging Face (`datalab-to/omni_extract_bench`), version `725aaa6`, la dernière au
2026-10-10, celle des 620 documents (faits : `00_docs/sources/2026-10-10_faits_omniextractbench.md`).
Il se range et se vérifie par `eke.banc_public.telechargement`, comme fr-bench-pdf2md.

Le manifeste du banc (`manifest.parquet`) porte la suite et le schéma de chaque document. EKE
n'ajoute aucune dépendance et la bibliothèque standard ne lit pas le Parquet : le script
`04_eke/tests/original/omni/lire_manifeste.py`, lancé dans un environnement jetable, en recopie
les lignes dans `manifeste_lu_<version>.json`, à côté du jeu, avec le sha256 du fichier lu. Le
chargement vérifie que ce sha256 est celui du manifeste du jeu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from eke.banc_public.telechargement import EcartJeu, dossier_donnees, lire_manifeste
from eke.contrat import racine_depot

DEPOT = "datalab-to/omni_extract_bench"
REVISION = "725aaa6e04f3097383527beca6640015b395772d"
"""Version des 620 documents, la dernière au 2026-10-10 (décision d'Alexandre : les 620, les
quatre suites ; journal de l'étape 6, vingt et unième entrée)."""
DOSSIER = racine_depot() / "99_local" / "bancs_documents" / "omniextractbench"
MANIFESTE_BANC = "manifest.parquet"
SUITES = ("extractbench", "internal", "longarray", "micro1")


def garder(chemin: str) -> bool:
    """Ce qu'EKE range : carte, licences, spécification de la métrique, manifeste, PDF, vérités."""
    return chemin in ("README.md", MANIFESTE_BANC, "docs/METRIC_SPEC.md") or chemin.startswith(
        ("licenses/", "pdfs/", "gold/")
    )


def chemin_manifeste_lu(dossier: Path = DOSSIER, revision: str = REVISION) -> Path:
    return dossier / f"manifeste_lu_{revision[:7]}.json"


@dataclass(frozen=True)
class Document:
    identifiant: str
    """`doc_id` du banc ; certains portent des espaces."""
    suite: str
    pdf: Path
    verite: Path
    schema: dict[str, Any]


def _relatif(chemin: str) -> PurePosixPath:
    pur = PurePosixPath(chemin)
    if pur.is_absolute() or ".." in pur.parts or not pur.parts:
        raise EcartJeu(f"chemin refusé dans le manifeste du banc : {chemin!r}")
    return pur


def charger(dossier: Path = DOSSIER, revision: str = REVISION) -> list[Document]:
    """Les documents du banc, dans l'ordre de son manifeste ; EcartJeu si le manifeste lu ne vient
    pas du `manifest.parquet` rangé, ou si un fichier qu'il nomme manque au jeu."""
    manifeste = lire_manifeste(dossier, revision)
    empreintes = {e.chemin: e.sha256 for e in manifeste.fichiers}
    chemin_lu = chemin_manifeste_lu(dossier, revision)
    if not chemin_lu.exists():
        raise EcartJeu(f"pas de manifeste lu : {chemin_lu} ; lancer lire_manifeste.py (04_eke/tests/original/omni)")
    lu: dict[str, Any] = json.loads(chemin_lu.read_text(encoding="utf-8"))
    if lu.get("source_sha256") != empreintes.get(MANIFESTE_BANC):
        raise EcartJeu(f"{chemin_lu.name} ne vient pas du {MANIFESTE_BANC} rangé")
    racine = dossier_donnees(dossier, revision)
    documents: list[Document] = []
    for ligne in cast(list[dict[str, Any]], lu["documents"]):
        for cle_ in ("doc_path", "gt_path"):
            if str(ligne[cle_]) not in empreintes:
                raise EcartJeu(f"{ligne[cle_]} : nommé par le manifeste du banc, absent du jeu")
        schema: dict[str, Any] = json.loads(str(ligne["schema"]))
        documents.append(
            Document(
                identifiant=str(ligne["doc_id"]),
                suite=str(ligne["suite"]),
                pdf=racine / _relatif(str(ligne["doc_path"])),
                verite=racine / _relatif(str(ligne["gt_path"])),
                schema=schema,
            )
        )
    if len({d.identifiant for d in documents}) != len(documents):
        raise EcartJeu("identifiants de documents en double")
    return documents


def lire_verite(document: Document) -> Any:
    return json.loads(document.verite.read_text(encoding="utf-8"))
