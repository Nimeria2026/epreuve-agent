"""Écrit `04_eke/tests/cas_omniextractbench.json` : des valeurs synthétiques et la clé canonique que
leur donne le correcteur original (omni-extract-bench 0.1.7), et l'aplatissement de quelques
vérités synthétiques. Aucun texte du jeu n'y entre. À lancer dans l'environnement jetable du
README de ce dossier, depuis la racine du dépôt ; `test_banc_omni_reference_eke.py` les relit.
"""

# pyright: basic, reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path
from typing import Any

from omni_extract_bench import __version__
from omni_extract_bench.metric import (
    flatten,
    prep_ground_truth,
    resolve_refs,
)
from omni_extract_bench.values import canon_key

CIBLE = Path("04_eke/tests/cas_omniextractbench.json")
DEBUTS = ["", "$", "(", "-", "+", " ", "• ", "−", "USD "]
CORPS = [
    "1,234", "1234.50", "0.0025", "02000", "12.34", "31/10/2024", "Oct 31, 2024", "31 October 2024",
    "2024-10-31T09:00:00Z", "2024-10-31T00:00:00", "2024-10-31 09:00", "10/31/24", "31.10.2024",
    "ACME CORP", "Acme  Corp.", "N/A", "--", "½", "10²", "ﬁle", "Müller", "PO BOX 125",
    "1.000.000", "512.784.7407", "1.5 mg", "TRUE", "yes", "Infinity", "NaN", "1e-05", "9" * 40,
    "31-1440073", "‘quoted’", "A(B)C", "and/or", "µg", "1:00.50", "Q1", "1/2", "",
    "  ", "0", "-0.0", "100%", "1.234,56", "​zero", "x́",
]  # fmt: skip
FINS = ["", "-", ")", "%", " [1]", " [a]", "*", ".", ","]
TYPES: list[Any] = [
    True, False, 0, 1, -1, 1240, 1240.0, 0.1, 1e-05, 123456.78, 2.5e20, 3.14159265358979, None, [], {},
]  # fmt: skip
VERITES: list[tuple[Any, Any]] = [
    ({"date": "2024-03-31", "rows": [{"x": 1}], "note": None, "memo": ""}, {"type": "object"}),
    (
        {"a": {"value": 3, "citations": ["p1"]}, "b": {"value": 4, "unit": "kg"}, "c": {"k1": 1, "k2": 2}},
        {"properties": {"c": {"type": "object", "additionalProperties": {"type": "integer"}}}},
    ),
    (
        {"lignes": [{"n": "A", "q": 2}, {"n": "", "q": None}], "tags": ["x", " ", "y"]},
        {"$defs": {"L": {"type": "object", "properties": {"n": {"type": "string"}}}},
         "properties": {"lignes": {"type": "array", "items": {"$ref": "#/$defs/L"}}}},
    ),
    ({"x": {"y": [[1, 2], [3]]}}, {"properties": {"x": {"anyOf": [{"type": "null"}, {"type": "object"}]}}}),
]  # fmt: skip


def adresses(feuilles: dict[Any, Any]) -> list[list[Any]]:
    return [[[list(etape) for etape in a], v] for a, v in feuilles.items()]


def main() -> int:
    textes = sorted({d + c + f for d, c, f in product(DEBUTS, CORPS, FINS)})
    cles = [["str", t, canon_key(t)] for t in textes]
    cles += [[type(v).__name__, v, canon_key(v)] for v in TYPES]
    verites = [[g, s, adresses(flatten(prep_ground_truth(g), resolve_refs(s)))] for g, s in VERITES]
    contenu = {"source": f"omni-extract-bench {__version__}", "cles": cles, "verites": verites}
    CIBLE.write_text(json.dumps(contenu, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"{len(cles)} clés et {len(verites)} vérités écrites dans {CIBLE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
