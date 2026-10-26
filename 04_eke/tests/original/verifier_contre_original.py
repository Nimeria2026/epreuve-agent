"""Compare la métrique portée dans EKE (`eke.banc_public`) au code original de fr-bench-pdf2md.

S'exécute dans l'environnement jetable décrit dans `README.md`, depuis la racine du dépôt :

    <python jetable> 04_eke/tests/original/verifier_contre_original.py table
    <python jetable> 04_eke/tests/original/verifier_contre_original.py comparer lignes pdfium

`table` relève, caractère par caractère, ce que fait unidecode des caractères non ASCII que la
mesure lit, et écrit les exceptions à la règle de `translitteration` dans
`99_local/bancs_documents/fr_bench_pdf2md/original/table_unidecode.json`.

`comparer` passe chaque test du jeu par le code original (chargement par `create_dataset` et
`load_single_test`, tests par `run`) et par le portage, sur les sorties d'EKE rangées par
`python -m eke.banc_public convertir`, et compte les désaccords : résultat des tests et des tests
de base, textes normalisés, partial_ratio, convert_to_markdown. Code de sortie 1 au premier
résultat en désaccord.
"""

# pyright: basic, reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources_originales import RACINE, preparer

sys.path.insert(0, str(preparer()))
sys.path.insert(0, str(RACINE / "04_eke" / "src"))
warnings.simplefilter("ignore")

from benchpdf2md.bench_tests.benchmark_tsts import BaselineTest, load_single_test, normalize_text  # noqa: E402
from benchpdf2md.create_dataset import create_dataset  # noqa: E402
from eke.banc_public import flou, html_markdown, jeu, metrique, translitteration  # noqa: E402
from html_to_markdown import convert_to_markdown  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402
from unidecode import unidecode  # noqa: E402

BANC = RACINE / "99_local" / "bancs_documents" / "fr_bench_pdf2md"
DONNEES = BANC / "6ee2095"
SORTIES = BANC / "sorties"
CHAMPS = ("text", "before", "after", "cell", "up", "down", "left", "right", "top_heading", "left_heading")


def h2m(texte: str) -> str:
    return convert_to_markdown(texte, escape_asterisks=False, escape_underscores=False, escape_misc=False)


def identifiant(pdf_path: str) -> str:
    relatif = Path(pdf_path).parent.relative_to(DONNEES / "pdfs")
    return f"{relatif.parts[0]}/{relatif.name}"


def sortie(variante: str, ident: str) -> str:
    dossier, nom = ident.split("/", 1)
    return (SORTIES / variante / dossier / f"{nom}.md").read_bytes().decode("utf-8")


def table(variantes: list[str]) -> None:
    caracteres: set[str] = set()
    for page in jeu.charger(DONNEES):
        textes = [t[c] for t in page.tests for c in CHAMPS if isinstance(t.get(c), str)]
        textes += [sortie(v, page.identifiant) for v in variantes]
        for texte in textes:
            caracteres.update(c for c in texte if ord(c) >= 0x80)
            caracteres.update(c for c in normalize_text(h2m(texte)) if ord(c) >= 0x80)
    exceptions = {}
    for caractere in sorted(caracteres):
        attendu = unidecode(caractere, errors="preserve")
        if translitteration.par_regle(caractere) != attendu:
            exceptions[caractere] = attendu
    resultat = {"verifies": "".join(sorted(caracteres)), "exceptions": exceptions}
    chemin = BANC / "original" / "table_unidecode.json"
    chemin.write_text(json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(caracteres)} caractères non ASCII, {len(exceptions)} exceptions à la règle ; {chemin}")
    manquants = set(caracteres) - translitteration.VERIFIES
    differents = {c for c, v in exceptions.items() if translitteration.EXCEPTIONS.get(c) != v}
    print(f"absents de VERIFIES : {len(manquants)} ; exceptions qui diffèrent du module : {len(differents)}")


def comparer(variante: str) -> bool:
    ds = create_dataset(DONNEES)
    portes = {t["id"]: t for p in jeu.charger(DONNEES) for t in p.tests}
    desaccords: list[tuple[str, str, bool, bool]] = []
    normalises = ratios = 0
    conversions: dict[str, bool] = {}
    lignes = ds.to_dict(orient="records")
    for ligne in lignes:
        ident = identifiant(ligne["pdf_path"])
        contenu = sortie(variante, ident)
        test = load_single_test(ligne)
        base = BaselineTest(
            pdf=ligne["pdf_path"], page=ligne["page"], id=f"{test.id}-b", type="baseline", category="baseline"
        )
        porte = portes[test.id]
        for nom, original, portage in (
            (test.id, bool(test.run(contenu)[0]), metrique.evaluer(porte, contenu)),
            (base.id, bool(base.run(contenu)[0]), metrique.test_base(contenu)),
        ):
            if original != portage:
                desaccords.append((nom, ident, original, portage))
        options = metrique.options_du_test(porte)
        for texte in [contenu] + [porte[c] for c in CHAMPS if isinstance(porte.get(c), str)]:
            if texte not in conversions:
                conversions[texte] = h2m(texte) == html_markdown.convertir(texte)
            if test.normalise(texte) != metrique.normaliser(options, texte):
                normalises += 1
        if porte["type"] in ("present", "absent"):
            a, b = test.normalise(test.text), test.normalise(contenu)
            if not porte.get("case_sensitive", True):
                a, b = a.lower(), b.lower()
            if fuzz.partial_ratio(a, b) != flou.partial_ratio(a, b):
                ratios += 1
    differentes = [t for t, egal in conversions.items() if not egal]
    print(f"{variante} : {len(lignes)} tests et autant de tests de base")
    print(f"  résultats en désaccord : {len(desaccords)}")
    for desaccord in desaccords[:20]:
        print("   ", desaccord)
    print(f"  normalisations différentes : {normalises} (test et texte)")
    print(f"  partial_ratio différents : {ratios}")
    print(
        f"  convert_to_markdown : {len(conversions)} textes distincts, {len(differentes)} différents, "
        f"dont {sum(html_markdown.balise_veritable(t) for t in differentes)} à balise"
    )
    return not desaccords


if __name__ == "__main__":
    if sys.argv[1] == "table":
        table(sys.argv[2:] or ["lignes", "pdfium"])
    else:
        resultats = [comparer(v) for v in sys.argv[2:]]
        sys.exit(0 if all(resultats) else 1)
