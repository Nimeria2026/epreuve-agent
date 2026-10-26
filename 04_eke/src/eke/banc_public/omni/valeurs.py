"""Quand deux valeurs sont la même valeur : la forme canonique d'OmniExtractBench, refaite.

Reprise de `omni_extract_bench/values.py` et `recognise.py` (paquet `omni-extract-bench` 0.1.7,
Datalab, licence Apache 2.0), fonction par fonction, en bibliothèque standard comme l'original,
typée pour pyright strict. Deux valeurs sont égales si leurs clés (`cle`) sont égales ; aucun
modèle, aucun crédit partiel. Ordre des routes : booléen, nombre décimal, date, heure, texte.
Les replis du texte s'appliquent dans l'ordre de `REPLIS` ; un repli qui décide la clé arrête
la suite.

Deux écarts d'écriture avec l'original, sans effet sur le résultat : l'original présélectionne
les formats de date par les expressions internes de `_strptime`, ici chaque format est essayé
par `datetime.strptime`, qui exige la même correspondance complète, dans le même ordre ; et un
texte ASCII qui ne peut correspondre à aucun format de date ne passe pas par strptime
(`_ni_date_ni_heure`). La
vérification contre l'original, valeur par valeur, est dans `04_eke/tests/original/omni/`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from functools import lru_cache

FORMATS_DATE = (
    "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y",
    "%d %B %Y", "%d-%b-%Y", "%d%b%Y", "%m/%d/%y", "%Y/%m/%d", "%d.%m.%Y",
    "%m.%d.%Y", "%b %d %Y", "%B %d %Y",
)  # fmt: skip
FORMATS_DATE_HEURE = (
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M",
)  # fmt: skip
CHIFFRES_FRACTION = 7
EXPOSANT_MAX = 100

_CHIFFRE = re.compile(r"\d")
_LETTRE_OU_SEPARATEUR = re.compile(r"[A-Za-z\-/.]")
_HORS_FORMATS_NUMERIQUES = re.compile(r"[^0-9\s\-/.:Tt+Z]")
_MOIS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_TIRETS = re.compile(r"-+")
_RENVOI = re.compile(r"\s*\[\s*(?:\d{1,2}|[a-z])\s*\]")
_PUCE = re.compile(r"^[•‣◦▪▶∙●■](?=\s|$)")
_ZEROS_DEVANT = re.compile(r"-?0\d")
_NOMBRE_SIMPLE = re.compile(r"[+-]?\d+(?:\.\d+)?")
_POINT_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")
_NEGATIF_ENTRE_PARENTHESES = re.compile(r"^\((.*)\)$")
TYPOGRAPHIE = (
    ("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("‚", ","),
    ("„", '"'), ("′", "'"), ("″", '"'), ("–", "-"), ("—", "-"),
    ("‐", "-"), ("‑", "-"), ("−", "-"), ("―", "-"), ("⁄", "/"),
)  # fmt: skip


class _Final(str):
    """Résultat d'un repli qui décide la clé : la suite des replis s'arrête."""

    __slots__ = ()


def _casse(s: str) -> str:
    return s.strip().lower()


def _accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c) and unicodedata.category(c) != "Cf")
    return s.replace("μ", "u")


def _renvoi(s: str) -> str:
    sortie = _RENVOI.sub("", s)
    return sortie if sortie.strip() else s


def _typographie(s: str) -> str:
    for a, b in TYPOGRAPHIE:
        s = s.replace(a, b)
    return s


def _puce(s: str) -> str:
    return _PUCE.sub("", s)


def _nombre(s: str) -> str:
    nombre = s.replace(",", "").replace("$", "").replace("%", "").strip()
    if not _NOMBRE_SIMPLE.fullmatch(nombre):
        return s
    if _ZEROS_DEVANT.match(nombre):
        return s
    f = float(nombre)
    return _Final(str(int(f)) if f == int(f) else str(f))


def _tiret(s: str) -> str:
    return _Final("#ph_dash") if _TIRETS.fullmatch(re.sub(r"\s+", "", s)) else s


def _ponctuation(s: str) -> str:
    if len(_POINT_DECIMAL.findall(s)) == 1:
        s = _POINT_DECIMAL.sub("\x00", s)
    s = re.sub(r"[\s,\-.]", "", s)
    return s.replace("\x00", ".")


def _guillemets(s: str) -> str:
    return s.strip("\"'").replace("(", "").replace(")", "").replace("/", "")


REPLIS: tuple[tuple[str, Callable[[str], str]], ...] = (
    ("case", _casse),
    ("accents", _accents),
    ("footnote marker", _renvoi),
    ("typography", _typographie),
    ("list marker", _puce),
    ("number", _nombre),
    ("dash mark", _tiret),
    ("punctuation", _ponctuation),
    ("quotes and brackets", _guillemets),
)
"""Les replis de l'original (`FOLDS`), sous leur nom d'origine, dans le même ordre."""


def _replier(s: str) -> str:
    for _nom, repli in REPLIS:
        s = repli(s)
        if isinstance(s, _Final):
            break
    return str(s)


def _texte(v: object) -> str:
    """`str(v)` à la manière de Python, qui écrit `True` pour un booléen."""
    return str(v)


def _canon(v: object) -> str:
    """Les replis, rendus totaux : une erreur imprévue rend le texte réduit, sans propager."""
    try:
        return _replier(_texte(v))
    except Exception:
        return " ".join(_texte(v).split()).lower()[:64]


def _formats_complets(s: str, formats: tuple[str, ...]) -> datetime | None:
    for format_ in formats:
        try:
            return datetime.strptime(s, format_)
        except ValueError:
            pass
    return None


def _ni_date_ni_heure(s: str) -> bool:
    """Condition nécessaire, pour aller vite, sans changer le résultat : un texte ASCII ne se lit
    comme une date ou une heure que s'il porte un nom de mois (dont « %B » et « %b » acceptent
    les trois premières lettres au moins) ou s'il n'a que des chiffres, des blancs et les signes
    des formats numériques (« - », « / », « . », « : », « T », « + », « Z »), dont au moins un
    « - », « / » ou « . ». Un texte non ASCII passe toujours par strptime, dont les expressions
    acceptent des chiffres et des lettres Unicode."""
    if not s.isascii():
        return False
    if _LETTRE_OU_SEPARATEUR.search(s) is None:
        return True
    bas = s.lower()
    if any(mois in bas for mois in _MOIS):
        return False
    return _HORS_FORMATS_NUMERIQUES.search(s) is not None


def en_date(v: object) -> str | None:
    """La date ISO que désigne la valeur, ou None ; un horodatage à minuit compte."""
    s = _texte(v).strip()
    if not _CHIFFRE.search(s) or len(s) > 34 or _ni_date_ni_heure(s):
        return None
    for format_ in FORMATS_DATE:
        try:
            return datetime.strptime(s, format_).date().isoformat()
        except ValueError:
            pass
    instant = _formats_complets(s, FORMATS_DATE_HEURE)
    if instant is not None and (instant.hour, instant.minute, instant.second, instant.microsecond) == (0, 0, 0, 0):
        return instant.date().isoformat()
    return None


def en_heure(v: object) -> str | None:
    """L'instant ISO, ou None ; minuit revient à `en_date`."""
    s = _texte(v).strip()
    if not _CHIFFRE.search(s) or len(s) > 34 or _ni_date_ni_heure(s):
        return None
    instant = _formats_complets(s, FORMATS_DATE_HEURE)
    if instant is None or (instant.hour, instant.minute, instant.second, instant.microsecond) == (0, 0, 0, 0):
        return None
    return instant.replace(tzinfo=None).isoformat(timespec="microseconds")


def _signe(s: str) -> tuple[str, int]:
    s = s.strip()
    signe = 1
    m = _NEGATIF_ENTRE_PARENTHESES.match(s)
    if m:
        signe, s = -1, m.group(1).strip()
    s = s.replace("−", "-").replace("–", "-")
    if s.endswith("-"):
        signe, s = -signe, s[:-1].strip()
    while s.startswith(("-", "+")):
        if s[0] == "-":
            signe = -signe
        s = s[1:].strip()
    return s, signe


def _texte_numerique(v: object) -> str | None:
    """Seul un texte qui porte un « . » est un nombre décimal : un identifiant reste exact."""
    corps, signe = _signe(_texte(v))
    corps = corps.replace(",", "").replace("$", "").replace("%", "").replace(" ", "")
    if "." not in corps:
        return None
    return ("-" if signe < 0 else "") + corps


def en_decimal(v: object) -> Decimal | None:
    t = _texte_numerique(v)
    if t is None:
        return None
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    if not d.is_finite() or not -EXPOSANT_MAX <= d.adjusted() <= EXPOSANT_MAX:
        return None
    return d


def _places(d: Decimal) -> int:
    """Décimales gardées : 7 chiffres significatifs, sans compter les zéros de tête."""
    _sgn, chiffres, exposant = d.as_tuple()
    if not isinstance(exposant, int) or exposant >= 0:
        return 0
    largeur = -exposant
    fraction = ((0,) * (largeur - len(chiffres)) + chiffres)[-largeur:]
    zeros = 0
    for chiffre in fraction:
        if chiffre:
            break
        zeros += 1
    if zeros == largeur:
        return 0
    return CHIFFRES_FRACTION + zeros


def arrondir(d: Decimal) -> Decimal:
    """`d`, sa partie fractionnaire arrondie ; la partie entière reste exacte."""
    places = _places(d)
    if not places:
        return d
    with localcontext() as contexte:
        contexte.prec = places + max(d.adjusted(), 0) + 2
        return d.quantize(Decimal(1).scaleb(-places))


def _cle_sans_garde(v: object) -> str:
    if isinstance(v, bool):
        return _canon(v)
    d = en_decimal(v)
    if d is not None:
        q = arrondir(d)
        if q == q.to_integral_value():
            return _canon(int(q))
        return _canon(f"{q.normalize():f}")
    jour = en_date(v)
    if jour:
        return f"#d{jour}"
    heure = en_heure(v)
    if heure:
        return f"#t{heure}"
    return _canon(_texte(v))


def ne_dit_rien(v: object) -> bool:
    """`states_nothing` : null, chaîne vide ou de blancs ; « N/A » et 0 disent quelque chose."""
    return v is None or (isinstance(v, str) and not v.strip())


def cle(v: object) -> str:
    """La clé canonique (`canon_key`) : deux valeurs sont égales si leurs clés le sont. Une
    valeur que les replis videraient se compare à elle-même, blancs retirés."""
    if v is None or v == [] or v == {} or (isinstance(v, str) and not v.strip()):
        return ""
    k = _cle_sans_garde(v)
    if k == "":
        return re.sub(r"\s+", "", _texte(v).strip().lower())
    return k


@lru_cache(maxsize=1_000_000)
def cle_texte(s: str) -> str:
    """`cle` d'un texte lu dans un document, mise en cache : les mêmes mots reviennent souvent."""
    return cle(s)
