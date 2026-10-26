"""Une lecture de document par EKE, rendue au contrat `lecture_document`.

Assemble les étapes génériques : PDFium lit les caractères (`pdfium`), la mise en page en fait
des lignes visuelles (`mise_en_page`), les règles du français en tirent les paires
étiquette-valeur (`valeurs`). Chaque texte rendu porte sa page et sa zone, et chaque sortie est
validée contre le contrat avant de partir (`contrat`).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from eke import VERSION
from eke.contrat import verifier
from eke.droits import RefusEke
from eke.geometrie import DECIMALES, Zone
from eke.mise_en_page import Morceau, morceaux_de_page, morceaux_du_flux
from eke.pdfium import MOTEUR, PageLue, lire_pages
from eke.valeurs import valeurs_de_ligne

ENTETE_PDF = b"%PDF-"
"""Un PDF commence par cet en-tête, au plus loin dans son premier kilo-octet."""


@dataclass(frozen=True)
class Lecture:
    chemin: str
    """Chemin du document dans les dossiers partagés, avec des « / »."""
    empreinte: str
    pages: list[PageLue]
    lignes: list[list[Morceau]]
    """Les lignes visuelles de tout le document, page après page, chacune de gauche à droite."""
    flux: list[Morceau]
    """Les morceaux de tout le document dans l'ordre du flux de PDFium, page après page."""


def lire(chemin: str, donnees: bytes) -> Lecture:
    """Lit un PDF ; RefusEke si ce n'en est pas un, DocumentIllisible si PDFium ne l'ouvre pas."""
    if ENTETE_PDF not in donnees[:1024]:
        raise RefusEke(f"EKE ne lit que les PDF : {chemin}")
    pages = lire_pages(donnees)
    lignes = [ligne for page in pages for ligne in morceaux_de_page(page)]
    flux = [morceau for page in pages for morceau in morceaux_du_flux(page)]
    return Lecture(chemin, "sha256:" + hashlib.sha256(donnees).hexdigest(), pages, lignes, flux)


def _citation(morceau: Morceau, debut: int, fin: int) -> dict[str, Any]:
    return {"texte": morceau.texte[debut:fin], "page": morceau.page, "zone": morceau.zone_de(debut, fin).en_contrat()}


def _entete(lecture: Lecture) -> dict[str, Any]:
    pages = [
        {"numero": p.numero, "largeur": round(p.largeur, DECIMALES), "hauteur": round(p.hauteur, DECIMALES)}
        for p in lecture.pages
    ]
    return {
        "document": {"chemin": lecture.chemin, "empreinte": lecture.empreinte, "pages": pages},
        "lecteur": {"version": VERSION, "moteur": MOTEUR},
    }


def sortie_lignes(lecture: Lecture) -> dict[str, Any]:
    """Outil lire_document : chaque morceau de ligne, avec sa page et sa zone, dans l'ordre du flux
    de PDFium, qui suit les colonnes d'un texte suivi (journal de l'étape 6, seizième entrée ; le
    tri par ligne visuelle perdait 21,5 points sur fr-bench-pdf2md)."""
    lignes = [_citation(m, 0, len(m.texte)) for m in lecture.flux]
    return verifier({**_entete(lecture), "lignes": lignes})


def sortie_valeurs(lecture: Lecture) -> dict[str, Any]:
    """Outil extraire_valeurs : chaque paire étiquette-valeur, la valeur citée."""
    valeurs = [
        {
            "etiquette": v.etiquette,
            "type": v.type,
            "valeur": v.valeur,
            "unite": v.unite,
            "citation": _citation(v.morceau, v.debut, v.fin),
        }
        for ligne in lecture.lignes
        for v in valeurs_de_ligne(ligne)
    ]
    return verifier({**_entete(lecture), "valeurs": valeurs})


def _ligne_entiere(ligne: list[Morceau]) -> Morceau:
    """Une ligne visuelle en un seul morceau, ses morceaux séparés d'une espace."""
    texte: list[str] = []
    zones: list[Zone | None] = []
    for rang, morceau in enumerate(ligne):
        if rang:
            texte.append(" ")
            zones.append(None)
        texte.append(morceau.texte)
        zones.extend(morceau.zones)
    return Morceau(ligne[0].page, "".join(texte), tuple(zones))


def sortie_citations(lecture: Lecture, recherche: str) -> dict[str, Any]:
    """Outil citer : chaque endroit d'une ligne visuelle où le texte cherché apparaît.

    Tout blanc vaut tout blanc (une espace tapée trouve une espace insécable du document), la
    casse et les accents se comparent à l'identique ; la citation rendue est le texte du
    document. Une citation coupée par un changement de ligne n'est pas trouvée.
    """
    mots = recherche.split()
    if not mots:
        raise RefusEke("texte à chercher vide")
    motif = re.compile(r"\s+".join(re.escape(mot) for mot in mots))
    citations: list[dict[str, Any]] = []
    for ligne in lecture.lignes:
        entiere = _ligne_entiere(ligne)
        debut = 0
        while (trouve := motif.search(entiere.texte, debut)) is not None:
            citations.append(_citation(entiere, trouve.start(), trouve.end()))
            debut = trouve.start() + 1
    return verifier({**_entete(lecture), "recherche": recherche, "citations": citations})
