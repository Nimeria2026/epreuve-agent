"""Paires étiquette-valeur d'un document en français, chaque valeur typée, normalisée et citée.

Générique pour un document en français : aucune étiquette n'est attendue, aucune n'est propre à
Calorelle ou à un type de document. EKE rend toute paire qu'il trouve ; c'est à l'agent de
choisir « Total TTC » ou « Date de facture ». Quatre règles, dans cet ordre, sur chaque ligne
visuelle (`mise_en_page`) :

1. « Étiquette : valeur » dans un morceau, deux-points suivi d'un blanc (« 9:30 » ne coupe pas) ;
   un morceau qui finit par « : » prend pour valeur le morceau suivant de la même ligne.
2. Un morceau qui est tout entier un montant, une date, un IBAN ou un pourcentage prend pour
   étiquette le plus proche morceau à sa gauche qui a une lettre : la colonne de droite d'un
   tableau, ou une ligne « Total TTC      512,40 € ».
3. Un morceau qui finit par un montant, une date, un IBAN ou un pourcentage : le texte qui
   précède est l'étiquette (« Règlement par virement, IBAN FR76 9999 »).
4. Un morceau qui finit par une référence, faite de capitales, de chiffres et de séparateurs,
   au moins un chiffre (« FACTURE F-2026-1151 »), ou par un numéro après « n° ».

Un montant se lit en euros, à la française : « 1 284,00 € », « 12,5 EUR ». « 512.40 € » reste du
texte, faute de savoir si le point sépare les décimales ou les milliers. Un IBAN se reconnaît à
sa forme, sans vérifier sa clé : ceux de la PME fictive ne la respectent pas.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from eke.mise_en_page import Morceau

MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}  # fmt: skip
JOURS = r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)"
BLANC = r"[   ]"

NOMBRE = rf"-?(?:\d{{1,3}}(?:{BLANC}\d{{3}})+|\d{{1,3}}(?:\.\d{{3}})+(?=,)|\d+)(?:,\d+)?"
MONTANT = rf"(?P<montant>{NOMBRE}){BLANC}?(?:€|EUR\b|euros?\b)(?:{BLANC}+(?:HT|TTC|H\.T\.|T\.T\.C\.|net)\b)?"
POURCENTAGE = rf"(?P<pourcentage>-?\d+(?:,\d+)?){BLANC}?%"
DATE_LONGUE = (
    rf"(?:{JOURS}{BLANC}+)?(?P<jour>1er|\d{{1,2}}){BLANC}+(?P<mois>{'|'.join(MOIS)}){BLANC}+(?P<annee>\d{{4}})"
)
DATE_COURTE = r"(?P<j>\d{1,2})[/.](?P<m>\d{1,2})[/.](?P<a>\d{4})"
DATE_ISO = r"(?P<ia>\d{4})-(?P<im>\d{2})-(?P<ij>\d{2})"
IBAN = r"(?P<iban>[A-Z]{2}\d{2}(?:[  ]?[A-Z0-9]){11,30})"
REFERENCE = r"(?P<reference>(?=[A-Z0-9/._-]*\d)(?=[A-Z0-9/._-]*[A-Z/_-])[A-Z0-9][A-Z0-9/._-]*[A-Z0-9])"
NUMERO = r"(?P<etiquette_numero>.*?\b(?:n°|N°|no|No|numéro|Numéro))\s*(?P<numero>\d[\d/._-]*)"

TYPES: list[tuple[str, re.Pattern[str]]] = [
    ("montant", re.compile(MONTANT)),
    ("date", re.compile(rf"(?:{DATE_LONGUE}|{DATE_COURTE}|{DATE_ISO})", re.IGNORECASE)),
    ("iban", re.compile(IBAN)),
    ("pourcentage", re.compile(POURCENTAGE)),
]
SEPARATEUR = re.compile(r":(?=\s|$)")
APRES_ETIQUETTE = " ,;-–—"


@dataclass(frozen=True)
class Valeur:
    """Une paire étiquette-valeur ; `debut` et `fin` situent la valeur citée dans son morceau."""

    etiquette: str
    type: str
    valeur: str
    unite: str | None
    morceau: Morceau
    debut: int
    fin: int

    @property
    def texte(self) -> str:
        return self.morceau.texte[self.debut : self.fin]


@dataclass(frozen=True)
class Typage:
    type: str
    valeur: str
    unite: str | None
    debut: int
    fin: int


def _montant(texte: str) -> str:
    chiffres = re.sub(rf"{BLANC}|\.", "", texte).replace(",", ".")
    return str(Decimal(chiffres).quantize(Decimal("0.01")))


def _date(trouve: re.Match[str]) -> str | None:
    groupes = trouve.groupdict()
    if groupes.get("jour") is not None:
        jour = 1 if groupes["jour"].lower() == "1er" else int(groupes["jour"])
        mois, annee = MOIS[groupes["mois"].lower()], int(groupes["annee"])
    elif groupes.get("j") is not None:
        jour, mois, annee = int(groupes["j"]), int(groupes["m"]), int(groupes["a"])
    else:
        jour, mois, annee = int(groupes["ij"]), int(groupes["im"]), int(groupes["ia"])
    try:
        return date(annee, mois, jour).isoformat()
    except ValueError:
        return None


def _normaliser(type_: str, trouve: re.Match[str]) -> tuple[str, str | None] | None:
    """La valeur normalisée et son unité, ou None si la forme trompe (une date impossible)."""
    match type_:
        case "montant":
            return _montant(trouve.group("montant")), "EUR"
        case "pourcentage":
            return trouve.group("pourcentage").replace(",", "."), "%"
        case "iban":
            compact = re.sub(r"[  ]", "", trouve.group("iban"))
            return (compact, None) if 15 <= len(compact) <= 34 else None
        case _:
            iso = _date(trouve)
            return None if iso is None else (iso, None)


def typer(texte: str, debut: int = 0, entier: bool = True) -> Typage | None:
    """Le type de texte[debut:] : tout entier (entier=True) ou seulement sa fin, sinon None."""
    for type_, motif in TYPES:
        if entier:
            trouve = motif.fullmatch(texte, debut)
        else:
            trouve = next((t for t in motif.finditer(texte, debut) if t.end() == len(texte)), None)
        if trouve is None:
            continue
        normale = _normaliser(type_, trouve)
        if normale is not None:
            return Typage(type_, normale[0], normale[1], trouve.start(), trouve.end())
    return None


def _sans_blancs(texte: str, debut: int, fin: int) -> tuple[int, int]:
    while debut < fin and texte[debut].isspace():
        debut += 1
    while fin > debut and texte[fin - 1].isspace():
        fin -= 1
    return debut, fin


def _valeur_entiere(etiquette: str, morceau: Morceau, debut: int, fin: int) -> Valeur:
    """La valeur de texte[debut:fin], typée si elle l'est tout entière, du texte sinon."""
    typage = typer(morceau.texte[:fin], debut, entier=True)
    if typage is None:
        return Valeur(etiquette, "texte", morceau.texte[debut:fin], None, morceau, debut, fin)
    return Valeur(etiquette, typage.type, typage.valeur, typage.unite, morceau, debut, fin)


def _deux_points(ligne: Sequence[Morceau], rang: int) -> Valeur | None:
    """Règle 1."""
    morceau = ligne[rang]
    separateur = SEPARATEUR.search(morceau.texte)
    if separateur is None:
        return None
    etiquette = morceau.texte[: separateur.start()].strip()
    if not etiquette:
        return None
    debut, fin = _sans_blancs(morceau.texte, separateur.end(), len(morceau.texte))
    if debut < fin:
        return _valeur_entiere(etiquette, morceau, debut, fin)
    if rang + 1 < len(ligne):
        suivant = ligne[rang + 1]
        return _valeur_entiere(etiquette, suivant, 0, len(suivant.texte))
    return None


def _etiquette_a_gauche(ligne: Sequence[Morceau], rang: int, pris: set[int]) -> Morceau | None:
    """Règle 2 : le plus proche morceau à gauche qui a une lettre et n'est pas déjà une valeur."""
    for autre in range(rang - 1, -1, -1):
        if autre not in pris and any(c.isalpha() for c in ligne[autre].texte):
            return ligne[autre]
    return None


def _fin_typee(morceau: Morceau) -> Valeur | None:
    """Règles 3 et 4 : seulement si le morceau suivant n'est pas une valeur, qui le prendrait
    pour étiquette (règle 2)."""
    typage = typer(morceau.texte, entier=False)
    if typage is not None:
        etiquette = morceau.texte[: typage.debut].rstrip(APRES_ETIQUETTE)
        if etiquette:
            return Valeur(etiquette, typage.type, typage.valeur, typage.unite, morceau, typage.debut, typage.fin)
    numero = re.fullmatch(NUMERO, morceau.texte)
    if numero is not None and numero.group("etiquette_numero").strip():
        return Valeur(
            numero.group("etiquette_numero").strip(), "texte", numero.group("numero"), None,
            morceau, numero.start("numero"), numero.end("numero"),
        )  # fmt: skip
    reference = re.search(rf"{BLANC}{REFERENCE}$", morceau.texte)
    if reference is not None:
        etiquette = morceau.texte[: reference.start()].rstrip(APRES_ETIQUETTE)
        if etiquette and not any(c.isdigit() for c in etiquette):
            debut, fin = reference.start("reference"), reference.end("reference")
            return Valeur(etiquette, "texte", morceau.texte[debut:fin], None, morceau, debut, fin)
    return None


def valeurs_de_ligne(ligne: Sequence[Morceau]) -> list[Valeur]:
    """Les paires d'une ligne visuelle, de gauche à droite ; un morceau pris comme valeur n'est
    plus une étiquette."""
    valeurs: list[Valeur] = []
    pris: set[int] = set()
    for rang, morceau in enumerate(ligne):
        if rang in pris:
            continue
        valeur = _deux_points(ligne, rang)
        if valeur is not None:
            valeurs.append(valeur)
            if valeur.morceau is not morceau:
                pris.add(rang + 1)
            continue
        typage = typer(morceau.texte)
        if typage is not None:
            etiquette = _etiquette_a_gauche(ligne, rang, pris)
            if etiquette is not None:
                pris.add(rang)
                valeurs.append(
                    Valeur(etiquette.texte, typage.type, typage.valeur, typage.unite, morceau, 0, len(morceau.texte))
                )
            continue
        if rang + 1 < len(ligne) and typer(ligne[rang + 1].texte) is not None:
            continue
        valeur = _fin_typee(morceau)
        if valeur is not None:
            valeurs.append(valeur)
    return valeurs
