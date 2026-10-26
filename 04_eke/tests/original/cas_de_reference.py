"""Écrit `04_eke/tests/cas_fr_bench_pdf2md.json` : des cas synthétiques et le résultat qu'en donne
le code original de fr-bench-pdf2md, oracles des tests de `eke.banc_public`.

S'exécute dans l'environnement jetable décrit dans `README.md`, depuis la racine du dépôt :

    <python jetable> 04_eke/tests/original/cas_de_reference.py

Aucun texte du jeu n'entre dans ces cas : ils sont écrits ici ou tirés au hasard (graine fixe).
"""

# pyright: basic, reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

import json
import random
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources_originales import COMMIT, RACINE, preparer

sys.path.insert(0, str(preparer()))
warnings.simplefilter("ignore")

import html_to_markdown  # noqa: E402
import rapidfuzz  # noqa: E402
import unidecode as module_unidecode  # noqa: E402
from benchpdf2md.bench_tests.benchmark_tsts import TextPresenceTest, find_near_matches, load_single_test  # noqa: E402
from html_to_markdown import convert_to_markdown  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402
from rapidfuzz.distance import Levenshtein  # noqa: E402

SORTIE = RACINE / "04_eke" / "tests" / "cas_fr_bench_pdf2md.json"
HASARD = random.Random(20261009)


def au_hasard(longueur: int, alphabet: str) -> str:
    return "".join(HASARD.choice(alphabet) for _ in range(longueur))


def paires() -> list[tuple[str, str]]:
    cas = [("", ""), ("a", ""), ("", "abc"), ("abc", "abc"), ("abc", "xabcx"), ("bonjour", "Bonjour")]
    cas += [
        ("Dépôt d'un rapport", "1re délibération. Dépôt d'un rapport de M. Henry"),
        ("texte", "un très long texte de référence que la sortie ne contient pas"),
        ("un très long texte de référence", "texte"),
    ]
    for _ in range(150):
        cas.append((au_hasard(HASARD.randint(1, 20), "abcde "), au_hasard(HASARD.randint(0, 60), "abcde ")))
    for _ in range(60):
        aiguille = au_hasard(HASARD.randint(65, 120), "abcdefgh ")
        meule = au_hasard(HASARD.randint(0, 80), "abcdefgh ") + aiguille[5:-5] + au_hasard(HASARD.randint(0, 80), "ab")
        cas.append((aiguille, meule))
    for _ in range(30):
        n = HASARD.randint(1, 90)
        cas.append((au_hasard(n, "abcd "), au_hasard(n, "abcd ")))
    return cas


SONDES_H2M = [
    "a\nb", "a\n\nb", "  a  ", "a\tb", "a b", "a b", "a\rb", "a\r\nb", "a\x0cb", "a \nb", " \nx",
    "R&D", "a & b", "&amp;", "&lt;", "&eacute;", "&copy", "&#233;", "&#x41;", "&nbsp;", "&nosuchentity;",
    "AT&T;", "R&D &amp; x", "&#+65;", "&#55296;", "&#x110000;", "&AMP;", "&lesg;", "&;", "&#;", "&#x;",
    "x < y", "<5", "a <5", "R&D <5", "a&lt;b<5", "1<2<3", "<", "a<", "<<5", "<é", "<!5", "</5",
    "<5 a \nb", "<5 a  \n  b", "<5\n a", "  <5 a ", "<5 a \n \n b", "<5\ta\t\nb", " \n<5", "\n\n<5 a",
    "a <5\n\n\n", "<5 &amp; &nbsp; x", "<5 a \x0b \nb", "9H-12H30<br>13H30-17H", "a<br/>b",
    "*a* _b_ **c**", "# t\n- l", "| a | b |\n|---|---|\n| 1 | 2 |", "", " ", "\n", "x\n", "\nx",
    "a\x02b c d e f g h", "a\x00b", "\x01\x02\x03abc", "%PDF-1.4 x",
]  # fmt: skip

OPTIONS: list[dict[str, Any]] = [
    {},
    {"alphanum": True, "unidecode": True},
    {"unidecode": True},
    {"alphanum": True, "unidecode": True, "ignore_space": True, "ignore_str": ["-", "*"]},
    {"unidecode": True, "ignore_chars": "][()", "ignore_newlines": False},
    {"alphanum": False, "unidecode": False, "remove_line_break_hyphenation": False},
]

TEXTES = [
    "L’accueil du « Musée » — œuvre d’Émile, É-T-É : 25 µm, 3º, [X] fait",
    "exam-\nple, week-end, Jean-Michel, x-\n145",
    "**Gras** et *italique* et __souligné__ et _penché_, <b>b</b> <i>i</i> \\*étoile\\*",
    "Ligne une<br>ligne deux<br/>trois ; quatre ! cinq ?",
    "☑ oui ☐ non ☒ peut-être ✓ ✔ ✗ ✖ ✅ ❌ ❎",
    "Prix : 1 234,50 € TTC — « net »",
    "Tél. 01 23 45 67 89 ; Fax.(01) 98-76",
    "R&D &amp; S&P 500 < 5 %",
    "  espaces   multiples\t et\n\n retours  ",
    "ﬁn de l’œuvre",
]


def cas_tests() -> list[dict[str, Any]]:
    contenu = (
        "Rapport annuel\n\nDépôt d'un rapport de M. Henry Boucher sur la proposition de loi, adoptée par la "
        "Chambre.\n\nLa séance est ouverte à quinze heures.\n\n| Région | 2022 | 2023 |\n|---|---|---|\n"
        "| Nord | 12 | 14 |\n| Sud | 7 | 9 |\n\nFin du docu-\nment."
    )
    sans_tableau = "Première colonne puis seconde colonne.\nLa seconde colonne suit."
    html = (
        "<table><tr><th>A</th><th colspan='2'>B</th></tr><tr><td rowspan='2'>x</td><td>1</td><td>2</td></tr>"
        "<tr><td>3</td><td>4</td></tr></table>"
    )
    long_ref = "La séance est ouverte à quinze heures. Dépôt d'un rapport de M. Henry Boucher sur la proposition"
    tests: list[tuple[dict[str, Any], str]] = [
        ({"type": "present", "text": "Dépôt d'un rapport de M. Henry Boucher"}, contenu),
        ({"type": "present", "text": "dépôt d'un rapport", "case_sensitive": False}, contenu),
        ({"type": "present", "text": "dépôt d'un rapport"}, contenu),
        ({"type": "present", "text": "Depot d un rapport", "alphanum": True, "unidecode": True}, contenu),
        ({"type": "present", "text": "document.", "alphanum": True}, contenu),
        ({"type": "present", "text": "Fin du document"}, contenu),
        ({"type": "present", "text": "Rapport annuel", "first_n": 20}, contenu),
        ({"type": "present", "text": "Rapport annuel", "last_n": 20}, contenu),
        ({"type": "present", "text": long_ref, "max_diffs": 3}, contenu),
        ({"type": "present", "text": long_ref.replace("quinze", "seize"), "max_diffs": 4}, contenu),
        ({"type": "present", "text": long_ref.replace("quinze", "seize"), "max_diffs": 1}, contenu),
        ({"type": "present", "text": "ouverte"}, "ouverte"),
        ({"type": "present", "text": "La séance est ouverte"}, "ouverte"),
        ({"type": "present", "text": "rien"}, ""),
        ({"type": "absent", "text": "Annexe secrète"}, contenu),
        ({"type": "absent", "text": "La séance"}, contenu),
        ({"type": "order", "before": "Dépôt d'un rapport", "after": "La séance est ouverte"}, contenu),
        ({"type": "order", "before": "La séance est ouverte", "after": "Dépôt d'un rapport"}, contenu),
        ({"type": "order", "before": "Depot d'un rapport", "after": "La seance", "max_diffs": 2}, contenu),
        ({"type": "order", "before": "Première colonne", "after": "seconde colonne"}, sans_tableau),
        ({"type": "order", "before": "seconde colonne", "after": "Première colonne"}, sans_tableau),
        ({"type": "table", "cell": "12", "left": "Nord", "up": "2022", "right": "14"}, contenu),
        ({"type": "table", "cell": "12", "left": "Sud"}, contenu),
        ({"type": "table", "cell": "9", "top_heading": "2023", "left_heading": "Sud"}, contenu),
        ({"type": "table", "cell": "Nord", "down": "Sud", "up": "Région"}, contenu),
        ({"type": "table", "cell": "13", "max_diffs": 1}, contenu),
        ({"type": "table", "cell": "1"}, sans_tableau),
        ({"type": "table", "cell": "3", "left": "x", "up": "1", "right": "4"}, html),
        ({"type": "table", "cell": "1", "top_heading": "B", "left": "x"}, html),
        ({"type": "table", "cell": "A", "down": "x"}, html),
        ({"type": "baseline"}, contenu),
        ({"type": "baseline"}, ""),
        ({"type": "baseline"}, "   \n  "),
        ({"type": "baseline"}, "début " + "ab " * 31),
        ({"type": "baseline"}, "début " + "ab " * 29),
        ({"type": "baseline"}, "texte 中文"),
        ({"type": "baseline"}, "texte \U0001f600"),
    ]
    sortie: list[dict[str, Any]] = []
    for rang, (test, texte) in enumerate(tests):
        complet = {"pdf": "cas.pdf", "page": 0, "id": f"cas{rang}", "category": "cas", **test}
        reussi, _, _ = load_single_test(complet).run(texte)
        sortie.append({"test": complet, "contenu": texte, "reussi": bool(reussi)})
    return sortie


def h2m(texte: str) -> str | None:
    try:
        return convert_to_markdown(texte, escape_asterisks=False, escape_underscores=False, escape_misc=False)
    except ValueError:
        return None


def main() -> None:
    cas_paires = paires()
    proches = [
        ("rapport", "le rapport du rapporteur", 0),
        ("rapport", "le raport du rapporteur", 1),
        ("ab", "xb ab ab", 0),
        ("abc", "zzzz", 1),
        ("abcdef", "abxdef abcdxf", 1),
    ]
    contenu = {
        "source": {
            "banc": f"github.com/ld-lab-pulsia/benchpdf2md@{COMMIT}",
            "rapidfuzz": rapidfuzz.__version__,
            "unidecode": module_unidecode.__name__ + " 1.4.0",
            "html_to_markdown": html_to_markdown.__name__ + " 2.20.0",
            "ecrit_le": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "partial_ratio": [[a, b, fuzz.partial_ratio(a, b)] for a, b in cas_paires],
        "ratio": [[a, b, fuzz.ratio(a, b)] for a, b in cas_paires[:120]],
        "levenshtein": [[a, b, Levenshtein.distance(a, b)] for a, b in cas_paires[:80]],
        "correspondances": [[m, t, k, [x.start for x in find_near_matches(m, t, k)]] for m, t, k in proches],
        "convert_to_markdown": [[t, h2m(t)] for t in SONDES_H2M],
        "normalise": [
            [o, t, TextPresenceTest(pdf="cas.pdf", page=0, id="n", type="present", text="", **o).normalise(t)]
            for o in OPTIONS
            for t in TEXTES
        ],
        "tests": cas_tests(),
    }
    SORTIE.write_text(json.dumps(contenu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{SORTIE} : {sum(len(v) for k, v in contenu.items() if k != 'source')} cas")


if __name__ == "__main__":
    main()
