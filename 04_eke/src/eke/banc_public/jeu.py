"""Les pages de fr-bench-pdf2md et leurs tests, chargés comme le banc les charge.

Repris de `benchpdf2md/create_dataset.py` et de `load_single_test`
(`benchpdf2md/bench_tests/benchmark_tsts.py`, commit `ceab1548`) : un dossier par page, qui porte
un `metadata.json`, un seul PDF et au moins un fichier de tests JSONL ; une ligne par test, où
les champs du test recouvrent ceux des métadonnées ; un champ absent ou nul prend la valeur par
défaut du test. Le lanceur ajoute à chaque test un test de base sur la même page.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATEGORIE_PUBLIEE = {"long_table2": "long_table"}
"""Le tableau publié réunit long_table et long_table2 sous « long_table » : ses scores sont des
fractions exactes de 594 = 134 + 460 tests (faits du 2026-10-09)."""
CATEGORIES_PUBLIEES = ("forms", "graphics", "handwritten", "long_table", "multicolumn", "tiny_text")


@dataclass(frozen=True)
class Page:
    dossier: str
    """Dossier de premier niveau sous `pdfs/` (charts, forms, tiny_text2…)."""
    nom: str
    """Nom du dossier de la page, unique dans le jeu."""
    pdf: Path
    tests: tuple[dict[str, Any], ...]
    """Les lignes de test, champs nuls retirés, comme `load_single_test` les reçoit."""

    @property
    def identifiant(self) -> str:
        return f"{self.dossier}/{self.nom}"


def categorie_publiee(categorie: str) -> str:
    return CATEGORIE_PUBLIEE.get(categorie, categorie)


def _sans_vide(ligne: dict[str, Any]) -> dict[str, Any]:
    """Ce que fait `load_single_test` : les valeurs nulles ou NaN tombent, « resources » et « tags »
    aussi."""
    garde = {k: v for k, v in ligne.items() if not (v is None or (isinstance(v, float) and math.isnan(v)))}
    garde.pop("resources", None)
    garde.pop("tags", None)
    return garde


def charger(racine: Path) -> list[Page]:
    """Les pages sous `racine/pdfs/`, triées comme `create_dataset` les parcourt."""
    pages: list[Page] = []
    for dossier in sorted(p for p in (racine / "pdfs").rglob("*") if p.is_dir()):
        fichiers_tests = sorted(dossier.glob("*.jsonl"))
        if not fichiers_tests:
            continue
        pdfs = list(dossier.glob("*.pdf"))
        if len(pdfs) != 1:
            raise ValueError(f"{dossier} : {len(pdfs)} PDF, le banc en attend un")
        metadonnees: dict[str, Any] = json.loads((dossier / "metadata.json").read_text(encoding="utf-8"))
        lignes: list[dict[str, Any]] = []
        for fichier in fichiers_tests:
            for brute in fichier.read_text(encoding="utf-8").splitlines():
                if not brute.strip():
                    continue
                test: dict[str, Any] = json.loads(brute.strip())
                ligne = {
                    "pdf_name": metadonnees["pdf"],
                    "page": metadonnees["page"],
                    "doc_type": metadonnees.get("doc_type"),
                    "original_doc_path": metadonnees.get("original_doc_path"),
                    "pdf_path": str(pdfs[0]),
                    **test,
                }
                lignes.append(_sans_vide(ligne))
        relatif = dossier.relative_to(racine / "pdfs")
        pages.append(Page(relatif.parts[0], dossier.name, pdfs[0], tuple(lignes)))
    identifiants = [t["id"] for p in pages for t in p.tests]
    if len(identifiants) != len(set(identifiants)):
        raise ValueError("identifiants de tests en double")
    return pages
