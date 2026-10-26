"""Le texte qu'EKE lit dans chaque document d'OmniExtractBench, celui de `lire_document`.

Les morceaux d'EKE dans l'ordre du flux de PDFium, page après page, comme la lecture « flux » de
fr-bench-pdf2md (`eke.banc_public.conversion.markdown_flux`, même règle, réécrite ici pour
compter aussi les pages sans texte, sans changer le code de lecture que ce banc-là empreinte).
Une page sans aucun morceau est une page sans couche de texte : EKE n'a pas d'OCR.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from eke.banc_public.omni.jeu import DOSSIER, Document
from eke.banc_public.telechargement import EcartJeu
from eke.contrat import racine_depot
from eke.lecture import ENTETE_PDF
from eke.mise_en_page import Morceau, morceaux_du_flux, sur_la_meme_ligne
from eke.pdfium import MOTEUR, DocumentIllisible, lire_pages

SEPARATEUR_PAGES = "\n\n"


@dataclass(frozen=True)
class Lu:
    texte: str
    pages: int
    pages_sans_texte: int
    illisible: bool
    """PDFium n'ouvre pas le fichier, ou ce n'est pas un PDF : texte vide, document compté."""


def lire_flux(donnees: bytes) -> Lu:
    """Le texte de `markdown_flux`, avec le compte des pages et des pages sans texte.

    Les morceaux du flux sont ceux de `eke.lecture.lire`, sans ses lignes visuelles : leur
    rangement est quadratique en nombre de morceaux, et une page dense du banc (27 612 morceaux)
    ne se range pas en deux minutes. `lire_document` ne rend que le flux."""
    if ENTETE_PDF not in donnees[:1024]:
        return Lu("", 0, 0, True)
    try:
        pages_lues = lire_pages(donnees)
    except DocumentIllisible:
        return Lu("", 0, 0, True)
    flux = [morceau for page in pages_lues for morceau in morceaux_du_flux(page)]
    pages: dict[int, list[str]] = {}
    precedent: Morceau | None = None
    for morceau in flux:
        textes = pages.setdefault(morceau.page, [])
        if textes and precedent is not None and sur_la_meme_ligne(precedent, morceau):
            textes.append(" " + morceau.texte)
        else:
            textes.append(("\n" if textes else "") + morceau.texte)
        precedent = morceau
    texte = SEPARATEUR_PAGES.join("".join(pages.get(p.numero, [])) for p in pages_lues)
    sans_texte = sum(1 for p in pages_lues if not "".join(pages.get(p.numero, [])).strip())
    return Lu(texte, len(pages_lues), sans_texte, False)


def empreinte_lecture() -> str:
    """sha256 du code qui écrit les textes : tout `eke` hors `banc_public`, plus ce module."""
    racine = racine_depot() / "04_eke" / "src" / "eke"
    condense = hashlib.sha256()
    for chemin in sorted(racine.rglob("*.py")):
        relatif = chemin.relative_to(racine).as_posix()
        if relatif.startswith("banc_public/") and relatif != "banc_public/omni/conversion.py":
            continue
        condense.update(relatif.encode() + b"\0" + chemin.read_bytes() + b"\0")
    return condense.hexdigest()


def chemin_sortie(dossier: Path, document: Document) -> Path:
    nom = PurePosixPath(document.identifiant)
    if len(nom.parts) != 1 or nom.name in (".", ".."):
        raise EcartJeu(f"identifiant de document refusé : {document.identifiant!r}")
    return dossier / "sorties" / "flux" / f"{document.identifiant}.txt"


def convertir(
    documents: Sequence[Document], dossier: Path = DOSSIER, dire: Callable[[str], None] = print
) -> dict[str, dict[str, Any]]:
    """Écrit le texte de chaque document sous `sorties/flux/` ; rend, par document, ses pages, ses
    pages sans texte et la durée de lecture en secondes (écriture non comprise)."""
    notes: dict[str, dict[str, Any]] = {}
    for rang, document in enumerate(documents, 1):
        debut = time.perf_counter()
        lu = lire_flux(document.pdf.read_bytes())
        duree = time.perf_counter() - debut
        cible = chemin_sortie(dossier, document)
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(lu.texte.encode("utf-8"))
        notes[document.identifiant] = {**{k: v for k, v in asdict(lu).items() if k != "texte"}, "duree_s": duree}
        if rang % 50 == 0 or rang == len(documents):
            dire(f"{rang}/{len(documents)} documents lus")
    return notes


def ecrire_note(notes: dict[str, dict[str, Any]], empreinte: str, dossier: Path = DOSSIER) -> None:
    """Note, à côté des textes, le code de lecture (empreinte prise avant la lecture) et le moteur."""
    contenu = {
        "date_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_lecture_sha256": empreinte,
        "moteur": MOTEUR,
        "documents": notes,
    }
    chemin = dossier / "sorties" / "conversion.json"
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def lire_note(dossier: Path = DOSSIER) -> dict[str, Any]:
    chemin = dossier / "sorties" / "conversion.json"
    if not chemin.exists():
        raise FileNotFoundError(f"pas de note de conversion : {chemin} ; lancer d'abord convertir")
    note: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
    return note


def lire_sortie(dossier: Path, document: Document) -> str:
    return chemin_sortie(dossier, document).read_bytes().decode("utf-8")
