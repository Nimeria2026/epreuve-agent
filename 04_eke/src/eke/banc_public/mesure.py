"""La mesure d'EKE sur fr-bench-pdf2md : les tests du banc sur ses sorties, les scores, leurs marges.

Score d'une catégorie : la part de ses tests réussis, comme le banc la calcule ; long_table et
long_table2 réunies comme dans le tableau publié ; « toutes » couvre tous les tests hors tests de
base, la définition de `run_benchmark.py`. Marge : intervalle à 95 % par bootstrap sur les pages
(une page tirée avec remise emporte tous ses tests), 10 000 tirages, graine fixe, comme
`ease.rapport` tire les tâches. Le banc publie une autre marge, deux écarts types d'un bootstrap
sur les tests ; la fiche la donne aussi, pour comparer.

Chaque mesure écrit sous `mesures/` une fiche JSON (ce qui permet de la refaire : jeu, manifeste,
code, moteur, machine) et le résultat de chaque test en JSONL.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import random
import statistics
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eke import VERSION
from eke.banc_public import translitteration
from eke.banc_public.conversion import lire_sortie
from eke.banc_public.html_markdown import balise_veritable
from eke.banc_public.jeu import CATEGORIES_PUBLIEES, Page, categorie_publiee, charger
from eke.banc_public.metrique import evaluer
from eke.banc_public.telechargement import DEPOT, DOSSIER, REVISION, dossier_donnees
from eke.contrat import racine_depot
from eke.pdfium import MOTEUR

TIRAGES = 10_000
GRAINE = 20261009
TIRAGES_BANC = 1_000
"""`vectorized_bootstrap_grouped_std` du banc (`benchpdf2md/utils.py`)."""
SOURCE_METRIQUE = {
    "banc": "github.com/ld-lab-pulsia/benchpdf2md@ceab1548ac914bff6585fa5c6227e2b24c35cfdb",
    "tableaux": "vlmparse 0.1.8, md_tables_to_html",
    "bibliotheques": "rapidfuzz 3.14.3, unidecode 1.4.0, html-to-markdown 2.20.0, beautifulsoup4 4.14.3",
}
CHAMPS_TEXTE = ("text", "before", "after", "cell", "up", "down", "left", "right", "top_heading", "left_heading")


@dataclass(frozen=True)
class Resultat:
    page: str
    test: str
    type: str
    categorie: str
    """Catégorie du tableau publié (long_table2 réunie à long_table) ; « baseline » pour la base."""
    reussi: bool


def evaluer_page(page: Page, contenu: str) -> list[Resultat]:
    """Chaque test de la page, puis, comme le lanceur du banc, un test de base par test."""
    resultats: list[Resultat] = []
    base = evaluer({"type": "baseline"}, contenu)
    for test in page.tests:
        categorie = categorie_publiee(str(test.get("category")))
        reussi = evaluer(test, contenu)
        resultats.append(Resultat(page.identifiant, str(test["id"]), str(test["type"]), categorie, reussi))
        resultats.append(Resultat(page.identifiant, f"{test['id']}-baseline", "baseline", "baseline", base))
    return resultats


def quantile(valeurs: Sequence[float], q: float) -> float:
    """Quantile par interpolation linéaire, comme `ease.rapport.quantile`."""
    tries = sorted(valeurs)
    position = q * (len(tries) - 1)
    bas, haut = math.floor(position), math.ceil(position)
    return tries[bas] + (tries[haut] - tries[bas]) * (position - bas)


def bootstrap_pages(
    pages: Sequence[Sequence[bool]], tirages: int = TIRAGES, graine: int = GRAINE
) -> tuple[float, float]:
    """Intervalle à 95 % de la part de tests réussis, les pages tirées avec remise."""
    hasard = random.Random(graine)
    n = len(pages)
    sommes = [(sum(p), len(p)) for p in pages]
    valeurs: list[float] = []
    for _ in range(tirages):
        tirees = [sommes[hasard.randrange(n)] for _ in range(n)]
        valeurs.append(sum(r for r, _ in tirees) / sum(t for _, t in tirees))
    return quantile(valeurs, 0.025), quantile(valeurs, 0.975)


def marge_banc(reussites: Sequence[bool], tirages: int = TIRAGES_BANC, graine: int = GRAINE) -> float:
    """Deux écarts types de la moyenne sur des tests tirés avec remise, la marge que le banc publie."""
    hasard = random.Random(graine)
    n = len(reussites)
    moyennes = [sum(hasard.choice(reussites) for _ in range(n)) / n for _ in range(tirages)]
    return 2 * statistics.pstdev(moyennes)


@dataclass(frozen=True)
class Score:
    categorie: str
    pages: int
    tests: int
    reussis: int
    score: float
    bas: float
    haut: float
    marge_banc: float


def scorer(categorie: str, resultats: Sequence[Resultat], filtre: Callable[[Resultat], bool]) -> Score:
    par_page = _par_page(resultats, filtre)
    tous = [r for page in par_page.values() for r in page]
    bas, haut = bootstrap_pages(list(par_page.values()))
    return Score(categorie, len(par_page), len(tous), sum(tous), sum(tous) / len(tous), bas, haut, marge_banc(tous))


def scores(resultats: Sequence[Resultat]) -> list[Score]:
    """Les catégories publiées qui ont des tests, puis « toutes » (hors base), puis la base."""
    presentes = {r.categorie for r in resultats}
    lignes = [scorer(c, resultats, lambda r, c=c: r.categorie == c) for c in CATEGORIES_PUBLIEES if c in presentes]
    lignes.append(scorer("toutes", resultats, lambda r: r.categorie != "baseline"))
    lignes.append(scorer("baseline", resultats, lambda r: r.categorie == "baseline"))
    return lignes


def _par_page(resultats: Sequence[Resultat], filtre: Callable[[Resultat], bool]) -> dict[str, list[bool]]:
    par_page: dict[str, list[bool]] = {}
    for resultat in resultats:
        if filtre(resultat):
            par_page.setdefault(resultat.page, []).append(resultat.reussi)
    return par_page


def bootstrap_ecart_pages(
    a: Mapping[str, Sequence[bool]], b: Mapping[str, Sequence[bool]], tirages: int = TIRAGES, graine: int = GRAINE
) -> tuple[float, float]:
    """Intervalle à 95 % de score(b) moins score(a) ; les mêmes pages sont tirées pour les deux."""
    if sorted(a) != sorted(b) or any(len(a[p]) != len(b[p]) for p in a):
        raise ValueError("les deux mesures doivent porter sur les mêmes tests")
    pages = sorted(a)
    sommes = [(sum(a[p]), sum(b[p]), len(a[p])) for p in pages]
    hasard = random.Random(graine)
    valeurs: list[float] = []
    for _ in range(tirages):
        tirees = [sommes[hasard.randrange(len(pages))] for _ in pages]
        total = sum(t for _, _, t in tirees)
        valeurs.append((sum(rb for _, rb, _ in tirees) - sum(ra for ra, _, _ in tirees)) / total)
    return quantile(valeurs, 0.025), quantile(valeurs, 0.975)


@dataclass(frozen=True)
class Ecart:
    categorie: str
    tests: int
    ecart: float
    """Score de la seconde lecture moins score de la première."""
    bas: float
    haut: float


def ecarts(premiere: Sequence[Resultat], seconde: Sequence[Resultat]) -> list[Ecart]:
    """Pour chaque catégorie publiée et pour « toutes », l'écart apparié entre deux lectures."""
    filtres: list[tuple[str, Callable[[Resultat], bool]]] = [
        (c, lambda r, c=c: r.categorie == c) for c in CATEGORIES_PUBLIEES
    ]
    filtres.append(("toutes", lambda r: r.categorie != "baseline"))
    lignes: list[Ecart] = []
    for categorie, filtre in filtres:
        a, b = _par_page(premiere, filtre), _par_page(seconde, filtre)
        tests = sum(len(v) for v in a.values())
        if not tests:
            continue
        ecart = (sum(sum(v) for v in b.values()) - sum(sum(v) for v in a.values())) / tests
        bas, haut = bootstrap_ecart_pages(a, b)
        lignes.append(Ecart(categorie, tests, ecart, bas, haut))
    return lignes


def empreinte_code(lecture_seule: bool = False) -> str:
    """sha256 des sources d'EKE (`04_eke/src/eke`, chemins et contenus, triés) ; avec
    `lecture_seule`, de celles qui écrivent les sorties : tout `eke` hors `banc_public`, plus
    `banc_public/conversion.py`."""
    racine = racine_depot() / "04_eke" / "src" / "eke"
    condense = hashlib.sha256()
    for chemin in sorted(racine.rglob("*.py")):
        relatif = chemin.relative_to(racine).as_posix()
        if lecture_seule and relatif.startswith("banc_public/") and relatif != "banc_public/conversion.py":
            continue
        condense.update(relatif.encode() + b"\0" + chemin.read_bytes() + b"\0")
    return condense.hexdigest()


class SortiesPerimees(Exception):
    """Les sorties d'EKE ont été écrites par un autre code de lecture que celui d'aujourd'hui."""


def ecrire_conversion(durees: Mapping[str, Mapping[str, float]], dossier: Path = DOSSIER) -> None:
    """Note, à côté des sorties, le code et le moteur qui les ont écrites, et les durées."""
    contenu = {
        "date_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_lecture_sha256": empreinte_code(lecture_seule=True),
        "moteur": MOTEUR,
        "durees_s": durees,
    }
    chemin = dossier / "sorties" / "conversion.json"
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def lire_conversion(dossier: Path = DOSSIER) -> dict[str, Any]:
    """La note de conversion ; SortiesPerimees si le code de lecture a changé depuis."""
    chemin = dossier / "sorties" / "conversion.json"
    if not chemin.exists():
        raise SortiesPerimees(f"pas de note de conversion : {chemin} ; lancer d'abord convertir")
    note: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
    if note["code_lecture_sha256"] != empreinte_code(lecture_seule=True) or note["moteur"] != MOTEUR:
        raise SortiesPerimees("le code de lecture ou le moteur a changé depuis la conversion ; relancer convertir")
    return note


def commit_de_base() -> str:
    """Le commit de HEAD, lu dans `.git` sans lancer git ; « ? » s'il ne se lit pas."""
    git = racine_depot() / ".git"
    try:
        tete = (git / "HEAD").read_text().strip()
        if not tete.startswith("ref: "):
            return tete
        reference = tete.removeprefix("ref: ")
        fichier = git / reference
        if fichier.exists():
            return fichier.read_text().strip()
        for ligne in (git / "packed-refs").read_text().splitlines():
            if ligne.endswith(" " + reference):
                return ligne.split()[0]
    except OSError:
        pass
    return "?"


def _textes_des_tests(pages: Sequence[Page]) -> list[str]:
    return [str(t[c]) for p in pages for t in p.tests for c in CHAMPS_TEXTE if isinstance(t.get(c), str)]


def mesurer(variante: str, empreinte_manifeste: str, dossier: Path = DOSSIER) -> tuple[str, list[Resultat]]:
    """Passe tous les tests sur les sorties de la variante ; écrit la fiche et les résultats ;
    rend le résumé et les résultats."""
    conversion = lire_conversion(dossier)
    pages = charger(dossier_donnees(dossier))
    sorties = {p.identifiant: lire_sortie(dossier / "sorties", variante, p) for p in pages}
    resultats = [r for p in pages for r in evaluer_page(p, sorties[p.identifiant])]
    lignes = scores(resultats)
    durees: dict[str, float] = conversion["durees_s"][variante]
    textes = list(sorties.values()) + _textes_des_tests(pages)
    non_verifies = sorted({c for t in textes for c in translitteration.non_verifies(t)})
    maintenant = datetime.now(UTC)
    fiche: dict[str, Any] = {
        "mesure": f"EKE sur fr-bench-pdf2md, lecture « {variante} »",
        "date_utc": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "jeu": {"depot": DEPOT, "revision": REVISION, "manifeste_sha256": empreinte_manifeste, "pages": len(pages)},
        "lecteur": {
            "eke": VERSION,
            "variante": variante,
            "moteur": MOTEUR,
            "code_sha256": empreinte_code(),
            "code_lecture_sha256": conversion["code_lecture_sha256"],
            "commit_de_base": commit_de_base(),
            "sorties_ecrites_le": conversion["date_utc"],
        },
        "metrique": SOURCE_METRIQUE,
        "marges": {"methode": "bootstrap sur les pages, intervalle à 95 %", "tirages": TIRAGES, "graine": GRAINE},
        "machine": {"python": sys.version.split()[0], "systeme": platform.platform(), "processeur": platform.machine()},
        "duree_par_page_s": {
            "mediane": statistics.median(durees.values()),
            "moyenne": statistics.fmean(durees.values()),
        },
        "pages_sans_texte": sum(1 for s in sorties.values() if not s.strip()),
        "sorties_a_balise_html": sum(1 for s in sorties.values() if balise_veritable(s)),
        "textes_des_tests_a_balise_html": sum(1 for t in _textes_des_tests(pages) if balise_veritable(t)),
        "caracteres_non_verifies": "".join(non_verifies),
        "scores": [asdict(s) for s in lignes],
    }
    sortie = dossier / "mesures"
    sortie.mkdir(parents=True, exist_ok=True)
    base = sortie / f"{maintenant.strftime('%Y-%m-%dT%H%M%SZ')}_{variante}"
    base.with_suffix(".json").write_text(json.dumps(fiche, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with base.with_suffix(".jsonl").open("w", encoding="utf-8") as flux:
        for resultat in resultats:
            flux.write(json.dumps(asdict(resultat), ensure_ascii=False) + "\n")
    return resume(fiche, base), resultats


def ecrire_ecarts(
    premiere: tuple[str, Sequence[Resultat]], seconde: tuple[str, Sequence[Resultat]], dossier: Path = DOSSIER
) -> str:
    """Écrit et résume l'écart apparié de la seconde lecture sur la première (règle 2 du BRIEF)."""
    lignes = ecarts(premiere[1], seconde[1])
    maintenant = datetime.now(UTC)
    chemin = (
        dossier / "mesures" / f"{maintenant.strftime('%Y-%m-%dT%H%M%SZ')}_ecart_{seconde[0]}_moins_{premiere[0]}.json"
    )
    contenu = {
        "ecart": f"{seconde[0]} moins {premiere[0]}",
        "date_utc": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "marges": {
            "methode": "bootstrap apparié sur les pages, intervalle à 95 %",
            "tirages": TIRAGES,
            "graine": GRAINE,
        },
        "ecarts": [asdict(e) for e in lignes],
    }
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    texte = [f"Écart « {seconde[0]} » moins « {premiere[0]} », en points ; {chemin}"]
    for e in lignes:
        texte.append(f"  {e.categorie:<12} {_pc(e.ecart):>6}  [{_pc(e.bas)} ; {_pc(e.haut)}]  {e.tests} tests")
    return "\n".join(texte)


def _pc(valeur: float) -> str:
    return f"{100 * valeur:.1f}".replace(".", ",")


def resume(fiche: dict[str, Any], base: Path) -> str:
    lignes = [f"{fiche['mesure']}, {fiche['date_utc']} ; fiche {base.with_suffix('.json')}"]
    for s in fiche["scores"]:
        lignes.append(
            f"  {s['categorie']:<12} {_pc(s['score']):>5} %  [{_pc(s['bas'])} ; {_pc(s['haut'])}]"
            f"  {s['reussis']}/{s['tests']} tests, {s['pages']} pages"
        )
    if fiche["caracteres_non_verifies"]:
        lignes.append(f"  caractères non comparés à unidecode : {fiche['caracteres_non_verifies']!r}")
    return "\n".join(lignes)
