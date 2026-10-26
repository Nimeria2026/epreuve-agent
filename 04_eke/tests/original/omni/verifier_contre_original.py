"""Compare le portage d'EKE au correcteur original d'OmniExtractBench, document par document.

À lancer dans l'environnement jetable du README de ce dossier (omni-extract-bench 0.1.7), depuis
la racine du dépôt, après `telecharger`, `lire_manifeste.py` et `convertir`. Trois comparaisons,
sur les 620 documents :

1. `verite` : les adresses et les valeurs notées, par `flatten(prep_ground_truth(gt),
   resolve_refs(schema))` de l'original et par `eke.banc_public.omni.verite` ;
2. `cles` : la clé canonique de chaque valeur distincte de la vérité, par `canon_key` et par
   `eke.banc_public.omni.valeurs.cle`, et celle de chaque suite de un à trois mots des textes
   d'EKE ;
3. `plafond` : chaque valeur trouvée ou non, par `eke.banc_public.omni.plafond.chercher` avec la
   clé du portage, puis avec `canon_key` à sa place.

Ce qu'on doit voir : `désaccords : 0` sur chaque ligne, code de sortie 0. Deux à trois heures sur
un seul cœur : `--part 1/2` et `--part 2/2`, lancés dans deux terminaux, se partagent les
documents (un sur deux).
"""

# pyright: basic, reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

sys.path.insert(0, "04_eke/src")

from eke.banc_public.omni import plafond, valeurs, verite
from omni_extract_bench.metric import (
    flatten,
    prep_ground_truth,
    resolve_refs,
)
from omni_extract_bench.values import (
    canon_key,
)

REVISION = "725aaa6e04f3097383527beca6640015b395772d"
DOSSIER = Path("99_local/bancs_documents/omniextractbench")


def documents() -> list[dict[str, Any]]:
    lu: dict[str, Any] = json.loads((DOSSIER / f"manifeste_lu_{REVISION[:7]}.json").read_text(encoding="utf-8"))
    return lu["documents"]


def lire(chemin: str) -> Any:
    return json.loads((DOSSIER / REVISION[:7] / chemin).read_text(encoding="utf-8"))


def texte(doc_id: str) -> str:
    return (DOSSIER / "sorties" / "flux" / f"{doc_id}.txt").read_bytes().decode("utf-8")


def main() -> int:
    part, parts = 1, 1
    if len(sys.argv) == 3 and sys.argv[1] == "--part":
        part, parts = (int(x) for x in sys.argv[2].split("/"))
    desaccords = {"verite": 0, "cles_verite": 0, "cles_textes": 0, "plafond": 0}
    comptes = {"verite": 0, "cles_verite": 0, "cles_textes": 0, "plafond": 0}
    vues: set[tuple[str, str]] = set()
    mots_vus: set[str] = set()
    # typed=True : sans lui, lru_cache confond 1, 1.0 et True, dont les clés diffèrent.
    original = lru_cache(maxsize=200_000, typed=True)(canon_key)
    for rang, d in enumerate(documents(), 1):
        if rang % parts != part % parts:
            continue
        schema = json.loads(d["schema"])
        gt = lire(d["gt_path"])
        attendu = flatten(prep_ground_truth(gt), resolve_refs(schema))
        porte = verite.valeurs_de_la_verite(gt, schema)
        comptes["verite"] += 1
        if attendu != porte or [type(v) for v in attendu.values()] != [type(v) for v in porte.values()]:
            desaccords["verite"] += 1
            print(f"vérité en désaccord : {d['doc_id']}")
        for v in porte.values():
            cle = (type(v).__name__, repr(v))
            if cle in vues:
                continue
            vues.add(cle)
            comptes["cles_verite"] += 1
            if canon_key(v) != valeurs.cle(v):
                desaccords["cles_verite"] += 1
                print(f"clé en désaccord : {v!r} : {canon_key(v)!r} contre {valeurs.cle(v)!r}")
        mots = texte(d["doc_id"]).split()
        for m in (1, 2, 3):
            for debut in range(len(mots) - m + 1):
                s = " ".join(mots[debut : debut + m])
                if s in mots_vus:
                    continue
                mots_vus.add(s)
                comptes["cles_textes"] += 1
                if original(s) != valeurs.cle(s):
                    desaccords["cles_textes"] += 1
                    print(f"clé de texte en désaccord : {s!r}")
        a = plafond.chercher(texte(d["doc_id"]), porte)
        plafond.cle, plafond.cle_texte = original, original  # pyright: ignore[reportPrivateImportUsage]
        b = plafond.chercher(texte(d["doc_id"]), porte)
        plafond.cle, plafond.cle_texte = valeurs.cle, valeurs.cle_texte  # pyright: ignore[reportPrivateImportUsage]
        comptes["plafond"] += len(a)
        ecarts = sum(1 for x, y in zip(a, b, strict=True) if x.trouvee != y.trouvee or x.cle != y.cle)
        if ecarts:
            desaccords["plafond"] += ecarts
            print(f"plafond en désaccord : {d['doc_id']} ({ecarts} valeurs)")
        # Les mémoires se vident à chaque document : celles d'un document aux longues valeurs
        # (Contracts_Awarded, suites de 154 mots) dépassaient 3 Go.
        original.cache_clear()
        valeurs.cle_texte.cache_clear()
        if rang % 50 == 0:
            print(f"{rang} documents comparés", flush=True)
    for nom in comptes:
        print(f"{nom} : {comptes[nom]} comparés ; désaccords : {desaccords[nom]}")
    return 1 if any(desaccords.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
