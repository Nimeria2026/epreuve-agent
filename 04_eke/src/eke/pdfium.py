"""Le seul module d'EKE qui parle à pypdfium2 : il en rend des types propres.

pypdfium2 (BSD-3-Clause ou Apache-2.0, PDFium sous BSD-3-Clause ; licence lue le 2026-10-08) n'a
pas d'annotations de types complètes : pyright strict ne sait pas typer ses retours. Ses appels
restent ici, et le reste d'EKE ne voit que des pages, des caractères et des zones dans le repère
de la page affichée (`geometrie.Repere`).

Ce que PDFium rend d'un caractère : son texte Unicode, sa boîte « large » (la hauteur de la
police, pas seulement l'encre), et s'il l'a ajouté lui-même (espace ou fin de ligne qu'il déduit
de la position du texte, absents du PDF).

PDFium remplace le trait d'union d'un mot coupé en fin de ligne (« - » ou trait d'union
conditionnel) par le caractère de contrôle 0x02, et le signale par `FPDFText_IsHyphen`. Ce
module rend « - », ce qui est tracé sur la page (journal de l'étape 6, dix-septième entrée). Un
0x02 sans ce signal vient d'une police dont la table Unicode est fausse : il reste tel quel.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import ctypes
import threading
from dataclasses import dataclass

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from eke.geometrie import Repere, Zone, union

MOTEUR = f"pypdfium2 {pdfium.PYPDFIUM_INFO} (PDFium {pdfium.PDFIUM_INFO})"
"""Bibliothèque de lecture et sa version, telles que le contrat les rend (champ lecteur.moteur)."""
_VERROU = threading.Lock()
MARQUE_COUPURE = 0x02
"""Ce que PDFium rend à la place du trait d'union d'un mot coupé en fin de ligne."""


class DocumentIllisible(Exception):
    """Le fichier n'est pas un PDF que PDFium sait ouvrir (abîmé, chiffré, autre format)."""


@dataclass(frozen=True)
class Caractere:
    """Un caractère de la page, dans l'ordre où PDFium le lit."""

    texte: str
    zone: Zone
    """Boîte du caractère sur la page affichée ; vide pour une fin de ligne ajoutée."""
    ajoute: bool
    """Vrai si PDFium l'a ajouté (espace ou fin de ligne déduite de la position du texte)."""


@dataclass(frozen=True)
class PageLue:
    numero: int
    """À partir de 1."""
    repere: Repere
    caracteres: tuple[Caractere, ...]

    @property
    def largeur(self) -> float:
        return self.repere.largeur

    @property
    def hauteur(self) -> float:
        return self.repere.hauteur


@dataclass(frozen=True)
class Image:
    """Une page rendue en niveaux de gris, un octet par pixel, 0 pour le noir."""

    largeur: int
    hauteur: int
    pas: int
    """Octets par ligne de pixels, au moins la largeur."""
    pixels: bytes

    def gris(self, x: int, y: int) -> int:
        return self.pixels[y * self.pas + x]


def _ouvrir(donnees: bytes) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(donnees)
    except pdfium.PdfiumError as erreur:
        raise DocumentIllisible(f"PDF illisible : {erreur}") from erreur


def _repere(page: pdfium.PdfPage) -> Repere:
    gauche, bas, droite, haut = page.get_bbox()
    return Repere(float(gauche), float(bas), float(droite), float(haut), int(page.get_rotation()))


def _caracteres(page_texte: pdfium.PdfTextPage, repere: Repere) -> tuple[Caractere, ...]:
    """Les caractères de la page ; une paire de demi-codets UTF-16 devient un seul caractère."""
    poignee = page_texte.raw
    caracteres: list[Caractere] = []
    attente: tuple[int, Zone] | None = None
    boite = pdfium_c.FS_RECTF()
    for rang in range(int(page_texte.count_chars())):
        code = int(pdfium_c.FPDFText_GetUnicode(poignee, rang))
        if code == MARQUE_COUPURE and int(pdfium_c.FPDFText_IsHyphen(poignee, rang)) == 1:
            code = ord("-")
        ajoute = int(pdfium_c.FPDFText_IsGenerated(poignee, rang)) == 1
        if pdfium_c.FPDFText_GetLooseCharBox(poignee, rang, ctypes.byref(boite)):
            zone = repere.zone_affichee(float(boite.left), float(boite.bottom), float(boite.right), float(boite.top))
        else:
            zone = Zone(0.0, 0.0, 0.0, 0.0)
        if 0xD800 <= code < 0xDC00:
            attente = (code, zone)
            continue
        if attente is not None and 0xDC00 <= code < 0xE000:
            haut, zone_haute = attente
            code = 0x10000 + ((haut - 0xD800) << 10) + (code - 0xDC00)
            zone = union([zone_haute, zone])
        attente = None
        if code == 0:
            continue
        caracteres.append(Caractere(chr(code), zone, ajoute))
    return tuple(caracteres)


def lire_pages(donnees: bytes) -> list[PageLue]:
    """Chaque page du PDF, avec ses caractères ; DocumentIllisible si PDFium ne l'ouvre pas."""
    with _VERROU:
        document = _ouvrir(donnees)
        try:
            pages: list[PageLue] = []
            for rang in range(len(document)):
                page = document[rang]
                page_texte = page.get_textpage()
                repere = _repere(page)
                pages.append(PageLue(rang + 1, repere, _caracteres(page_texte, repere)))
                page_texte.close()
                page.close()
            return pages
        finally:
            document.close()


def texte_dans_zone(donnees: bytes, numero: int, zone: Zone) -> str:
    """Le texte que PDFium trouve dans une zone de la page affichée : une relecture indépendante
    de la mise en page d'EKE, qui sert à vérifier une citation."""
    with _VERROU:
        document = _ouvrir(donnees)
        try:
            page = document[numero - 1]
            page_texte = page.get_textpage()
            gauche, bas, droite, haut = _repere(page).rectangle_pdf(zone)
            texte = str(page_texte.get_text_bounded(left=gauche, bottom=bas, right=droite, top=haut))
            page_texte.close()
            page.close()
            return texte
        finally:
            document.close()


def rendre_en_gris(donnees: bytes, numero: int, echelle: int = 1) -> Image:
    """La page telle qu'un lecteur l'affiche, en niveaux de gris ; un pixel vaut 1/echelle point."""
    with _VERROU:
        document = _ouvrir(donnees)
        try:
            page = document[numero - 1]
            image = page.render(scale=echelle, grayscale=True)
            rendu = Image(int(image.width), int(image.height), int(image.stride), bytes(image.buffer))
            image.close()
            page.close()
            return rendu
        finally:
            document.close()


def point_affiche(donnees: bytes, numero: int, x: float, y: float) -> tuple[float, float]:
    """Où PDFium affiche ce point de l'espace PDF, à l'échelle 1 : sa conversion à lui,
    indépendante de `geometrie.Repere`, qui sert à vérifier celle d'EKE."""
    with _VERROU:
        document = _ouvrir(donnees)
        try:
            page = document[numero - 1]
            image = page.render(scale=1)
            px, py = image.get_posconv(page).to_bitmap(x, y)
            image.close()
            page.close()
            return float(px), float(py)
        finally:
            document.close()
