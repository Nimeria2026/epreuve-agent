"""Le Markdown simple d'EKE : le texte qu'il lit dans un PDF, sans mise en forme ajoutée.

Trois ordres de lecture (journal de l'étape 6, dixième et seizième entrées) :

- `flux`, le score d'EKE : ses morceaux dans l'ordre du flux de PDFium, celui de `lire_document`
  (dix-neuvième entrée) ; une espace entre deux morceaux qui se suivent sur la même ligne
  visuelle, une fin de ligne sinon ;
- `lignes` : les lignes visuelles d'EKE, de haut en bas puis de gauche à droite, que garde
  `extraire_valeurs` ; une ligne de sortie par ligne visuelle, ses morceaux séparés d'une espace ;
- `pdfium` : les caractères dans l'ordre où PDFium les rend, avec les espaces et les fins de
  ligne qu'il déduit de la position du texte, sans la mise en page d'EKE.

Markdown simple : le texte tel quel, ni titre, ni tableau, ni échappement ; les pages d'un PDF
séparées par une ligne vide, comme `Document.text` de vlmparse. Un fichier que PDFium n'ouvre pas
rend un texte vide, que le banc compte en échec.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from eke.banc_public.jeu import Page
from eke.droits import RefusEke
from eke.lecture import lire
from eke.mise_en_page import Morceau, sur_la_meme_ligne
from eke.pdfium import DocumentIllisible, lire_pages

SEPARATEUR_PAGES = "\n\n"


def _ligne(ligne: list[Morceau]) -> str:
    return " ".join(m.texte for m in ligne)


def markdown_lignes(donnees: bytes) -> str:
    """Les lignes visuelles d'EKE, page après page."""
    try:
        lecture = lire("banc.pdf", donnees)
    except (RefusEke, DocumentIllisible):
        return ""
    pages: dict[int, list[str]] = {}
    for ligne in lecture.lignes:
        pages.setdefault(ligne[0].page, []).append(_ligne(ligne))
    return SEPARATEUR_PAGES.join("\n".join(pages.get(p.numero, [])) for p in lecture.pages)


def markdown_flux(donnees: bytes) -> str:
    """Les morceaux d'EKE dans l'ordre du flux de PDFium, page après page : deux morceaux qui se
    suivent sur la même ligne visuelle sont séparés d'une espace, les autres d'une fin de ligne."""
    try:
        lecture = lire("banc.pdf", donnees)
    except (RefusEke, DocumentIllisible):
        return ""
    pages: dict[int, list[str]] = {}
    precedent: Morceau | None = None
    for morceau in lecture.flux:
        textes = pages.setdefault(morceau.page, [])
        if textes and precedent is not None and sur_la_meme_ligne(precedent, morceau):
            textes.append(" " + morceau.texte)
        else:
            textes.append(("\n" if textes else "") + morceau.texte)
        precedent = morceau
    return SEPARATEUR_PAGES.join("".join(pages.get(p.numero, [])) for p in lecture.pages)


def markdown_pdfium(donnees: bytes) -> str:
    """Les caractères de chaque page dans l'ordre de PDFium ; ses fins de ligne en « \\n »."""
    try:
        pages = lire_pages(donnees)
    except DocumentIllisible:
        return ""
    textes = ["".join(c.texte for c in page.caracteres).replace("\r\n", "\n").replace("\r", "\n") for page in pages]
    return SEPARATEUR_PAGES.join(textes)


VARIANTES: dict[str, Callable[[bytes], str]] = {
    "flux": markdown_flux,
    "lignes": markdown_lignes,
    "pdfium": markdown_pdfium,
}
"""Les lectures mesurées : les lignes visuelles d'EKE, ses morceaux dans l'ordre du flux (journal
de l'étape 6, seizième entrée), et l'ordre brut de PDFium."""


def chemin_sortie(dossier: Path, variante: str, page: Page) -> Path:
    return dossier / variante / page.dossier / f"{page.nom}.md"


def convertir_jeu(
    pages: Sequence[Page], variante: str, dossier: Path, dire: Callable[[str], None] = print
) -> dict[str, float]:
    """Écrit la sortie de chaque page en UTF-8 sous `dossier/variante/` ; rend les durées en
    secondes par page (lecture du PDF comprise, écriture non)."""
    lecteur = VARIANTES[variante]
    durees: dict[str, float] = {}
    for rang, page in enumerate(pages, 1):
        debut = time.perf_counter()
        texte = lecteur(page.pdf.read_bytes())
        durees[page.identifiant] = time.perf_counter() - debut
        cible = chemin_sortie(dossier, variante, page)
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(texte.encode("utf-8"))
        if rang % 100 == 0 or rang == len(pages):
            dire(f"{variante} : {rang}/{len(pages)} pages lues")
    return durees


def lire_sortie(dossier: Path, variante: str, page: Page) -> str:
    return chemin_sortie(dossier, variante, page).read_bytes().decode("utf-8")
