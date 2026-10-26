"""Génère l'état initial v1 de Négovelle, troisième PME fictive (ADR 0006) : dossiers partagés,
messagerie, facturation et ventes.

Rejouable à l'octet près : graine fixe, PDF sans date ni identifiant, JSON et YAML dans un ordre
fixe. Écrit dossiers/, messagerie/, facturation/ et ventes/ sous 05_pme/societes/negovelle/v1/ ;
le dossier entreprise/ reste écrit à la main. Cahier des charges : v1/inventaire.yaml ; cadrage :
00_docs/sources/2026-10-17_cadrage_negoce_de_gros.md, sections 4 à 6. Le monde est commun aux
tâches ; les courriels non lus d'une tâche vont dans son complément. Tout est fictif : adresses en
.example, téléphones dans les plages réservées à la fiction, code banque 99999, communes inventées,
mention FICTIF dans chaque PDF.

Les prix des commandes se calculent comme le service de ventes les calcule (05_pme/ventes/src/
chiffrage.ts) : en centimes entiers, la moitié arrondie vers le haut.

Usage, depuis la racine du dépôt :
    uv run python 09_outillage/scripts/generer_negovelle_v1.py              # régénère
    uv run python 09_outillage/scripts/generer_negovelle_v1.py --verifier   # contrôle sans écrire

Codes de sortie : 0 à jour ou régénéré, 1 données périmées.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import itertools
import json
import math
import random
import shutil
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import yaml

RACINE = Path(__file__).resolve().parents[2]
V1 = RACINE / "05_pme" / "societes" / "negovelle" / "v1"
ENTREPRISE = V1 / "entreprise"
GENERES = ("dossiers", "messagerie", "facturation", "ventes")
GRAINE = 20260706
AUJOURD_HUI = date(2026, 7, 6)
PARIS = ZoneInfo("Europe/Paris")
DOMAINE = "negovelle.example"
MENTION = "Document FICTIF : Négovelle et ses partenaires n'existent pas."
CP = "36999"
TRANSPORTEUR = "transports-delorme"
MOIS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
FERIES = {date(2026, 5, 1), date(2026, 5, 8), date(2026, 5, 14), date(2026, 5, 25), date(2026, 7, 14)}

# Communes inventées, absentes de geo.api.gouv.fr (vérifié le 2026-10-17) : clé, nom, secteur, poids
# dans la clientèle. Vaumoreau-sur-Indre, le siège, est rattachée au secteur nord.
COMMUNES = [
    ("vaumoreau", "Vaumoreau-sur-Indre", "nord", 34),
    ("corvalet", "Corvalet", "nord", 16),
    ("brissonne", "Brissonne", "nord", 14),
    ("vendrigny", "Vendrigny", "est", 36),
    ("ardillac", "Ardillac", "est", 28),
    ("laubrissac", "Laubrissac", "sud", 38),
    ("saulvenne", "Saulvenne", "sud", 28),
    ("merolles", "Mérolles-en-Brenne", "ouest", 36),
    ("fontclavier", "Fontclavier", "ouest", 28),
]
NOM_COMMUNE = {cle: nom for cle, nom, _, _ in COMMUNES}
SECTEUR_COMMUNE = {cle: secteur for cle, _, secteur, _ in COMMUNES}
# Secteur : le commercial, puis la personne de l'administration des ventes (cadrage, section 4).
SECTEURS = {
    "nord": ("laurent.gimenez", "manon.rey"),
    "sud": ("aurelie.bonnefoy", "laetitia.garnier"),
    "est": ("fabrice.mercier", "benoit.faure"),
    "ouest": ("samir.ouali", "oceane.collin"),
}

# Prénoms : ceux de la liste de Domivelle. Noms de famille : une liste à part, sans aucun nom de celle
# de Domivelle ni des salariés de Calorelle, de Domivelle et de Négovelle : aucune personne de
# Négovelle ne porte le nom d'une personne des deux autres sociétés.
PRENOMS_F = [
    "Agnès",
    "Alice",
    "Amandine",
    "Anne",
    "Aurélie",
    "Béatrice",
    "Brigitte",
    "Camille",
    "Caroline",
    "Catherine",
    "Chantal",
    "Christine",
    "Claire",
    "Corinne",
    "Delphine",
    "Denise",
    "Émilie",
    "Estelle",
    "Fabienne",
    "Florence",
    "Françoise",
    "Geneviève",
    "Hélène",
    "Inès",
    "Isabelle",
    "Jacqueline",
    "Jeanne",
    "Josiane",
    "Julie",
    "Laure",
    "Léa",
    "Lucie",
    "Madeleine",
    "Manon",
    "Marion",
    "Martine",
    "Monique",
    "Nathalie",
    "Noémie",
    "Odile",
    "Pauline",
    "Sandrine",
    "Simone",
    "Sophie",
    "Suzanne",
    "Sylvie",
    "Valérie",
    "Yvette",
]
PRENOMS_H = [
    "Alain",
    "Albert",
    "André",
    "Antoine",
    "Arnaud",
    "Bernard",
    "Bruno",
    "Christian",
    "Claude",
    "Daniel",
    "Denis",
    "Didier",
    "Dominique",
    "Éric",
    "Étienne",
    "Fabrice",
    "François",
    "Frédéric",
    "Gérard",
    "Gilles",
    "Guy",
    "Henri",
    "Hervé",
    "Hugo",
    "Jacques",
    "Jean",
    "Jérôme",
    "Joël",
    "Julien",
    "Laurent",
    "Louis",
    "Luc",
    "Marcel",
    "Maxime",
    "Michel",
    "Olivier",
    "Pascal",
    "Patrice",
    "Paul",
    "Philippe",
    "Pierre",
    "René",
    "Robert",
    "Roger",
    "Serge",
    "Sylvain",
    "Vincent",
    "Xavier",
]
NOMS = [
    "Achard",
    "Allard",
    "Ancelin",
    "Auger",
    "Baillet",
    "Barbe",
    "Baudouin",
    "Baudry",
    "Becker",
    "Bellanger",
    "Belin",
    "Besson",
    "Billard",
    "Bocquet",
    "Bonneau",
    "Bouchard",
    "Boulay",
    "Boutin",
    "Brochard",
    "Bruneau",
    "Bunel",
    "Cadiou",
    "Cazenave",
    "Chartier",
    "Chatelain",
    "Chevrier",
    "Clerc",
    "Collet",
    "Combes",
    "Cordonnier",
    "Cosson",
    "Crozet",
    "Daniel",
    "Delaunay",
    "Desjardins",
    "Doré",
    "Drouet",
    "Ducret",
    "Dufour",
    "Durieux",
    "Fleurot",
    "Forestier",
    "Foucault",
    "Gabriel",
    "Gallet",
    "Gay",
    "Genet",
    "Grenier",
    "Grondin",
    "Guillon",
    "Guyot",
    "Hamel",
    "Hervé",
    "Hoarau",
    "Humbert",
    "Lacour",
    "Lagarde",
    "Langlais",
    "Legendre",
    "Lelièvre",
    "Lhomme",
    "Martineau",
    "Maurin",
    "Monnier",
    "Morel",
    "Navarre",
    "Noblet",
    "Parmentier",
    "Pelletier",
    "Raynaud",
    "Rocher",
    "Salmon",
    "Simonet",
    "Tixier",
    "Vaillant",
    "Valentin",
    "Vallet",
    "Barre",
    "Blanchet",
    "Bodin",
    "Boisson",
    "Bouvier",
    "Brault",
    "Chauveau",
    "Coulon",
    "Ducros",
    "Dumont",
    "Ernault",
    "Feuillet",
    "Gautier",
    "Gervais",
    "Gonnet",
    "Granger",
    "Hardy",
    "Jolivet",
    "Lecoq",
    "Lemarchand",
    "Mabille",
    "Mahé",
    "Mignot",
    "Moulin",
    "Pasquet",
    "Péron",
    "Pinson",
    "Quéré",
    "Rigaud",
    "Rouxel",
    "Ruel",
    "Sauvage",
    "Thiery",
    "Toussaint",
    "Voisin",
]

RUES = [
    "rue de la Halle",
    "rue des Remparts",
    "avenue de la Gare",
    "rue du Moulin",
    "rue des Écoles",
    "place du Marché",
    "rue Saint-Martin",
    "rue des Vignes",
    "boulevard de l'Indre",
    "rue de la Poste",
    "rue des Lilas",
    "chemin des Prés",
    "rue du Lavoir",
    "rue de l'Église",
    "allée des Acacias",
    "rue des Forges",
    "rue du Château",
    "impasse des Noyers",
    "rue de la Fontaine",
    "avenue Pasteur",
    "rue des Jardins",
    "rue du Four",
    "rue des Peupliers",
    "chemin du Bois",
    "rue des Chênes",
    "rue du Pont",
]
ZONES = [
    "zone d'activités des Grands Prés",
    "zone artisanale du Moulin",
    "zone industrielle des Brandes",
    "parc d'activités de la Gare",
]


# --- briques ---------------------------------------------------------------------------------


def pdf(lignes: list[str]) -> bytes:
    """Un PDF d'une page, en Helvetica, sans date ni identifiant : mêmes lignes, mêmes octets."""
    flux = [b"BT", b"/F1 11 Tf", b"15 TL", b"56 786 Td"]
    for ligne in [*lignes, "", MENTION]:
        texte = ligne.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        flux.append(b"(" + texte + b") Tj T*")
    flux.append(b"ET")
    contenu = b"\n".join(flux)
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> "
        b"/Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(contenu)).encode() + b" >>\nstream\n" + contenu + b"\nendstream",
    ]
    sortie = bytearray(b"%PDF-1.4\n")
    positions: list[int] = []
    for numero, objet in enumerate(objets, start=1):
        positions.append(len(sortie))
        sortie += f"{numero} 0 obj\n".encode() + objet + b"\nendobj\n"
    debut_xref = len(sortie)
    sortie += f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode()
    sortie += b"".join(f"{p:010d} 00000 n \n".encode() for p in positions)
    sortie += f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\nstartxref\n{debut_xref}\n%%EOF\n".encode()
    return bytes(sortie)


def horodatage(jour: date, heure: int = 9, minute: int = 0) -> str:
    """Date et heure de Paris au format RFC 3339, avec le décalage de la saison."""
    return datetime(jour.year, jour.month, jour.day, heure, minute, tzinfo=PARIS).isoformat(timespec="seconds")


def jour_fr(jour: date) -> str:
    premier = "1er" if jour.day == 1 else str(jour.day)
    return f"{premier} {MOIS[jour.month - 1]} {jour.year}"


def euros(centimes: int) -> str:
    entier, reste = divmod(centimes, 100)
    return f"{entier:,}".replace(",", " ") + f",{reste:02d} €"


def decimal(centimes: int) -> str:
    """Un montant pour un tableur français : 57,60 pour 5 760 centimes."""
    return f"{centimes / 100:.2f}".replace(".", ",")


def en_euros(centimes: int) -> float:
    return centimes / 100


def sans_accent(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def slug(texte: str) -> str:
    propre = "".join(c if c.isalnum() else "-" for c in sans_accent(texte).lower())
    return "-".join(partie for partie in propre.split("-") if partie)


def nombre(valeur: float) -> str:
    """3,5 pour 3.5 ; 40 pour 40.0."""
    texte = f"{valeur:g}"
    return texte.replace(".", ",")


def en_yaml(entete: str, donnees: dict[str, Any]) -> str:
    """YAML lisible, clés dans l'ordre donné, précédé d'un commentaire d'en-tête."""
    corps = yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False, default_flow_style=False, width=110)
    return f"# {entete}\n{corps}"


def en_csv(colonnes: list[str], lignes: list[list[str]]) -> str:
    """CSV séparé par des points-virgules, comme l'exporte un tableur français."""
    return "\n".join(";".join(ligne) for ligne in [colonnes, *lignes]) + "\n"


def en_json(donnees: Any) -> str:
    return json.dumps(donnees, ensure_ascii=False, indent=2) + "\n"


def iban(alea: random.Random) -> str:
    chiffres = "".join(str(alea.randrange(10)) for _ in range(18))
    return f"FR76 9999 9{chiffres[0:3]} {chiffres[3:7]} {chiffres[7:11]} {chiffres[11:15]} {chiffres[15:18]}"


def rib(titulaire: str, compte: str) -> bytes:
    return pdf(
        [
            "RELEVÉ D'IDENTITÉ BANCAIRE",
            f"Titulaire : {titulaire}",
            f"IBAN : {compte}",
            "BIC : FICTFRPPXXX",
            "Banque : Banque Fictive du Centre (code banque 99999)",
        ]
    )


def jours_ouvres(debut: date, fin: date) -> list[date]:
    """Les jours du lundi au vendredi, fériés exclus, de debut à fin compris."""
    jours: list[date] = []
    jour = debut
    while jour <= fin:
        if jour.weekday() < 5 and jour not in FERIES:
            jours.append(jour)
        jour += timedelta(days=1)
    return jours


def jour_ouvre_suivant(jour: date, n: int = 1) -> date:
    for _ in range(n):
        jour += timedelta(days=1)
        while jour.weekday() >= 5 or jour in FERIES:
            jour += timedelta(days=1)
    return jour


class Etat:
    """Fichiers à écrire, rangés par chemin relatif à v1/."""

    def __init__(self) -> None:
        self.fichiers: dict[str, bytes] = {}

    def ecrire(self, chemin: str, contenu: bytes | str) -> int:
        if chemin in self.fichiers:
            raise ValueError(f"fichier déjà produit : {chemin}")
        donnees = contenu.encode("utf-8") if isinstance(contenu, str) else contenu
        self.fichiers[chemin] = donnees
        return len(donnees)


class Annuaire:
    """Tire des personnes fictives toutes différentes, et des numéros uniques. Les numéros de 60 00 à
    60 99 sont ceux de Négovelle, dans entreprise/organigramme.yaml."""

    def __init__(self, alea: random.Random) -> None:
        self.alea = alea
        self.pris: set[tuple[str, str]] = set()
        fixes = list(range(6100, 10000))
        mobiles = list(range(6100, 10000))
        alea.shuffle(fixes)
        alea.shuffle(mobiles)
        self.fixes = fixes
        self.mobiles = mobiles

    def personne(self) -> tuple[str, str, str]:
        """(civilité, prénom, nom)"""
        while True:
            femme = self.alea.random() < 0.5
            prenom = self.alea.choice(PRENOMS_F if femme else PRENOMS_H)
            nom = self.alea.choice(NOMS)
            if (prenom, nom) not in self.pris:
                self.pris.add((prenom, nom))
                return ("Mme" if femme else "M.", prenom, nom)

    def fixe(self) -> str:
        n = self.fixes.pop()
        return f"02 61 91 {n // 100:02d} {n % 100:02d}"

    def mobile(self) -> str:
        n = self.mobiles.pop()
        return f"06 39 98 {n // 100:02d} {n % 100:02d}"

    def adresse(self, commune: str) -> str:
        return f"{self.alea.randrange(1, 140)} {self.alea.choice(RUES)}, {CP} {NOM_COMMUNE[commune]} (FICTIF)"

    def adresse_zone(self, commune: str) -> str:
        return f"{self.alea.randrange(1, 40)} {self.alea.choice(ZONES)}, {CP} {NOM_COMMUNE[commune]} (FICTIF)"


# --- le catalogue ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Modele:
    """Un modèle de libellé, ses paramètres et la fourchette de son prix de vente hors taxes."""

    gabarit: str
    parametres: dict[str, list[Any]]
    prix: tuple[float, float]
    conditionnements: tuple[int, ...] = (1,)


@dataclass(frozen=True)
class Famille:
    cle: str
    prefixe: str
    titre: str
    nombre: int
    modeles: tuple[Modele, ...]
    part_prix_net: float = 0.05


def m(
    gabarit: str, prix: tuple[float, float], conditionnements: tuple[int, ...] = (1,), **parametres: list[Any]
) -> Modele:
    return Modele(gabarit, parametres, prix, conditionnements)


TAILLES = ["S", "M", "L", "XL", "XXL", "3XL"]
FAMILLES = (
    Famille(
        "visserie",
        "VIS",
        "Visserie et boulonnerie",
        600,
        (
            m(
                "Vis à bois tête fraisée {d}x{l}, {fin}, boîte de {n}",
                (3.2, 24.0),
                d=[3, 3.5, 4, 4.5, 5, 6],
                l=[16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80],
                fin=["zinguée", "inox A2", "bichromatée"],
                n=[100, 200, 500],
            ),
            m(
                "Vis à tôle tête cylindrique {d}x{l}, {fin}, boîte de {n}",
                (3.5, 16.0),
                d=[3.5, 3.9, 4.2, 4.8],
                l=[9.5, 13, 16, 19, 25],
                fin=["zinguée", "inox A2"],
                n=[100, 250],
            ),
            m(
                "Boulon tête hexagonale M{d}x{l}, {fin}, sachet de {n}",
                (2.4, 18.0),
                d=[6, 8, 10, 12],
                l=[20, 30, 40, 50, 60, 80, 100],
                fin=["zingué", "inox A2"],
                n=[10, 25],
            ),
            m(
                "Écrou hexagonal M{d}, {fin}, sachet de {n}",
                (1.8, 9.0),
                d=[4, 5, 6, 8, 10, 12, 14, 16],
                fin=["zingué", "inox A2"],
                n=[50, 100],
            ),
            m(
                "Rondelle plate M{d}, {fin}, sachet de {n}",
                (1.5, 6.0),
                d=[4, 5, 6, 8, 10, 12, 14, 16],
                fin=["zinguée", "inox A2"],
                n=[50, 100],
            ),
        ),
    ),
    Famille(
        "fixation",
        "FIX",
        "Fixation et ancrage",
        350,
        (
            m(
                "Cheville nylon {d}x{l}, boîte de {n}",
                (3.0, 14.0),
                d=[5, 6, 8, 10, 12],
                l=[25, 30, 40, 50, 60],
                n=[50, 100, 200],
            ),
            m(
                "Cheville à frapper {d}x{l}, boîte de {n}",
                (4.5, 19.0),
                d=[5, 6, 8],
                l=[30, 40, 50, 60, 80],
                n=[50, 100],
            ),
            m(
                "Cheville métallique à expansion M{d}x{l}, boîte de {n}",
                (6.0, 24.0),
                d=[4, 5, 6, 8],
                l=[32, 45, 52, 65],
                n=[25, 50],
            ),
            m(
                "Goujon d'ancrage M{d}x{l}, boîte de {n}",
                (12.0, 48.0),
                d=[8, 10, 12, 16],
                l=[75, 90, 100, 120, 140],
                n=[25, 50],
            ),
            m(
                "Tige filetée M{d}, longueur 1 m, {fin}",
                (1.2, 14.0),
                (1, 5),
                d=[6, 8, 10, 12, 14, 16, 20],
                fin=["zinguée", "inox A2", "brute"],
            ),
            m(
                "Scellement chimique {t}, cartouche de {v} ml",
                (8.5, 32.0),
                t=["polyester", "vinylester", "époxy"],
                v=[150, 300, 410],
            ),
            m(
                "Cheville pour plaque de plâtre {d}x{l}, boîte de {n}",
                (4.0, 16.0),
                d=[4, 5, 6],
                l=[32, 37, 45, 52],
                n=[50, 100],
            ),
            m(
                "Collier de fixation {d} mm, sachet de {n}",
                (2.5, 12.0),
                d=[12, 14, 16, 18, 20, 22, 25, 28, 32, 40],
                n=[10, 25, 50],
            ),
            m(
                "Équerre de fixation {a}x{b}x{c} mm, {fin}",
                (0.6, 4.5),
                (1, 10),
                a=[40, 60, 80, 100, 120],
                b=[40, 60, 80, 100],
                c=[20, 40],
                fin=["zinguée", "galvanisée"],
            ),
            m(
                "Crochet {forme} à visser {l} mm, sachet de {n}",
                (1.5, 7.0),
                forme=["droit", "coudé", "en S"],
                l=[20, 30, 40, 50, 60, 80],
                n=[10, 25],
            ),
        ),
    ),
    Famille(
        "quincaillerie",
        "QUI",
        "Quincaillerie de bâtiment",
        500,
        (
            m(
                "Charnière {t} {l} mm, {fin}",
                (1.8, 16.0),
                (1, 2),
                t=["à lames", "invisible", "piano", "de meuble à visser"],
                l=[25, 30, 40, 50, 60, 70, 80, 100],
                fin=["acier zingué", "laiton", "inox"],
            ),
            m(
                "Paumelle {l} mm, {fin}, sachet de {n}",
                (3.5, 28.0),
                l=[60, 80, 100, 110, 120, 140],
                fin=["acier", "laiton", "inox"],
                n=[2, 4, 10],
            ),
            m(
                "Cylindre européen {a}x{b} mm, {n} clés",
                (14.0, 68.0),
                a=[30, 35, 40, 45, 50],
                b=[30, 35, 40, 45, 50],
                n=[3, 5],
            ),
            m(
                "Serrure en applique {t}, axe {a} mm",
                (22.0, 85.0),
                t=["à cylindre", "à fouillot", "horizontale", "verticale"],
                a=[40, 50, 60, 70],
            ),
            m(
                "Serrure à larder {t}, axe {a} mm",
                (9.0, 42.0),
                t=["bec-de-cane", "à clé L", "à condamnation", "à cylindre"],
                a=[40, 45, 50, 60],
            ),
            m(
                "Poignée de porte {style} sur {support}, {fin}",
                (12.0, 58.0),
                style=["droite", "ronde", "béquille", "carrée", "à plaque"],
                support=["rosace", "plaque"],
                fin=["aluminium", "laiton", "inox", "noir mat"],
            ),
            m(
                "Verrou {t} {l} mm, {fin}",
                (3.0, 26.0),
                t=["à targette", "à baïonnette", "de sûreté", "à ressort"],
                l=[60, 80, 100, 120, 150],
                fin=["acier", "laiton", "inox"],
            ),
            m(
                "Butoir de porte {t}, {fin}",
                (2.5, 14.0),
                t=["au sol", "mural", "magnétique", "à visser"],
                fin=["inox", "caoutchouc noir", "laiton"],
            ),
            m(
                "Ferme-porte {t}, force {f}",
                (28.0, 140.0),
                t=["à bras compas", "à glissière", "encastré"],
                f=["EN 2", "EN 3", "EN 4", "EN 2 à 5"],
            ),
            m(
                "Cadenas {t} {l} mm, {n} clés",
                (6.0, 38.0),
                t=["laiton", "acier", "inox marine", "à combinaison"],
                l=[30, 40, 50, 60, 70],
                n=[2, 3],
            ),
            m(
                "Boîte aux lettres {t}, {c}",
                (24.0, 95.0),
                t=["normalisée", "murale", "à encastrer", "double face"],
                c=["blanc", "gris anthracite", "noir", "vert"],
            ),
            m(
                "Coulisse de tiroir {t} {l} mm, la paire",
                (6.0, 32.0),
                t=["à billes", "à galets", "à sortie totale", "à fermeture amortie"],
                l=[250, 300, 350, 400, 450, 500, 550],
            ),
            m(
                "Patère {t}, {fin}",
                (2.0, 12.0),
                t=["simple", "double", "triple"],
                fin=["inox", "laiton", "noir mat", "blanc"],
            ),
            m(
                "Équerre d'assemblage {l} mm, {fin}, sachet de {n}",
                (1.6, 9.0),
                l=[20, 30, 40, 50, 60],
                fin=["zinguée", "laiton"],
                n=[4, 10, 20],
            ),
            m(
                "Arrêt de volet {t}, {fin}",
                (3.5, 15.0),
                t=["à bascule", "automatique", "tête de bergère", "marseillais"],
                fin=["galvanisé", "noir", "blanc"],
            ),
            m("Gond {t} {d} mm", (2.0, 9.0), (1, 2), t=["à visser", "à scellement", "à platine"], d=[10, 12, 14, 16]),
        ),
    ),
    Famille(
        "outillage",
        "OUT",
        "Outillage à main",
        450,
        (
            m("Tournevis {t} n° {n}", (3.5, 12.0), t=["plat", "Phillips", "Pozidriv", "Torx"], n=[0, 1, 2, 3, 4, 5, 6]),
            m("Clé mixte {n} mm", (4.0, 24.0), n=list(range(6, 33))),
            m("Clé à pipe débouchée {n} mm", (5.0, 18.0), n=list(range(8, 25))),
            m("Clé à molette {l} mm", (12.0, 38.0), l=[150, 200, 250, 300, 375]),
            m("Jeu de clés mâles {t}, {n} pièces", (8.0, 32.0), t=["six pans", "Torx"], n=[7, 9, 10, 13]),
            m(
                "Marteau {t} {g} g",
                (9.0, 36.0),
                t=["de menuisier", "de coffreur", "rivoir", "à panne fendue", "de maçon"],
                g=[200, 300, 400, 500, 600, 800],
            ),
            m(
                "Niveau à bulle {t} {l} cm",
                (7.0, 78.0),
                t=["tubulaire", "de maçon", "magnétique", "compact"],
                l=[30, 40, 60, 80, 100, 120, 150, 180, 200],
            ),
            m("Mètre ruban {l} m, ruban de {w} mm", (4.5, 24.0), l=[3, 5, 8, 10], w=[16, 19, 25, 32]),
            m(
                "Scie {t} {l} mm",
                (8.0, 42.0),
                t=["égoïne", "à dos", "à métaux", "à plâtre", "à bûches", "de carreleur"],
                l=[150, 250, 300, 350, 400, 450, 500, 550, 600],
            ),
            m(
                "Pince {t} {l} mm",
                (7.0, 36.0),
                t=["universelle", "coupante diagonale", "à bec long", "multiprise", "étau", "à dénuder", "à sertir"],
                l=[140, 160, 180, 200, 250, 300],
            ),
            m("Ciseau à bois {l} mm", (6.0, 22.0), l=list(range(6, 42, 2))),
            m("Burin {t} {l} mm", (5.0, 19.0), t=["plat", "pointu", "à goujon"], l=[150, 200, 250, 300, 400]),
            m(
                "Truelle {t} {l} mm",
                (6.0, 24.0),
                t=["ronde", "carrée", "langue-de-chat", "de plâtrier", "à joint"],
                l=[120, 140, 160, 180, 200, 220],
            ),
            m(
                "Spatule {t} {l} mm",
                (3.0, 18.0),
                t=["à enduire", "de peintre", "à reboucher", "japonaise"],
                l=[40, 60, 80, 100, 150, 200, 250, 300],
            ),
            m("Cutter {t} {l} mm", (3.5, 16.0), t=["à lame sécable", "à lame trapèze", "rétractable"], l=[9, 18, 25]),
            m("Lames de cutter {l} mm, étui de {n}", (2.5, 28.0), l=[9, 18, 25], n=[10, 50, 100]),
            m(
                "Équerre de {t} {l} mm",
                (6.0, 32.0),
                t=["menuisier", "maçon", "charpentier", "contrôle"],
                l=[200, 250, 300, 400, 500, 600],
            ),
            m(
                "Serre-joint {t} {o} mm",
                (7.0, 46.0),
                t=["à pompe", "à vis", "à une main", "à pression rapide"],
                o=[150, 200, 300, 400, 500, 600, 800, 1000],
            ),
            m(
                "Lime {t} {l} mm, taille {n}",
                (5.0, 21.0),
                t=["plate", "ronde", "demi-ronde", "triangulaire", "carrée"],
                l=[150, 200, 250, 300],
                n=["bâtarde", "demi-douce"],
            ),
            m(
                "Caisse à outils {t} {l} mm",
                (14.0, 89.0),
                t=["métallique", "plastique", "à tiroirs", "à roulettes"],
                l=[400, 500, 600, 700],
            ),
        ),
    ),
    Famille(
        "electroportatif",
        "ELP",
        "Électroportatif et accessoires",
        250,
        (
            m(
                "Perceuse-visseuse {v} V, {n} batterie(s) {a} Ah, coffret",
                (89.0, 329.0),
                v=[12, 18],
                n=[1, 2],
                a=[2, 4, 5],
            ),
            m(
                "Perforateur SDS-plus {j} J, {alim}",
                (99.0, 389.0),
                j=[1.7, 2.2, 2.7, 3.2],
                alim=["filaire", "sans fil 18 V, nu"],
            ),
            m(
                "Meuleuse d'angle {d} mm, {w} W",
                (45.0, 229.0),
                d=[115, 125, 150, 180, 230],
                w=[750, 900, 1200, 1500, 2000, 2200],
            ),
            m("Scie circulaire {d} mm, {w} W", (89.0, 249.0), d=[165, 190, 210], w=[1200, 1400, 1600]),
            m(
                "Ponceuse {t} {w} W",
                (49.0, 219.0),
                t=["excentrique", "orbitale", "à bande"],
                w=[200, 300, 400, 600, 800],
            ),
            m(
                "Disque à tronçonner {mat} {d} mm, boîte de {n}",
                (9.0, 69.0),
                mat=["métal", "inox", "pierre", "béton"],
                d=[115, 125, 230],
                n=[10, 25],
            ),
            m(
                "Disque diamant {mat} {d} mm",
                (12.0, 129.0),
                mat=["béton", "carrelage", "polyvalent", "granit"],
                d=[115, 125, 180, 230, 300, 350],
            ),
            m(
                "Foret béton SDS-plus {d}x{l} mm",
                (2.8, 28.0),
                d=[5, 6, 8, 10, 12, 14, 16, 18, 20],
                l=[110, 160, 210, 260, 310, 450],
            ),
            m(
                "Foret métal HSS {d} mm, étui de {n}",
                (2.2, 34.0),
                d=[1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7, 8, 9, 10, 11, 12, 13],
                n=[2, 5, 10],
            ),
            m("Foret à bois trois pointes {d} mm", (2.0, 12.0), d=list(range(3, 21))),
            m(
                "Embout de vissage {t}, étui de {n}",
                (2.0, 22.0),
                t=["PH1", "PH2", "PH3", "PZ1", "PZ2", "PZ3", "T10", "T15", "T20", "T25", "T30", "T40"],
                n=[3, 10, 25],
            ),
            m("Batterie {v} V {a} Ah", (39.0, 149.0), v=[12, 18], a=[2, 3, 4, 5, 6, 8]),
        ),
    ),
    Famille(
        "plomberie",
        "PLB",
        "Plomberie et sanitaire",
        500,
        (
            m(
                "Raccord laiton {t} {dim}",
                (1.6, 9.5),
                (1, 5),
                t=["droit mâle-femelle", "coude mâle-femelle", "té égal", "manchon", "réduction mâle-femelle"],
                dim=["12x17", "15x21", "20x27", "26x34", "33x42"],
            ),
            m(
                "Raccord à sertir {t} {d} mm",
                (2.5, 14.0),
                (1, 5),
                t=["droit", "coude 90°", "té", "réduction", "applique"],
                d=[12, 14, 16, 18, 20, 22, 26, 32],
            ),
            m(
                "Tube cuivre écroui {d} mm, barre de {l} m",
                (9.0, 69.0),
                d=[8, 10, 12, 14, 16, 18, 22, 28, 32],
                l=[2, 4],
            ),
            m("Tube multicouche {d} mm, couronne de {l} m", (28.0, 189.0), d=[16, 20, 26, 32], l=[25, 50, 100]),
            m(
                "Tube PER {d} mm, {g}, couronne de {l} m",
                (14.0, 98.0),
                d=[12, 16, 20],
                g=["nu", "gainé bleu", "gainé rouge"],
                l=[25, 50, 100],
            ),
            m(
                "Tube PVC évacuation {d} mm, barre de {l} m",
                (3.0, 32.0),
                d=[32, 40, 50, 63, 80, 100, 110, 125],
                l=[1, 2, 4],
            ),
            m("Coude PVC {a}° {d} mm", (0.8, 6.5), (1, 5), a=[15, 30, 45, 67, 87], d=[32, 40, 50, 63, 80, 100, 110]),
            m(
                "Coude cuivre à souder {a}° {d} mm, sachet de {n}",
                (2.0, 16.0),
                a=[45, 90],
                d=[10, 12, 14, 16, 18, 22, 28],
                n=[5, 10],
            ),
            m(
                "Robinet d'arrêt {t} {dim}",
                (6.0, 28.0),
                t=["à boisseau sphérique", "quart de tour", "à clapet", "de machine à laver"],
                dim=["12x17", "15x21", "20x27", "26x34"],
            ),
            m(
                "Flexible inox {t} {l} cm",
                (3.5, 19.0),
                t=["femelle-femelle 15x21", "femelle-femelle 12x17", "mâle-femelle 15x21", "de douche"],
                l=[30, 40, 50, 60, 80, 100, 150, 200],
            ),
            m(
                "Siphon {t} {d} mm",
                (4.0, 22.0),
                t=["d'évier", "de lavabo", "de baignoire", "de douche", "à culot"],
                d=[32, 40],
            ),
            m(
                "Joint {t} {dim}, sachet de {n}",
                (1.2, 8.0),
                t=["fibre", "caoutchouc", "torique", "plat EPDM"],
                dim=["12x17", "15x21", "20x27", "26x34", "33x42"],
                n=[10, 50],
            ),
            m(
                "Collier de fixation tube {d} mm, sachet de {n}",
                (2.0, 11.0),
                d=[12, 14, 16, 18, 20, 22, 25, 28, 32, 40, 50],
                n=[10, 25],
            ),
            m(
                "Mitigeur {t}, {fin}",
                (39.0, 189.0),
                t=[
                    "de lavabo",
                    "d'évier",
                    "de douche",
                    "de bain-douche",
                    "thermostatique de douche",
                    "d'évier à douchette",
                ],
                fin=["chromé", "noir mat", "inox brossé"],
            ),
            m(
                "Vanne {t} {dim}",
                (6.0, 34.0),
                t=[
                    "d'arrêt à sertir",
                    "à boisseau sphérique femelle-femelle",
                    "de radiateur droite",
                    "de radiateur équerre",
                    "thermostatique",
                ],
                dim=["12x17", "15x21", "20x27"],
            ),
            m(
                "Pâte à joint {c}, pot de {g} g",
                (4.0, 18.0),
                c=["pour filetage", "d'étanchéité gaz", "d'étanchéité eau"],
                g=[100, 200, 500],
            ),
            m("Groupe de sécurité {t} {dim}", (14.0, 39.0), t=["droit", "coudé", "inox"], dim=["20x27", "15x21"]),
            m(
                "Chauffe-eau électrique {v} l, {t}",
                (189.0, 699.0),
                v=[50, 75, 100, 150, 200, 300],
                t=["vertical mural", "vertical sur socle", "horizontal"],
            ),
            m(
                "Clapet anti-retour {t} {dim}",
                (5.0, 24.0),
                t=["à ressort", "à battant", "laiton"],
                dim=["15x21", "20x27", "26x34", "33x42"],
            ),
            m("Manchon PVC {d} mm", (0.6, 4.5), (1, 5), d=[32, 40, 50, 63, 80, 100, 110, 125]),
            m("Té PVC {a}° {d} mm", (1.0, 7.0), (1, 5), a=[45, 87], d=[32, 40, 50, 100]),
            m("Bouchon de visite PVC {d} mm", (1.0, 6.0), d=[32, 40, 50, 63, 80, 100, 110, 125]),
            m("Colle PVC, pot de {v} ml", (4.0, 22.0), v=[125, 250, 500, 1000]),
            m(
                "Réduction PVC {dim} mm",
                (0.8, 5.0),
                dim=["40x32", "50x32", "50x40", "63x50", "80x63", "100x80", "110x100", "125x110", "100x50", "110x40"],
            ),
            m(
                "Bonde {t} {d} mm",
                (5.0, 29.0),
                t=["à grille", "à clapet", "de douche", "de baignoire", "à écoulement libre"],
                d=[32, 40, 60, 90],
            ),
            m(
                "Robinet de puisage {t} {dim}",
                (7.0, 26.0),
                t=["à nez fileté", "à tête potence", "à clé", "antigel"],
                dim=["15x21", "20x27"],
            ),
            m(
                "Mécanisme de chasse {t}",
                (14.0, 39.0),
                t=["double débit 3/6 l", "simple débit", "à tirette", "à bouton-poussoir", "universel"],
            ),
            m(
                "Robinet flotteur {t}",
                (9.0, 24.0),
                t=["à alimentation latérale", "à alimentation par le bas", "silencieux", "universel"],
            ),
            m(
                "Étanchéité {t}",
                (1.5, 9.0),
                t=[
                    "filasse de chanvre, écheveau de 40 g",
                    "filasse de chanvre, écheveau de 100 g",
                    "filasse de chanvre, écheveau de 250 g",
                    "ruban PTFE de 12 m",
                    "ruban PTFE de 15 m",
                    "ruban PTFE de 25 m",
                ],
            ),
            m(
                "Abattant WC {t}",
                (19.0, 69.0),
                t=["thermodur blanc", "à frein de chute", "en bois naturel", "pour enfant", "double"],
            ),
            m(
                "Purgeur {t}",
                (2.5, 19.0),
                t=[
                    "automatique de radiateur",
                    "manuel de radiateur",
                    "d'air à flotteur 3/8",
                    "d'air à flotteur 1/2",
                    "thermostatique",
                ],
            ),
            m("Mamelon laiton {dim}", (1.2, 6.0), (1, 5), dim=["12x17", "15x21", "20x27", "26x34", "33x42"]),
        ),
    ),
    Famille(
        "electricite",
        "ELE",
        "Électricité",
        500,
        (
            m(
                "Câble {t} {s} mm², couronne de {l} m",
                (18.0, 389.0),
                t=["R2V 3G", "R2V 5G", "H07V-U", "H07V-K", "U1000 R2V 2x"],
                s=[1.5, 2.5, 6, 10],
                l=[25, 50, 100],
            ),
            m(
                "Disjoncteur {p} {a} A, courbe {c}",
                (6.0, 59.0),
                p=["phase-neutre", "bipolaire", "tétrapolaire"],
                a=[2, 10, 16, 20, 25, 32, 40],
                c=["C", "D"],
            ),
            m(
                "Interrupteur différentiel {a} A 30 mA, type {t}",
                (32.0, 129.0),
                a=[25, 40, 63],
                t=["AC", "A", "F", "Hpi"],
            ),
            m("Tableau électrique {r} rangée(s), {n} modules", (24.0, 119.0), r=[1, 2, 3, 4], n=[13, 18]),
            m(
                "Peigne d'alimentation {t}, {n} modules",
                (4.0, 29.0),
                t=["phase-neutre", "triphasé"],
                n=[13, 18, 26, 52],
            ),
            m("Gaine ICTA {d} mm, couronne de {l} m", (9.0, 79.0), d=[16, 20, 25, 32, 40], l=[25, 50, 100]),
            m("Conduit IRL {d} mm, barre de {l} m", (1.2, 9.0), (1, 10), d=[16, 20, 25, 32, 40, 50], l=[2, 3]),
            m(
                "Boîte d'encastrement {t} {d} mm",
                (0.4, 4.0),
                (1, 10),
                t=["simple", "double", "triple", "pour cloison sèche", "étanche"],
                d=[40, 50, 67, 85],
            ),
            m(
                "Boîte de dérivation {t} {d} mm",
                (1.5, 12.0),
                t=["étanche IP55", "à encastrer", "à couvercle vissé", "à embouts"],
                d=[80, 100, 150, 220],
            ),
            m(
                "Prise de courant {t}, {c}",
                (3.5, 34.0),
                t=["2P+T", "2P+T à éclips", "2P+T en saillie étanche", "double 2P+T", "USB A et C"],
                c=["blanc", "anthracite", "aluminium", "noir"],
            ),
            m(
                "Interrupteur {t}, {c}",
                (3.0, 49.0),
                t=["va-et-vient", "double va-et-vient", "poussoir", "variateur", "de volet roulant", "temporisé"],
                c=["blanc", "anthracite", "aluminium", "noir"],
            ),
            m("Domino {s} mm², barrette de {n}", (0.8, 4.5), (1, 10), s=[1.5, 2.5, 4, 6, 10, 16], n=[10, 12]),
            m(
                "Borne de connexion {t} {n} conducteurs, boîte de {q}",
                (6.0, 38.0),
                t=["automatique", "à levier"],
                n=[2, 3, 5],
                q=[50, 100],
            ),
            m(
                "Ampoule LED {culot} {w} W, {k} K",
                (2.0, 9.0),
                (1, 10),
                culot=["E27", "E14", "GU10", "B22", "G9"],
                w=[4, 6, 9, 12],
                k=[2700, 4000],
            ),
            m(
                "Projecteur LED {w} W, {t}",
                (12.0, 129.0),
                w=[10, 20, 30, 50, 100, 150, 200],
                t=["à détecteur", "sans détecteur", "portable sur pied"],
            ),
            m("Hublot {t} LED {w} W", (9.0, 49.0), t=["rond", "ovale", "à détecteur", "étanche"], w=[8, 12, 15, 18]),
            m("Réglette LED {l} mm, {w} W", (9.0, 32.0), l=[600, 1200, 1500], w=[18, 24, 36]),
            m("Tube LED T8 {l} mm, {w} W", (3.0, 12.0), (1, 10), l=[600, 900, 1200, 1500], w=[9, 14, 18, 22]),
            m("Fil de terre vert-jaune {s} mm², couronne de {l} m", (12.0, 149.0), s=[6, 10, 16, 25], l=[25, 50, 100]),
            m("Câble téléphonique {p} paire(s), couronne de {l} m", (9.0, 89.0), p=[1, 2, 4, 7], l=[25, 50, 100]),
            m("Câble RJ45 cat. {c}, couronne de {l} m", (49.0, 289.0), c=["5e", "6", "6a"], l=[100, 305]),
            m(
                "Collier de serrage {l}x{w} mm, sachet de 100",
                (1.5, 9.0),
                l=[100, 140, 200, 300, 370],
                w=[2.5, 3.6, 4.8, 7.6],
            ),
            m(
                "Ruban isolant {c}, rouleau de {l} m",
                (0.6, 3.5),
                (1, 10),
                c=["noir", "bleu", "rouge", "vert-jaune", "blanc", "marron", "gris"],
                l=[10, 20, 33],
            ),
            m(
                "Rallonge électrique {t} {l} m",
                (8.0, 89.0),
                t=["2P+T", "enrouleur 4 prises", "multiprise 6 prises", "de chantier IP44"],
                l=[3, 5, 10, 15, 25, 50],
            ),
            m(
                "Appareil modulaire {t}",
                (12.0, 69.0),
                t=[
                    "contacteur jour-nuit 20 A",
                    "contacteur jour-nuit 25 A",
                    "contacteur jour-nuit 40 A",
                    "télérupteur 16 A",
                    "télérupteur 20 A",
                    "minuterie d'escalier",
                    "parafoudre type 2",
                    "délesteur",
                    "programmateur journalier",
                    "programmateur hebdomadaire",
                ],
            ),
            m(
                "Câble souple {t} {s} mm², couronne de {l} m",
                (24.0, 189.0),
                t=["H05VV-F 3G", "H07RN-F 3G"],
                s=[1.5, 2.5],
                l=[25, 50],
            ),
            m(
                "Prise de courant étanche {t}, {c}",
                (6.0, 24.0),
                t=["en saillie IP44", "à encastrer IP44", "double en saillie IP55"],
                c=["gris", "blanc"],
            ),
            m(
                "Spot encastrable LED {w} W, {k} K, {c}",
                (6.0, 24.0),
                w=[5, 7],
                k=[3000, 4000],
                c=["blanc", "noir", "aluminium brossé"],
            ),
            m(
                "Goulotte {d}x{h} mm, barre de 2 m",
                (2.0, 14.0),
                (1, 5),
                d=[12, 16, 20, 32, 40, 60],
                h=[12, 16, 20, 25, 40],
            ),
            m(
                "Détecteur {t}",
                (9.0, 59.0),
                t=[
                    "de fumée autonome",
                    "de fumée à pile 10 ans",
                    "de fumée connecté",
                    "de chaleur",
                    "de mouvement infrarouge",
                    "de présence plafonnier",
                ],
            ),
        ),
    ),
    Famille(
        "protection",
        "PRO",
        "Équipements de protection individuelle",
        300,
        (
            m(
                "Gants nitrile {t}, taille {s}, boîte de 100",
                (6.0, 18.0),
                t=["jetables non poudrés", "renforcés", "à longue manchette"],
                s=[7, 8, 9, 10, 11],
            ),
            m(
                "Gants de manutention {t}, taille {s}",
                (1.8, 12.0),
                (1, 12),
                t=[
                    "cuir fleur",
                    "enduits nitrile",
                    "enduits polyuréthane",
                    "anticoupure niveau D",
                    "anticoupure niveau F",
                    "hiver",
                ],
                s=[7, 8, 9, 10, 11],
            ),
            m(
                "Chaussures de sécurité {t} S3, pointure {p}",
                (39.0, 119.0),
                t=["basses", "montantes", "légères composite"],
                p=list(range(38, 48)),
            ),
            m(
                "Bottes de sécurité {t}, pointure {p}",
                (29.0, 79.0),
                t=["caoutchouc S5", "PVC S5", "fourrées S5"],
                p=list(range(38, 48)),
            ),
            m(
                "Lunettes de protection {t}",
                (2.5, 14.0),
                (1, 10),
                t=["incolores", "teintées", "panoramiques", "surlunettes", "anti-buée", "de meulage"],
            ),
            m(
                "Masque {t}, boîte de {n}",
                (6.0, 59.0),
                t=["FFP1", "FFP2", "FFP3", "FFP2 à valve", "FFP3 à valve"],
                n=[10, 20, 50],
            ),
            m(
                "Casque de chantier {t}, {c}",
                (6.0, 28.0),
                t=["ventilé", "non ventilé", "à jugulaire"],
                c=["blanc", "jaune", "bleu", "rouge", "vert", "orange"],
            ),
            m(
                "Bouchons d'oreille {t}, boîte de {n}",
                (9.0, 69.0),
                t=["en mousse", "réutilisables", "à cordelette", "détectables"],
                n=[50, 200, 500],
            ),
            m(
                "Casque antibruit {t} SNR {db} dB",
                (12.0, 49.0),
                t=["serre-tête", "adaptable sur casque", "pliable"],
                db=[27, 30, 33, 37],
            ),
            m("Gilet haute visibilité {c}, taille {s}", (3.0, 9.0), (1, 5), c=["jaune", "orange"], s=TAILLES[1:]),
            m(
                "Pantalon de travail {t}, taille {s}",
                (19.0, 59.0),
                t=["multipoches gris", "multipoches noir", "coupe droite bleu marine", "haute visibilité orange"],
                s=list(range(36, 54, 2)),
            ),
            m(
                "Veste de travail {t}, taille {s}",
                (24.0, 89.0),
                t=["softshell noire", "polaire grise", "de pluie jaune", "d'hiver bleu marine"],
                s=TAILLES,
            ),
            m(
                "Combinaison jetable {t}, taille {s}",
                (4.0, 14.0),
                (1, 5),
                t=["type 5/6 blanche", "type 4/5/6"],
                s=TAILLES[1:],
            ),
            m("Gants de soudeur {t}, taille {s}", (6.0, 19.0), t=["cuir croûte", "cuir fleur TIG"], s=[9, 10, 11]),
            m("Manchettes anticoupure {l} cm", (6.0, 18.0), l=[25, 35, 45, 55]),
            m("Chaussettes de travail {t}, pointures {p}", (4.0, 9.0), t=["d'été", "d'hiver"], p=["39-42", "43-46"]),
            m(
                "Tee-shirt de travail {c}, taille {s}",
                (6.0, 14.0),
                (1, 5),
                c=["gris", "noir", "bleu marine"],
                s=TAILLES,
            ),
            m("Polo haute visibilité {c}, taille {s}", (9.0, 19.0), c=["jaune", "orange"], s=TAILLES[1:]),
            m("Bonnet de travail {c}", (4.0, 9.0), c=["noir", "gris", "orange fluo"]),
            m("Cartouche filtrante {t}, la paire", (12.0, 39.0), t=["A2", "ABEK1", "P3", "A2P3", "ABEK1P3"]),
            m(
                "Protection {t}",
                (6.0, 89.0),
                t=[
                    "genouillères en mousse",
                    "genouillères à gel",
                    "genouillères rigides",
                    "harnais antichute 1 point",
                    "harnais antichute 2 points",
                    "longe antichute à absorbeur 2 m",
                    "longe double à absorbeur 1,5 m",
                    "écran facial relevable",
                    "écran facial de meulage",
                    "trousse de secours 4 personnes",
                    "trousse de secours 10 personnes",
                    "tablier de soudeur en cuir",
                ],
            ),
        ),
        part_prix_net=0.25,
    ),
    Famille(
        "consommables",
        "CON",
        "Consommables d'atelier et de chantier",
        350,
        (
            m(
                "Disque abrasif {t} {d} mm, grain {g}, boîte de {n}",
                (6.0, 48.0),
                t=["auto-agrippant", "à lamelles", "fibre"],
                d=[115, 125, 150],
                g=[40, 60, 80, 120, 180, 240],
                n=[10, 25, 50],
            ),
            m(
                "Papier abrasif {t}, grain {g}, rouleau de {l} m",
                (5.0, 59.0),
                t=["corindon", "carbure de silicium", "toile"],
                g=[40, 60, 80, 100, 120, 180, 240],
                l=[5, 25, 50],
            ),
            m(
                "Mastic {t}, cartouche de 310 ml, {c}",
                (3.5, 14.0),
                (1, 12),
                t=["silicone sanitaire", "silicone neutre", "acrylique", "polyuréthane", "hybride MS polymère"],
                c=["blanc", "transparent", "gris", "noir", "ton bois"],
            ),
            m(
                "Mousse polyuréthane {t}, {v} ml",
                (6.0, 19.0),
                (1, 12),
                t=["expansive manuelle", "expansive pistolable", "coupe-feu", "basse expansion"],
                v=[500, 750],
            ),
            m(
                "Colle {t}, {v}",
                (4.0, 49.0),
                t=["néoprène", "vinylique", "polyuréthane", "de montage", "pour carrelage", "à bois rapide"],
                v=["pot de 1 l", "bidon de 5 l", "cartouche de 310 ml", "tube de 125 ml"],
            ),
            m(
                "Ruban adhésif {t} {w} mm, rouleau de {l} m",
                (1.5, 14.0),
                (1, 6),
                t=["toilé gris", "de masquage", "double face", "aluminium", "PVC"],
                w=[19, 25, 38, 48, 50],
                l=[10, 25, 33, 50],
            ),
            m(
                "Bombe {t}, {c}, aérosol de {v} ml",
                (4.0, 14.0),
                (1, 6),
                t=["de traçage", "de peinture antirouille", "de peinture haute température", "galvanisante"],
                c=["noir", "gris", "blanc", "rouge fluo", "orange fluo", "jaune fluo"],
                v=[400, 500],
            ),
            m(
                "Dégrippant {t}, aérosol de {v} ml",
                (4.0, 12.0),
                (1, 6),
                t=["multifonction", "au PTFE", "à choc thermique", "à la graisse blanche"],
                v=[400, 500],
            ),
            m(
                "Marqueur de chantier {c}, boîte de {n}",
                (6.0, 22.0),
                c=["noir", "rouge", "bleu", "blanc", "jaune"],
                n=[10, 12],
            ),
        ),
        part_prix_net=0.10,
    ),
    Famille(
        "entretien",
        "ENT",
        "Hygiène et entretien",
        200,
        (
            m(
                "Nettoyant {t}, bidon de {v} l",
                (4.0, 49.0),
                t=[
                    "dégraissant industriel",
                    "multisurface",
                    "pour sols",
                    "pour vitres",
                    "détartrant sanitaire",
                    "désinfectant",
                    "pour mains d'atelier",
                ],
                v=[1, 5, 10],
            ),
            m(
                "Savon d'atelier {t}, {v}",
                (5.0, 29.0),
                t=["aux microbilles", "en crème", "en gel"],
                v=["pot de 3 l", "cartouche de 4 l", "flacon de 500 ml"],
            ),
            m(
                "Sacs poubelle {v} l, {t}, rouleau de {n}",
                (2.0, 14.0),
                (1, 10),
                v=[30, 50, 100, 130, 160],
                t=["noirs", "transparents", "renforcés"],
                n=[10, 20, 25],
            ),
            m(
                "Essuie-mains {t}, carton de {n}",
                (14.0, 79.0),
                t=["à dévidage central", "en papier plié", "en rouleau industriel"],
                n=[2, 6, 12],
            ),
            m(
                "Papier toilette {t}, colis de {n}",
                (9.0, 69.0),
                t=["maxi jumbo", "en rouleau standard", "à dévidage central"],
                n=[6, 12, 24, 96],
            ),
            m(
                "Balai {t} {l} cm",
                (6.0, 29.0),
                t=["brosse coco", "brosse PVC", "de cantonnier", "d'atelier", "à franges"],
                l=[30, 40, 50, 60, 80],
            ),
            m(
                "Absorbant {t}, sac de {g} kg",
                (12.0, 49.0),
                t=["industriel minéral", "végétal", "pour hydrocarbures"],
                g=[10, 20],
            ),
            m("Raclette {t} {l} cm", (4.0, 24.0), t=["de sol", "à vitres", "en mousse"], l=[35, 45, 55, 75]),
            m("Seau {t} {v} l", (3.0, 29.0), t=["rond", "rectangulaire", "à essorage", "de maçon"], v=[10, 12, 15, 20]),
            m(
                "Lavette microfibre {c}, paquet de {n}",
                (4.0, 22.0),
                c=["bleue", "rouge", "verte", "jaune"],
                n=[5, 10, 20],
            ),
            m(
                "Chiffon d'essuyage {t}, carton de {g} kg",
                (14.0, 39.0),
                t=["coton blanc", "coton de couleur", "non tissé"],
                g=[5, 10],
            ),
            m("Bac de rétention {v} l", (29.0, 249.0), v=[20, 60, 120, 220, 450]),
            m("Sacs à gravats {v} l, paquet de {n}", (4.0, 19.0), v=[50, 80, 120], n=[10, 25]),
            m(
                "Désinfectant {t}, {v}",
                (4.0, 29.0),
                t=["pour surfaces", "pour les mains"],
                v=["flacon de 500 ml", "bidon de 5 l"],
            ),
            m(
                "Distributeur {t}, {c}",
                (19.0, 69.0),
                t=["d'essuie-mains", "de papier toilette", "de savon", "de sacs poubelle"],
                c=["blanc", "inox"],
            ),
            m(
                "Brosse {t}",
                (2.5, 12.0),
                t=["à récurer", "de lavage à manche", "métallique", "à main en chiendent", "de cantonnier sans manche"],
            ),
            m("Poubelle {t} {v} l", (12.0, 69.0), t=["à pédale", "à couvercle basculant", "de tri"], v=[30, 50, 80]),
        ),
        part_prix_net=0.20,
    ),
)
FAMILLE = {f.cle: f for f in FAMILLES}


@dataclass
class Article:
    reference: str
    libelle: str
    famille: str
    unite: str
    conditionnement: int
    prix_vente: int  # centimes HT
    prix_net: bool
    bareme: list[tuple[int, float]]
    fournisseur: str
    prix_achat: int  # centimes HT, dernière facture
    avantages: float
    transport: int  # centimes HT par unité
    stock: int
    point_de_commande: int
    quantite_reassort: int
    reassort: tuple[int, date] | None
    statut: str
    substituts: list[str] = field(default_factory=lambda: [])


CONTENANTS = [
    (", boîte de", "boîte"),
    (", sachet de", "sachet"),
    (", étui de", "étui"),
    ("couronne de", "couronne"),
    ("barre de", "barre"),
    ("rouleau de", "rouleau"),
    ("carton de", "carton"),
    ("paquet de", "paquet"),
    ("colis de", "colis"),
    ("la paire", "paire"),
    ("pot de", "pot"),
    ("bidon de", "bidon"),
    ("flacon de", "flacon"),
    ("cartouche de", "cartouche"),
    ("aérosol de", "aérosol"),
    ("sac de", "sac"),
    ("écheveau de", "écheveau"),
    ("tube de", "tube"),
]


def unite(libelle: str, conditionnement: int) -> str:
    """L'unité de vente que dit le libellé, et le multiple qu'une commande en demande."""
    nom = next((u for motif, u in CONTENANTS if motif in libelle), "pièce")
    accord = "vendue" if nom in {"pièce", "boîte", "couronne", "barre", "paire", "cartouche"} else "vendu"
    return nom if conditionnement == 1 else f"{nom}, {accord} par {conditionnement}"


def arrondi_prix(valeur: float) -> int:
    """Un prix de vente en centimes, arrondi aux 5 centimes, comme un tarif."""
    return max(5, round(valeur * 20) * 5)


def libelles(famille: Famille, alea: random.Random) -> list[tuple[str, Modele]]:
    """Les libellés possibles d'une famille, tous différents, dans un ordre tiré."""
    vus: set[str] = set()
    sortie: list[tuple[str, Modele]] = []
    for modele in famille.modeles:
        cles = list(modele.parametres)
        for valeurs in itertools.product(*(modele.parametres[c] for c in cles)):
            texte = modele.gabarit.format(
                **{c: nombre(v) if isinstance(v, float | int) else v for c, v in zip(cles, valeurs, strict=True)}
            )
            if texte not in vus:
                vus.add(texte)
                sortie.append((texte, modele))
    if len(sortie) < famille.nombre:
        raise ValueError(f"famille {famille.cle} : {len(sortie)} libellés pour {famille.nombre} articles")
    alea.shuffle(sortie)
    return sortie[: famille.nombre]


def catalogue(fournisseurs: dict[str, list[str]], alea: random.Random) -> list[Article]:
    articles: list[Article] = []
    for famille in FAMILLES:
        choisis = sorted(libelles(famille, alea), key=lambda paire: paire[0])
        for rang, (texte, modele) in enumerate(choisis, start=1):
            reference = f"{famille.prefixe}-{rang * 7 + 10000 + (rang % 7):05d}"
            prix = arrondi_prix(alea.uniform(*modele.prix))
            achat = round(prix * alea.uniform(0.55, 0.72))
            avantages = alea.choice([0.0, 0.0, 0.0, 1.0, 1.5, 2.0, 3.0])
            transport = max(1, round(achat * alea.uniform(0.01, 0.04)))
            prix_net = alea.random() < famille.part_prix_net
            bareme: list[tuple[int, float]] = []
            if not prix_net and alea.random() < 0.4:
                bareme = alea.choice(
                    [[(10, 3.0), (50, 6.0)], [(5, 2.0), (20, 5.0)], [(25, 4.0)], [(12, 3.0), (48, 7.0)]]
                )
            conditionnement = alea.choice(modele.conditionnements)
            point = alea.choice([5, 10, 10, 20, 20, 30, 40, 60, 80])
            reassort_qte = point * alea.choice([2, 3, 4, 5])
            tirage = alea.random()
            statut = "fin_de_serie" if tirage < 0.03 else "dereference" if tirage < 0.05 else "courant"
            rupture = statut == "courant" and alea.random() < 0.04
            stock = 0 if rupture else alea.randrange(point // 2, point * 8 + 20)
            reassort = None
            if statut == "courant" and stock < point and alea.random() < 0.8:
                arrivee = jour_ouvre_suivant(AUJOURD_HUI, alea.randrange(2, 14))
                reassort = (reassort_qte, arrivee)
            stock = (stock // conditionnement) * conditionnement
            articles.append(
                Article(
                    reference=reference,
                    libelle=texte,
                    famille=famille.cle,
                    unite=unite(texte, conditionnement),
                    conditionnement=conditionnement,
                    prix_vente=prix,
                    prix_net=prix_net,
                    bareme=bareme,
                    fournisseur=alea.choice(fournisseurs[famille.cle]),
                    prix_achat=achat,
                    avantages=avantages,
                    transport=transport,
                    stock=stock,
                    point_de_commande=point,
                    quantite_reassort=reassort_qte,
                    reassort=reassort,
                    statut=statut,
                )
            )
    # Les substituts : un ou deux articles de la même famille et du même modèle de libellé.
    par_debut: dict[str, list[Article]] = {}
    for article in articles:
        par_debut.setdefault(f"{article.famille}:{article.libelle.split(',')[0].rsplit(' ', 1)[0]}", []).append(article)
    for article in articles:
        if alea.random() < 0.12:
            voisins = [
                a
                for a in par_debut[f"{article.famille}:{article.libelle.split(',')[0].rsplit(' ', 1)[0]}"]
                if a is not article and a.statut == "courant"
            ]
            if voisins:
                article.substituts = sorted(
                    a.reference for a in alea.sample(voisins, min(len(voisins), alea.choice([1, 1, 2])))
                )
    return articles


def article_en_json(a: Article) -> dict[str, Any]:
    return {
        "reference": a.reference,
        "libelle": a.libelle,
        "famille": a.famille,
        "unite": a.unite,
        "conditionnement": a.conditionnement,
        "prix_vente_ht_euros": en_euros(a.prix_vente),
        "prix_net": a.prix_net,
        "bareme_quantite": [{"a_partir_de": q, "remise_pourcent": r} for q, r in a.bareme],
        "taux_tva": 20,
        "achat": {
            "fournisseur": a.fournisseur,
            "prix_net_facture_ht_euros": en_euros(a.prix_achat),
            "avantages_financiers_pourcent": a.avantages,
            "transport_unitaire_ht_euros": en_euros(a.transport),
        },
        "stock_physique": a.stock,
        "point_de_commande": a.point_de_commande,
        "quantite_reassort": a.quantite_reassort,
        "reassort": None
        if a.reassort is None
        else {"quantite": a.reassort[0], "date_prevue": a.reassort[1].isoformat()},
        "statut": a.statut,
        "substituts": a.substituts,
    }


# --- le chiffrage, celui du service de ventes ---------------------------------------------------

REMISES = {"A": 0.0, "B": 4.0, "C": 8.0}
PORT_STANDARD = 1500
FRANCO = 30000
FORFAIT_EXPRESS = 2500


def remise_quantite(article: Article, quantite: int) -> float:
    remise = 0.0
    for seuil, taux in article.bareme:
        if quantite >= seuil and taux > remise:
            remise = taux
    return remise


def prix_net(article: Article, categorie: str, quantite: int) -> tuple[int, float]:
    if article.prix_net:
        return article.prix_vente, 0.0
    a = 10_000 - round(REMISES[categorie] * 100)
    b = 10_000 - round(remise_quantite(article, quantite) * 100)
    prix = (article.prix_vente * a * b + 50_000_000) // 100_000_000
    return prix, round((100_000_000 - a * b) / 1_000_000, 2)


def tva(base: int) -> int:
    return (base * 200 + 500) // 1000


@dataclass
class Ligne:
    article: Article
    quantite: int
    prix: int
    remise: float

    @property
    def montant(self) -> int:
        return self.prix * self.quantite


def chiffrer(lignes: list[Ligne], mode: str, reliquat: bool) -> tuple[int, int, int, int]:
    """Port, total HT, TVA et TTC, en centimes, comme le service de ventes."""
    somme = sum(ligne.montant for ligne in lignes)
    port = 0 if reliquat else FORFAIT_EXPRESS if mode == "express" else 0 if somme >= FRANCO else PORT_STANDARD
    ht = somme + port
    taxe = tva(ht)
    return port, ht, taxe, ht + taxe


# --- les clients ---------------------------------------------------------------------------------

METIERS = [
    "Plomberie",
    "Électricité",
    "Menuiserie",
    "Maçonnerie",
    "Couverture",
    "Peinture",
    "Chauffage",
    "Serrurerie",
    "Carrelage",
    "Plâtrerie",
    "Charpente",
    "Paysage",
]
FORMES_ENTREPRISE = [
    "{nom} Bâtiment",
    "Entreprise {nom}",
    "{nom} et Fils",
    "{nom} Maintenance",
    "{nom} Rénovation",
    "{nom} Travaux publics",
]
FORMES_PME = [
    "Ateliers {nom}",
    "{nom} Industrie",
    "Transports {nom}",
    "Garage {nom}",
    "Imprimerie {nom}",
    "Menuiserie industrielle {nom}",
    "{nom} Agencement",
]
COLLECTIVITES = [
    *(f"Mairie de {nom}" for _, nom, _, _ in COMMUNES),
    *(f"Services techniques de {nom}" for _, nom, _, _ in COMMUNES),
    "Communauté de communes du Val de Vaumoreau",
    "Syndicat intercommunal des eaux de la Brenne",
    "Syndicat d'électrification du canton de Laubrissac",
    "Collège des Grands Prés, Vaumoreau-sur-Indre",
    "Lycée professionnel de Vendrigny",
    "Résidence autonomie de Corvalet",
    "Centre aquatique intercommunal de Fontclavier",
    "Office de tourisme du Val de Vaumoreau",
    "Office public de l'habitat du Val de Vaumoreau",
    "Base de loisirs de Saulvenne",
]
FONCTIONS = {
    "artisan": [
        ("gérant", "gérante"),
        ("conjoint collaborateur", "conjointe collaboratrice"),
        ("secrétaire", "secrétaire"),
    ],
    "entreprise": [
        ("conducteur de travaux", "conductrice de travaux"),
        ("responsable des achats", "responsable des achats"),
        ("comptable", "comptable"),
    ],
    "pme": [
        ("responsable des achats", "responsable des achats"),
        ("responsable de maintenance", "responsable de maintenance"),
        ("comptable", "comptable"),
    ],
    "collectivite": [
        ("responsable des services techniques", "responsable des services techniques"),
        ("secrétaire de mairie", "secrétaire de mairie"),
        ("gestionnaire des achats", "gestionnaire des achats"),
    ],
}


@dataclass
class Client:
    code: str
    nom: str
    type: str
    commune: str
    secteur: str
    adresse: str
    telephone: str
    domaine: str
    contacts: list[dict[str, str]]
    adresses: list[dict[str, str]]
    categorie: str
    delai: str
    depuis: date
    volume: int  # centimes HT par mois
    limite: int = 0  # centimes TTC
    partielles: bool = True
    substitution: bool = False
    statut: str = "ouvert"
    motif: str | None = None
    bloque_depuis: date | None = None


def clients(annuaire: Annuaire, alea: random.Random) -> list[Client]:
    types = ["artisan"] * 210 + ["entreprise"] * 70 + ["pme"] * 42 + ["collectivite"] * 28
    alea.shuffle(types)
    poids = [p for _, _, _, p in COMMUNES]
    cles = [c for c, _, _, _ in COMMUNES]
    noms_pris: set[str] = set()
    collectivites = list(COLLECTIVITES)
    sortie: list[Client] = []
    for rang, type_ in enumerate(types, start=1):
        if type_ == "collectivite":
            nom = collectivites.pop(0)
            commune = next((c for c, n, _, _ in COMMUNES if n in nom), "vaumoreau")
        else:
            commune = alea.choices(cles, weights=poids)[0]
            while True:
                famille = alea.choice(NOMS)
                if type_ == "artisan":
                    nom = f"{alea.choice(METIERS)} {famille}"
                elif type_ == "entreprise":
                    nom = alea.choice(FORMES_ENTREPRISE).format(nom=famille)
                else:
                    nom = alea.choice(FORMES_PME).format(nom=famille)
                if nom not in noms_pris:
                    break
        noms_pris.add(nom)
        domaine = f"{slug(nom)}.example"
        contacts: list[dict[str, str]] = []
        for indice in range(1 if type_ == "artisan" and alea.random() < 0.6 else 2):
            civilite, prenom, famille_contact = annuaire.personne()
            masculin, feminin = FONCTIONS[type_][indice if indice < len(FONCTIONS[type_]) else 0]
            contacts.append(
                {
                    "nom": f"{prenom} {famille_contact}",
                    "fonction": feminin if civilite == "Mme" else masculin,
                    "courriel": f"{slug(prenom)}.{slug(famille_contact)}@{domaine}",
                }
            )
        siege = annuaire.adresse_zone(commune) if type_ in ("entreprise", "pme") else annuaire.adresse(commune)
        adresses = [{"code": "L1", "libelle": "siège", "adresse": siege}]
        if type_ != "artisan" and alea.random() < 0.35:
            adresses.append({"code": "L2", "libelle": "dépôt", "adresse": annuaire.adresse_zone(alea.choice(cles))})
        if type_ in ("entreprise", "artisan") and alea.random() < 0.2:
            adresses.append(
                {
                    "code": f"L{len(adresses) + 1}",
                    "libelle": "chantier déclaré",
                    "adresse": annuaire.adresse(alea.choice(cles)),
                }
            )
        depuis = date(alea.randrange(2008, 2026), alea.randrange(1, 13), 1)
        if rang % 29 == 0:
            depuis = date(2026, alea.randrange(1, 7), alea.randrange(1, 28))
        nouveau = depuis > date(2026, 1, 6)
        if type_ == "collectivite":
            categorie = alea.choice(["A", "A", "B"])
        elif type_ == "entreprise":
            categorie = alea.choice(["B", "B", "C"])
        elif type_ == "pme":
            categorie = alea.choice(["A", "B"])
        else:
            categorie = alea.choices(["A", "B", "C"], weights=[45, 40, 15])[0]
        delai = (
            "comptant"
            if nouveau
            else "60_jours_date_de_facture"
            if type_ in ("entreprise", "pme") and alea.random() < 0.3
            else "30_jours_date_de_facture"
        )
        echelle = {"artisan": 900_00, "entreprise": 2600_00, "pme": 1400_00, "collectivite": 700_00}[type_]
        volume = int(echelle * math.exp(alea.gauss(0, 0.55)))
        sortie.append(
            Client(
                code=f"c-{rang:04d}",
                nom=nom,
                type=type_,
                commune=commune,
                secteur=SECTEUR_COMMUNE[commune],
                adresse=siege,
                telephone=annuaire.fixe(),
                domaine=domaine,
                contacts=contacts,
                adresses=adresses,
                categorie=categorie,
                delai=delai,
                depuis=depuis,
                volume=volume,
                partielles=alea.random() < 0.8,
                substitution=alea.random() < 0.3,
            )
        )
    return sortie


# --- les fournisseurs ----------------------------------------------------------------------------

LIEUX_FOURNISSEURS = [
    "des Brandes",
    "du Val-Corvalet",
    "de la Garenne",
    "des Grands Champs",
    "du Pont-Rouge",
    "de la Brenne",
    "des Tilleuls",
    "du Moulin-Neuf",
    "de la Croisette",
    "des Hautes-Bornes",
]
ACTIVITES = {
    "visserie": ("Visserie", "fabricant de visserie et de boulonnerie"),
    "fixation": ("Fixations", "fabricant de chevilles et de systèmes d'ancrage"),
    "quincaillerie": ("Quincaillerie", "fabricant de quincaillerie de bâtiment"),
    "outillage": ("Outillage", "fabricant d'outillage à main"),
    "electroportatif": ("Électroportatif", "distributeur d'outillage électroportatif"),
    "plomberie": ("Sanitaire", "fabricant de raccords et de robinetterie"),
    "electricite": ("Matériel électrique", "fabricant d'appareillage électrique"),
    "protection": ("Protection", "fabricant d'équipements de protection individuelle"),
    "consommables": ("Abrasifs et colles", "fabricant de consommables d'atelier"),
    "entretien": ("Hygiène", "fabricant de produits d'hygiène et d'entretien"),
}


@dataclass
class Fournisseur:
    code: str
    nom: str
    activite: str
    adresse: str
    telephone: str
    courriel: str
    iban: str
    conditions: str
    minimum: int  # centimes HT


def fournisseurs(annuaire: Annuaire, alea: random.Random) -> tuple[list[Fournisseur], dict[str, list[str]]]:
    tous: list[Fournisseur] = []
    par_famille: dict[str, list[str]] = {}
    lieux = list(LIEUX_FOURNISSEURS)
    for famille in FAMILLES:
        mot, activite = ACTIVITES[famille.cle]
        alea.shuffle(lieux)
        codes: list[str] = []
        for lieu in lieux[:4]:
            nom = f"{mot} {lieu}"
            code = slug(nom)
            commune = alea.choice([c for c, _, _, _ in COMMUNES])
            tous.append(
                Fournisseur(
                    code=code,
                    nom=nom,
                    activite=activite,
                    adresse=annuaire.adresse_zone(commune),
                    telephone=annuaire.fixe(),
                    courriel=f"commandes@{code}.example",
                    iban=iban(alea),
                    conditions=alea.choice(
                        [
                            "paiement à 30 jours date de facture",
                            "paiement à 45 jours fin de mois",
                            "paiement à 60 jours date de facture",
                        ]
                    ),
                    minimum=alea.choice([150_00, 250_00, 300_00, 500_00]),
                )
            )
            codes.append(code)
        par_famille[famille.cle] = sorted(codes)
    tous.append(
        Fournisseur(
            code=TRANSPORTEUR,
            nom="Transports Delorme",
            activite="transport de messagerie, livraisons express",
            adresse=annuaire.adresse_zone("vendrigny"),
            telephone=annuaire.fixe(),
            courriel=f"service-client@{TRANSPORTEUR}.example",
            iban=iban(alea),
            conditions="paiement à 30 jours date de facture",
            minimum=0,
        )
    )
    return sorted(tous, key=lambda f: f.code), par_famille


# --- le monde ------------------------------------------------------------------------------------


@dataclass
class Facture:
    numero: str
    client: Client
    jour: date
    objet: str
    ttc: int
    payee: bool


@dataclass
class Commande:
    numero: str
    client: Client
    jour: date
    par: str
    mode: str
    adresse: dict[str, str]
    lignes: list[Ligne]
    statut: str
    reliquat_de: str | None = None
    livraison: str | None = None
    facture: str | None = None
    reference_client: str | None = None


@dataclass
class Livraison:
    numero: str
    commande: Commande
    expedition: date
    livraison: date | None
    transporteur: bool
    recepisse: str | None
    colis: int
    reserves: str | None
    signataire: str | None
    statut: str


@dataclass
class Monde:
    articles: list[Article] = field(default_factory=lambda: [])
    clients: list[Client] = field(default_factory=lambda: [])
    fournisseurs: list[Fournisseur] = field(default_factory=lambda: [])
    factures: list[Facture] = field(default_factory=lambda: [])
    avoirs: list[dict[str, Any]] = field(default_factory=lambda: [])
    commandes: list[Commande] = field(default_factory=lambda: [])
    livraisons: list[Livraison] = field(default_factory=lambda: [])
    retours: list[dict[str, Any]] = field(default_factory=lambda: [])
    encaissements: list[tuple[date, str, int]] = field(default_factory=lambda: [])


BLOQUES = [
    ("contentieux : factures de février et de mars impayées, dossier chez l'avocat", date(2026, 3, 31)),
    ("contentieux : chèque impayé de mars", date(2026, 3, 31)),
    ("impayé : mise en demeure du 2 juin restée sans effet", date(2026, 4, 30)),
    ("impayé : mise en demeure du 5 juin restée sans effet", date(2026, 4, 30)),
    ("redressement judiciaire ouvert le 12 juin 2026", date(2026, 5, 31)),
]
RESERVES = [
    "un colis enfoncé, contenu à vérifier",
    "un carton ouvert, il manque un sachet",
    "colis mouillé",
    "2 colis livrés sur 3",
    "emballage déchiré, article rayé",
]


def lignes_au_hasard(client: Client, articles: list[Article], alea: random.Random, nombre_lignes: int) -> list[Ligne]:
    choisis = alea.sample([a for a in articles if a.statut == "courant" and a.stock > 0], nombre_lignes)
    lignes: list[Ligne] = []
    for article in sorted(choisis, key=lambda a: a.reference):
        quantite = article.conditionnement * alea.choice([1, 1, 2, 2, 3, 4, 5, 6, 10, 12])
        prix, remise = prix_net(article, client.categorie, quantite)
        lignes.append(Ligne(article, quantite, prix, remise))
    return lignes


def facturation(monde: Monde, alea: random.Random) -> None:
    """Une facture par client et par mois, datée du dernier jour du mois ; quelques ventes au comptoir,
    facturées le jour même. Les avoirs du printemps. Les règlements reçus, pour les relevés."""
    rang = {date(2026, 3, 31): 101, date(2026, 4, 30): 301, date(2026, 5, 31): 601, date(2026, 6, 30): 1001}
    for client in monde.clients:
        for fin_de_mois in sorted(rang):
            if fin_de_mois < client.depuis or alea.random() < 0.08:
                continue
            if client.bloque_depuis is not None and fin_de_mois > client.bloque_depuis:
                continue
            ttc = int(client.volume * alea.uniform(0.6, 1.4) * 1.2)
            echeance = fin_de_mois + timedelta(
                days={"comptant": 0, "30_jours_date_de_facture": 30, "60_jours_date_de_facture": 60}[client.delai]
            )
            if client.statut == "bloque" or echeance >= AUJOURD_HUI:
                payee = False
            elif echeance >= date(2026, 6, 29):
                payee = alea.random() < 0.85
            else:
                payee = alea.random() < 0.97
            reglement = min(echeance, AUJOURD_HUI - timedelta(days=4)) - timedelta(days=alea.randrange(0, 4))
            # Une facture réglée avant juin ne sert plus : elle n'est ni dans la facturation, ni au relevé.
            if payee and reglement < date(2026, 6, 1):
                continue
            numero = f"FC-2026-{rang[fin_de_mois]:04d}"
            rang[fin_de_mois] += 1
            mois = MOIS[fin_de_mois.month - 1]
            monde.factures.append(Facture(numero, client, fin_de_mois, f"Relevé mensuel de {mois} 2026", ttc, payee))
            if payee:
                monde.encaissements.append((reglement, f"VIR {client.nom.upper()} {numero}", ttc))
            elif echeance == date(2026, 6, 30) and client.statut == "ouvert" and alea.random() < 0.35:
                # Réglée entre le 1er et le 3 juillet, pas encore lettrée : la facture reste à payer.
                monde.encaissements.append(
                    (date(2026, 7, alea.randrange(1, 4)), f"VIR {client.nom.upper()} {numero}", ttc)
                )
    # Les ventes au comptoir de juin et de juillet, facturées le jour même.
    comptoir = 1401
    for jour in jours_ouvres(date(2026, 6, 1), date(2026, 7, 3)):
        for client in alea.sample([c for c in monde.clients if c.statut == "ouvert"], 2):
            ttc = arrondi_prix(alea.uniform(12, 240)) * 12 // 10
            numero = f"FC-2026-{comptoir:04d}"
            comptoir += 1
            payee = client.delai == "comptant" or jour < date(2026, 6, 6)
            monde.factures.append(Facture(numero, client, jour, f"Vente au comptoir du {jour_fr(jour)}", ttc, payee))
            if payee:
                monde.encaissements.append((jour, f"CB COMPTOIR {numero}", ttc))
    monde.factures.sort(key=lambda f: f.numero)
    # Des avoirs de mai et de juin, sur des factures de mai.
    candidates = [f for f in monde.factures if f.jour == date(2026, 5, 31)]
    for rang_avoir, facture in enumerate(alea.sample(candidates, 12), start=1):
        montant = min(facture.ttc // 4, arrondi_prix(alea.uniform(8, 90)) * 12 // 10)
        monde.avoirs.append(
            {
                "numero": f"AV-2026-{rang_avoir:04d}",
                "client": facture.client.code,
                "facture": facture.numero,
                "date": horodatage(jour_ouvre_suivant(date(2026, 6, 1), rang_avoir), 10, 30),
                "montant_ttc_euros": en_euros(montant),
                "motif": alea.choice(
                    [
                        "article cassé à la livraison",
                        "retour d'un article conforme, décote de 10 %",
                        "erreur de référence à la préparation",
                        "manquant au récépissé du transporteur",
                    ]
                ),
                "emis_par": alea.choice(["remi.joly", "nathalie.brunet"]),
            }
        )


def ventes(monde: Monde, alea: random.Random) -> None:
    """Les commandes du 22 juin au 3 juillet, leurs bons de livraison, quelques reliquats et retours."""
    actifs = [c for c in monde.clients if c.statut == "ouvert"]
    poids = [c.volume for c in actifs]
    numero = 1801
    bl = 1650
    juin = {f.client.code: f.numero for f in monde.factures if f.jour == date(2026, 6, 30)}
    for jour in jours_ouvres(date(2026, 6, 22), date(2026, 7, 3)):
        for _ in range(alea.randrange(20, 30)):
            client = alea.choices(actifs, weights=poids)[0]
            if jour.month == 6 and client.code not in juin:
                continue
            mode = "express" if alea.random() < 0.15 else "standard"
            adresse = (
                client.adresses[0] if len(client.adresses) == 1 or alea.random() < 0.7 else alea.choice(client.adresses)
            )
            lignes = lignes_au_hasard(client, monde.articles, alea, alea.choice([1, 1, 2, 2, 3, 4, 5, 6, 8]))
            _, secteur_adv = SECTEURS[client.secteur]
            # Le 3 juillet, une commande est encore à préparer ou vient de partir ; avant, elle est
            # livrée, et facturée au relevé de juin si elle l'a été en juin. Express : départ le jour
            # même par transporteur, livraison le lendemain ouvré ; standard : départ et livraison
            # par une camionnette le lendemain ouvré.
            statut = alea.choice(["expediee", "validee", "validee"]) if jour == date(2026, 7, 3) else "livree"
            transporteur = mode == "express"
            expedition = jour if transporteur or statut == "expediee" else jour_ouvre_suivant(jour)
            livree = None if statut == "expediee" else jour_ouvre_suivant(expedition) if transporteur else expedition
            if statut == "livree" and livree is not None and livree <= date(2026, 6, 30):
                statut = "facturee"
            commande = Commande(
                numero=f"CO-2026-{numero:05d}",
                client=client,
                jour=jour,
                par=secteur_adv,
                mode=mode,
                adresse=adresse,
                lignes=lignes,
                statut=statut,
                reference_client=f"BC-{alea.randrange(100, 9999)}"
                if client.type != "artisan" and alea.random() < 0.6
                else None,
            )
            numero += 1
            if commande.statut == "facturee":
                commande.facture = juin[client.code]
            if commande.statut != "validee":
                reserves = alea.choice(RESERVES) if livree is not None and alea.random() < 0.04 else None
                livraison = Livraison(
                    numero=f"BL-2026-{bl:05d}",
                    commande=commande,
                    expedition=expedition,
                    livraison=livree,
                    transporteur=transporteur,
                    recepisse=f"TD-{alea.randrange(100000, 999999)}" if transporteur else None,
                    colis=max(1, len(lignes) // 3 + alea.choice([0, 0, 1])),
                    reserves=reserves,
                    signataire=None if livree is None else client.contacts[0]["nom"],
                    statut="en_cours" if livree is None else "livre",
                )
                bl += 1
                commande.livraison = livraison.numero
                monde.livraisons.append(livraison)
            monde.commandes.append(commande)
    # Des reliquats en attente de réassort, sur des articles en rupture qui ont un réassort annoncé.
    en_rupture = [a for a in monde.articles if a.stock == 0 and a.reassort is not None]
    origines = [c for c in monde.commandes if c.statut in ("livree", "expediee") and c.client.partielles]
    for article, origine in zip(alea.sample(en_rupture, 6), alea.sample(origines, 6), strict=True):
        quantite = article.conditionnement * alea.choice([2, 4, 5, 10])
        prix, remise = prix_net(article, origine.client.categorie, quantite)
        monde.commandes.append(
            Commande(
                numero=f"CO-2026-{numero:05d}",
                client=origine.client,
                jour=origine.jour,
                par=origine.par,
                mode=origine.mode,
                adresse=origine.adresse,
                lignes=[Ligne(article, quantite, prix, remise)],
                statut="en_attente_reassort",
                reliquat_de=origine.numero,
            )
        )
        numero += 1
    # Le stock en rayon couvre les commandes validées, qui le réservent.
    reserve: dict[str, int] = {}
    for commande in monde.commandes:
        if commande.statut == "validee":
            for ligne in commande.lignes:
                reserve[ligne.article.reference] = reserve.get(ligne.article.reference, 0) + ligne.quantite
    for article in monde.articles:
        if reserve.get(article.reference, 0) > article.stock:
            article.stock = reserve[article.reference] + article.conditionnement * alea.randrange(0, 6)
    # Des retours de juin, déjà enregistrés.
    livrees = [lv for lv in monde.livraisons if lv.statut == "livre" and lv.commande.jour.month == 6]
    for rang, livraison in enumerate(alea.sample(livrees, 5), start=1):
        ligne = livraison.commande.lignes[0]
        monde.retours.append(
            {
                "numero": f"RT-2026-{rang:04d}",
                "livraison": livraison.numero,
                "client": livraison.commande.client.code,
                "date": horodatage(jour_ouvre_suivant(livraison.livraison or livraison.expedition, 2), 14, 10 + rang),
                "lignes": [
                    {
                        "reference": ligne.article.reference,
                        "quantite": ligne.article.conditionnement,
                        "etat": alea.choice(["revendable", "rebut"]),
                    }
                ],
                "motif": alea.choice(
                    [
                        "retour accepté, article conforme",
                        "article abîmé au transport",
                        "erreur de référence à la préparation",
                    ]
                ),
                "enregistre_par": "remi.joly",
            }
        )


def completer_factures_de_juin(monde: Monde) -> None:
    """Une facture de juin reprend au moins les commandes qui la citent : quand son montant tiré au
    hasard est plus petit que leur total, il devient ce total, et un règlement reçu en juillet suit
    (étape 6, JOURNAL, entrée 191). Aucun tirage : les autres factures ne changent pas."""
    totaux: dict[str, int] = {}
    for c in monde.commandes:
        if c.facture is not None:
            totaux[c.facture] = totaux.get(c.facture, 0) + chiffrer(c.lignes, c.mode, c.reliquat_de is not None)[3]
    for facture in monde.factures:
        total = totaux.get(facture.numero, 0)
        if total > facture.ttc:
            ancien = facture.ttc
            facture.ttc = total
            monde.encaissements = [
                (jour, libelle, total if libelle.endswith(f" {facture.numero}") and ttc == ancien else ttc)
                for jour, libelle, ttc in monde.encaissements
            ]


def limites_et_blocages(monde: Monde, alea: random.Random) -> None:
    """Les limites d'encours tiennent les commandes déjà validées ; cinq clients sont bloqués."""
    for client, (motif, depuis) in zip(
        alea.sample([c for c in monde.clients if c.type != "collectivite" and c.delai != "comptant"], len(BLOQUES)),
        BLOQUES,
        strict=True,
    ):
        client.statut = "bloque"
        client.motif = motif
        client.bloque_depuis = depuis
    for client in monde.clients:
        client.limite = max(1000_00, math.ceil(client.volume * 1.2 * 2.4 / 500_00) * 500_00)


def encours(monde: Monde, client: Client) -> int:
    rendu: dict[str, int] = {}
    for avoir in monde.avoirs:
        rendu[avoir["facture"]] = rendu.get(avoir["facture"], 0) + round(avoir["montant_ttc_euros"] * 100)
    factures = sum(max(0, f.ttc - rendu.get(f.numero, 0)) for f in monde.factures if f.client is client and not f.payee)
    commandes = sum(
        chiffrer(c.lignes, c.mode, c.reliquat_de is not None)[3]
        for c in monde.commandes
        if c.client is client and c.statut in ("validee", "expediee", "livree")
    )
    return factures + commandes


def ajuster_limites(monde: Monde) -> None:
    """Aucun client ouvert n'est au-delà de sa limite : une commande validée l'a été dans l'encours."""
    for client in monde.clients:
        if client.statut == "ouvert":
            besoin = encours(monde, client)
            if besoin > client.limite:
                client.limite = math.ceil(besoin * 1.15 / 500_00) * 500_00


# --- écriture ------------------------------------------------------------------------------------


def ecrire_catalogue(etat: Etat, monde: Monde) -> None:
    entete = {
        "annee_tarif": 2026,
        "conditions": {
            "remises_categories": REMISES,
            "port_standard_ht_euros": en_euros(PORT_STANDARD),
            "franco_a_partir_de_ht_euros": en_euros(FRANCO),
            "forfait_express_ht_euros": en_euros(FORFAIT_EXPRESS),
            "taux_tva_port": 20,
        },
    }
    debut = json.dumps(entete, ensure_ascii=False)[:-1]
    articles = ",\n".join(json.dumps(article_en_json(a), ensure_ascii=False) for a in monde.articles)
    etat.ecrire("ventes/catalogue.json", f'{debut}, "articles": [\n{articles}\n]}}\n')


def fiche_client(client: Client) -> dict[str, Any]:
    commercial, adv = SECTEURS[client.secteur]
    return {
        "code": client.code,
        "nom": client.nom,
        "type": client.type,
        "adresse": client.adresse,
        "telephone": client.telephone,
        "secteur": client.secteur,
        "commercial": commercial,
        "administration_des_ventes": adv,
        "contacts": client.contacts,
        "adresses_livraison": client.adresses,
        "categorie_remise": client.categorie,
        "delai_paiement": client.delai,
        "client_depuis": client.depuis.isoformat(),
        "limite_encours_euros": en_euros(client.limite),
        "livraisons_partielles": client.partielles,
        "substitution_acceptee": client.substitution,
        "statut": client.statut,
        "motif_blocage": client.motif,
    }


def ecrire_clients(etat: Etat, monde: Monde) -> None:
    """Une fiche par client, et la liste des clients : le seul moyen de passer du nom d'un client,
    lu dans un courriel, à son code (étape 6, JOURNAL, entrée 191)."""
    for client in monde.clients:
        etat.ecrire(
            f"dossiers/clients/{client.code}/fiche_client.yaml",
            en_yaml(f"Fiche du client {client.code} de Négovelle. Données FICTIVES.", fiche_client(client)),
        )
    etat.ecrire(
        "dossiers/clients/liste.csv",
        en_csv(["code", "nom", "type", "secteur"], [[c.code, c.nom, c.type, c.secteur] for c in monde.clients]),
    )


def ecrire_fournisseurs(etat: Etat, monde: Monde, alea: random.Random) -> None:
    for f in monde.fournisseurs:
        etat.ecrire(
            f"dossiers/fournisseurs/{f.code}/fiche_fournisseur.yaml",
            "\n".join(
                [
                    "# Fiche d'un fournisseur de Négovelle. Données FICTIVES.",
                    f"nom: {f.nom}",
                    f"activite: {f.activite}",
                    f"adresse: {f.adresse}",
                    f"telephone: {f.telephone}",
                    f"courriel_commandes: {f.courriel}",
                    f"courriel_facturation: facturation@{f.code}.example",
                    f"iban: {f.iban} (FICTIF)",
                    f"conditions: {f.conditions}",
                    f"minimum_de_commande: {euros(f.minimum)} HT" if f.minimum else "minimum_de_commande: aucun",
                    "",
                ]
            ),
        )
        etat.ecrire(f"dossiers/fournisseurs/{f.code}/rib_{f.code}.pdf", rib(f.nom, f.iban))
    # Les factures de juin, rangées, et l'échéancier des fournisseurs.
    lignes: list[list[str]] = []
    for f in [f for f in monde.fournisseurs if f.code != TRANSPORTEUR]:
        for _ in range(alea.choice([0, 1, 1, 2])):
            numero = f"F{alea.randrange(10000, 99999)}"
            jour = jour_ouvre_suivant(date(2026, 6, 1), alea.randrange(0, 20))
            ttc = arrondi_prix(alea.uniform(180, 4200)) * 12 // 10
            delai = 60 if "60" in f.conditions else 30
            echeance = jour + timedelta(days=delai)
            if "fin de mois" in f.conditions:
                fin = date(jour.year, jour.month + 1, 1) - timedelta(days=1)
                echeance = fin + timedelta(days=45)
            statut = "payée" if echeance < AUJOURD_HUI else "à payer"
            etat.ecrire(
                f"dossiers/fournisseurs/{f.code}/factures/{numero}.pdf",
                pdf(
                    [
                        f"FACTURE {numero}",
                        f.nom,
                        f"Date : {jour_fr(jour)}",
                        "Client : Négovelle, 36999 Vaumoreau-sur-Indre",
                        f"Montant TTC : {euros(ttc)}",
                        f"Échéance : {jour_fr(echeance)}",
                    ]
                ),
            )
            lignes.append([f.code, numero, jour.isoformat(), euros(ttc), echeance.isoformat(), statut])
    lignes.append([TRANSPORTEUR, "TD-2026-0612", "2026-06-30", euros(1_842_60), "2026-07-30", "à payer"])
    etat.ecrire(
        "dossiers/comptabilite/echeancier_fournisseurs.csv",
        en_csv(
            ["fournisseur", "numero", "date", "montant_ttc", "echeance", "statut"],
            sorted(lignes, key=lambda x: (x[4], x[0])),
        ),
    )


def ecrire_facturation(etat: Etat, monde: Monde) -> None:
    for f in monde.factures:
        etat.ecrire(
            f"facturation/factures/{f.numero}.json",
            en_json(
                {
                    "numero": f.numero,
                    "client": f.client.code,
                    "date": f.jour.isoformat(),
                    "objet": f.objet,
                    "montant_ttc_euros": en_euros(f.ttc),
                    "payee": f.payee,
                }
            ),
        )
    for avoir in monde.avoirs:
        etat.ecrire(f"facturation/avoirs/{avoir['numero']}.json", en_json(avoir))


def ecrire_ventes(etat: Etat, monde: Monde) -> None:
    for c in monde.commandes:
        port, ht, taxe, ttc = chiffrer(c.lignes, c.mode, c.reliquat_de is not None)
        historique = [
            {
                "date": horodatage(c.jour, 9, 10),
                "par": c.par,
                "action": "creee",
                "detail": "" if c.reliquat_de is None else f"reliquat de {c.reliquat_de}",
            }
        ]
        if c.statut != "en_attente_reassort":
            historique.append({"date": horodatage(c.jour, 9, 12), "par": c.par, "action": "validee", "detail": ""})
        livraison = next((lv for lv in monde.livraisons if lv.numero == c.livraison), None)
        if livraison is not None:
            # Une camionnette part le matin et livre dans la matinée ; le transporteur enlève l'après-midi.
            depart = (7, 30) if not livraison.transporteur and livraison.livraison is not None else (16, 0)
            historique.append(
                {
                    "date": horodatage(livraison.expedition, *depart),
                    "par": "gilles.poirier",
                    "action": "expediee",
                    "detail": livraison.numero,
                }
            )
            if livraison.livraison is not None:
                historique.append(
                    {
                        "date": horodatage(livraison.livraison, 11, 0),
                        "par": "gilles.poirier",
                        "action": "livree",
                        "detail": livraison.numero,
                    }
                )
        if c.facture is not None:
            historique.append(
                {
                    "date": horodatage(date(2026, 6, 30), 18, 0),
                    "par": "isabelle.royer",
                    "action": "facturee",
                    "detail": c.facture,
                }
            )
        etat.ecrire(
            f"ventes/commandes/{c.numero}.json",
            en_json(
                {
                    "numero": c.numero,
                    "client": c.client.code,
                    "reference_client": c.reference_client,
                    "cree_le": horodatage(c.jour, 9, 10),
                    "cree_par": c.par,
                    "mode": c.mode,
                    "livraison": {"code": c.adresse["code"], "adresse": c.adresse["adresse"]},
                    "lignes": [
                        {
                            "reference": ligne.article.reference,
                            "libelle": ligne.article.libelle,
                            "quantite": ligne.quantite,
                            "prix_tarif_ht_euros": en_euros(ligne.article.prix_vente),
                            "remise_pourcent": ligne.remise,
                            "prix_net_ht_euros": en_euros(ligne.prix),
                            "prix_derogatoire": False,
                            "taux_tva": 20,
                            "montant_ht_euros": en_euros(ligne.montant),
                        }
                        for ligne in c.lignes
                    ],
                    "port_ht_euros": en_euros(port),
                    "total_ht_euros": en_euros(ht),
                    "total_tva_euros": en_euros(taxe),
                    "total_ttc_euros": en_euros(ttc),
                    "statut": c.statut,
                    "motif_attente": None,
                    "reliquat_de": c.reliquat_de,
                    "livraisons": [] if c.livraison is None else [c.livraison],
                    "facture": c.facture,
                    "historique": historique,
                }
            ),
        )
    for lv in monde.livraisons:
        etat.ecrire(
            f"ventes/livraisons/{lv.numero}.json",
            en_json(
                {
                    "numero": lv.numero,
                    "commande": lv.commande.numero,
                    "client": lv.commande.client.code,
                    "date_expedition": lv.expedition.isoformat(),
                    "date_livraison": None if lv.livraison is None else lv.livraison.isoformat(),
                    "transport": {
                        "mode": "transporteur" if lv.transporteur else "flotte",
                        "transporteur": TRANSPORTEUR if lv.transporteur else None,
                        "recepisse": lv.recepisse,
                    },
                    "adresse": lv.commande.adresse["adresse"],
                    "colis": lv.colis,
                    "lignes": [
                        {
                            "reference": ligne.article.reference,
                            "libelle": ligne.article.libelle,
                            "quantite": ligne.quantite,
                        }
                        for ligne in lv.commande.lignes
                    ],
                    "reserves": lv.reserves,
                    "signataire": lv.signataire,
                    "statut": lv.statut,
                }
            ),
        )
    for retour in monde.retours:
        etat.ecrire(f"ventes/retours/{retour['numero']}.json", en_json(retour))


def ecrire_achats(etat: Etat, monde: Monde, alea: random.Random) -> None:
    """Les commandes aux fournisseurs de juin et leurs réceptions, en CSV."""
    par_fournisseur: dict[str, list[Article]] = {}
    for article in monde.articles:
        par_fournisseur.setdefault(article.fournisseur, []).append(article)
    jours = jours_ouvres(date(2026, 6, 1), date(2026, 7, 3))
    for rang in range(1, 41):
        fournisseur = alea.choice(sorted(par_fournisseur))
        jour = alea.choice(jours[:-3])
        numero = f"CA-2026-{300 + rang:04d}"
        articles = alea.sample(
            par_fournisseur[fournisseur], min(len(par_fournisseur[fournisseur]), alea.randrange(2, 7))
        )
        lignes = [
            [
                fournisseur,
                jour.isoformat(),
                a.reference,
                a.libelle,
                str(a.quantite_reassort if a.prix_achat < 20_00 else max(2, a.quantite_reassort // 10)),
                decimal(a.prix_achat),
            ]
            for a in sorted(articles, key=lambda a: a.reference)
        ]
        etat.ecrire(
            f"dossiers/achats/commandes/{jour:%Y-%m}/{numero}.csv",
            en_csv(["fournisseur", "date", "reference", "libelle", "quantite", "prix_unitaire_ht_euros"], lignes),
        )
        arrivee = jour_ouvre_suivant(jour, alea.randrange(3, 9))
        if arrivee < AUJOURD_HUI:
            recues = [[numero, fournisseur, arrivee.isoformat(), ligne[2], ligne[4]] for ligne in lignes]
            etat.ecrire(
                f"dossiers/achats/receptions/{arrivee:%Y-%m}/BR-2026-{300 + rang:04d}.csv",
                en_csv(["commande", "fournisseur", "date_reception", "reference", "quantite_recue"], recues),
            )


def ecrire_releves(etat: Etat, monde: Monde) -> None:
    for mois in (6, 7):
        lignes = [
            [d.isoformat(), libelle, "", decimal(montant)]
            for d, libelle, montant in sorted(monde.encaissements)
            if d.month == mois and d.year == 2026
        ]
        etat.ecrire(
            f"dossiers/comptabilite/releves/2026-{mois:02d}.csv",
            en_csv(["date", "libelle", "debit_euros", "credit_euros"], lignes),
        )


def ecrire_courrier(etat: Etat, monde: Monde, alea: random.Random) -> None:
    objets = [
        ("avis-passage", "Avis de passage du facteur"),
        ("facture", "Facture papier d'un fournisseur"),
        ("publicite", "Catalogue publicitaire"),
        ("courrier-mairie", "Courrier de la mairie"),
        ("releve-banque", "Relevé de la banque"),
    ]
    for rang, jour in enumerate(jours_ouvres(date(2026, 6, 15), date(2026, 7, 3))):
        if rang % 2:
            continue
        code, titre = alea.choice(objets)
        etat.ecrire(
            f"dossiers/courrier/{jour:%Y-%m}/{jour.isoformat()}_{code}.pdf",
            pdf(
                [
                    titre.upper(),
                    f"Reçu le {jour_fr(jour)}",
                    "Destinataire : Négovelle, 14 rue des Charrons, 36999 Vaumoreau-sur-Indre",
                ]
            ),
        )


def ecrire_direction_et_rh(etat: Etat, organigramme: dict[str, Any], alea: random.Random) -> None:
    personnes = cast(list[dict[str, Any]], organigramme["personnes"])
    for p in personnes:
        etat.ecrire(
            f"dossiers/rh/{p['id']}/contrat_de_travail.pdf",
            pdf(["CONTRAT DE TRAVAIL", f"Salarié : {p['nom']}", f"Emploi : {p['role']}", "Employeur : Négovelle SAS"]),
        )
    for candidat, poste in (("lucie.brossard", "préparatrice de commandes"), ("hugo.tellier", "chauffeur-livreur")):
        etat.ecrire(
            f"dossiers/rh/candidatures/{candidat}/lettre.md",
            f"# Candidature (FICTIF)\n\nCandidature au poste de {poste}, reçue en juin 2026.\n",
        )
        etat.ecrire(f"dossiers/rh/candidatures/{candidat}/cv.pdf", pdf(["CURRICULUM VITAE", f"Poste visé : {poste}"]))
    for ident in ("laurent.gimenez", "aurelie.bonnefoy", "fabrice.mercier", "samir.ouali"):
        nom = next(p["nom"] for p in personnes if p["id"] == ident)
        lignes = ["| Date | Nature | Lieu | Montant TTC | Retenu |", "|---|---|---|---|---|"]
        total = 0
        for jour in sorted(alea.sample(jours_ouvres(date(2026, 5, 4), date(2026, 5, 29)), 4)):
            nature, montant = alea.choice(
                [
                    ("repas en tournée", alea.randrange(1250, 2000)),
                    ("péage", alea.randrange(320, 1480)),
                    ("stationnement", alea.randrange(200, 900)),
                    ("nuit d'hôtel", alea.randrange(6900, 8900)),
                ]
            )
            lignes.append(
                f"| {jour_fr(jour)} | {nature} | {NOM_COMMUNE[alea.choice(list(NOM_COMMUNE))]} | {euros(montant)} | {euros(montant)} |"
            )
            total += montant
        etat.ecrire(
            f"dossiers/direction/notes_de_frais/2026-05/{ident}.md",
            f"# Note de frais de mai 2026 : {nom} (FICTIF)\n\nVisée par Bruno Castaing le 2 juin 2026, réglée avec la paie de juin.\n\n"
            + "\n".join(lignes)
            + f"\n\nTotal retenu : {euros(total)}.\n",
        )


def ecrire_commun(etat: Etat, organigramme: dict[str, Any], monde: Monde) -> None:
    for nom in ("manuel_procedures.md", "conditions_generales_de_vente.md", "fiche_entreprise.md"):
        etat.ecrire(f"dossiers/commun/{nom}", (ENTREPRISE / nom).read_bytes())
    personnes = cast(list[dict[str, Any]], organigramme["personnes"])
    lignes = ["# Annuaire de Négovelle (FICTIF)", "", "| Nom | Rôle | Courriel | Téléphone |", "|---|---|---|---|"]
    lignes += [f"| {p['nom']} | {p['role']} | {p['courriel']} | {p['telephone']} |" for p in personnes]
    lignes += ["", "Standard : 02 61 91 60 00.", ""]
    etat.ecrire("dossiers/commun/annuaire.md", "\n".join(lignes))
    noms = {p["id"]: p["nom"] for p in personnes}
    secteurs = [
        "# Les secteurs de Négovelle (FICTIF)",
        "",
        "| Secteur | Communes | Commercial | Administration des ventes | Clients |",
        "|---|---|---|---|---|",
    ]
    for secteur, (commercial, adv) in SECTEURS.items():
        communes = ", ".join(nom for _, nom, s, _ in COMMUNES if s == secteur)
        nombre_clients = sum(1 for c in monde.clients if c.secteur == secteur)
        secteurs.append(f"| {secteur} | {communes} | {noms[commercial]} | {noms[adv]} | {nombre_clients} |")
    secteurs += ["", "Toutes les communes sont dans l'Indre, au code postal 36999 ; elles sont fictives.", ""]
    etat.ecrire("dossiers/commun/secteurs.md", "\n".join(secteurs))
    familles = [
        "# Les familles du catalogue (FICTIF)",
        "",
        "| Famille | Préfixe des références | Articles | Fournisseurs |",
        "|---|---|---|---|",
    ]
    for famille in FAMILLES:
        codes = sorted({a.fournisseur for a in monde.articles if a.famille == famille.cle})
        familles.append(f"| {famille.titre} | {famille.prefixe} | {famille.nombre} | {', '.join(codes)} |")
    familles += ["", "Le catalogue se consulte au logiciel des ventes : chercher_articles, consulter_article.", ""]
    etat.ecrire("dossiers/commun/familles.md", "\n".join(familles))


# --- la messagerie -------------------------------------------------------------------------------


class Messagerie:
    def __init__(self, etat: Etat) -> None:
        self.etat = etat

    def deposer(
        self, boite: str, identifiant: str, de: tuple[str | None, str], objet: str, quand: str, corps: str
    ) -> None:
        courriel = {
            "identifiant": identifiant,
            "de": {"nom": de[0], "adresse": de[1]},
            "a": [boite],
            "cc": [],
            "objet": objet,
            "date": quand,
            "corps": corps,
            "pieces_jointes": [],
            "lu": True,
            "en_reponse_a": None,
            "transfere_de": None,
        }
        self.etat.ecrire(f"messagerie/boites/{boite}/reception/{identifiant}.json", en_json(courriel))


MODELES_CLIENTS = [
    (
        "Disponibilité",
        "Bonjour,\n\nAvez-vous en stock la référence {reference} ? Il m'en faudrait {quantite} pour la fin de semaine.\n\nMerci,\n{nom}",
    ),
    ("Commande reçue, merci", "Bonjour,\n\nLa livraison de ce matin est complète. Merci.\n\n{nom}"),
    (
        "Copie de facture",
        "Bonjour,\n\nPouvez-vous me renvoyer la facture de mai ? Je ne la retrouve pas.\n\nCordialement,\n{nom}",
    ),
    ("Horaires du comptoir cet été", "Bonjour,\n\nLe comptoir reste-t-il ouvert en août ?\n\n{nom}"),
]
MODELES_FOURNISSEURS = [
    (
        "Confirmation de commande",
        "Bonjour,\n\nNous confirmons votre commande ; livraison prévue la semaine prochaine.\n\nLe service commandes\n{nom}",
    ),
    (
        "Nouveau tarif au 1er septembre",
        "Bonjour,\n\nVous trouverez notre tarif de rentrée dans notre prochain envoi.\n\n{nom}",
    ),
    ("Fermeture estivale", "Bonjour,\n\nNos bureaux seront fermés du 10 au 21 août.\n\n{nom}"),
]
MODELES_INTERNES = [
    (
        "bruno.castaing",
        "Inventaire tournant",
        "Bonjour à tous,\n\nL'inventaire tournant de la visserie se fait jeudi après-midi.\n\nBruno",
    ),
    (
        "bruno.castaing",
        "Congés d'été",
        "Bonjour,\n\nMerci de m'envoyer vos dates de congés d'août avant le 10 juillet.\n\nBruno",
    ),
    (
        "corinne.vidal",
        "Commandes express",
        "Bonjour,\n\nRappel : une commande express se valide avant 15 h.\n\nCorinne",
    ),
    ("gilles.poirier", "Quai de réception", "Bonjour,\n\nLe quai 2 est libre à nouveau pour les réceptions.\n\nGilles"),
    (
        "chantal.robin",
        "Courrier du jour",
        "Bonjour,\n\nLe courrier du jour est numérisé et rangé dans courrier/.\n\nChantal",
    ),
]
FAMILLES_BOITES = {
    "contact": "clients",
    "commandes": "clients",
    "sav": "clients",
    "compta": "fournisseurs",
    "denis.barthe": "fournisseurs",
    "vincent.arnaud": "fournisseurs",
}


def messagerie(etat: Etat, monde: Monde, organigramme: dict[str, Any], alea: random.Random) -> None:
    """Des courriels déjà lus des trois dernières semaines, dans chaque boîte : le bruit d'un négoce."""
    boite = Messagerie(etat)
    personnes = cast(list[dict[str, Any]], organigramme["personnes"])
    collegues = {p["id"]: (p["nom"], p["courriel"]) for p in personnes}
    boites: list[tuple[str, str, str]] = [
        (f"{cle}@{DOMAINE}", cle, abrege)
        for cle, abrege in (("contact", "ctc"), ("commandes", "cmd"), ("compta", "cpt"), ("sav", "sav"))
    ] + [(p["courriel"], p["id"], "".join(part[:2] for part in p["id"].split("."))) for p in personnes]
    jours = jours_ouvres(date(2026, 6, 15), date(2026, 7, 3))
    references = [a.reference for a in monde.articles if a.statut == "courant"]
    for adresse, cle, abrege in boites:
        nombre_courriels = alea.randrange(3, 7)
        choisis = sorted(alea.sample(jours, nombre_courriels), reverse=True)
        for rang, jour in enumerate(choisis, start=1):
            quand = horodatage(jour, alea.randrange(8, 17), alea.randrange(60))
            identifiant = f"m-{abrege}-b{rang:02d}"
            famille = FAMILLES_BOITES.get(
                cle,
                "clients" if cle in {p["id"] for p in personnes if "saisir_commandes" in p["droits"]} else "internes",
            )
            if famille == "internes" or alea.random() < 0.25:
                internes = [modele for modele in MODELES_INTERNES if modele[0] != cle]
                auteur, objet, corps = alea.choice(internes)
                boite.deposer(adresse, identifiant, collegues[auteur], objet, quand, corps)
            elif famille == "clients":
                client = alea.choice(monde.clients)
                contact = client.contacts[0]
                objet, corps = alea.choice(MODELES_CLIENTS)
                texte = corps.format(
                    nom=contact["nom"], reference=alea.choice(references), quantite=alea.choice([5, 10, 20, 50])
                )
                boite.deposer(adresse, identifiant, (contact["nom"], contact["courriel"]), objet, quand, texte)
            else:
                fournisseur = alea.choice([f for f in monde.fournisseurs if f.code != TRANSPORTEUR])
                objet, corps = alea.choice(MODELES_FOURNISSEURS)
                boite.deposer(
                    adresse,
                    identifiant,
                    (fournisseur.nom, fournisseur.courriel),
                    objet,
                    quand,
                    corps.format(nom=fournisseur.nom),
                )


# --- assemblage ----------------------------------------------------------------------------------


def alea_de(partie: str) -> random.Random:
    """Le tirage d'une partie de l'état, à part de celui des autres : changer une partie ne déplace
    pas les noms ni les montants des parties qu'elle ne touche pas, dont dépendent les tâches."""
    return random.Random(f"{GRAINE}:{partie}")


def construire() -> Etat:
    """Construit tous les fichiers en mémoire, dans un ordre fixe."""
    etat = Etat()
    annuaire = Annuaire(alea_de("annuaire"))
    organigramme = cast(dict[str, Any], yaml.safe_load((ENTREPRISE / "organigramme.yaml").read_text(encoding="utf-8")))
    monde = Monde()
    monde.fournisseurs, par_famille = fournisseurs(annuaire, alea_de("fournisseurs"))
    monde.articles = catalogue(par_famille, alea_de("catalogue"))
    monde.clients = clients(annuaire, alea_de("clients"))
    limites_et_blocages(monde, alea_de("limites"))
    facturation(monde, alea_de("facturation"))
    ventes(monde, alea_de("ventes"))
    completer_factures_de_juin(monde)
    ajuster_limites(monde)
    ecrire_catalogue(etat, monde)
    ecrire_clients(etat, monde)
    ecrire_fournisseurs(etat, monde, alea_de("factures_fournisseurs"))
    ecrire_facturation(etat, monde)
    ecrire_ventes(etat, monde)
    ecrire_achats(etat, monde, alea_de("achats"))
    ecrire_releves(etat, monde)
    ecrire_courrier(etat, monde, alea_de("courrier"))
    ecrire_direction_et_rh(etat, organigramme, alea_de("direction"))
    ecrire_commun(etat, organigramme, monde)
    messagerie(etat, monde, organigramme, alea_de("messagerie"))
    return etat


def ecrire(etat: Etat, destination: Path) -> None:
    for relatif, contenu in sorted(etat.fichiers.items()):
        chemin = destination / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(contenu)


def ecarts(etat: Etat) -> list[str]:
    """Différences entre les données présentes dans v1 et une génération fraîche."""
    with tempfile.TemporaryDirectory() as dossier:
        frais = Path(dossier)
        ecrire(etat, frais)
        messages: list[str] = []
        for partie in GENERES:
            attendus = {p.relative_to(frais) for p in (frais / partie).rglob("*") if p.is_file()}
            presents: set[Path] = set()
            if (V1 / partie).exists():
                presents = {p.relative_to(V1) for p in (V1 / partie).rglob("*") if p.is_file()}
            messages += [f"absent : {p}" for p in sorted(attendus - presents)]
            messages += [f"en trop : {p}" for p in sorted(presents - attendus)]
            messages += [
                f"différent : {p}"
                for p in sorted(attendus & presents)
                if not filecmp.cmp(frais / p, V1 / p, shallow=False)
            ]
        return messages


def main() -> int:
    analyse = argparse.ArgumentParser(description=(__doc__ or "Génère l'état v1 de Négovelle.").splitlines()[0])
    analyse.add_argument("--verifier", action="store_true", help="contrôle sans rien écrire")
    args = analyse.parse_args()
    etat = construire()
    if args.verifier:
        messages = ecarts(etat)
        if messages:
            print(f"État v1 de Négovelle à régénérer ({len(messages)} écart(s)) :", file=sys.stderr)
            for message in messages[:20]:
                print(f"  {message}", file=sys.stderr)
            return 1
        print(f"État v1 de Négovelle à jour ({len(etat.fichiers)} fichiers).")
        return 0
    for partie in GENERES:
        shutil.rmtree(V1 / partie, ignore_errors=True)
    ecrire(etat, V1)
    empreinte = hashlib.sha256(b"".join(etat.fichiers[c] for c in sorted(etat.fichiers))).hexdigest()[:12]
    print(f"État v1 de Négovelle généré : {len(etat.fichiers)} fichiers dans {V1.relative_to(RACINE)} ({empreinte}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
