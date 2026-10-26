"""La métrique de fr-bench-pdf2md : ses tests unitaires, refaits à l'identique de leur code publié.

Source : `benchpdf2md/bench_tests/benchmark_tsts.py` du dépôt GitHub `ld-lab-pulsia/benchpdf2md`,
commit `ceab1548ac914bff6585fa5c6227e2b24c35cfdb` (licence MIT), lui-même adapté d'olmocr
(AllenAI) ; `md_tables_to_html` de vlmparse 0.1.8 (MIT). Les fonctions gardent leur ordre
d'opérations, expressions régulières comprises : `normalize_text`, `BasePDFTest.normalise`, puis
les tests `present`/`absent`, `order`, `table` et `baseline`. Seul le résultat (réussi ou non)
est rendu ; les explications d'échec du banc n'entrent pas dans le score.

Les trois bibliothèques que le banc appelle sont portées à part : `flou` (rapidfuzz),
`translitteration` (unidecode), `html_markdown` (html-to-markdown). Le portage est comparé au
code original, test par test, sur les sorties d'EKE (journal de l'étape 6, onzième entrée).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any

from eke.banc_public import flou
from eke.banc_public.html_markdown import convertir
from eke.banc_public.translitteration import translitterer

REMPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("‘", "'"),
    ("’", "'"),
    ("‚", "'"),
    ("“", '"'),
    ("”", '"'),
    ("„", '"'),
    ("＿", "_"),
    ("–", "-"),
    ("—", "-"),
    ("‑", "-"),
    ("‒", "-"),
    ("−", "-"),
    ("µ", "μ"),
    ("º", "°"),
    ("œ", "oe"),
    ("\\*", ""),
    ("\\*\\*", ""),
    ("« ", "«"),
    (" »", "»"),
    (" .", "."),
    (" :", ":"),
    (" ,", ","),
    (" !", "!"),
    (" ?", "?"),
    (" ;", ";"),
    ("É", "E"),
    ("☑", "[x]"),
    ("☐", "[ ]"),
    ("☒", "[x]"),
    ("✅", "[x]"),
    ("❌", "[x]"),
    ("❎", "[x]"),
    ("✓", "[x]"),
    ("✔", "[x]"),
    ("✗", "[x]"),
    ("✖", "[x]"),
    ("\U0001f5f9", "[x]"),
    ("[X]", "[x]"),
)
"""Le dictionnaire `replacements` de `normalize_text`, dans son ordre d'itération (la clé « ’ »,
écrite deux fois dans la source, garde sa première place)."""

COUPURE = re.compile(r"(?<=[^\W\d_])-\s*\r?\n?\s*(?=[^\W\d_])")
NON_ALPHANUM = re.compile(r"[^a-zA-Z0-9\.,:;\+\(\)\'\"]")
INTERDITS = re.compile(
    "[一-鿿぀-ゟ゠-ヿ\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff\U0001f1e0-\U0001f1ff]"
)
TABLEAU_MD = re.compile(r"(\|[^\n]*\|\n(?:\|[-\s:]*\|\n)?(?:\|[^\n]*\|\n?)*)", re.MULTILINE)
SEPARATEUR_MD = re.compile(r"^\|[-:\s|]+\|$")


def normaliser_texte(texte: str) -> str:
    """`normalize_text`."""
    texte = re.sub(r"<br/?>", " ", texte)
    texte = re.sub(r"\s+", " ", texte)
    texte = re.sub(r"\*\*(.*?)\*\*", r"\1", texte)
    texte = re.sub(r"\\\*(.*?)\\\*", r"\1", texte)
    texte = re.sub(r"__(.*?)__", r"\1", texte)
    texte = re.sub(r"</?b>", "", texte)
    texte = re.sub(r"</?i>", "", texte)
    texte = re.sub(r"\*(.*?)\*", r"\1", texte)
    texte = re.sub(r"_(.*?)_", r"\1", texte)
    texte = unicodedata.normalize("NFC", texte)
    for ancien, nouveau in REMPLACEMENTS:
        texte = texte.replace(ancien, nouveau)
    return texte


@dataclass(frozen=True)
class Options:
    """Les champs de `BasePDFTest` qui changent la normalisation, avec leurs valeurs par défaut."""

    alphanum: bool = False
    unidecode: bool = False
    ignore_space: bool = False
    ignore_newlines: bool = True
    ignore_chars: str = ""
    ignore_str: tuple[str, ...] = ()
    remove_line_break_hyphenation: bool = True


@lru_cache(maxsize=65536)
def normaliser(options: Options, texte: str) -> str:
    """`BasePDFTest.normalise(texte)`, avec `to_markdown=True` comme le banc l'appelle."""
    texte = convertir(texte)
    texte = normaliser_texte(texte)
    if options.unidecode:
        texte = translitterer(texte)
    if options.alphanum:
        texte = NON_ALPHANUM.sub("", texte).lower()
        texte = texte.replace(",", ".")
        texte = texte.replace(";", ":")
    if options.ignore_space:
        texte = re.sub(r"[^\S\r\n]+", "", texte)
    if options.ignore_newlines:
        texte = re.sub(r"\n+", "", texte)
    for caractere in options.ignore_chars:
        texte = texte.replace(caractere, "")
    for chaine in options.ignore_str:
        texte = texte.replace(chaine, "")
    if options.remove_line_break_hyphenation:
        texte = COUPURE.sub("", texte)
    return texte.strip()


def options_du_test(test: Mapping[str, Any]) -> Options:
    """Les options de normalisation d'un test, valeurs par défaut de `BasePDFTest` comprises."""
    return Options(
        alphanum=bool(test.get("alphanum", False)),
        unidecode=bool(test.get("unidecode", False)),
        ignore_space=bool(test.get("ignore_space", False)),
        ignore_newlines=bool(test.get("ignore_newlines", True)),
        ignore_chars=str(test.get("ignore_chars", "")),
        ignore_str=tuple(str(s) for s in test.get("ignore_str", [])),
        remove_line_break_hyphenation=bool(test.get("remove_line_break_hyphenation", True)),
    )


# ------------------------------------------------------------------------------- présence


def test_presence(test: Mapping[str, Any], contenu: str) -> bool:
    """`TextPresenceTest.run` : `present` réussit si le texte s'y trouve, `absent` sinon."""
    options = options_du_test(test)
    attendu = normaliser(options, str(test["text"]))
    sortie = normaliser(options, contenu)
    if not test.get("case_sensitive", True):
        attendu, sortie = attendu.lower(), sortie.lower()
    premiers, derniers = test.get("first_n"), test.get("last_n")
    if premiers and derniers:
        sortie = sortie[:premiers] + sortie[-derniers:]
    elif premiers:
        sortie = sortie[:premiers]
    elif derniers:
        sortie = sortie[-derniers:]
    ecarts = int(test.get("max_diffs", 0))
    seuil = 1.0 - (ecarts / (len(attendu) if len(attendu) > 0 else 1))
    meilleur = flou.partial_ratio(attendu, sortie) / 100.0
    if test.get("type", "present") == "present":
        return meilleur >= seuil
    return meilleur < seuil


# ----------------------------------------------------------------------------------- ordre


def correspondances(motif: str, texte: str, plafond: int) -> list[int]:
    """`find_near_matches` : pour chaque taille de fenêtre (n, n-1, n+1), le début de la première
    fenêtre la plus proche du motif, si sa distance de Levenshtein est au plus le plafond."""
    if not motif or not texte:
        return []
    debuts: list[int] = []
    for taille in (len(motif), len(motif) - 1, len(motif) + 1):
        if taille <= 0 or taille > len(texte):
            continue
        if plafond == 0:
            # Seule une fenêtre identique est à distance 0 ; extractOne garde la première.
            if taille == len(motif) and (position := texte.find(motif)) >= 0:
                debuts.append(position)
            continue
        morceaux = [texte[i : i + taille] for i in range(len(texte) - taille + 1)]
        meilleur = flou.premier_meilleur(motif, morceaux, plafond)
        if meilleur is not None:
            debuts.append(meilleur[0])
    return debuts


def test_ordre(test: Mapping[str, Any], contenu: str) -> bool:
    """`TextOrderTest.run` : un `before` trouvé commence avant un `after` trouvé."""
    ecarts = int(test.get("max_diffs", 0))
    if ecarts > len(str(test["before"])) // 2 or ecarts > len(str(test["after"])) // 2:
        raise ValueError(f"{test['id']} : max_diffs trop grand pour ce test (le banc le refuse au chargement)")
    options = options_du_test(test)
    sortie = normaliser(options, contenu)
    avant = correspondances(normaliser(options, str(test["before"])), sortie, ecarts)
    apres = correspondances(normaliser(options, str(test["after"])), sortie, ecarts)
    return any(a < b for a in avant for b in apres)


# --------------------------------------------------------------------------------- tableau


def md_tables_to_html(texte: str) -> str:
    """`md_tables_to_html` de vlmparse 0.1.8 : les tableaux Markdown en tableaux HTML."""

    def remplacer(trouve: re.Match[str]) -> str:
        bloc = trouve.group(1).strip()
        lignes = [ligne for ligne in bloc.split("\n") if ligne.strip()]
        if len(lignes) < 2 or not SEPARATEUR_MD.match(lignes[1]):
            return bloc
        entete = [c.strip() for c in lignes[0].split("|")[1:-1]]
        rangs = [[c.strip() for c in ligne.split("|")[1:-1]] for ligne in lignes[2:] if ligne.strip()]
        parties = ["<table>"]
        if entete:
            parties += ["<thead>", "<tr>", *(f"<th>{c}</th>" for c in entete), "</tr>", "</thead>"]
        if rangs:
            parties.append("<tbody>")
            for rang in rangs:
                parties += ["<tr>", *(f"<td>{c}</td>" for c in rang), "</tr>"]
            parties.append("</tbody>")
        parties.append("</table>")
        return "".join(parties)

    return TABLEAU_MD.sub(remplacer, texte)


VIDES = frozenset(
    (
        "area", "base", "br", "col", "embed", "hr", "img", "input", "keygen", "link", "menuitem", "meta", "param",
        "source", "track", "wbr", "basefont", "bgsound", "command", "frame", "image", "isindex", "nextid", "spacer",
    )
)  # fmt: skip
"""Balises sans contenu pour l'analyseur html.parser de BeautifulSoup 4.14."""


@dataclass
class _Noeud:
    nom: str
    attributs: dict[str, str]
    enfants: list[_Noeud | str] = field(default_factory=lambda: [])

    def descendants(self, noms: frozenset[str]) -> list[_Noeud]:
        trouves: list[_Noeud] = []
        for enfant in self.enfants:
            if isinstance(enfant, _Noeud):
                if enfant.nom in noms:
                    trouves.append(enfant)
                trouves.extend(enfant.descendants(noms))
        return trouves

    def texte(self) -> str:
        """`get_text()`, chaque `<br>` remplacé par une fin de ligne comme le banc le fait."""
        morceaux: list[str] = []
        for enfant in self.enfants:
            if isinstance(enfant, str):
                morceaux.append(enfant)
            elif enfant.nom == "br":
                morceaux.append("\n")
            elif enfant.nom not in ("script", "style", "template"):
                morceaux.append(enfant.texte())
        return "".join(morceaux)


class _Arbre(HTMLParser):
    """Un arbre comme celui de BeautifulSoup(contenu, "html.parser"), réduit à ce qu'en lit le
    test de tableau : balises, attributs et texte ; commentaires et déclarations ignorés."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.racine = _Noeud("[document]", {})
        self.pile = [self.racine]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        noeud = _Noeud(tag, {k: v or "" for k, v in attrs})
        self.pile[-1].enfants.append(noeud)
        if tag not in VIDES:
            self.pile.append(noeud)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.pile[-1].enfants.append(_Noeud(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for rang in range(len(self.pile) - 1, 0, -1):
            if self.pile[rang].nom == tag:
                del self.pile[rang:]
                return

    def handle_data(self, data: str) -> None:
        self.pile[-1].enfants.append(data)


def _tableaux(contenu: str) -> list[_Noeud]:
    if "<table" not in contenu.lower():
        return []
    arbre = _Arbre()
    arbre.feed(contenu)
    arbre.close()
    return arbre.racine.descendants(frozenset({"table"}))


@dataclass(frozen=True)
class _Case:
    rang: int
    colonne: int
    hauteur: int
    largeur: int
    texte: str
    entete: bool


def _cases(tableau: _Noeud, normaliser_case: Callable[[str], str]) -> list[_Case]:
    cases: list[_Case] = []
    occupees: set[tuple[int, int]] = set()
    for rang, ligne in enumerate(tableau.descendants(frozenset({"tr"}))):
        colonne = 0
        for case in ligne.descendants(frozenset({"th", "td"})):
            while (rang, colonne) in occupees:
                colonne += 1
            hauteur = int(case.attributs.get("rowspan", 1))
            largeur = int(case.attributs.get("colspan", 1))
            cases.append(
                _Case(rang, colonne, hauteur, largeur, normaliser_case(case.texte().strip()), case.nom == "th")
            )
            occupees.update((rang + i, colonne + j) for i in range(hauteur) for j in range(largeur))
            colonne += largeur
    return cases


def _seuil(ecarts: int, texte: str) -> float:
    return max(0.5, 1.0 - (ecarts / (len(texte) if len(texte) > 0 else 1)))


def _voisines(case: _Case, cases: Sequence[_Case]) -> dict[str, list[_Case]]:
    """Les cases que chaque contrainte du test regarde, comme `TableTest.run` les choisit."""
    fin_rang, fin_colonne = case.rang + case.hauteur, case.colonne + case.largeur

    def memes_colonnes(c: _Case) -> bool:
        return not (c.colonne >= fin_colonne or c.colonne + c.largeur <= case.colonne)

    def memes_rangs(c: _Case) -> bool:
        return not (c.rang >= fin_rang or c.rang + c.hauteur <= case.rang)

    autres = [c for c in cases if c != case]
    return {
        "up": [c for c in autres if c.rang + c.hauteur == case.rang and memes_colonnes(c)],
        "down": [c for c in autres if c.rang == fin_rang and memes_colonnes(c)],
        "left": [c for c in autres if c.colonne + c.largeur == case.colonne and memes_rangs(c)],
        "right": [c for c in autres if c.colonne == fin_colonne and memes_rangs(c)],
        "top_heading": [c for c in cases if c.entete and memes_colonnes(c)],
        "left_heading": [c for c in cases if c.colonne == 0 and memes_rangs(c)],
    }


def test_tableau(test: Mapping[str, Any], contenu: str) -> bool:
    """`TableTest.run` : une case du tableau et, si demandées, ses voisines et ses en-têtes."""
    options = options_du_test(test)
    ecarts = int(test.get("max_diffs", 0))
    contenu = md_tables_to_html(contenu)
    noms = ("cell", "up", "down", "left", "right", "top_heading", "left_heading")
    voulus = {nom: normaliser(options, str(test.get(nom, ""))) for nom in noms}
    cible = voulus["cell"]
    for tableau in _tableaux(contenu):
        cases = _cases(tableau, lambda texte: normaliser(options, texte))
        for case in cases:
            if flou.ratio(cible, case.texte) / 100.0 < _seuil(ecarts, cible):
                continue
            satisfait = True
            for nom, candidates in _voisines(case, cases).items():
                attendu = voulus[nom]
                if not attendu:
                    continue
                meilleure = max((flou.ratio(attendu, c.texte) / 100.0 for c in candidates), default=None)
                if meilleure is None or meilleure < _seuil(ecarts, attendu):
                    satisfait = False
            if satisfait:
                return True
    return False


# ------------------------------------------------------------------------------------ base


def _repetitions_finales(texte: str, taille_max: int = 5) -> list[int]:
    """`RepeatDetector.ngram_repeats` : combien de fois chaque n-gramme final se répète."""
    resultat = [0] * taille_max
    if not texte:
        return resultat
    texte = re.sub(r"\s+", " ", texte)
    for taille in range(1, taille_max + 1):
        if len(texte) < taille:
            continue
        cible = texte[-taille:]
        compte = 0
        position = len(texte) - taille
        while position >= 0 and texte[position : position + taille] == cible:
            compte += 1
            position -= taille
        resultat[taille - 1] = compte
    return resultat


def test_base(contenu: str, repetitions_max: int = 30) -> bool:
    """`BaselineTest.run` sur la sortie brute : un caractère alphanumérique au moins, pas plus de
    30 répétitions d'un n-gramme final, ni caractères chinois, japonais ou émojis."""
    if len("".join(c for c in contenu if c.isalnum()).strip()) == 0:
        return False
    if any(compte > repetitions_max for compte in _repetitions_finales(contenu)):
        return False
    return INTERDITS.search(contenu) is None


def evaluer(test: Mapping[str, Any], contenu: str) -> bool:
    """Le résultat d'un test du jeu sur une sortie, comme `test.run(md_text)[0]`."""
    sorte = test["type"]
    if sorte in ("present", "absent"):
        return test_presence(test, contenu)
    if sorte == "order":
        return test_ordre(test, contenu)
    if sorte == "table":
        return test_tableau(test, contenu)
    if sorte == "baseline":
        return test_base(contenu)
    raise ValueError(f"type de test inconnu : {sorte}")
