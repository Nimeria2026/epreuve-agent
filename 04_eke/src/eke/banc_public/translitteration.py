"""`unidecode(texte, errors="preserve")` d'unidecode 1.4.0, pour les caractères que la mesure lit.

unidecode (GPL-2.0-or-later) translittère caractère par caractère, sans contexte. Ce module ne
recopie pas ses tables : il applique une règle, la décomposition NFKD dont on garde les
caractères ASCII, et une liste d'exceptions, les caractères pour lesquels unidecode rend autre
chose. Exceptions et liste des caractères vérifiés : relevées le 2026-10-09 en comparant, un par
un, chaque caractère non ASCII des tests du jeu et des sorties d'EKE à unidecode 1.4.0.
"""

from __future__ import annotations

import unicodedata

# fmt: off
EXCEPTIONS: dict[str, str] = {
    "\x80": "", "\x81": "", "\x82": "", "\x83": "", "\x84": "", "\x86": "", "\x87": "", "\x88": "", "\x89": "",
    "\x8a": "", "\x8b": "", "\x8e": "", "\x8f": "", "\x90": "", "\x91": "", "\x94": "", "\x95": "", "\x96": "",
    "\x98": "", "\x99": "", "\x9a": "", "\x9d": "", "\x9e": "", "\x9f": "", "\xa1": "!", "\xa3": "PS", "\xa4": "$?",
    "\xa5": "Y=", "\xa7": "SS", "\xa8": "\"", "\xa9": "(c)", "\xab": "<<", "\xac": "!", "\xad": "", "\xae": "(r)",
    "\xaf": "-", "\xb0": "deg", "\xb1": "+-", "\xb4": "'", "\xb5": "u", "\xb6": "P", "\xb7": "*", "\xb8": ",",
    "\xbb": ">>", "\xbc": " 1/4", "\xbd": " 1/2", "\xbe": " 3/4", "\xbf": "?", "\xc6": "AE", "\xd0": "D",
    "\xd7": "x", "\xd8": "O", "\xde": "Th", "\xdf": "ss", "\xe6": "ae", "\xf0": "d", "\xf7": "/", "\xf8": "o",
    "\u0131": "i", "\u0152": "OE", "\u0153": "oe", "\u0275": "o", "\u02c6": "^", "\u0301": "", "\u0394": "D",
    "\u03a0": "P", "\u03a8": "Ps", "\u03a9": "O", "\u03ac": "a", "\u03ad": "e", "\u03b1": "a", "\u03b2": "b",
    "\u03b3": "g", "\u03b4": "d", "\u03b5": "e", "\u03b7": "e", "\u03b8": "th", "\u03b9": "i", "\u03bb": "l",
    "\u03bc": "m", "\u03bd": "n", "\u03c0": "p", "\u03c1": "r", "\u03c3": "s", "\u03c4": "t", "\u03c6": "ph",
    "\u03c9": "o", "\u03cd": "u", "\u0421": "S", "\u05d0": "A", "\u05dc": "l", "\u099e": "ny", "\u2010": "-",
    "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "--", "\u2018": "'", "\u2019": "'", "\u201a": ",",
    "\u201c": "\"", "\u201d": "\"", "\u201e": ",,", "\u2020": "+", "\u2021": "++", "\u2022": "*", "\u2028": "\x0a",
    "\u2039": "<", "\u203a": ">", "\u207b": "-", "\u20ac": "EUR", "\u2122": "(tm)", "\u2126": "ohm", "\u2191": "|",
    "\u2192": "-", "\u2193": "|", "\u2212": "-", "\u2260": "\u2260", "\u2264": "<=", "\u2265": ">=", "\u2588": "#",
    "\u25a0": "#", "\u25a1": "#", "\u25aa": "#", "\u25b2": "^", "\u25b6": ">", "\u25b7": ">", "\u25ba": ">",
    "\u25c6": "*", "\u25cb": "*", "\u25cf": "*", "\u2605": "", "\u2611": "", "\u2612": "", "\u2666": "diamonds",
    "\u266b": "", "\u2713": "", "\u2716": "", "\u274f": "", "\u2756": "", "\u2758": "|", "\u2776": "", "\u2777": "",
    "\u2778": "", "\u278a": "", "\u278b": "", "\u278c": "", "\u2794": "", "\u279c": "", "\u27a2": "",
    "\uacbd": "gyeong", "\ub780": "ran", "\uc2a4": "seu", "\uc545": "ag", "\uc5d0": "e", "\uc625": "og",
    "\uc678": "oe", "\uc74c": "eum", "\uc804": "jeon", "\ud1a0": "to", "\ud398": "pe", "\ud68c": "hoe",
    "\ufffd": "",
}
# fmt: on
"""Caractère : ce qu'en fait unidecode, là où la règle rendrait autre chose (163 valeurs)."""
VERIFIES: frozenset[str] = frozenset(
    "\x80\x81\x82\x83\x84\x86\x87\x88\x89\x8a\x8b\x8e\x8f\x90\x91\x94\x95\x96\x98\x99\x9a\x9d\x9e\x9f\xa0"
    "\xa1\xa3\xa4\xa5\xa7\xa8\xa9\xaa\xab\xac\xad\xae\xaf\xb0\xb1\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xbb"
    "\xbc\xbd\xbe\xbf\xc0\xc1\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xcb\xcc\xcd\xce\xcf\xd0\xd3\xd4\xd5\xd6"
    "\xd7\xd8\xd9\xda\xdb\xdc\xdd\xde\xdf\xe0\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xeb\xec\xed\xee\xef"
    "\xf0\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xfb\xfc\xff\u0116\u0117\u0119\u012e\u012f\u0131\u0150"
    "\u0152\u0153\u0154\u0160\u0161\u0173\u017e\u0275\u02b3\u02c6\u0301\u0394\u03a0\u03a8\u03a9\u03ac"
    "\u03ad\u03b1\u03b2\u03b3\u03b4\u03b5\u03b7\u03b8\u03b9\u03bb\u03bc\u03bd\u03c0\u03c1\u03c3\u03c4"
    "\u03c6\u03c9\u03cd\u0421\u05d0\u05dc\u099e\u1087\u1088\u1089\u1d2e\u1d49\u1d63\u2003\u2007\u2009"
    "\u2010\u2011\u2012\u2013\u2014\u2018\u2019\u201a\u201c\u201d\u201e\u2020\u2021\u2022\u2026\u2028"
    "\u202f\u2039\u203a\u207b\u207e\u2081\u2082\u2085\u2091\u209a\u209b\u209c\u20ac\u2122\u2126\u2191"
    "\u2192\u2193\u2200\u2206\u2208\u220e\u2212\u2219\u221a\u222a\u2248\u2260\u2264\u2265\u2282\u2588"
    "\u25a0\u25a1\u25aa\u25b2\u25b6\u25b7\u25ba\u25c6\u25cb\u25cf\u2605\u2611\u2612\u2666\u266b\u2713"
    "\u2716\u274f\u2756\u2758\u2776\u2777\u2778\u278a\u278b\u278c\u2794\u279c\u27a2\uacbd\ub780\uc2a4"
    "\uc545\uc5d0\uc625\uc678\uc74c\uc804\ud1a0\ud398\ud68c\uf007\uf01f\uf022\uf027\uf02d\uf02e\uf034"
    "\uf06c\uf06e\uf070\uf071\uf076\uf080\uf084\uf09e\uf09f\uf0a7\uf0a8\uf0a9\uf0aa\uf0ab\uf0ac\uf0b7"
    "\uf0c6\uf0d8\uf0dc\uf0dd\uf0e9\uf0ea\uf0eb\uf0f5\uf0fc\uf108\uf111\uf6ba\uf8eb\uf8ec\uf8ed\uf8f1"
    "\uf8f2\uf8f3\uf8f4\uf8f6\uf8f7\uf8f8\ufb01\ufb02\ufffd"
)
"""Les 306 caractères non ASCII dont la translittération a été comparée à unidecode."""


def par_regle(caractere: str) -> str:
    """La décomposition NFKD réduite à l'ASCII ; le caractère lui-même si elle n'en garde rien."""
    decompose = "".join(c for c in unicodedata.normalize("NFKD", caractere) if ord(c) < 0x80)
    return decompose or caractere


def translitterer_caractere(caractere: str) -> str:
    if ord(caractere) < 0x80:
        return caractere
    return EXCEPTIONS.get(caractere, par_regle(caractere))


def translitterer(texte: str) -> str:
    if texte.isascii():
        return texte
    return "".join(translitterer_caractere(c) for c in texte)


def non_verifies(texte: str) -> set[str]:
    """Les caractères du texte dont la translittération n'a pas été comparée à unidecode."""
    return {c for c in texte if ord(c) >= 0x80 and c not in VERIFIES}
