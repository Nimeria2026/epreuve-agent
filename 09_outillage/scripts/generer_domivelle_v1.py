"""Génère l'état initial v1 de Domivelle, seconde PME fictive (ADR 0006) : dossiers partagés et
messagerie.

Rejouable à l'octet près : graine fixe, PDF sans date ni identifiant, JSON et YAML dans un ordre
fixe. Écrit 05_pme/societes/domivelle/v1/dossiers/ et 05_pme/societes/domivelle/v1/messagerie/ ; le
dossier entreprise/ reste écrit à la main. Cahier des charges : v1/inventaire.yaml ; cadrage :
00_docs/sources/2026-10-15_cadrage_administration_de_biens.md, sections 6 et 8. Le monde est commun
aux tâches ; les courriels non lus d'une tâche vont dans son complément. Tout est fictif : adresses
en .example, téléphones dans les plages réservées à la fiction, code banque 99999, communes
inventées, mention FICTIF dans chaque document.

Usage, depuis la racine du dépôt :
    uv run python 09_outillage/scripts/generer_domivelle_v1.py              # régénère
    uv run python 09_outillage/scripts/generer_domivelle_v1.py --verifier   # contrôle sans écrire

Codes de sortie : 0 à jour ou régénéré, 1 données périmées.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
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
V1 = RACINE / "05_pme" / "societes" / "domivelle" / "v1"
ENTREPRISE = V1 / "entreprise"
GENERES = ("dossiers", "messagerie")
GRAINE = 20260608
AUJOURD_HUI = date(2026, 6, 8)
PARIS = ZoneInfo("Europe/Paris")
DOMAINE = "domivelle.example"
MENTION = "Document FICTIF : Domivelle et ses partenaires n'existent pas."
CP = "18999"
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

# Communes inventées, absentes de geo.api.gouv.fr (vérifié le 2026-10-15) : clé, nom, secteur,
# distances de l'agence en kilomètres, lots en gestion.
COMMUNES = [
    ("montclavel", "Montclavel-sur-Cher", "centre", (1, 6), 420),
    ("vernillac", "Vernillac", "nord", (8, 16), 240),
    ("saint_aubrin", "Saint-Aubrin-des-Bois", "nord", (14, 24), 160),
    ("chantebrune", "Chantebrune", "sud", (7, 15), 230),
    ("sorlay", "Sorlay-le-Haut", "sud", (12, 22), 150),
]
NOM_COMMUNE = {cle: nom for cle, nom, *_ in COMMUNES}
GESTIONNAIRES = {"nord": "Élodie Chauvin", "centre": "Cédric Maillard", "sud": "Solène Audoin"}

# Immeubles fixés pour les tâches (inventaire, reserve_pour_les_taches) : code, commune, nature,
# nombre de lots, distance de l'agence. Ils prennent les premiers codes de leur secteur.
IMMEUBLES_FIXES = [
    ("n01", "vernillac", "collectif", 14, 9),  # dv03, le lot n01-06 ; dv16, l'état des lieux du 22 mai
    ("n02", "vernillac", "collectif", 12, 12),  # dv16, l'état des lieux du 4 mai
    ("n03", "saint_aubrin", "maisons", 6, 22),  # dv16, l'état des lieux du 12 mai
    ("c01", "montclavel", "collectif", 16, 3),  # dv02, les quatre baux à réviser
    ("s01", "sorlay", "collectif", 10, 18),  # dv16, la visite du 7 mai
    ("s02", "chantebrune", "collectif", 8, 15),  # dv16, la visite du 28 avril
]
# Lots fixés : loyer en centimes, dépôt, date d'entrée, révision (mois, jour), trimestre, DPE.
# Lots dont une tâche écrit au propriétaire : sa fiche complète existe (inventaire, reserve_pour_les_taches).
LOTS_DES_TACHES = [
    "s01-01",  # dv01, congé pour mutation ; même propriétaire que s01-02, congé remis en main propre
    "s01-05",  # dv01, congé sans justificatif
    "c01-14",  # dv12, le propriétaire qui écrit d'une adresse inconnue
    "s02-04",  # dv05, le propriétaire qui demande le dossier d'une candidate
    "n02-03",  # dv06, le chauffe-eau accepté par écrit
    "n02-07",  # dv06, le volet roulant sans accord
    "c04-03",  # dv09, la locataire d'un lot en gestion dans une copropriété du syndic
]
# Immeubles dont une tâche fixe le gardien, sans toucher aux tirages : n38, dvh01, un gardien qui ne fait
# que sortir les conteneurs, récupérable à 40 %.
GARDIENS_FIXES: dict[str, bool] = {"n38": True}
# Copropriétés dont une tâche prépare l'assemblée : aucun procès-verbal dans l'état. cp22, dvh04.
ASSEMBLEES_A_PREPARER = {"cp22"}
# Copropriétés fixées pour les tâches : budget et part de l'ascenseur en centimes, tantièmes d'un lot.
COPROPRIETES_FIXES: dict[str, dict[str, Any]] = {
    # dv14 : budget de 48 000 €, dont 8 000 € d'ascenseur ; le lot 17, 312/10 000 généraux et 420/10 000 d'ascenseur.
    "cp04": {"budget": 4800000, "ascenseur": 800000, "lot": 17, "tantiemes": 312, "tantiemes_ascenseur": 420},
}
LOTS_FIXES: dict[str, dict[str, Any]] = {
    "n21-12": {"provision": 7000},  # dv11, provision de 70 € par mois
    "n21-18": {"provision": 8000},  # dv11, provision de 80 € par mois
    "n38-01": {"provision": 9500},  # dvh01, toute l'année 2025
    "n38-02": {"provision": 4000},  # dvh01, toute l'année 2025
    "n38-03": {"entree": date(2025, 7, 1), "provision": 3500},  # dvh01, après le départ du 31 mai 2025
    "n38-04": {"entree": date(2025, 10, 16), "provision": 3800},  # dvh01, entrée en cours d'année
    "c01-03": {"type": "T3", "surface": 66, "loyer": 68400, "entree": date(2023, 7, 1), "trimestre": "T1", "dpe": "C"},
    "c01-07": {"type": "T3", "surface": 60, "loyer": 61500, "entree": date(2022, 7, 1), "trimestre": "T2", "dpe": "D"},
    "c01-09": {"type": "T2", "surface": 52, "loyer": 54000, "entree": date(2021, 7, 1), "trimestre": "T1", "dpe": "F"},
    "c01-12": {"type": "T3", "surface": 58, "loyer": 55200, "entree": date(2024, 3, 1), "trimestre": "T4", "dpe": "D"},
    "n01-06": {
        "type": "T3",
        "surface": 66,
        "loyer": 61000,
        "depot": 61000,
        "entree": date(2023, 2, 1),
        "sortie": date(2026, 5, 22),
        "dpe": "D",
    },
}

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
    "Aubert",
    "Barbier",
    "Baudin",
    "Bazin",
    "Bénard",
    "Berthier",
    "Besnard",
    "Blondel",
    "Boisseau",
    "Bonnet",
    "Bouchet",
    "Boulanger",
    "Bourdon",
    "Brunet",
    "Buisson",
    "Camus",
    "Carpentier",
    "Chabert",
    "Chapuis",
    "Charpentier",
    "Chevalier",
    "Clément",
    "Collin",
    "Colas",
    "Cordier",
    "Coste",
    "Courtois",
    "Couturier",
    "Delattre",
    "Delorme",
    "Deschamps",
    "Devaux",
    "Dumas",
    "Dupuy",
    "Durand",
    "Duval",
    "Étienne",
    "Fabre",
    "Faure",
    "Ferrand",
    "Fleury",
    "Fontaine",
    "Fournier",
    "Gaillard",
    "Garnier",
    "Gauthier",
    "Germain",
    "Gilbert",
    "Giraud",
    "Godard",
    "Gomez",
    "Bigot",
    "Guichard",
    "Guillot",
    "Hamon",
    "Hébert",
    "Bourgeois",
    "Hubert",
    "Huet",
    "Jacob",
    "Jacquet",
    "Joly",
    "Jourdan",
    "Julien",
    "Labbé",
    "Lacroix",
    "Lainé",
    "Lamy",
    "Langlois",
    "Laporte",
    "Laurent",
    "Leblanc",
    "Lebon",
    "Leclerc",
    "Lecomte",
    "Lefort",
    "Legrand",
    "Lejeune",
    "Lemaire",
    "Leroux",
    "Lesage",
    "Lévêque",
    "Lucas",
    "Maillot",
    "Marchand",
    "Maréchal",
    "Marie",
    "Martel",
    "Masse",
    "Mathieu",
    "Meunier",
    "Meyer",
    "Michaud",
    "Millet",
    "Moreau",
    "Morin",
    "Mouton",
    "Muller",
    "Navarro",
    "Noël",
    "Olivier",
    "Paris",
    "Pagès",
    "Picot",
    "Perret",
    "Perrot",
    "Petitjean",
    "Pichon",
    "Poirier",
    "Poulain",
    "Prévost",
    "Raymond",
    "Régnier",
    "Renard",
    "Rey",
    "Rivière",
    "Robin",
    "Roche",
    "Rolland",
    "Rousset",
    "Roy",
    "Royer",
    "Sanchez",
    "Schmitt",
    "Simon",
    "Tanguy",
    "Texier",
    "Thibault",
    "Tissier",
    "Vallée",
    "Vasseur",
    "Verdier",
    "Vidal",
    "Vincent",
    "Weber",
    "Bertin",
    "Chauvet",
    "Ferry",
    "Pasquier",
    "Brun",
]
# Noms du personnel de Domivelle et de Calorelle : aucune personne servie ne les porte.
NOMS_RESERVES = {
    "Tessier",
    "Lebrun",
    "Chauvin",
    "Maillard",
    "Audoin",
    "Mallet",
    "Renaud",
    "Delmas",
    "Fournel",
    "Sabatier",
    "Ollivier",
    "Carrière",
    "Marchal",
    "Lefèvre",
    "Roux",
    "Benali",
    "Perrin",
    "Girard",
    "Caron",
    "Blanc",
    "Guérin",
    "Lambert",
    "Haddad",
    "Picard",
    "Leroy",
    "Masson",
}
FOURNISSEURS_COURRIEL = ["courriel.example", "messagerie.example", "boite-postale.example", "mel-perso.example"]
RUES = [
    "rue de la Halle",
    "rue des Remparts",
    "avenue de la Gare",
    "rue du Moulin",
    "rue des Écoles",
    "place du Marché",
    "rue Saint-Martin",
    "rue des Vignes",
    "boulevard du Cher",
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
    "rue Victor-Hugo",
    "rue Jean-Jaurès",
    "rue des Jardins",
    "rue du Four",
    "rue des Peupliers",
    "rue de la Croix-Blanche",
    "chemin du Bois",
    "rue des Chênes",
    "rue Émile-Zola",
    "rue du Pont",
]
RESIDENCES = [
    "Les Charmilles",
    "Le Clos Saint-Roch",
    "Les Glycines",
    "Le Parc des Ormes",
    "Les Hauts de Montclavel",
    "Le Belvédère",
    "Les Coteaux",
    "Le Domaine des Saules",
    "Les Jardins de la Halle",
    "Le Carré Pasteur",
    "Les Terrasses du Cher",
    "Le Grand Pré",
    "Les Marronniers",
    "Le Clos des Vignes",
    "Les Iris",
    "Le Mail",
    "Les Platanes",
    "Le Square des Écoles",
    "Les Hortensias",
    "Le Clos Fleuri",
    "Les Cèdres",
    "Le Moulin Neuf",
    "Les Rives du Cher",
    "Le Parc Saint-Martin",
    "Les Camélias",
    "Le Panorama",
    "Les Pins",
    "Le Vieux Pont",
    "Les Roseraies",
    "Le Bocage",
    "Les Magnolias",
    "La Croix-Blanche",
    "Les Noisetiers",
    "Le Vallon",
    "Les Bruyères",
    "Le Clos du Lavoir",
    "Les Mimosas",
    "Le Cours des Remparts",
    "Les Aubépines",
    "Le Prieuré",
    "Les Lauriers",
    "Le Clos des Forges",
    "Les Violettes",
    "Le Hameau des Prés",
    "Les Peupliers",
]
# Artisans et prestataires : nom, activité. Lieux-dits inventés.
ARTISANS = [
    ("Plomberie du Moulin-Barrat", "plomberie"),
    ("Plomberie des Chaumes-Rouges", "plomberie"),
    ("Sanitaires de la Garenne-Aubry", "plomberie"),
    ("Électricité du Pré-Carré", "électricité"),
    ("Électricité des Rouches", "électricité"),
    ("Serrurerie de la Motte-Brûlée", "serrurerie"),
    ("Serrurerie des Quatre-Vents", "serrurerie"),
    ("Chauffage de la Garenne-Aubry", "chauffage et eau chaude"),
    ("Chauffage des Fontenils", "chauffage et eau chaude"),
    ("Menuiserie des Fontenils", "menuiserie et volets"),
    ("Menuiserie du Gué-Morin", "menuiserie et volets"),
    ("Peinture du Gué-Morin", "peinture"),
    ("Peinture des Rouches", "peinture"),
    ("Nettoyage des Quatre-Vents", "nettoyage des parties communes"),
    ("Nettoyage du Pré-Carré", "nettoyage des parties communes"),
    ("Propreté de la Motte-Brûlée", "nettoyage des parties communes"),
    ("Ascenseurs des Chaumes-Rouges", "ascenseurs"),
    ("Ascenseurs du Moulin-Barrat", "ascenseurs"),
    ("Espaces verts des Fontenils", "espaces verts"),
    ("Espaces verts de la Garenne-Aubry", "espaces verts"),
    ("Couverture des Rouches", "couverture et zinguerie"),
    ("Couverture du Gué-Morin", "couverture et zinguerie"),
    ("Vitrerie des Quatre-Vents", "vitrerie"),
    ("Désinsectisation du Pré-Carré", "désinsectisation"),
    ("Diagnostics de la Motte-Brûlée", "diagnostics immobiliers"),
    ("Maçonnerie des Chaumes-Rouges", "maçonnerie"),
    ("Antennes du Moulin-Barrat", "antennes et interphones"),
    ("Ramonage des Fontenils", "ramonage"),
]
ASSUREURS = ["Mutuelle Carrelis (FICTIF)", "Assurances Brévalle (FICTIF)", "Mutuelle des Deux-Rives (FICTIF)"]
SINISTRES = {
    "Mutuelle Carrelis (FICTIF)": "sinistres@mutuelle-carrelis.example",
    "Assurances Brévalle (FICTIF)": "sinistres@assurances-brevalle.example",
    "Mutuelle des Deux-Rives (FICTIF)": "sinistres@mutuelle-des-deux-rives.example",
}
"""L'adresse où le syndic déclare un sinistre à l'assureur de l'immeuble (manuel, section 15 ; tâche
dvh08) : tirée du nom de l'assureur, sans tirage."""


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


def sans_accent(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def slug(texte: str) -> str:
    propre = "".join(c if c.isalnum() else "-" for c in sans_accent(texte).lower())
    return "-".join(partie for partie in propre.split("-") if partie)


def en_yaml(entete: str, donnees: dict[str, Any]) -> str:
    """YAML lisible, clés dans l'ordre donné, précédé d'un commentaire d'en-tête."""
    corps = yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False, default_flow_style=False, width=110)
    return f"# {entete}\n{corps}"


def en_csv(colonnes: list[str], lignes: list[list[str]]) -> str:
    """CSV séparé par des points-virgules, comme l'exporte un tableur français."""
    return "\n".join(";".join(ligne) for ligne in [colonnes, *lignes]) + "\n"


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
            "Banque : Banque Fictive du Berry (code banque 99999)",
        ]
    )


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
    """Tire des personnes fictives toutes différentes, et des numéros et adresses uniques."""

    def __init__(self, alea: random.Random) -> None:
        self.alea = alea
        self.pris: set[tuple[str, str]] = set()
        mobiles = list(range(5000, 10000))
        fixes = list(range(5000, 10000))
        alea.shuffle(mobiles)
        alea.shuffle(fixes)
        self.mobiles = mobiles
        self.fixes = fixes
        self.numeros: set[int] = set()

    def personne(self) -> tuple[str, str, str]:
        """(civilité, prénom, nom)"""
        noms = [n for n in NOMS if n not in NOMS_RESERVES]
        while True:
            femme = self.alea.random() < 0.5
            prenom = self.alea.choice(PRENOMS_F if femme else PRENOMS_H)
            nom = self.alea.choice(noms)
            if (prenom, nom) not in self.pris:
                self.pris.add((prenom, nom))
                return ("Mme" if femme else "M.", prenom, nom)

    def mobile(self) -> str:
        n = self.mobiles.pop()
        while n in self.numeros:
            n = self.mobiles.pop()
        self.numeros.add(n)
        return f"06 39 98 {n // 100:02d} {n % 100:02d}"

    def mobile_de(self, cle: str) -> str:
        """Le numéro d'une personne d'après une clé stable (son lot et son nom) : il ne bouge pas quand le
        tirage d'avant change."""
        n = 5000 + int(hashlib.sha256(cle.encode()).hexdigest(), 16) % 5000
        while n in self.numeros:
            n = 5000 + (n - 5000 + 1) % 5000
        self.numeros.add(n)
        return f"06 39 98 {n // 100:02d} {n % 100:02d}"

    def fixe(self) -> str:
        n = self.fixes.pop()
        return f"02 61 91 {n // 100:02d} {n % 100:02d}"

    def courriel(self, prenom: str, nom: str) -> str:
        """L'adresse d'une personne ne dépend que de son nom : elle ne bouge pas d'une génération à l'autre."""
        identifiant = f"{slug(prenom)}.{slug(nom)}"
        rang = int(hashlib.sha256(identifiant.encode()).hexdigest(), 16) % len(FOURNISSEURS_COURRIEL)
        return f"{identifiant}@{FOURNISSEURS_COURRIEL[rang]}"

    def adresse(self, commune: str) -> str:
        return f"{self.alea.randrange(1, 140)} {self.alea.choice(RUES)}, {CP} {NOM_COMMUNE[commune]} (FICTIF)"


# --- le monde --------------------------------------------------------------------------------


@dataclass
class Proprietaire:
    code: str
    nom: str
    secteur: str
    courriel: str
    telephone: str
    adresse: str
    iban: str
    envoi: str
    lots: list[str] = field(default_factory=lambda: [])


@dataclass
class Lot:
    code: str
    type: str
    surface: int
    etage: int | None
    proprietaire: str
    locataire: str | None
    entree: date | None
    loyer: int
    provision: int
    depot: int
    revision: date | None
    trimestre: str | None
    dpe: str
    sortie: date | None = None
    ancien_locataire: str | None = None


@dataclass
class Immeuble:
    code: str
    commune: str
    secteur: str
    nature: str
    adresse: str
    distance: int
    annee: int
    gardien: bool
    lots: list[Lot] = field(default_factory=lambda: [])
    copropriete: str | None = None


@dataclass
class Coproprietaire:
    lot: int
    type: str
    etage: int
    tantiemes: int
    tantiemes_ascenseur: int | None
    nom: str
    courriel: str
    notification: str
    adresse: str
    lot_gerance: str | None


@dataclass
class Copropriete:
    code: str
    nom: str
    commune: str
    adresse: str
    annee: int
    ascenseur: bool
    gestionnaire: str
    exercice_fin: tuple[int, int]
    budget: int
    seuil_concurrence: int
    seuil_conseil: int
    assureur: str
    coproprietaires: list[Coproprietaire] = field(default_factory=lambda: [])
    immeuble: str | None = None
    assemblee: date | None = None


@dataclass
class Monde:
    immeubles: list[Immeuble] = field(default_factory=lambda: [])
    proprietaires: dict[str, Proprietaire] = field(default_factory=lambda: {})
    coproprietes: list[Copropriete] = field(default_factory=lambda: [])
    artisans: list[tuple[str, str, str]] = field(default_factory=lambda: [])  # nom, identifiant, activité


TYPES_COLLECTIF = [("T1", 28, 34), ("T2", 38, 50), ("T3", 55, 70), ("T4", 72, 88), ("T5", 90, 110)]
POIDS_COLLECTIF = [15, 35, 30, 15, 5]
TYPES_MAISON = [("maison T3", 70, 85), ("maison T4", 85, 105), ("maison T5", 100, 125)]
DPE = ["A", "B", "C", "D", "E", "F", "G"]
POIDS_DPE = [2, 5, 20, 35, 25, 10, 3]


def trimestre_a_l_entree(entree: date) -> str:
    """Le dernier IRL paru à la signature : T4 de mi-janvier à mi-avril, T1 jusqu'à mi-juillet, etc."""
    return {2: "T4", 3: "T4", 4: "T4", 5: "T1", 6: "T1", 7: "T1", 8: "T2", 9: "T2", 10: "T2"}.get(entree.month, "T3")


def nouveau_proprietaire(monde: Monde, annuaire: Annuaire, alea: random.Random, secteur: str) -> Proprietaire:
    code = f"p-{len(monde.proprietaires) + 1:04d}"
    commune = alea.choice([c for c, _, s, _, _ in COMMUNES if s == secteur] + ["montclavel"])
    if alea.random() < 0.08:
        raison = f"SCI {alea.choice(RESIDENCES)}"
        while any(p.nom == raison for p in monde.proprietaires.values()):
            raison = f"SCI {alea.choice(RESIDENCES)} {alea.choice(['Patrimoine', 'Famille', 'Invest'])}"
        nom, courriel = raison, f"gestion@{slug(raison)}.example"
    else:
        civilite, prenom, famille = annuaire.personne()
        nom, courriel = f"{civilite} {prenom} {famille}", annuaire.courriel(prenom, famille)
    proprietaire = Proprietaire(
        code=code,
        nom=nom,
        secteur=secteur,
        courriel=courriel,
        telephone=annuaire.mobile(),
        adresse=annuaire.adresse(commune),
        iban=iban(alea),
        envoi="courriel" if alea.random() < 0.8 else "courrier",
    )
    monde.proprietaires[code] = proprietaire
    return proprietaire


def proprietaire_pour(monde: Monde, annuaire: Annuaire, alea: random.Random, secteur: str) -> Proprietaire:
    """Environ 700 propriétaires pour 1 200 lots : un sur trois en possède plusieurs, dans son secteur."""
    candidats = [p for p in monde.proprietaires.values() if p.secteur == secteur and 0 < len(p.lots) < 5]
    if candidats and alea.random() < 0.42:
        return alea.choice(candidats[-60:])
    return nouveau_proprietaire(monde, annuaire, alea, secteur)


def lot_aleatoire(monde: Monde, annuaire: Annuaire, alea: random.Random, immeuble: Immeuble, numero: int) -> Lot:
    code = f"{immeuble.code}-{numero:02d}"
    fixe = LOTS_FIXES.get(code, {})
    if immeuble.nature == "immeuble collectif":
        nom_type, smin, smax = alea.choices(TYPES_COLLECTIF, weights=POIDS_COLLECTIF)[0]
        etage: int | None = (numero - 1) // 4
    else:
        nom_type, smin, smax = alea.choice(TYPES_MAISON)
        etage = None
    surface = alea.randrange(smin, smax + 1)
    nom_type, surface = cast(str, fixe.get("type", nom_type)), cast(int, fixe.get("surface", surface))
    prix = alea.uniform(9.2, 11.0) if immeuble.secteur == "centre" else alea.uniform(7.8, 9.6)
    loyer = cast(int, fixe.get("loyer", round(surface * prix) * 100))
    sortie = cast("date | None", fixe.get("sortie"))
    tirage = alea.random()  # toujours tiré : fixer un lot ne déplace pas le tirage des suivants
    vacant = sortie is not None or (not fixe and tirage < 0.03)
    entree = cast(date, fixe.get("entree", AUJOURD_HUI - timedelta(days=alea.randrange(30, 14 * 365))))
    annees = max(0, (AUJOURD_HUI - entree).days // 365)
    depot = cast(int, fixe.get("depot", round(loyer / (1 + 0.025 * annees) / 100) * 100))
    proprietaire = proprietaire_pour(monde, annuaire, alea, immeuble.secteur)
    proprietaire.lots.append(code)
    occupant = None
    if not vacant or sortie is not None:
        civilite, prenom, nom = annuaire.personne()
        occupant = f"{civilite} {prenom} {nom}"
    return Lot(
        code=code,
        type=nom_type,
        surface=surface,
        etage=etage,
        proprietaire=proprietaire.code,
        locataire=None if vacant else occupant,
        entree=entree if occupant else None,
        loyer=loyer,
        # Tirée ici, à sa place dans la suite des tirages, même quand la tâche la fixe.
        provision=cast(
            int, fixe.get("provision", (alea.randrange(30, 121) if etage is not None else alea.randrange(0, 21)) * 100)
        ),
        depot=depot,
        revision=None if vacant else entree,
        trimestre=None if vacant else cast(str, fixe.get("trimestre", trimestre_a_l_entree(entree))),
        dpe=cast(str, fixe.get("dpe", alea.choices(DPE, weights=POIDS_DPE)[0])),
        sortie=sortie,
        ancien_locataire=occupant if sortie is not None else None,
    )


def gerance(monde: Monde, annuaire: Annuaire, alea: random.Random) -> None:
    """Les immeubles en gestion, d'abord ceux que fixent les tâches, puis le reste par commune."""
    compteurs = {"nord": 0, "centre": 0, "sud": 0}
    restants = {cle: lots for cle, _, _, _, lots in COMMUNES}
    adresses: set[str] = set()

    def immeuble(commune: str, nature: str, taille: int, distance: int | None) -> None:
        secteur = next(s for c, _, s, _, _ in COMMUNES if c == commune)
        dmin, dmax = next(d for c, _, _, d, _ in COMMUNES if c == commune)
        compteurs[secteur] += 1
        code = f"{secteur[0]}{compteurs[secteur]:02d}"
        adresse = annuaire.adresse(commune)
        while adresse in adresses:
            adresse = annuaire.adresse(commune)
        adresses.add(adresse)
        nouveau = Immeuble(
            code=code,
            commune=commune,
            secteur=secteur,
            nature="immeuble collectif" if nature == "collectif" else "groupe de maisons",
            adresse=adresse,
            distance=distance if distance is not None else alea.randrange(dmin, dmax + 1),
            annee=alea.randrange(1955, 2019),
            gardien=nature == "collectif" and taille >= 20 and alea.random() < 0.5,
        )
        nouveau.gardien = GARDIENS_FIXES.get(code, nouveau.gardien)
        nouveau.lots = [lot_aleatoire(monde, annuaire, alea, nouveau, n) for n in range(1, taille + 1)]
        restants[commune] -= taille
        monde.immeubles.append(nouveau)

    for code, commune, nature, taille, distance in IMMEUBLES_FIXES:
        immeuble(commune, nature, taille, distance)
        assert monde.immeubles[-1].code == code, (code, monde.immeubles[-1].code)
    for commune, _, _, _, _ in COMMUNES:
        while restants[commune] > 0:
            collectif = alea.random() < (0.75 if commune == "montclavel" else 0.5)
            taille = alea.randrange(6, 31) if collectif else alea.randrange(3, 11)
            taille = min(taille, restants[commune])
            immeuble(commune, "collectif" if collectif and taille >= 4 else "maisons", taille, None)


def coproprietes(monde: Monde, annuaire: Annuaire, alea: random.Random) -> None:
    """45 copropriétés, dont une partie abrite des lots en gestion : un immeuble pour une copropriété."""
    communes = ["montclavel"] * 30 + ["vernillac"] * 8 + ["chantebrune"] * 7
    liables = [
        i
        for i in monde.immeubles
        if i.nature == "immeuble collectif" and i.commune in {"montclavel", "vernillac", "chantebrune"}
    ]
    liables = [i for i in liables if i.code not in {c for c, *_ in IMMEUBLES_FIXES}]
    alea.shuffle(liables)
    noms = list(RESIDENCES)
    alea.shuffle(noms)
    # cp22 : dvh04, une assemblée à préparer pour un exercice clos le 31 mars.
    fins = {5: (3, 31), 22: (3, 31), 29: (3, 31), 41: (3, 31), 12: (6, 30), 36: (6, 30), 20: (9, 30)}
    for numero in range(1, 46):
        commune = communes[numero - 1]
        lie = next((i for i in liables if i.commune == commune and i.copropriete is None), None)
        if lie is not None and alea.random() < 0.45:
            lie.copropriete = f"cp{numero:02d}"
        else:
            lie = None
        nombre = min(60, max(8, len(lie.lots) + alea.randrange(2, 21))) if lie else alea.randrange(8, 61)
        annee = lie.annee if lie else alea.randrange(1958, 2014)
        copro = Copropriete(
            code=f"cp{numero:02d}",
            nom=f"Résidence {noms[numero - 1]}",
            commune=commune,
            adresse=lie.adresse if lie else annuaire.adresse(commune),
            annee=annee,
            ascenseur=nombre >= 15,
            gestionnaire="yohan.delmas" if numero <= 23 else "gaelle.fournel",
            exercice_fin=fins.get(numero, (12, 31)),
            budget=nombre * alea.randrange(9, 19) * 10000,
            seuil_concurrence=alea.randrange(3, 9) * 100000,
            seuil_conseil=alea.randrange(1, 3) * 50000,
            assureur=alea.choice(ASSUREURS),
            immeuble=lie.code if lie else None,
        )
        lots_geres = lie.lots if lie else []
        surfaces = [alea.randrange(28, 111) for _ in range(nombre)]
        for rang, lot in enumerate(lots_geres):
            surfaces[rang] = lot.surface
        repartition = tantiemes(surfaces, 10000)
        etages = [(n // 4) for n in range(nombre)]
        hauts = [n for n in range(nombre) if etages[n] >= 1]
        ascenseur = tantiemes([surfaces[n] * etages[n] for n in hauts], 10000) if copro.ascenseur else []
        for n in range(nombre):
            if n < len(lots_geres):
                gere = lots_geres[n]
                proprietaire = monde.proprietaires[gere.proprietaire]
                nom, courriel, adresse = proprietaire.nom, proprietaire.courriel, proprietaire.adresse
                lot_gerance: str | None = gere.code
            else:
                civilite, prenom, famille = annuaire.personne()
                nom, courriel = f"{civilite} {prenom} {famille}", annuaire.courriel(prenom, famille)
                adresse, lot_gerance = annuaire.adresse(commune), None
            copro.coproprietaires.append(
                Coproprietaire(
                    lot=n + 1,
                    type="appartement",
                    etage=etages[n],
                    tantiemes=repartition[n],
                    tantiemes_ascenseur=ascenseur[hauts.index(n)] if copro.ascenseur and n in hauts else None,
                    nom=nom,
                    courriel=courriel,
                    notification="voie postale" if alea.random() < 0.15 else "électronique",
                    adresse=adresse,
                    lot_gerance=lot_gerance,
                )
            )
        fixer_copropriete(copro)
        monde.coproprietes.append(copro)
    for copro in monde.coproprietes:
        copro.assemblee = date_assemblee(copro, alea)
        if copro.code in ASSEMBLEES_A_PREPARER:
            copro.assemblee = None  # tirée quand même : les copropriétés suivantes ne bougent pas


def fixer_tantiemes(valeurs: list[int], rang: int, cible: int) -> list[int]:
    """Donne cible au rang voulu et répartit le reste des 10 000 sur les autres, en proportion de
    leurs parts : la somme tombe toujours juste."""
    autres = [v for r, v in enumerate(valeurs) if r != rang]
    reparties = tantiemes(autres, 10000 - cible)
    return [*reparties[:rang], cible, *reparties[rang:]]


def fixer_copropriete(copro: Copropriete) -> None:
    """Applique COPROPRIETES_FIXES, sans tirage : les autres copropriétés ne bougent pas."""
    fixe = COPROPRIETES_FIXES.get(copro.code)
    if fixe is None:
        return
    copro.budget = cast(int, fixe["budget"])
    rang = cast(int, fixe["lot"]) - 1
    generaux = fixer_tantiemes([c.tantiemes for c in copro.coproprietaires], rang, cast(int, fixe["tantiemes"]))
    for c, valeur in zip(copro.coproprietaires, generaux, strict=True):
        c.tantiemes = valeur
    hauts = [c for c in copro.coproprietaires if c.tantiemes_ascenseur is not None]
    position = hauts.index(copro.coproprietaires[rang])
    ascenseur = fixer_tantiemes(
        [cast(int, c.tantiemes_ascenseur) for c in hauts], position, cast(int, fixe["tantiemes_ascenseur"])
    )
    for c, valeur in zip(hauts, ascenseur, strict=True):
        c.tantiemes_ascenseur = valeur


def tantiemes(poids: list[int], total: int) -> list[int]:
    """Répartit total proportionnellement aux poids, au plus fort reste : la somme tombe juste."""
    somme = sum(poids)
    bruts = [p * total / somme for p in poids]
    parts = [int(b) for b in bruts]
    for rang in sorted(range(len(poids)), key=lambda r: (parts[r] - bruts[r], r))[: total - sum(parts)]:
        parts[rang] += 1
    return parts


def date_assemblee(copro: Copropriete, alea: random.Random) -> date:
    """La dernière assemblée tenue, ou la prochaine si celle de l'exercice n'a pas encore eu lieu."""
    mois, jour = copro.exercice_fin
    if (mois, jour) == (12, 31):
        debut, fin = date(2026, 3, 9), date(2026, 6, 26)
    elif (mois, jour) == (3, 31):
        debut, fin = date(2025, 6, 2), date(2025, 9, 26)
    elif (mois, jour) == (6, 30):
        debut, fin = date(2025, 9, 15), date(2025, 12, 12)
    else:
        debut, fin = date(2025, 12, 1), date(2026, 3, 20)
    jour_ = debut + timedelta(days=alea.randrange((fin - debut).days + 1))
    while jour_.weekday() >= 5:
        jour_ += timedelta(days=1)
    return jour_


def artisans(monde: Monde, etat: Etat, annuaire: Annuaire, alea: random.Random) -> None:
    for nom, activite in ARTISANS:
        identifiant = slug(nom)
        compte = iban(alea)
        base = f"dossiers/artisans/{identifiant}"
        etat.ecrire(
            f"{base}/fiche_fournisseur.yaml",
            en_yaml(
                "Fiche d'un artisan ou prestataire de Domivelle. Données FICTIVES.",
                {
                    "nom": nom,
                    "activite": activite,
                    "adresse": f"{alea.randrange(2, 60)} zone artisanale des Tanneries, {CP} Montclavel-sur-Cher (FICTIF)",
                    "telephone": annuaire.fixe(),
                    "courriel_facturation": f"facturation@{identifiant}.example",
                    "iban": f"{compte} (FICTIF)",
                    "conditions": "paiement à 30 jours",
                },
            ),
        )
        etat.ecrire(f"{base}/rib_{identifiant}.pdf", rib(nom, compte))
        monde.artisans.append((nom, identifiant, activite))
        if activite in ACTIVITES_DE_LA_GERANCE:
            factures_rangees(etat, monde, alea, nom, identifiant, activite)


# Métiers qui travaillent dans les lots en gestion : leurs factures se rangent chez l'artisan (manuel,
# section 18). Les autres travaillent pour les copropriétés.
ACTIVITES_DE_LA_GERANCE = {
    "plomberie",
    "électricité",
    "serrurerie",
    "chauffage et eau chaude",
    "menuiserie et volets",
    "peinture",
    "vitrerie",
    "désinsectisation",
    "diagnostics immobiliers",
}


def factures_rangees(etat: Etat, monde: Monde, alea: random.Random, nom: str, identifiant: str, activite: str) -> None:
    """Une à trois factures d'avril et de mai, déjà rangées sous <numero>_<lot>.pdf."""
    lots = [lot for immeuble in monde.immeubles for lot in immeuble.lots]
    for _ in range(alea.randrange(1, 4)):
        lot = alea.choice(lots)
        emission = date(2026, alea.choice([4, 5]), alea.randrange(1, 29))
        numero = f"2026-{alea.randrange(100, 1000):04d}"
        ttc = alea.randrange(80, 300) * 100
        etat.ecrire(
            f"dossiers/artisans/{identifiant}/factures/{numero}_{lot.code}.pdf",
            pdf(
                [
                    f"FACTURE n° {numero}",
                    nom,
                    f"Date : {jour_fr(emission)} ; échéance : {jour_fr(emission + timedelta(days=30))}",
                    f"Lot {lot.code}, {activite}",
                    f"Montant TTC : {euros(ttc)}",
                ]
            ),
        )


# --- écriture des dossiers -------------------------------------------------------------------


def registre(etat: Etat, monde: Monde) -> None:
    for immeuble in monde.immeubles:
        lots: list[dict[str, Any]] = []
        for lot in immeuble.lots:
            ligne: dict[str, Any] = {"lot": lot.code, "type": lot.type, "surface_m2": lot.surface}
            if lot.etage is not None:
                ligne["etage"] = lot.etage
            ligne["proprietaire"] = lot.proprietaire
            ligne["locataire"] = lot.locataire if lot.locataire else "vacant"
            if lot.locataire and lot.entree:
                ligne["entree"] = lot.entree.isoformat()
            ligne["loyer_hors_charges"] = euros(lot.loyer)
            ligne["provision_sur_charges"] = euros(lot.provision)
            if lot.locataire:
                ligne["depot_de_garantie"] = euros(lot.depot)
                if lot.revision:
                    ligne["revision"] = f"chaque {jour_fr(lot.revision).rsplit(' ', 1)[0]}"
                ligne["trimestre_irl"] = lot.trimestre
            ligne["dpe"] = lot.dpe
            lots.append(ligne)
        etat.ecrire(
            f"dossiers/gerance/{immeuble.code}/registre.yaml",
            en_yaml(
                f"Registre des lots en gestion, {immeuble.code}. Données FICTIVES.",
                {
                    "immeuble": immeuble.code,
                    "nature": immeuble.nature,
                    "adresse": immeuble.adresse,
                    "secteur": immeuble.secteur,
                    "gestionnaire": GESTIONNAIRES[immeuble.secteur],
                    "distance_agence_km": immeuble.distance,
                    "annee_construction": immeuble.annee,
                    "gardien": immeuble.gardien,
                    "copropriete_du_syndic": immeuble.copropriete,
                    "lots": lots,
                },
            ),
        )


def documents_des_lots(etat: Etat, monde: Monde, annuaire: Annuaire, alea: random.Random) -> None:
    """Le dossier complet des lots que touchent les tâches, de leurs voisins et d'un échantillon."""
    choisis: list[Lot] = []
    for immeuble in monde.immeubles:
        if immeuble.code in {c for c, *_ in IMMEUBLES_FIXES}:
            choisis += immeuble.lots
        elif alea.random() < 0.12:
            choisis += alea.sample(immeuble.lots, min(2, len(immeuble.lots)))
    # Les lots fixés ou cités par une tâche ont aussi leur dossier, ajoutés à la fin : le tirage des
    # autres ne bouge pas.
    deja = {lot.code for lot in choisis}
    for immeuble in monde.immeubles:
        choisis += [lot for lot in immeuble.lots if lot.code in {*LOTS_FIXES, *LOTS_DES_TACHES} - deja]
    par_code = {i.code: i for i in monde.immeubles}
    for lot in choisis:
        immeuble = par_code[lot.code.split("-")[0]]
        base = f"dossiers/gerance/{immeuble.code}/{lot.code}"
        occupant = lot.locataire or lot.ancien_locataire
        fiche: dict[str, Any] = {
            "lot": lot.code,
            "adresse": immeuble.adresse,
            "type": lot.type,
            "surface_m2": lot.surface,
        }
        if occupant:
            civilite, prenom, nom = occupant.split(" ", 2)
            del civilite
            fiche["locataire"] = {
                "nom": occupant,
                "courriel": annuaire.courriel(prenom, nom),
                "telephone": annuaire.mobile_de(f"{lot.code}:{occupant}"),
                "entree": lot.entree.isoformat() if lot.entree else None,
            }
            if lot.sortie:
                fiche["locataire"]["cles_rendues"] = lot.sortie.isoformat()
            fiche["bail"] = {
                "signature": lot.entree.isoformat() if lot.entree else None,
                "duree": "trois ans, renouvelable",
                "loyer_hors_charges": euros(lot.loyer),
                "depot_de_garantie": euros(lot.depot),
                "revision": "chaque année à la date anniversaire du bail, selon l'IRL",
                "trimestre_irl": lot.trimestre or trimestre_a_l_entree(lot.entree or AUJOURD_HUI),
            }
        fiche["dpe"] = {"classe": lot.dpe, "etabli_le": "2022-05-12"}
        fiche["documents"] = ["bail.pdf", "etat_des_lieux_entree.md", "dpe.pdf"] if occupant else ["dpe.pdf"]
        etat.ecrire(f"{base}/fiche_lot.yaml", en_yaml(f"Fiche du lot {lot.code}. Données FICTIVES.", fiche))
        etat.ecrire(
            f"{base}/dpe.pdf", pdf([f"DIAGNOSTIC DE PERFORMANCE ÉNERGÉTIQUE, lot {lot.code}", f"Classe {lot.dpe}"])
        )
        if occupant and lot.entree:
            etat.ecrire(
                f"{base}/bail.pdf",
                pdf(
                    [
                        "CONTRAT DE LOCATION, LOGEMENT VIDE",
                        f"Lot {lot.code}, {immeuble.adresse}",
                        f"Locataire : {occupant}",
                        f"Prise d'effet : {jour_fr(lot.entree)}",
                        f"Loyer mensuel hors charges : {euros(lot.loyer)}",
                    ]
                ),
            )
            etat.ecrire(f"{base}/etat_des_lieux_entree.md", etat_des_lieux(lot, occupant, lot.entree, alea))


PIECES = ["Entrée", "Séjour", "Cuisine", "Chambre", "Salle d'eau", "WC"]


def etat_des_lieux(lot: Lot, occupant: str, jour: date, alea: random.Random) -> str:
    lignes = [
        f"# État des lieux d'entrée, lot {lot.code} (FICTIF)",
        "",
        f"Établi le {jour_fr(jour)} entre Domivelle, mandataire du propriétaire, et {occupant}, contradictoirement.",
        "",
        "| Pièce | Sols | Murs et plafonds | Menuiseries | Équipements |",
        "|---|---|---|---|---|",
    ]
    etats = ["neuf", "bon état", "bon état", "état d'usage"]
    for piece in PIECES:
        lignes.append(
            f"| {piece} | {alea.choice(etats)} | {alea.choice(etats)} | {alea.choice(etats)} | {alea.choice(etats)} |"
        )
    lignes += ["", "Compteurs relevés, clés remises : trois clés de l'entrée, un badge.", "", MENTION, ""]
    return "\n".join(lignes)


def proprietaires(etat: Etat, monde: Monde, alea: random.Random) -> None:
    for secteur in ("nord", "centre", "sud"):
        lignes = [[p.code, p.nom, " ".join(p.lots)] for p in monde.proprietaires.values() if p.secteur == secteur]
        etat.ecrire(f"dossiers/proprietaires/liste_{secteur}.csv", en_csv(["code", "nom", "lots"], lignes))
    codes = list(monde.proprietaires)
    fixes = {monde_lot_proprietaire(monde, code) for code in [*LOTS_FIXES, *LOTS_DES_TACHES]}
    echantillon = sorted(fixes | set(alea.sample(codes, 60)))
    for code in echantillon:
        p = monde.proprietaires[code]
        etat.ecrire(
            f"dossiers/proprietaires/{code}/fiche_proprietaire.yaml",
            en_yaml(
                f"Fiche du propriétaire {code}, mandant de Domivelle. Données FICTIVES.",
                {
                    "code": code,
                    "nom": p.nom,
                    "adresse": p.adresse,
                    "courriel": p.courriel,
                    "telephone": p.telephone,
                    "iban": f"{p.iban} (FICTIF)",
                    "comptes_rendus": f"par {p.envoi}",
                    "lots": p.lots,
                    "mandat_de_gestion": "en cours, honoraires de gestion selon le mandat",
                },
            ),
        )
        etat.ecrire(f"dossiers/proprietaires/{code}/rib_{code}.pdf", rib(p.nom, p.iban))


def monde_lot_proprietaire(monde: Monde, code_lot: str) -> str:
    for immeuble in monde.immeubles:
        for lot in immeuble.lots:
            if lot.code == code_lot:
                return lot.proprietaire
    raise KeyError(code_lot)


def ecrire_coproprietes(etat: Etat, monde: Monde, alea: random.Random) -> None:
    contrats_par_activite: dict[str, list[tuple[str, str, str]]] = {}
    for artisan in monde.artisans:
        contrats_par_activite.setdefault(artisan[2], []).append(artisan)
    noms_gestionnaires = {"yohan.delmas": "Yohan Delmas", "gaelle.fournel": "Gaëlle Fournel"}
    for copro in monde.coproprietes:
        base = f"dossiers/coproprietes/{copro.code}"
        mois, jour = copro.exercice_fin
        conseil = alea.sample(copro.coproprietaires, 3)
        etat.ecrire(
            f"{base}/fiche_copropriete.yaml",
            en_yaml(
                f"Fiche de la copropriété {copro.code}. Données FICTIVES.",
                {
                    "copropriete": copro.code,
                    "nom": copro.nom,
                    "adresse": copro.adresse,
                    "lots_principaux": len(copro.coproprietaires),
                    "annee_construction": copro.annee,
                    "ascenseur": copro.ascenseur,
                    "exercice": f"du lendemain du {jour} {MOIS[mois - 1]} au {jour} {MOIS[mois - 1]}",
                    "gestionnaire": noms_gestionnaires[copro.gestionnaire],
                    "conseil_syndical": {
                        "president": conseil[0].nom,
                        "membres": [conseil[1].nom, conseil[2].nom],
                    },
                    "seuil_mise_en_concurrence": euros(copro.seuil_concurrence),
                    "seuil_consultation_du_conseil_syndical": euros(copro.seuil_conseil),
                    "assureur_de_l_immeuble": copro.assureur,
                    "declaration_des_sinistres": SINISTRES[copro.assureur],
                    "immeuble_en_gestion_locative": copro.immeuble,
                    "fonds_de_travaux": "5 % du budget prévisionnel, aux tantièmes généraux, appelé avec chaque provision"
                    if copro.annee <= 2016
                    else "aucun, immeuble de moins de dix ans",
                },
            ),
        )
        colonnes = ["lot", "etage", "tantiemes_generaux"]
        if copro.ascenseur:
            colonnes.append("tantiemes_ascenseur")
        colonnes += ["coproprietaire", "courriel", "notification", "adresse_postale"]
        lignes: list[list[str]] = []
        for c in copro.coproprietaires:
            ligne = [str(c.lot), str(c.etage), str(c.tantiemes)]
            if copro.ascenseur:
                ligne.append(str(c.tantiemes_ascenseur or 0))
            ligne += [c.nom, c.courriel, c.notification, c.adresse]
            lignes.append(ligne)
        etat.ecrire(f"{base}/coproprietaires.csv", en_csv(colonnes, lignes))
        etat.ecrire(f"{base}/budget.yaml", budget(copro))
        prestataires: list[tuple[str, str, str]] = []
        for activite in ["nettoyage des parties communes", "espaces verts"] + (
            ["ascenseurs"] if copro.ascenseur else []
        ):
            choix = alea.choice(contrats_par_activite[activite])
            prestataires.append(choix)
            etat.ecrire(f"{base}/contrats/{choix[1]}.md", contrat(copro, choix, alea))
        if copro.assemblee and copro.assemblee < AUJOURD_HUI:
            etat.ecrire(f"{base}/proces_verbal_{copro.assemblee.isoformat()}.md", proces_verbal(copro, alea))


def budget(copro: Copropriete) -> str:
    postes = [
        ("nettoyage des parties communes", 22),
        ("espaces verts", 8),
        ("électricité des parties communes", 9),
        ("eau", 14),
        ("assurance de l'immeuble", 11),
        ("honoraires du syndic", 18),
        ("entretien et petites réparations", 10),
    ]
    fixe = COPROPRIETES_FIXES.get(copro.code, {})
    montants = tantiemes([p for _, p in postes], copro.budget // 100)
    if copro.ascenseur:
        part = cast(int, fixe.get("ascenseur", copro.budget * 8 // 100 // 100 * 100)) // 100
        montants = [*tantiemes([p for _, p in postes], copro.budget // 100 - part), part]
        postes.append(("ascenseur, contrat et électricité", 0))
    mois, jour = copro.exercice_fin
    exercice = {(12, 31): "2026", (3, 31): "2026-2027"}.get((mois, jour), "2025-2026")
    donnees: dict[str, Any] = {
        "copropriete": copro.code,
        "exercice": exercice,
        "total": euros(copro.budget),
        "postes": {nom: euros(m * 100) for (nom, _), m in zip(postes, montants, strict=True)},
    }
    if copro.ascenseur:
        donnees["repartition"] = {
            "charges générales, aux tantièmes généraux": euros((sum(montants) - montants[-1]) * 100),
            "ascenseur, aux tantièmes d'ascenseur": euros(montants[-1] * 100),
        }
    else:
        donnees["repartition"] = {"charges générales, aux tantièmes généraux": euros(copro.budget)}
    donnees["appel"] = "un quart du budget, exigible le premier jour de chaque trimestre"
    return en_yaml(
        f"Budget prévisionnel de l'exercice en cours, voté, copropriété {copro.code}. Données FICTIVES.", donnees
    )


def contrat(copro: Copropriete, artisan: tuple[str, str, str], alea: random.Random) -> str:
    nom, _, activite = artisan
    annuel = (len(copro.coproprietaires) * alea.randrange(40, 120)) * 100
    effet = date(alea.randrange(2019, 2025), alea.choice([1, 4, 7, 10]), 1)
    return "\n".join(
        [
            f"# Contrat d'entretien, {activite}, copropriété {copro.code} (FICTIF)",
            "",
            f"- Titulaire : {nom}",
            f"- Objet : {activite}, {copro.nom}",
            f"- Montant annuel : {euros(annuel)} TTC",
            f"- Prise d'effet : {jour_fr(effet)}, pour un an, renouvelable par tacite reconduction",
            "- Résiliation : par lettre recommandée, trois mois avant l'échéance annuelle",
            "",
            MENTION,
            "",
        ]
    )


def proces_verbal(copro: Copropriete, alea: random.Random) -> str:
    assert copro.assemblee is not None
    presents = [c for c in copro.coproprietaires if alea.random() < 0.75]
    while sum(c.tantiemes for c in presents) < 5500:
        presents = [c for c in copro.coproprietaires if alea.random() < 0.75]
    absents = [c for c in copro.coproprietaires if c not in presents]
    voix_presentes = sum(c.tantiemes for c in presents)
    resolutions = [
        ("Élection du président de séance", "24"),
        ("Approbation des comptes de l'exercice clos", "24"),
        ("Budget prévisionnel de l'exercice suivant", "24"),
        ("Montant à partir duquel la mise en concurrence est obligatoire : " + euros(copro.seuil_concurrence), "25"),
        (
            "Montant à partir duquel la consultation du conseil syndical est obligatoire : "
            + euros(copro.seuil_conseil),
            "25",
        ),
    ]
    lignes = [
        f"# Procès-verbal de l'assemblée générale du {jour_fr(copro.assemblee)} (FICTIF)",
        "",
        f"{copro.nom}, copropriété {copro.code}, {copro.adresse}.",
        "",
        f"Présents, représentés ou ayant voté par correspondance : {len(presents)} copropriétaires,"
        f" {voix_presentes} tantièmes sur 10 000.",
        "",
    ]
    opposants: set[str] = set()
    for rang, (intitule, article) in enumerate(resolutions, start=1):
        while True:
            contre = [c for c in presents if alea.random() < 0.1]
            abstention = [c for c in presents if c not in contre and alea.random() < 0.05]
            pour = [c for c in presents if c not in contre and c not in abstention]
            voix_pour, voix_contre = sum(c.tantiemes for c in pour), sum(c.tantiemes for c in contre)
            if voix_pour > voix_contre and (article == "24" or voix_pour * 3 >= 10000):
                break
        votes = f"Pour : {voix_pour} ; contre : {voix_contre} ; abstention : {sum(c.tantiemes for c in abstention)}."
        if article == "25" and voix_pour <= 5000:
            issue = (
                "Faute de la majorité de l'article 25, et le projet ayant recueilli au moins le tiers des voix de"
                " tous les copropriétaires, l'assemblée procède aussitôt à un second vote, à la majorité de"
                f" l'article 24 (article 25-1). {votes} Résolution adoptée au second vote."
            )
        else:
            issue = f"Résolution adoptée à la majorité de l'article {article}."
        opposants.update(c.nom for c in contre)
        lignes += [f"## Résolution {rang} : {intitule}", "", f"{votes} {issue}", ""]
    lignes += [
        "## Copropriétaires opposants",
        "",
        ", ".join(sorted(opposants)) or "aucun",
        "",
        "## Copropriétaires défaillants",
        "",
        ", ".join(sorted(c.nom for c in absents)) or "aucun",
        "",
        MENTION,
        "",
    ]
    return "\n".join(lignes)


def candidatures(etat: Etat, monde: Monde, annuaire: Annuaire, alea: random.Random) -> None:
    vacants = [lot for i in monde.immeubles for lot in i.lots if lot.locataire is None and lot.sortie is None]
    for lot in vacants[:3]:
        for _ in range(alea.randrange(2, 4)):
            civilite, prenom, nom = annuaire.personne()
            dossier = f"dossiers/candidatures/{lot.code}/{slug(prenom)}.{slug(nom)}"
            pieces = [
                ("piece_identite.pdf", "Carte nationale d'identité"),
                ("quittances_de_loyer.pdf", "Trois dernières quittances de loyer"),
                ("contrat_de_travail.pdf", "Contrat de travail"),
                ("bulletins_de_salaire.pdf", "Trois derniers bulletins de salaire"),
                ("avis_d_imposition_2025.pdf", "Avis d'imposition 2025 sur les revenus 2024"),
            ]
            for fichier, titre in pieces:
                etat.ecrire(f"{dossier}/{fichier}", pdf([titre, f"{civilite} {prenom} {nom}"]))
            etat.ecrire(
                f"{dossier}/liste_des_pieces.md",
                "\n".join(
                    [
                        f"# Candidature de {civilite} {prenom} {nom} pour le lot {lot.code} (FICTIF)",
                        "",
                        *(f"- {titre} : {fichier}" for fichier, titre in pieces),
                        "",
                        MENTION,
                        "",
                    ]
                ),
            )


def courrier(etat: Etat, monde: Monde, alea: random.Random) -> None:
    # Le code suit le manuel, section 1 : le lot pour un locataire, le propriétaire, la copropriété.
    proprietaires_ = sorted(monde.proprietaires)
    lots_occupes = sorted(lot.code for immeuble in monde.immeubles for lot in immeuble.lots if lot.locataire)
    coproprietes_ = sorted(copro.code for copro in monde.coproprietes)
    objets = [
        ("avis-taxe-fonciere", "Avis de taxe foncière transmis par le propriétaire", proprietaires_),
        ("attestation-assurance", "Attestation d'assurance habitation du locataire", lots_occupes),
        ("releve-eau", "Relevé de compteur d'eau d'un logement", lots_occupes),
        ("courrier-mairie", "Courrier de la mairie sur le ramassage des encombrants", coproprietes_),
        ("avis-echeance", "Avis d'échéance de l'assureur d'un immeuble", coproprietes_),
    ]
    for mois, jours in ((5, range(4, 30)), (6, range(1, 6))):
        for jour in sorted(alea.sample(list(jours), 6 if mois == 5 else 3)):
            reception = date(2026, mois, jour)
            if reception.weekday() >= 5 or reception in FERIES_ET_FERMETURES:
                continue
            nom_objet, titre, codes = alea.choice(objets)
            code = alea.choice(codes)
            etat.ecrire(
                f"dossiers/courrier/2026-{mois:02d}/{reception.isoformat()}_{nom_objet}_{code}.pdf",
                pdf([titre, f"Concerne : {code}", f"Reçu le {jour_fr(reception)}"]),
            )


def comptabilite(etat: Etat, monde: Monde) -> None:
    lots = {lot.code: lot for i in monde.immeubles for lot in i.lots}
    for secteur in ("nord", "centre", "sud"):
        lignes: list[list[str]] = []
        for p in monde.proprietaires.values():
            if p.secteur != secteur:
                continue
            loyers = sum(lots[c].loyer for c in p.lots if lots[c].locataire)
            honoraires = round(loyers * 0.084)
            lignes.append([p.code, p.nom, euros(loyers), euros(honoraires), euros(0), euros(loyers - honoraires)])
        etat.ecrire(
            f"dossiers/comptabilite/reversements/2026-05-10_{secteur}.csv",
            en_csv(
                ["proprietaire", "nom", "loyers_encaisses", "honoraires_ttc", "depenses_deduites", "reverse"], lignes
            ),
        )


def direction_et_rh(etat: Etat, organigramme: dict[str, Any], monde: Monde) -> None:
    distances = {i.code: i.distance for i in monde.immeubles}
    notes = {
        "2026-03": [
            ("maelle.carriere", "Maëlle Carrière", [(date(2026, 3, 12), "visite de chantier", "s01", 0)]),
        ],
        "2026-04": [
            (
                "quentin.mallet",
                "Quentin Mallet",
                [
                    (date(2026, 4, 9), "état des lieux d'entrée", "n02", 0),
                    (date(2026, 4, 17), "visite", "c01", 0),
                    (date(2026, 4, 28), "visite", "s02", 0),
                ],
            ),
            ("cedric.maillard", "Cédric Maillard", [(date(2026, 4, 21), "visite technique", "c01", 350)]),
        ],
    }
    for mois, liste in notes.items():
        for identifiant, nom, lignes_note in liste:
            total = 0
            corps = [
                f"# Note de frais de {nom}, {MOIS[int(mois[5:]) - 1]} {mois[:4]} (FICTIF)",
                "",
                "| Date | Objet | Immeuble | Kilomètres | Stationnement | Montant |",
                "|---|---|---|---|---|---|",
            ]
            for jour, objet, immeuble, stationnement in lignes_note:
                km = 2 * distances[immeuble]
                montant = km * 40 + stationnement
                total += montant
                corps.append(
                    f"| {jour_fr(jour)} | {objet} | {immeuble} | {km} | {euros(stationnement)} | {euros(montant)} |"
                )
            dernier = date(int(mois[:4]), int(mois[5:]) + 1, 1) - timedelta(days=1)
            corps += [
                "",
                f"Total : {euros(total)}. Visée par Véronique Tessier le {jour_fr(dernier)}, réglée avec la paie du mois.",
                "",
                MENTION,
                "",
            ]
            etat.ecrire(f"dossiers/direction/notes_de_frais/{mois}/{identifiant}.md", "\n".join(corps))
    etat.ecrire(
        "dossiers/direction/objectifs_2026.md",
        "\n".join(
            [
                "# Objectifs 2026 de Domivelle (FICTIF)",
                "",
                "- Garder le délai de réponse de deux jours ouvrés sur toutes les boîtes.",
                "- Tenir toutes les assemblées générales des exercices civils avant le 30 juin.",
                "- Relouer chaque lot vacant en moins de six semaines.",
                "",
                MENTION,
                "",
            ]
        ),
    )
    for personne in cast(list[dict[str, Any]], organigramme["personnes"]):
        etat.ecrire(
            f"dossiers/rh/{personne['id']}/contrat_de_travail.pdf",
            pdf(["CONTRAT DE TRAVAIL", f"{personne['nom']}, {personne['role']}"]),
        )
    for prenom_nom in ("lea.bertin", "hugo.vasseur"):
        etat.ecrire(
            f"dossiers/rh/candidatures/{prenom_nom}/cv.pdf",
            pdf(["CURRICULUM VITAE", prenom_nom.replace(".", " ").title()]),
        )


def liste_des_immeubles(etat: Etat, monde: Monde) -> None:
    """Pour l'accueil et tout le personnel : où est chaque immeuble, qui le gère, et les copropriétés du
    syndic, sans aucune donnée des personnes servies."""
    gestionnaires_copro = {"yohan.delmas": "Yohan Delmas", "gaelle.fournel": "Gaëlle Fournel"}
    lignes = [
        "# Les immeubles et les copropriétés de Domivelle (FICTIF)",
        "",
        "## Immeubles en gestion locative",
        "",
        "| Immeuble | Adresse | Secteur | Gestionnaire | Copropriété du syndic |",
        "|---|---|---|---|---|",
        *(
            f"| {i.code} | {i.adresse} | {i.secteur} | {GESTIONNAIRES[i.secteur]} | {i.copropriete or '-'} |"
            for i in monde.immeubles
        ),
        "",
        "## Copropriétés du syndic",
        "",
        "| Copropriété | Nom | Adresse | Gestionnaire |",
        "|---|---|---|---|",
        *(f"| {c.code} | {c.nom} | {c.adresse} | {gestionnaires_copro[c.gestionnaire]} |" for c in monde.coproprietes),
        "",
        MENTION,
        "",
    ]
    etat.ecrire("dossiers/commun/immeubles.md", "\n".join(lignes))


def commun(etat: Etat, organigramme: dict[str, Any]) -> None:
    for nom in ("manuel_procedures.md", "fiche_entreprise.md", "indices_irl.md", "pieces_exigibles.md"):
        etat.ecrire(f"dossiers/commun/{nom}", (ENTREPRISE / nom).read_bytes())
    personnes = cast(list[dict[str, Any]], organigramme["personnes"])
    noms = {p["id"]: p["nom"] for p in personnes}
    lignes = [
        "# Annuaire du personnel de Domivelle (FICTIF)",
        "",
        "Tiré de l'organigramme. Adresses et numéros fictifs.",
        "",
        "| Nom | Rôle | Courriel | Téléphone |",
        "|---|---|---|---|",
        *(f"| {p['nom']} | {p['role']} | {p['courriel']} | {p['telephone']} |" for p in personnes),
        "",
        "Boîtes partagées :",
        "",
        "| Boîte | Tenue par |",
        "|---|---|",
        *(
            f"| {adresse} | {noms[regle['gere_par']]} |"
            for adresse, regle in cast(dict[str, dict[str, str]], organigramme["boites_partagees"]).items()
        ),
        "",
        MENTION,
        "",
    ]
    etat.ecrire("dossiers/commun/annuaire.md", "\n".join(lignes))


# --- messagerie ------------------------------------------------------------------------------


class Messagerie:
    def __init__(self, etat: Etat) -> None:
        self.etat = etat

    def deposer(
        self,
        boite: str,
        identifiant: str,
        de: tuple[str | None, str],
        objet: str,
        quand: str,
        corps: str,
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
        chemin = f"messagerie/boites/{boite}/reception/{identifiant}.json"
        self.etat.ecrire(chemin, json.dumps(courriel, ensure_ascii=False, indent=2) + "\n")


# Le bruit d'une agence : ce que reçoit chaque famille de boîtes, de l'extérieur.
MODELES_GERANCE = [
    (
        "Question sur mon compte rendu de gérance",
        "Bonjour,\n\nPouvez-vous me confirmer le montant reversé le 10 mai ?\n\nMerci,\n{nom}",
    ),
    (
        "Attestation pour ma déclaration de revenus",
        "Bonjour,\n\nJe n'ai pas reçu l'attestation annuelle pour ma déclaration des revenus fonciers."
        " Pouvez-vous me la renvoyer ?\n\nCordialement,\n{nom}",
    ),
    ("Merci", "Bonjour,\n\nMerci pour votre réponse rapide.\n\n{nom}"),
    (
        "Provision sur charges",
        "Bonjour,\n\nJ'aimerais comprendre la hausse de la provision sur charges de mon lot.\n\nMerci d'avance,\n{nom}",
    ),
]
MODELES_COPROPRIETE = [
    (
        "Date de la prochaine assemblée",
        "Bonjour,\n\nPouvez-vous me dire quand se tiendra notre prochaine assemblée ?\n\n{nom}",
    ),
    ("Appel de fonds", "Bonjour,\n\nJ'ai bien reçu l'appel de fonds du trimestre ; le virement est parti.\n\n{nom}"),
    ("Éclairage de l'entrée", "Bonjour,\n\nL'éclairage du hall ne fonctionne plus depuis deux jours.\n\n{nom}"),
    ("Procès-verbal reçu", "Bonjour,\n\nMerci pour l'envoi du procès-verbal.\n\n{nom}"),
]
MODELES_ARTISANS = [
    ("Intervention terminée", "Bonjour,\n\nL'intervention prévue est terminée ; la facture suivra.\n\n{nom}"),
    (
        "Planning de la semaine",
        "Bonjour,\n\nVoici nos disponibilités de la semaine prochaine : lundi et jeudi matin.\n\n{nom}",
    ),
    (
        "Accès au local technique",
        "Bonjour,\n\nPouvez-vous nous confirmer le code d'accès au local technique ?\n\n{nom}",
    ),
]
# Courriels internes : l'auteur, l'objet, le texte. Personne ne s'écrit à soi-même.
MODELES_INTERNES = [
    (
        "veronique.tessier",
        "Point d'équipe jeudi",
        "Bonjour à tous,\n\nPoint d'équipe jeudi à 9 h, salle du rez-de-chaussée.\n\nVéronique",
    ),
    (
        "veronique.tessier",
        "Fermeture du pont de l'Ascension",
        "Bonjour,\n\nL'agence sera fermée le vendredi 15 mai, pont de l'Ascension.\n\nVéronique",
    ),
    (
        "nadege.lebrun",
        "Imprimante du premier étage",
        "Bonjour,\n\nL'imprimante du premier étage est réparée.\n\nNadège",
    ),
    (
        "nadege.lebrun",
        "Courrier du jour",
        "Bonjour,\n\nLe courrier du jour est numérisé et rangé dans courrier/.\n\nNadège",
    ),
]
FAMILLES = {
    "contact": "gerance",
    "comptabilite": "gerance",
    "elodie.chauvin": "gerance",
    "cedric.maillard": "gerance",
    "solene.audoin": "gerance",
    "quentin.mallet": "gerance",
    "pascale.renaud": "gerance",
    "veronique.tessier": "gerance",
    "nadege.lebrun": "gerance",
    "copropriete": "copropriete",
    "yohan.delmas": "copropriete",
    "gaelle.fournel": "copropriete",
    "melanie.sabatier": "copropriete",
    "thierry.ollivier": "copropriete",
    "maelle.carriere": "artisans",
}
FERIES_ET_FERMETURES = {date(2026, 5, 1), date(2026, 5, 8), date(2026, 5, 14), date(2026, 5, 15), date(2026, 5, 25)}


def messagerie(etat: Etat, monde: Monde, organigramme: dict[str, Any], alea: random.Random) -> None:
    """Des courriels déjà lus des trois dernières semaines, dans chaque boîte : le bruit d'une agence."""
    m = Messagerie(etat)
    personnes = cast(list[dict[str, Any]], organigramme["personnes"])
    collegues = {p["id"]: (p["nom"], p["courriel"]) for p in personnes}
    expediteurs: dict[str, list[tuple[str, str]]] = {
        "gerance": [(p.nom, p.courriel) for p in monde.proprietaires.values()],
        "copropriete": [(c.nom, c.courriel) for copro in monde.coproprietes for c in copro.coproprietaires],
        "artisans": [(nom, f"contact@{identifiant}.example") for nom, identifiant, _ in monde.artisans],
    }
    modeles = {"gerance": MODELES_GERANCE, "copropriete": MODELES_COPROPRIETE, "artisans": MODELES_ARTISANS}
    boites: list[tuple[str, str, str]] = [
        (f"{cle}@{DOMAINE}", cle, abrege)
        for cle, abrege in (
            ("contact", "ctc"),
            ("comptabilite", "cpt"),
            ("copropriete", "cop"),
            ("notifications", "ntf"),
        )
    ] + [(p["courriel"], p["id"], "".join(part[:2] for part in p["id"].split("."))) for p in personnes]
    for boite, cle, abrege in boites:
        nombre = alea.randrange(3, 7)
        jours = sorted(alea.sample(range(1, 22), nombre), reverse=True)
        for rang, recul in enumerate(jours, start=1):
            jour = AUJOURD_HUI - timedelta(days=recul)
            quand = horodatage(jour, alea.randrange(8, 18), alea.randrange(60))
            identifiant = f"m-{abrege}-b{rang:02d}"
            if cle == "notifications":
                copro = alea.choice(monde.coproprietes)
                m.deposer(
                    boite,
                    identifiant,
                    ("Service d'envoi électronique", "accuses@envoi-electronique.example"),
                    f"Accusé de dépôt : envoi pour {copro.nom}",
                    quand,
                    f"Votre envoi électronique pour la copropriété {copro.code} a été déposé et remis à ses"
                    f" destinataires.\n\n{MENTION}",
                )
                continue
            internes = [modele for modele in MODELES_INTERNES if modele[0] != cle]
            if alea.random() < 0.3:
                auteur, objet, corps = alea.choice(internes)
                m.deposer(boite, identifiant, collegues[auteur], objet, quand, corps)
            else:
                famille = FAMILLES[cle]
                nom, adresse = alea.choice(expediteurs[famille])
                objet, corps = alea.choice(modeles[famille])
                m.deposer(boite, identifiant, (nom, adresse), objet, quand, corps.format(nom=nom))


# --- assemblage ------------------------------------------------------------------------------


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
    gerance(monde, annuaire, alea_de("gerance"))
    coproprietes(monde, annuaire, alea_de("coproprietes"))
    artisans(monde, etat, annuaire, alea_de("artisans"))
    registre(etat, monde)
    documents_des_lots(etat, monde, annuaire, alea_de("documents"))
    proprietaires(etat, monde, alea_de("proprietaires"))
    ecrire_coproprietes(etat, monde, alea_de("ecriture_coproprietes"))
    candidatures(etat, monde, annuaire, alea_de("candidatures"))
    courrier(etat, monde, alea_de("courrier"))
    comptabilite(etat, monde)
    direction_et_rh(etat, organigramme, monde)
    commun(etat, organigramme)
    liste_des_immeubles(etat, monde)
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
    analyse = argparse.ArgumentParser(description=(__doc__ or "Génère l'état v1 de Domivelle.").splitlines()[0])
    analyse.add_argument("--verifier", action="store_true", help="contrôle sans rien écrire")
    args = analyse.parse_args()
    etat = construire()
    if args.verifier:
        messages = ecarts(etat)
        if messages:
            print(f"État v1 de Domivelle à régénérer ({len(messages)} écart(s)) :", file=sys.stderr)
            for message in messages[:20]:
                print(f"  {message}", file=sys.stderr)
            return 1
        print(f"État v1 de Domivelle à jour ({len(etat.fichiers)} fichiers).")
        return 0
    for partie in GENERES:
        shutil.rmtree(V1 / partie, ignore_errors=True)
    ecrire(etat, V1)
    print(f"État v1 de Domivelle généré : {len(etat.fichiers)} fichiers dans {V1.relative_to(RACINE)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
