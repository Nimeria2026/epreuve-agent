"""Le plafond de lecture d'EKE sur OmniExtractBench : par document, par suite, et ses marges.

Plafond d'un document : la part de ses valeurs notées (adresses de la vérité) que le texte d'EKE
contient (`plafond`). Agrégats, comme le banc les définit ou les publie (faits du 2026-10-10) :

- par suite, la moyenne des documents de la suite ;
- « toutes », la moyenne des 620 documents, celle du tableau publié (moyenne des documents) ;
- « unifié », la moyenne des quatre moyennes de suite, la note globale de la spécification (§7).

À côté, la part des valeurs trouvées, toutes valeurs confondues, que les grands tableaux tirent
vers eux. Marges : intervalle à 95 % par bootstrap sur les documents (un document tiré avec
remise emporte toutes ses valeurs), 10 000 tirages, graine fixe ; tirage dans chaque suite pour
« unifié ». La mesure écrit sous `mesures/` sa fiche JSON et une ligne JSON par document.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eke import VERSION
from eke.banc_public.mesure import commit_de_base, empreinte_code, quantile
from eke.banc_public.omni.conversion import empreinte_lecture, lire_note, lire_sortie
from eke.banc_public.omni.jeu import DEPOT, DOSSIER, REVISION, SUITES, Document, chemin_manifeste_lu, lire_verite
from eke.banc_public.omni.plafond import ECART_DE_MOTS, MOTS_D_UNE_DATE, chercher
from eke.banc_public.omni.verite import valeurs_de_la_verite
from eke.banc_public.telechargement import chemin_manifeste
from eke.pdfium import MOTEUR

TIRAGES = 10_000
GRAINE = 20261010
SOURCE_METRIQUE = {
    "paquet": "omni-extract-bench 0.1.7 (PyPI, Apache-2.0), sdist sha256 "
    "b0af6b8ba96d0c48477adb524a9ee86e1d1d10e0d0659c309d96fdf1fab3d2c1",
    "repris": "values.py et recognise.py (canon_key), metric.py côté vérité (unwrap, resolve_refs, "
    "unwrap_schema, is_open_map, flatten)",
}


class SortiesPerimees(Exception):
    """Les textes d'EKE ont été écrits par un autre code de lecture que celui d'aujourd'hui."""


@dataclass(frozen=True)
class ResultatDocument:
    document: str
    suite: str
    pages: int
    pages_sans_texte: int
    illisible: bool
    valeurs: int
    trouvees: int
    par_type: dict[str, list[int]] = field(default_factory=dict[str, list[int]])
    """Par type JSON de la valeur : [valeurs, trouvées]."""
    duree_s: float = 0.0

    @property
    def plafond(self) -> float:
        return self.trouvees / self.valeurs if self.valeurs else 0.0


def mesurer_document(document: Document, texte: str, note: Mapping[str, Any]) -> ResultatDocument:
    debut = time.perf_counter()
    valeurs = chercher(texte, valeurs_de_la_verite(lire_verite(document), document.schema))
    par_type: dict[str, list[int]] = {}
    for v in valeurs:
        compte = par_type.setdefault(v.type, [0, 0])
        compte[0] += 1
        compte[1] += v.trouvee
    return ResultatDocument(
        document=document.identifiant,
        suite=document.suite,
        pages=int(note["pages"]),
        pages_sans_texte=int(note["pages_sans_texte"]),
        illisible=bool(note["illisible"]),
        valeurs=len(valeurs),
        trouvees=sum(v.trouvee for v in valeurs),
        par_type=par_type,
        duree_s=time.perf_counter() - debut,
    )


def bootstrap(valeurs: Sequence[float], tirages: int = TIRAGES, graine: int = GRAINE) -> tuple[float, float]:
    """Intervalle à 95 % d'une moyenne, documents tirés avec remise."""
    hasard = random.Random(graine)
    n = len(valeurs)
    moyennes = [statistics.fmean(valeurs[hasard.randrange(n)] for _ in range(n)) for _ in range(tirages)]
    return quantile(moyennes, 0.025), quantile(moyennes, 0.975)


def bootstrap_unifie(
    par_suite: Mapping[str, Sequence[float]], tirages: int = TIRAGES, graine: int = GRAINE
) -> tuple[float, float]:
    """Intervalle à 95 % de la moyenne des moyennes de suite, tirage dans chaque suite."""
    hasard = random.Random(graine)
    suites = [list(v) for _, v in sorted(par_suite.items())]
    moyennes: list[float] = []
    for _ in range(tirages):
        moyennes.append(statistics.fmean(statistics.fmean(s[hasard.randrange(len(s))] for _ in s) for s in suites))
    return quantile(moyennes, 0.025), quantile(moyennes, 0.975)


@dataclass(frozen=True)
class Score:
    categorie: str
    documents: int
    valeurs: int
    trouvees: int
    part_des_valeurs: float
    plafond: float
    """Moyenne des plafonds des documents ; pour « unifié », moyenne des quatre suites."""
    bas: float
    haut: float


def scores(resultats: Sequence[ResultatDocument]) -> list[Score]:
    lignes: list[Score] = []
    par_suite: dict[str, list[float]] = {}

    def ligne(nom: str, choisis: Sequence[ResultatDocument]) -> Score:
        plafonds = [r.plafond for r in choisis]
        valeurs, trouvees = sum(r.valeurs for r in choisis), sum(r.trouvees for r in choisis)
        bas, haut = bootstrap(plafonds)
        return Score(nom, len(choisis), valeurs, trouvees, trouvees / valeurs, statistics.fmean(plafonds), bas, haut)

    for suite in SUITES:
        choisis = [r for r in resultats if r.suite == suite]
        if choisis:
            par_suite[suite] = [r.plafond for r in choisis]
            lignes.append(ligne(suite, choisis))
    lignes.append(ligne("toutes", resultats))
    bas, haut = bootstrap_unifie(par_suite)
    valeurs, trouvees = sum(r.valeurs for r in resultats), sum(r.trouvees for r in resultats)
    unifie = statistics.fmean(statistics.fmean(v) for v in par_suite.values())
    lignes.append(Score("unifie", len(resultats), valeurs, trouvees, trouvees / valeurs, unifie, bas, haut))
    return lignes


def _sha256(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def mesurer(
    documents: Sequence[Document], dossier: Path = DOSSIER, dire: Callable[[str], None] = print
) -> tuple[str, list[ResultatDocument]]:
    """Mesure chaque document sur son texte ; écrit la fiche et les résultats ; rend le résumé."""
    note = lire_note(dossier)
    if note["code_lecture_sha256"] != empreinte_lecture() or note["moteur"] != MOTEUR:
        raise SortiesPerimees("le code de lecture ou le moteur a changé depuis la conversion ; relancer convertir")
    notes: dict[str, dict[str, Any]] = note["documents"]
    resultats: list[ResultatDocument] = []
    for rang, document in enumerate(documents, 1):
        resultats.append(mesurer_document(document, lire_sortie(dossier, document), notes[document.identifiant]))
        if rang % 50 == 0 or rang == len(documents):
            dire(f"{rang}/{len(documents)} documents mesurés")
    lignes = scores(resultats)
    types: Counter[str] = Counter()
    trouves: Counter[str] = Counter()
    for r in resultats:
        for t, (n, k) in r.par_type.items():
            types[t] += n
            trouves[t] += k
    durees = [float(n["duree_s"]) for n in notes.values()]
    maintenant = datetime.now(UTC)
    fiche: dict[str, Any] = {
        "mesure": "Plafond de lecture d'EKE sur OmniExtractBench, lecture « flux » (lire_document)",
        "date_utc": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "jeu": {
            "depot": DEPOT,
            "revision": REVISION,
            "manifeste_sha256": _sha256(chemin_manifeste(dossier, REVISION)),
            "manifeste_lu_sha256": _sha256(chemin_manifeste_lu(dossier, REVISION)),
            "documents": len(documents),
        },
        "lecteur": {
            "eke": VERSION,
            "moteur": MOTEUR,
            "code_sha256": empreinte_code(),
            "code_lecture_sha256": note["code_lecture_sha256"],
            "commit_de_base": commit_de_base(),
            "sorties_ecrites_le": note["date_utc"],
        },
        "metrique": SOURCE_METRIQUE,
        "definition": {
            "trouvee": "une suite de m mots consécutifs du texte, telle quelle ou privée de ses bords "
            "sans lettre ni chiffre, a la clé canonique de la valeur ; m de t - 1 à t + 1, t le nombre "
            "de mots de la valeur ; de 1 à 3 au moins pour une date ou une heure",
            "ecart_de_mots": ECART_DE_MOTS,
            "mots_d_une_date": MOTS_D_UNE_DATE,
        },
        "marges": {"methode": "bootstrap sur les documents, intervalle à 95 %", "tirages": TIRAGES, "graine": GRAINE},
        "machine": {"python": sys.version.split()[0], "systeme": platform.platform(), "processeur": platform.machine()},
        "pages": sum(r.pages for r in resultats),
        "pages_sans_texte": sum(r.pages_sans_texte for r in resultats),
        "documents_sans_texte": sum(1 for r in resultats if r.pages and r.pages_sans_texte == r.pages),
        "documents_illisibles": sum(1 for r in resultats if r.illisible),
        "lecture_par_document_s": {"mediane": statistics.median(durees), "moyenne": statistics.fmean(durees)},
        "par_type": {t: {"valeurs": types[t], "trouvees": trouves[t]} for t in sorted(types)},
        "scores": [asdict(s) for s in lignes],
    }
    sortie = dossier / "mesures"
    sortie.mkdir(parents=True, exist_ok=True)
    base = sortie / f"{maintenant.strftime('%Y-%m-%dT%H%M%SZ')}_plafond_flux"
    base.with_suffix(".json").write_text(json.dumps(fiche, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with base.with_suffix(".jsonl").open("w", encoding="utf-8") as flux:
        for r in resultats:
            flux.write(json.dumps({**asdict(r), "plafond": r.plafond}, ensure_ascii=False) + "\n")
    return resume(fiche, base), resultats


def _pc(valeur: float) -> str:
    return f"{100 * valeur:.1f}".replace(".", ",")


def resume(fiche: Mapping[str, Any], base: Path) -> str:
    lignes = [f"{fiche['mesure']}, {fiche['date_utc']} ; fiche {base.with_suffix('.json')}"]
    for s in fiche["scores"]:
        lignes.append(
            f"  {s['categorie']:<13} {_pc(s['plafond']):>5} %  [{_pc(s['bas'])} ; {_pc(s['haut'])}]"
            f"  {s['documents']} documents ; valeurs trouvées {s['trouvees']}/{s['valeurs']}"
            f" ({_pc(s['part_des_valeurs'])} %)"
        )
    lignes.append(
        f"  pages {fiche['pages']}, sans texte {fiche['pages_sans_texte']} ;"
        f" documents sans texte {fiche['documents_sans_texte']}, illisibles {fiche['documents_illisibles']}"
    )
    return "\n".join(lignes)
