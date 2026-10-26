"""Fabrique de PDF pour les tests d'EKE : des documents fictifs que la PME n'a pas.

Les PDF de Calorelle sont simples (une page, une ligne par valeur, Helvetica à 11 points). EKE
doit valoir pour d'autres documents : ceux-ci ont plusieurs pages, une boîte qui ne commence
pas en 0, une page tournée, du texte placé où l'on veut, deux polices, des tailles diverses et
du crénage (TJ). Tout y est fictif.

Les textes se placent dans le repère de la page telle qu'elle s'affiche, origine en bas à
gauche, y vers le haut : c'est la page que l'on a sous les yeux en écrivant un test. Une matrice
`cm` au début du contenu les porte dans l'espace du PDF, selon la boîte et la rotation de la
page, comme le font les logiciels qui produisent une page à l'italienne : à l'affichage, le
texte se lit à l'horizontale.
"""

from __future__ import annotations

from dataclasses import dataclass, field

POLICES = {"F1": "Helvetica", "F2": "Helvetica-Bold"}


@dataclass(frozen=True)
class Texte:
    """Un texte posé sur sa ligne de base, en (x, y) sur la page affichée, origine en bas à gauche."""

    x: float
    y: float
    texte: str
    taille: float = 11.0
    police: str = "F1"
    creneau: int = 0
    """Si non nul, le texte est écrit lettre par lettre par TJ, avec ce crénage entre lettres."""


@dataclass(frozen=True)
class PageDeTest:
    textes: list[Texte]
    mediabox: tuple[float, float, float, float] = (0, 0, 595, 842)
    cropbox: tuple[float, float, float, float] | None = None
    rotation: int = 0


@dataclass
class _Objets:
    corps: list[bytes] = field(default_factory=list[bytes])

    def ajouter(self, objet: bytes) -> int:
        self.corps.append(objet)
        return len(self.corps)


def _chaine(texte: str) -> bytes:
    octets = texte.encode("cp1252")
    return b"(" + octets.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _boite(valeurs: tuple[float, float, float, float]) -> bytes:
    return ("[" + " ".join(f"{v:g}" for v in valeurs) + "]").encode()


def _matrice(page: PageDeTest) -> str:
    """La matrice qui porte un point de la page affichée dans l'espace du PDF."""
    g, b, d, h = page.cropbox if page.cropbox is not None else page.mediabox
    return {
        0: f"1 0 0 1 {g:g} {b:g}",
        90: f"0 1 -1 0 {d:g} {b:g}",
        180: f"-1 0 0 -1 {d:g} {h:g}",
        270: f"0 -1 1 0 {g:g} {h:g}",
    }[page.rotation]


def _flux(page: PageDeTest) -> bytes:
    textes = page.textes
    lignes: list[bytes] = [f"{_matrice(page)} cm".encode()]
    for t in textes:
        lignes += [b"BT", f"/{t.police} {t.taille:g} Tf".encode(), f"1 0 0 1 {t.x:g} {t.y:g} Tm".encode()]
        if t.creneau:
            morceaux = f" {t.creneau} ".encode().join(_chaine(lettre) for lettre in t.texte)
            lignes.append(b"[" + morceaux + b"] TJ")
        else:
            lignes.append(_chaine(t.texte) + b" Tj")
        lignes.append(b"ET")
    return b"\n".join(lignes)


def fabriquer_pdf(pages: list[PageDeTest]) -> bytes:
    """Un PDF valide, sans date ni identifiant : mêmes pages, mêmes octets."""
    objets = _Objets()
    catalogue = objets.ajouter(b"")
    arbre = objets.ajouter(b"")
    polices = {
        nom: objets.ajouter(f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} /Encoding /WinAnsiEncoding >>".encode())
        for nom, base in POLICES.items()
    }
    ressources = b"<< /Font << " + b" ".join(f"/{n} {o} 0 R".encode() for n, o in polices.items()) + b" >> >>"
    feuilles: list[int] = []
    for page in pages:
        contenu = _flux(page)
        flux = objets.ajouter(b"<< /Length " + str(len(contenu)).encode() + b" >>\nstream\n" + contenu + b"\nendstream")
        entree = b"<< /Type /Page /Parent " + str(arbre).encode() + b" 0 R /MediaBox " + _boite(page.mediabox)
        if page.cropbox is not None:
            entree += b" /CropBox " + _boite(page.cropbox)
        if page.rotation:
            entree += f" /Rotate {page.rotation}".encode()
        entree += b" /Resources " + ressources + b" /Contents " + str(flux).encode() + b" 0 R >>"
        feuilles.append(objets.ajouter(entree))
    objets.corps[catalogue - 1] = b"<< /Type /Catalog /Pages " + str(arbre).encode() + b" 0 R >>"
    enfants = " ".join(f"{f} 0 R" for f in feuilles)
    objets.corps[arbre - 1] = f"<< /Type /Pages /Kids [{enfants}] /Count {len(feuilles)} >>".encode()
    sortie = bytearray(b"%PDF-1.4\n")
    positions: list[int] = []
    for numero, objet in enumerate(objets.corps, start=1):
        positions.append(len(sortie))
        sortie += f"{numero} 0 obj\n".encode() + objet + b"\nendobj\n"
    debut_xref = len(sortie)
    sortie += f"xref\n0 {len(positions) + 1}\n0000000000 65535 f \n".encode()
    sortie += b"".join(f"{p:010d} 00000 n \n".encode() for p in positions)
    sortie += (
        f"trailer\n<< /Size {len(positions) + 1} /Root {catalogue} 0 R >>\nstartxref\n{debut_xref}\n%%EOF\n".encode()
    )
    return bytes(sortie)
