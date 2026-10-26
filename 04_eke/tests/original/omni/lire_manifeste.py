"""Recopie le manifeste d'OmniExtractBench (Parquet) en JSON, à côté du jeu rangé.

À lancer dans un environnement jetable qui a pyarrow (README de ce dossier), depuis la racine du
dépôt, après `python -m eke.banc_public.omni telecharger`. EKE n'ajoute aucune dépendance : il lit
ensuite `manifeste_lu_725aaa6.json`, et vérifie que `source_sha256` est celui du `manifest.parquet`
du jeu. Les schémas sont recopiés tels quels, octets décodés en UTF-8.
"""

# pyright: basic, reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

REVISION = "725aaa6e04f3097383527beca6640015b395772d"
DOSSIER = Path("99_local/bancs_documents/omniextractbench")


def main() -> int:
    source = DOSSIER / REVISION[:7] / "manifest.parquet"
    if not source.exists():
        print(f"absent : {source} ; lancer d'abord le téléchargement, depuis la racine du dépôt", file=sys.stderr)
        return 2
    table = pq.read_table(source).to_pylist()
    documents = []
    for ligne in table:
        schema = ligne["schema"]
        documents.append({
            "doc_id": ligne["doc_id"],
            "doc_path": ligne["doc_path"],
            "gt_path": ligne["gt_path"],
            "suite": ligne["suite"],
            "schema": schema.decode("utf-8") if isinstance(schema, bytes) else schema,
        })  # fmt: skip
    sortie = {
        "source": f"{REVISION[:7]}/manifest.parquet",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "lu_par": "pyarrow " + __import__("pyarrow").__version__,
        "documents": documents,
    }
    cible = DOSSIER / f"manifeste_lu_{REVISION[:7]}.json"
    cible.write_text(json.dumps(sortie, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(documents)} documents recopiés dans {cible} ; sha256 du Parquet {sortie['source_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
