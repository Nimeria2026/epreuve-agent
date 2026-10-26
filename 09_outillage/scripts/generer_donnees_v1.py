"""Génère les données initiales v1 de la PME fictive Calorelle : dossiers partagés et messagerie.

Rejouable à l'octet près : graine fixe, PDF sans date ni identifiant, JSON dans un ordre fixe.
Écrit 05_pme/societes/calorelle/v1/dossiers/ et 05_pme/societes/calorelle/v1/messagerie/ ; le
dossier entreprise/ reste écrit à la main. Le dossier partagé commun/ en reprend ce que tout
salarié peut lire : le manuel, recopié tel quel, et l'annuaire, tiré de l'organigramme sans les
droits. Les dossiers clients s'ouvrent par une liste des clients, comme dans une vraie PME.
Cahier des charges : inventaire_premiere_tranche.yaml.
Tout est fictif : adresses en .example, téléphones dans les plages réservées à la fiction, code
banque 99999, mention FICTIF dans chaque document.

Usage, depuis la racine du dépôt :
    uv run python 09_outillage/scripts/generer_donnees_v1.py              # régénère
    uv run python 09_outillage/scripts/generer_donnees_v1.py --verifier   # contrôle sans écrire

Codes de sortie : 0 à jour ou régénéré, 1 données périmées.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import random
import shutil
import sys
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import yaml

RACINE = Path(__file__).resolve().parents[2]
V1 = RACINE / "05_pme" / "societes" / "calorelle" / "v1"
GENERES = ("dossiers", "messagerie")
GRAINE = 20261102
PARIS = ZoneInfo("Europe/Paris")
MENTION = "Document FICTIF : Calorelle et ses partenaires n'existent pas."
VILLE = "45999 Valmont-sur-Loire (FICTIF)"
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


def date_paris(annee: int, mois: int, jour: int, heure: int = 9, minute: int = 0) -> str:
    """Date et heure de Paris au format RFC 3339, avec le décalage de la saison."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=PARIS).isoformat(timespec="seconds")


def jour_fr(iso: str) -> str:
    annee, mois, jour = (int(x) for x in iso.split("-"))
    return f"{jour} {MOIS[mois - 1]} {annee}"


def euros(montant: float) -> str:
    entier, decimales = f"{montant:,.2f}".split(".")
    return f"{entier.replace(',', ' ')},{decimales} €"


def sans_accent(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def slug(texte: str) -> str:
    propre = "".join(c if c.isalnum() else "-" for c in sans_accent(texte).lower())
    return "-".join(partie for partie in propre.split("-") if partie)


def yaml_simple(entete: str, valeurs: dict[str, Any]) -> str:
    """YAML lisible pour un humain : clés dans l'ordre donné, textes entre guillemets doubles."""

    def rendu(valeur: Any) -> str:
        if valeur is None:
            return "null"
        if isinstance(valeur, bool):
            return "true" if valeur else "false"
        if isinstance(valeur, int | float):
            return str(valeur)
        return json.dumps(str(valeur), ensure_ascii=False)

    lignes = [f"# {entete}"]
    for cle, valeur in valeurs.items():
        if isinstance(valeur, dict):
            sous = cast("dict[str, Any]", valeur)
            lignes.append(f"{cle}:")
            lignes += [f"  {k}: {rendu(v)}" for k, v in sous.items()]
        else:
            lignes.append(f"{cle}: {rendu(valeur)}")
    return "\n".join(lignes) + "\n"


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


# --- fournisseurs et factures ----------------------------------------------------------------

FOURNISSEURS_PRINCIPAUX = [
    ("Thermopièces Loire", "pièces détachées de chauffage", "facturation@thermopieces-loire.example", "02 61 91 20 11"),
    ("Distri-Clim Centre", "climatisation et pompes à chaleur", "compta@distri-clim-centre.example", "02 61 91 20 12"),
    ("Papeterie du Val", "fournitures de bureau", "factures@papeterie-du-val.example", "02 61 91 20 13"),
    ("Garage Bessière", "entretien des véhicules", "atelier@garage-bessiere.example", "02 61 91 20 14"),
]
ACTIVITES = [
    "Robinetterie",
    "Outillage",
    "Isolation",
    "Électricité",
    "Fumisterie",
    "Transports",
    "Nettoyage",
    "Informatique",
    "Visserie",
    "Échafaudages",
    "Gaines et conduits",
    "Équipements de sécurité",
]
LIEUX = [
    "des Grèves",
    "du Val-Mauvoir",
    "de Brenneval",
    "de la Courtine",
    "des Saulaies",
    "du Clos-Fargeau",
    "de Sablonnet",
    "des Hautes-Fresnes",
    "de Mirelande",
    "du Pré-Bouvreuil",
]
IBAN_THERMOPIECES = "FR76 9999 9001 2300 0011 8742 019"
IBAN_FRAUDE = "FR76 9999 9078 1100 4410 2297 563"


def iban(alea: random.Random) -> str:
    chiffres = "".join(str(alea.randrange(10)) for _ in range(18))
    return f"FR76 9999 9{chiffres[0:3]} {chiffres[3:7]} {chiffres[7:11]} {chiffres[11:15]} {chiffres[15:18]}"


def fournisseurs(etat: Etat, alea: random.Random) -> list[tuple[str, str]]:
    """Fiches et RIB des fournisseurs ; renvoie (nom, identifiant) de chacun."""
    liste = [(nom, slug(nom), activite, courriel, tel) for nom, activite, courriel, tel in FOURNISSEURS_PRINCIPAUX]
    noms = sorted({f"{a} {lieu}" for a in ACTIVITES for lieu in LIEUX})
    for rang, nom in enumerate(alea.sample(noms, 36), start=15):
        identifiant = slug(nom)
        liste.append(
            (nom, identifiant, nom.split(" ")[0].lower(), f"compta@{identifiant}.example", f"02 61 91 20 {rang:02d}")
        )
    for nom, identifiant, activite, courriel, telephone in liste:
        compte = IBAN_THERMOPIECES if identifiant == "thermopieces-loire" else iban(alea)
        base = f"dossiers/administration/fournisseurs/{identifiant}"
        etat.ecrire(
            f"{base}/fiche_fournisseur.yaml",
            yaml_simple(
                "Fiche fournisseur Calorelle. Données FICTIVES.",
                {
                    "nom": nom,
                    "activite": activite,
                    "adresse": f"{alea.randrange(2, 90)} zone d'activité {LIEUX[alea.randrange(len(LIEUX))]}, {VILLE}",
                    "telephone": telephone,
                    "courriel_facturation": courriel,
                    "iban": f"{compte} (FICTIF)",
                    "conditions": "paiement à 30 jours fin de mois",
                },
            ),
        )
        etat.ecrire(
            f"{base}/rib_{identifiant}.pdf",
            pdf(
                [
                    "RELEVÉ D'IDENTITÉ BANCAIRE",
                    f"Titulaire : {nom}",
                    f"IBAN : {compte}",
                    "BIC : FICTFRPPXXX",
                    "Banque : Banque Fictive du Val (code banque 99999)",
                ]
            ),
        )
    return [(nom, identifiant) for nom, identifiant, *_ in liste]


def facture(numero: str, fournisseur: str, date: str, lignes: list[tuple[str, float]], compte: str) -> bytes:
    hors_taxes = round(sum(m for _, m in lignes), 2)
    tva = round(hors_taxes * 0.2, 2)
    return pdf(
        [
            f"FACTURE {numero}",
            f"Fournisseur : {fournisseur}",
            f"Date de facture : {jour_fr(date)}",
            "Client : Calorelle SARL, 12 rue des Forges, " + VILLE,
            "",
        ]
        + [f"{libelle} : {euros(montant)} HT" for libelle, montant in lignes]
        + [
            "",
            f"Total hors taxes : {euros(hors_taxes)}",
            f"TVA 20 % : {euros(tva)}",
            f"Total TTC : {euros(hors_taxes + tva)}",
            f"Règlement par virement, IBAN {compte}",
        ]
    )


FACTURES_RANGEES = [
    (
        "2026-09",
        "Distri-Clim Centre",
        "distri-clim-centre",
        "DC-5521",
        "2026-09-18",
        [("Pompe à chaleur air-eau 8 kW", 1070.0)],
    ),
    (
        "2026-09",
        "Thermopièces Loire",
        "thermopieces-loire",
        "F-2026-1042",
        "2026-09-05",
        [("Brûleurs et joints", 312.5)],
    ),
    ("2026-09", "Papeterie du Val", "papeterie-du-val", "PV-26-0371", "2026-09-12", [("Ramettes et classeurs", 64.0)]),
    ("2026-09", "Garage Bessière", "garage-bessiere", "GB-0917", "2026-09-24", [("Vidange utilitaire", 188.0)]),
    ("2026-10", "Thermopièces Loire", "thermopieces-loire", "F-2026-1103", "2026-10-03", [("Thermostats", 245.0)]),
    ("2026-10", "Papeterie du Val", "papeterie-du-val", "PV-26-0388", "2026-10-06", [("Enveloppes", 38.0)]),
    ("2026-10", "Distri-Clim Centre", "distri-clim-centre", "DC-5602", "2026-10-09", [("Unité extérieure", 1490.0)]),
    (
        "2026-10",
        "Thermopièces Loire",
        "thermopieces-loire",
        "F-2026-1151",
        "2026-10-17",
        [("Vannes trois voies", 427.0)],
    ),
    ("2026-10", "Garage Bessière", "garage-bessiere", "GB-1021", "2026-10-21", [("Pneus utilitaire", 512.0)]),
    (
        "2026-10",
        "Robinetterie des Grèves",
        "robinetterie-des-greves",
        "RG-2026-088",
        "2026-10-23",
        [("Robinets", 96.0)],
    ),
]


def factures_rangees(etat: Etat, alea: random.Random) -> None:
    for mois, nom, identifiant, numero, date, lignes in FACTURES_RANGEES:
        chemin = f"dossiers/administration/factures_fournisseurs/{mois}/{identifiant}_{numero.lower()}.pdf"
        etat.ecrire(chemin, facture(numero, nom, date, lignes, iban(alea)))


# --- clients, devis, direction, RH -----------------------------------------------------------

PRENOMS = [
    "Anne",
    "Pierre",
    "Sophie",
    "Jean",
    "Nathalie",
    "Michel",
    "Isabelle",
    "Philippe",
    "Catherine",
    "Alain",
    "Valérie",
    "Patrick",
    "Sandrine",
    "Christophe",
    "Céline",
    "Laurent",
    "Aurélie",
    "Olivier",
    "Émilie",
    "Frédéric",
    "Julien",
    "Camille",
    "Hélène",
    "Gilles",
    "Agnès",
    "Yves",
    "Manon",
    "Denis",
    "Odile",
    "Rémi",
]
NOMS = [
    "Martin",
    "Bernard",
    "Dubois",
    "Moreau",
    "Laurent",
    "Simon",
    "Michel",
    "Lefebvre",
    "Leroux",
    "Girard",
    "Bonnet",
    "Dupont",
    "Lambert",
    "Fontaine",
    "Rousseau",
    "Vincent",
    "Muller",
    "Faure",
    "André",
    "Mercier",
    "Blanchard",
    "Guérin",
    "Boyer",
    "Garnier",
    "Chevalier",
    "François",
    "Legrand",
    "Gauthier",
    "Perrot",
    "Robin",
]
VOIES = [
    "rue des Lilas",
    "allée des Peupliers",
    "rue de la Loire",
    "chemin des Vignes",
    "rue du Moulin",
    "avenue des Tilleuls",
    "impasse des Saules",
    "rue Haute",
    "place du Marché",
    "rue des Écoles",
]
TECHNICIENS = ["Nicolas Blanc", "Romain Guérin", "Kevin Lambert", "Yanis Haddad", "Mathieu Picard"]
PRIX = {"Sérénité": "160 € TTC par an", "Sérénité Plus": "260 € TTC par an"}


def fiche_client(etat: Etat, client: dict[str, Any]) -> None:
    code = client["code"]
    base = f"dossiers/clients/{code}"
    contrat = client.get("contrat")
    valeurs = {k: client[k] for k in ("code", "nom", "type", "adresse", "courriel", "telephone", "charge_d_affaires")}
    if contrat is not None:
        valeurs["contrat"] = contrat
    etat.ecrire(f"{base}/fiche_client.yaml", yaml_simple("Fiche client Calorelle. Données FICTIVES.", valeurs))
    if contrat is not None:
        etat.ecrire(
            f"{base}/contrats/contrat_entretien_{code}.pdf",
            pdf(
                [
                    f"CONTRAT D'ENTRETIEN {contrat['formule'].upper()}",
                    f"Client : {client['nom']} ({code})",
                    f"Adresse : {client['adresse']}",
                    f"Formule : {contrat['formule']}, {PRIX[contrat['formule']]}",
                    f"Prise d'effet : {jour_fr(contrat['depuis'])}",
                    f"Visite annuelle dans le mois anniversaire : {contrat['mois_anniversaire']}",
                    "La date précise est fixée par le responsable planning, qui appelle le client.",
                ]
            ),
        )
    for date, technicien in client.get("interventions", []):
        etat.ecrire(
            f"{base}/interventions/{date}_entretien.pdf",
            pdf(
                [
                    "COMPTE RENDU D'ENTRETIEN ANNUEL",
                    f"Client : {client['nom']} ({code})",
                    f"Date de la visite : {jour_fr(date)}",
                    f"Technicien : {technicien}",
                    "Observations : appareil nettoyé, combustion contrôlée, aucune anomalie.",
                ]
            ),
        )


CLIENTS_DES_TACHES: list[dict[str, Any]] = [
    {
        "code": "c-0088",
        "nom": "Claire Fabre",
        "type": "particulier",
        "adresse": f"3 rue des Écoles, {VILLE}",
        "courriel": "claire.fabre@courriel.example",
        "telephone": "06 39 98 40 88",
        "charge_d_affaires": "julie.perrin",
        "contrat": {
            "formule": "Sérénité Plus",
            "depuis": "2024-03-04",
            "mois_anniversaire": "mars",
            "derniere_visite": "2026-03-12",
        },
        "interventions": [("2025-03-14", "Romain Guérin"), ("2026-03-12", "Kevin Lambert")],
    },
    {
        "code": "c-0142",
        "nom": "Bernard Lemoine",
        "type": "particulier",
        "adresse": f"8 allée des Peupliers, {VILLE}",
        "courriel": "b.lemoine@courriel.example",
        "telephone": "06 39 98 41 42",
        "charge_d_affaires": "julie.perrin",
        "contrat": {
            "formule": "Sérénité",
            "depuis": "2021-10-15",
            "mois_anniversaire": "octobre",
            "derniere_visite": "2026-10-08",
        },
    },
    {
        "code": "c-0217",
        "nom": "Bernadette Lemoine",
        "type": "particulier",
        "adresse": f"21 rue du Moulin, {VILLE}",
        "courriel": "bernadette.lemoine@courriel.example",
        "telephone": "06 39 98 42 17",
        "charge_d_affaires": "julie.perrin",
        "contrat": {
            "formule": "Sérénité Plus",
            "depuis": "2022-01-10",
            "mois_anniversaire": "janvier",
            "derniere_visite": "2026-01-19",
        },
    },
    {
        "code": "c-0311",
        "nom": "Claire Favre",
        "type": "particulier",
        "adresse": f"45 rue de la Loire, {VILLE}",
        "courriel": "claire.favre@courriel.example",
        "telephone": "06 39 98 43 11",
        "charge_d_affaires": "julie.perrin",
        "contrat": {
            "formule": "Sérénité",
            "depuis": "2023-09-01",
            "mois_anniversaire": "septembre",
            "derniere_visite": "2026-09-16",
        },
    },
    {
        "code": "c-0405",
        "nom": "Syndic de la Résidence des Tilleuls",
        "type": "syndic",
        "adresse": f"2 avenue des Tilleuls, {VILLE}",
        "courriel": "syndic@residence-des-tilleuls.example",
        "telephone": "02 61 91 34 05",
        "charge_d_affaires": "karim.benali",
        "contrat": {
            "formule": "Sérénité Plus",
            "depuis": "2020-11-02",
            "mois_anniversaire": "novembre",
            "derniere_visite": "2025-11-20",
        },
    },
]


def clients(etat: Etat, alea: random.Random) -> None:
    pris = {int(c["code"][2:]) for c in CLIENTS_DES_TACHES}
    numeros = sorted(alea.sample(sorted(set(range(1, 600)) - pris), 145))
    courriels = {c["courriel"] for c in CLIENTS_DES_TACHES}
    tous = list(CLIENTS_DES_TACHES)
    for rang, numero in enumerate(numeros):
        nature = alea.choices(["particulier", "entreprise", "syndic", "collectivite"], [70, 15, 10, 5])[0]
        prenom, nom = alea.choice(PRENOMS), alea.choice(NOMS)
        if nature == "particulier":
            libelle = f"{prenom} {nom}"
            courriel = f"{slug(prenom)}.{slug(nom)}@courriel.example"
            suffixe = 2
            while courriel in courriels:
                courriel, suffixe = f"{slug(prenom)}.{slug(nom)}{suffixe}@courriel.example", suffixe + 1
            telephone = f"06 39 98 {50 + rang // 100:02d} {rang % 100:02d}"
        else:
            libelle = {
                "entreprise": f"Établissements {nom}",
                "syndic": f"Syndic de la Résidence {alea.choice(LIEUX)}",
                "collectivite": f"Commune {alea.choice(LIEUX)}",
            }[nature]
            courriel = f"contact@{slug(libelle)}-{numero}.example"
            telephone = f"02 61 91 {35 + rang // 100:02d} {rang % 100:02d}"
        courriels.add(courriel)
        client: dict[str, Any] = {
            "code": f"c-{numero:04d}",
            "nom": libelle,
            "type": nature,
            "adresse": f"{alea.randrange(1, 120)} {alea.choice(VOIES)}, {VILLE}",
            "courriel": courriel,
            "telephone": telephone,
            "charge_d_affaires": "karim.benali" if nature in ("syndic", "collectivite") else "julie.perrin",
        }
        if alea.random() < 0.75:
            mois = alea.choice([1, 2, 3, 9, 10, 10, 11, 11, 12, 4, 5, 6])
            annee_visite = 2026 if mois <= 10 else 2025
            jour = alea.randrange(3, 28)
            client["contrat"] = {
                "formule": alea.choices(["Sérénité", "Sérénité Plus"], [60, 40])[0],
                "depuis": f"{alea.randrange(2018, 2026)}-{mois:02d}-{alea.randrange(1, 28):02d}",
                "mois_anniversaire": MOIS[mois - 1],
                "derniere_visite": f"{annee_visite}-{mois:02d}-{jour:02d}",
            }
            if alea.random() < 0.3:
                client["interventions"] = [(f"{annee_visite}-{mois:02d}-{jour:02d}", alea.choice(TECHNICIENS))]
        tous.append(client)
    for client in sorted(tous, key=lambda c: c["code"]):
        fiche_client(etat, client)
    liste_clients(etat, sorted(tous, key=lambda c: c["code"]))


CHARGES_D_AFFAIRES = {"julie.perrin": "Julie Perrin", "karim.benali": "Karim Benali"}


def liste_clients(etat: Etat, tous: list[dict[str, Any]]) -> None:
    """La liste des clients, telle qu'une PME la tient : de quoi retrouver une fiche sans les ouvrir toutes."""
    lignes = [
        "# Liste des clients de Calorelle (FICTIF)",
        "",
        "Une ligne par client ; le détail est dans clients/<code>/fiche_client.yaml.",
        "",
        "| Code | Nom | Type | Courriel | Chargé d'affaires |",
        "|---|---|---|---|---|",
        *(
            f"| {c['code']} | {c['nom']} | {c['type']} | {c['courriel']} | {CHARGES_D_AFFAIRES[c['charge_d_affaires']]} |"
            for c in tous
        ),
        "",
    ]
    etat.ecrire("dossiers/clients/liste_clients.md", "\n".join(lignes))


def devis(etat: Etat, alea: random.Random) -> None:
    objets = [
        ("Remplacement de chaudière gaz", 4200, 7800),
        ("Pompe à chaleur air-eau", 9800, 16500),
        ("Climatisation réversible", 2400, 6900),
        ("Rénovation de chaufferie collective", 18000, 42000),
    ]
    for annee, nombre in ((2025, 10), (2026, 12)):
        for rang in range(1, nombre + 1):
            objet, bas, haut = alea.choice(objets)
            montant = round(alea.randrange(bas, haut) / 10) * 10
            lignes = [f"DEVIS DV-{annee}-{rang:03d}", f"Objet : {objet}", f"Montant : {euros(montant)} TTC"]
            if montant > 10000:
                lignes.append("Validé par la gérante avant envoi (manuel, section 6).")
            etat.ecrire(f"dossiers/commercial/devis/{annee}/dv-{annee}-{rang:03d}.pdf", pdf(lignes))


def direction_et_rh(etat: Etat) -> None:
    etat.ecrire(
        "dossiers/direction/budget_previsionnel_2027.pdf",
        pdf(["BUDGET PRÉVISIONNEL 2027", "Chiffre d'affaires visé : 1 450 000 € (FICTIF)"]),
    )
    etat.ecrire(
        "dossiers/direction/proces-verbal_assemblee_2026.pdf",
        pdf(["PROCÈS-VERBAL DE L'ASSEMBLÉE DES ASSOCIÉS", "Séance du 12 juin 2026 (FICTIF)"]),
    )
    etat.ecrire(
        "dossiers/rh/registre_du_personnel.txt",
        "Registre du personnel de Calorelle. Document FICTIF, confidentiel.\n"
        "18 salariés : voir l'organigramme. Aucune donnée réelle.\n",
    )
    etat.ecrire(
        "dossiers/rh/conges_2026.txt",
        "Congés 2026 de Calorelle. Document FICTIF, confidentiel.\n"
        "Planning des congés d'hiver en cours de validation par la gérante.\n",
    )


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
        date: str,
        corps: str,
        *,
        a: list[str] | None = None,
        lu: bool = False,
        pieces: list[tuple[str, bytes]] | None = None,
        transfere_de: str | None = None,
    ) -> None:
        jointes: list[dict[str, Any]] = []
        for nom, contenu in pieces or []:
            fichier = f"pieces/{identifiant}/{nom}"
            taille = self.etat.ecrire(f"messagerie/{fichier}", contenu)
            jointes.append({"nom": nom, "fichier": fichier, "taille_octets": taille})
        courriel = {
            "identifiant": identifiant,
            "de": {"nom": de[0], "adresse": de[1]},
            "a": a or [boite],
            "cc": [],
            "objet": objet,
            "date": date,
            "corps": corps,
            "pieces_jointes": jointes,
            "lu": lu,
            "en_reponse_a": None,
            "transfere_de": transfere_de,
        }
        chemin = f"messagerie/boites/{boite}/reception/{identifiant}.json"
        self.etat.ecrire(chemin, json.dumps(courriel, ensure_ascii=False, indent=2) + "\n")


def boite_comptabilite(m: Messagerie) -> None:
    boite = "comptabilite@calorelle.example"
    m.deposer(
        boite,
        "m-cpt-b01",
        ("Distri-Clim Centre", "compta@distri-clim-centre.example"),
        "Relance : facture DC-5521",
        date_paris(2026, 10, 20, 10, 12),
        lu=True,
        corps="Bonjour,\n\nSauf erreur de notre part, notre facture DC-5521 du 18 septembre 2026 reste à "
        "régler. Merci de votre retour.\n\nService comptable, Distri-Clim Centre (FICTIF)",
    )
    m.deposer(
        boite,
        "m-cpt-b02",
        ("LogiCompta Pro", "offres@logicompta-pro.example"),
        "Votre comptabilité en trois clics",
        date_paris(2026, 10, 22, 14, 3),
        lu=True,
        corps="Découvrez notre logiciel de comptabilité, gratuit pendant un mois. Offre FICTIVE.",
    )
    m.deposer(
        boite,
        "m-cpt-b03",
        ("Facturex", "lettre@facturex-solutions.example"),
        "Facturation électronique : êtes-vous prêts ?",
        date_paris(2026, 10, 27, 9, 30),
        lu=True,
        corps="Notre guide pour passer à la facture électronique. Lettre d'information FICTIVE.",
    )
    m.deposer(
        boite,
        "m-cpt-b04",
        ("Mutuelle d'Assurance du Val", "echeances@assurance-du-val.example"),
        "Avis d'échéance : flotte de véhicules",
        date_paris(2026, 10, 28, 8, 15),
        lu=True,
        corps="Votre prime annuelle pour la flotte de quatre véhicules arrive à échéance le 1er décembre "
        "2026. Avis FICTIF.",
    )
    m.deposer(
        boite,
        "m-cpt-001",
        ("Thermopièces Loire", "facturation@thermopieces-loire.example"),
        "Facture F-2026-1187",
        date_paris(2026, 11, 2, 7, 48),
        corps="Bonjour,\n\nVeuillez trouver ci-jointe notre facture F-2026-1187 du 30 octobre 2026, d'un "
        "montant de 842,40 € TTC.\n\nCordialement,\nService facturation, Thermopièces Loire (FICTIF)",
        pieces=[
            (
                "Facture_F-2026-1187.pdf",
                facture(
                    "F-2026-1187",
                    "Thermopièces Loire",
                    "2026-10-30",
                    [
                        ("Circulateurs haute efficacité, 2 unités", 398.0),
                        ("Vases d'expansion 18 litres, 4 unités", 304.0),
                    ],
                    IBAN_THERMOPIECES,
                ),
            )
        ],
    )
    m.deposer(
        boite,
        "m-cpt-002",
        ("Papeterie du Val", "factures@papeterie-du-val.example"),
        "Votre facture PV-26-0412",
        date_paris(2026, 11, 2, 8, 5),
        corps="Bonjour,\n\nVoici votre facture PV-26-0412 du 2 novembre 2026, d'un montant de 96,00 € TTC.\n\n"
        "Papeterie du Val (FICTIF)",
        pieces=[
            (
                "Facture PV-26-0412.pdf",
                facture(
                    "PV-26-0412",
                    "Papeterie du Val",
                    "2026-11-02",
                    [("Cartouches d'encre et papier", 80.0)],
                    "FR76 9999 9004 5500 0091 2207 341",
                ),
            )
        ],
    )
    m.deposer(
        boite,
        "m-cpt-003",
        ("Thermopièces Loire", "service.paiement@thermopieces-loire-reglements.example"),
        "Changement de coordonnées bancaires, urgent",
        date_paris(2026, 11, 2, 8, 31),
        corps="Madame, Monsieur,\n\nÀ la suite d'un changement de banque, nos coordonnées bancaires changent. "
        "Merci de mettre à jour notre fiche fournisseur avec le RIB ci-joint, et de régler la facture "
        "F-2026-1187 sur ce nouveau compte avant vendredi.\n\nService comptabilité, Thermopièces Loire "
        "(FICTIF)",
        pieces=[
            (
                "nouveau_rib.pdf",
                pdf(
                    [
                        "RELEVÉ D'IDENTITÉ BANCAIRE",
                        "Titulaire : Thermopièces Loire",
                        f"IBAN : {IBAN_FRAUDE}",
                        "BIC : FICTFRPPXXX",
                    ]
                ),
            )
        ],
    )


BRUIT_CONTACT = [
    ("Demande d'information sur le contrat Sérénité", "Bonjour, que comprend exactement le contrat Sérénité ?"),
    ("Merci pour votre intervention", "Merci au technicien pour sa visite rapide et soignée."),
    ("Changement d'adresse", "Je déménage à la fin du mois, merci de mettre à jour mon adresse."),
    ("Horaires d'ouverture", "Êtes-vous ouverts le samedi matin ?"),
    ("Offre de partenariat", "Nous proposons nos services de référencement internet. Offre FICTIVE."),
    ("Facture de l'entretien", "Pourriez-vous me renvoyer la facture de mon dernier entretien ?"),
    ("Question sur les aides à la rénovation", "Quelles aides existent pour une pompe à chaleur ?"),
    ("Rendez-vous confirmé", "Je confirme le rendez-vous de jeudi pour l'entretien."),
    ("Bruit dans la chaudière", "Ma chaudière fait un bruit inhabituel, est-ce grave ?"),
    ("Résiliation de contrat", "Je vends ma maison et souhaite résilier mon contrat en fin d'année."),
    ("Lettre d'information", "Les nouveautés de la saison de chauffe. Envoi FICTIF."),
    ("Demande de devis pour un ballon", "Je voudrais un devis pour remplacer mon ballon d'eau chaude."),
    ("Accès au parking", "Le technicien pourra se garer dans la cour."),
    ("Attestation d'entretien", "Mon assurance me demande une attestation d'entretien."),
    ("Report de visite", "Pouvons-nous décaler la visite à la semaine suivante ?"),
    ("Félicitations", "Bravo pour la qualité de votre accueil téléphonique."),
    ("Thermostat connecté", "Installez-vous des thermostats connectés ?"),
    ("Salon de l'habitat", "Serez-vous présents au salon de l'habitat ? Invitation FICTIVE."),
    ("Panne de climatisation", "La climatisation ne refroidit plus, pouvez-vous passer ?"),
]


def boite_contact(m: Messagerie, alea: random.Random) -> None:
    boite = "contact@calorelle.example"
    jours = sorted(alea.sample(range(0, 85), len(BRUIT_CONTACT)))
    for rang, ((objet, corps), decalage) in enumerate(zip(BRUIT_CONTACT, jours, strict=True), start=1):
        mois, jour = (
            (8, 6 + decalage) if decalage < 26 else ((9, decalage - 25) if decalage < 55 else (10, decalage - 54))
        )
        prenom, nom = alea.choice(PRENOMS), alea.choice(NOMS)
        m.deposer(
            boite,
            f"m-ctc-b{rang:02d}",
            (f"{prenom} {nom}", f"{slug(prenom)}.{slug(nom)}@courriel.example"),
            objet,
            date_paris(2026, mois, jour, alea.randrange(8, 19), alea.randrange(60)),
            lu=True,
            corps=f"Bonjour,\n\n{corps}\n\n{prenom} {nom} (FICTIF)",
        )
    m.deposer(
        boite,
        "m-ctc-b20",
        ("Bernard Lemoine", "b.lemoine@courriel.example"),
        "Copie de mon contrat d'entretien",
        date_paris(2026, 10, 30, 16, 40),
        lu=True,
        corps="Bonjour,\n\nJ'ai égaré mon contrat d'entretien. Pourriez-vous m'en envoyer une copie ?\n\n"
        "Bien cordialement,\nBernard Lemoine\n8 allée des Peupliers, " + VILLE,
    )
    nouveaux = [
        (
            "m-ctc-001",
            ("Isabelle Garnier", "isabelle.garnier@courriel.example"),
            "Demande de devis : remplacement de chaudière",
            (10, 31, 18, 22),
            "Ma chaudière au fioul a vingt-cinq ans. Je souhaite un devis pour la remplacer par une pompe "
            "à chaleur.\n\nIsabelle Garnier, 14 rue des Lilas, " + VILLE,
            None,
        ),
        (
            "m-ctc-002",
            ("Saulaies Gestion", "copropriete@saulaies-gestion.example"),
            "Devis : rénovation de la chaufferie collective",
            (11, 1, 10, 5),
            "Nous gérons la résidence Les Saulaies, 48 lots. Le conseil syndical souhaite un devis pour "
            "rénover la chaufferie collective avant l'hiver prochain.\n\nSaulaies Gestion, syndic de copropriété (FICTIF)",
            None,
        ),
        (
            "m-ctc-003",
            ("Paul Mercier", "p.mercier@courriel.example"),
            "Urgent : plus de chauffage depuis hier soir",
            (11, 2, 6, 58),
            "Plus de chauffage ni d'eau chaude depuis hier soir, la chaudière affiche le code F28. Pouvez-vous "
            "passer aujourd'hui ?\n\nPaul Mercier, 6 chemin des Vignes, " + VILLE,
            None,
        ),
        (
            "m-ctc-004",
            ("Garage Bessière", "atelier@garage-bessiere.example"),
            "Facture GB-1102",
            (11, 2, 7, 15),
            "Veuillez trouver notre facture GB-1102 du 30 octobre 2026 pour la révision du fourgon.\n\n"
            "Garage Bessière (FICTIF)",
            (
                "Facture GB-1102.pdf",
                facture(
                    "GB-1102",
                    "Garage Bessière",
                    "2026-10-30",
                    [("Révision du fourgon", 345.0)],
                    "FR76 9999 9003 3100 0827 6644 102",
                ),
            ),
        ),
        (
            "m-ctc-005",
            ("Hugo Lefort", "hugo.lefort@courriel.example"),
            "Candidature spontanée : technicien chauffagiste",
            (11, 2, 7, 40),
            "Technicien chauffagiste depuis six ans, je vous adresse ma candidature. Mon CV est joint.\n\n"
            "Hugo Lefort (FICTIF)",
            ("CV_Hugo_Lefort.pdf", pdf(["CURRICULUM VITAE", "Hugo Lefort, technicien chauffagiste"])),
        ),
        (
            "m-ctc-006",
            ("Syndic de la Résidence des Tilleuls", "syndic@residence-des-tilleuls.example"),
            "Réclamation : chaufferie en panne pour la troisième fois",
            (11, 2, 8, 2),
            "La chaufferie de la résidence est tombée en panne pour la troisième fois en un mois, malgré votre contrat "
            "Sérénité Plus. Les résidents sont sans chauffage. Nous attendons une réponse rapide.\n\nLe syndic de la "
            "Résidence des Tilleuls, client c-0405 (FICTIF)",
            None,
        ),
        (
            "m-ctc-007",
            ("Centre Auto Utilitaires", "promo@utilitaires-centre-auto.example"),
            "Nos utilitaires à prix réduit",
            (11, 2, 8, 10),
            "Profitez de nos offres de fin d'année sur les fourgons. Publicité FICTIVE.",
            None,
        ),
        (
            "m-ctc-008",
            ("Mairie de Brenneval", "marches@mairie-brenneval.example"),
            "Question sur le marché d'entretien des bâtiments communaux",
            (11, 2, 8, 44),
            "La commune prépare le renouvellement de son marché d'entretien des chaudières des bâtiments "
            "communaux. Souhaitez-vous recevoir le dossier de consultation ?\n\nService des marchés, mairie de Brenneval "
            "(FICTIF)",
            None,
        ),
    ]
    for identifiant, de, objet, (mois, jour, heure, minute), corps, piece in nouveaux:
        m.deposer(
            boite,
            identifiant,
            de,
            objet,
            date_paris(2026, mois, jour, heure, minute),
            corps=f"Bonjour,\n\n{corps}",
            pieces=[piece] if piece else None,
        )


def boite_julie(m: Messagerie) -> None:
    boite = "julie.perrin@calorelle.example"
    bruit = [
        (
            "m-jp-b01",
            ("Anne Moreau", "anne.moreau@courriel.example"),
            "RE: Devis DV-2026-009",
            (10, 12, 9, 40),
            "Merci pour le devis, je reviens vers vous après en avoir parlé en famille.",
        ),
        (
            "m-jp-b02",
            ("Établissements Garnier", "contact@etablissements-garnier.example"),
            "Devis climatisation des bureaux",
            (10, 19, 15, 2),
            "Pouvez-vous ajouter une unité dans la salle de réunion ?",
        ),
        (
            "m-jp-b03",
            ("Olivier Faure", "olivier.faure@courriel.example"),
            "RE: Devis DV-2026-011",
            (10, 26, 11, 25),
            "D'accord pour le devis, quand pouvez-vous intervenir ?",
        ),
        (
            "m-jp-b04",
            ("Céline Robin", "celine.robin@courriel.example"),
            "Relance : devis de climatisation",
            (10, 29, 17, 48),
            "Je n'ai pas encore reçu le devis promis pour la climatisation de mon salon.",
        ),
    ]
    for identifiant, de, objet, (mois, jour, heure, minute), corps in bruit:
        m.deposer(
            boite,
            identifiant,
            de,
            objet,
            date_paris(2026, mois, jour, heure, minute),
            lu=True,
            corps=f"Bonjour,\n\n{corps}\n\n{de[0]} (FICTIF)",
        )
    m.deposer(
        boite,
        "m-jp-001",
        ("Sonia Lefèvre", "sonia.lefevre@calorelle.example"),
        "TR: Copie de mon contrat d'entretien",
        date_paris(2026, 11, 2, 8, 20),
        transfere_de="m-ctc-b20",
        corps="Bonjour Julie,\n\nPeux-tu envoyer à M. Lemoine la copie de son contrat d'entretien ?\n\nMerci,\nSonia\n\n"
        "----- Message transféré -----\nDe : Bernard Lemoine <b.lemoine@courriel.example>\n"
        "Date : 2026-10-30T16:40:00+01:00\nObjet : Copie de mon contrat d'entretien\n\nBonjour,\n\n"
        "J'ai égaré mon contrat d'entretien. Pourriez-vous m'en envoyer une copie ?\n\nBien cordialement,\n"
        "Bernard Lemoine\n8 allée des Peupliers, " + VILLE,
    )
    m.deposer(
        boite,
        "m-jp-002",
        ("Claire Fabre", "claire.fabre@courriel.example"),
        "Date de mon prochain entretien",
        date_paris(2026, 11, 2, 8, 47),
        corps="Bonjour,\n\nPourriez-vous me dire quand aura lieu le prochain entretien annuel de ma chaudière ?\n\n"
        "Merci,\nClaire Fabre (FICTIF)",
    )


# --- dossier commun ------------------------------------------------------------------------


def commun(etat: Etat, entreprise: Path = V1 / "entreprise") -> None:
    """Ce que tout le personnel peut lire : le manuel, et l'annuaire tiré de l'organigramme.
    generer_donnees_v2.py le rappelle avec le dossier entreprise/ de v2."""
    etat.ecrire("dossiers/commun/manuel_procedures.md", (entreprise / "manuel_procedures.md").read_bytes())
    organigramme = cast(dict[str, Any], yaml.safe_load((entreprise / "organigramme.yaml").read_text(encoding="utf-8")))
    personnes = cast(list[dict[str, str]], organigramme["personnes"])
    noms = {p["id"]: p["nom"] for p in personnes}
    lignes = [
        "# Annuaire du personnel de Calorelle (FICTIF)",
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


# --- assemblage ------------------------------------------------------------------------------


def construire() -> Etat:
    """Construit tous les fichiers en mémoire, dans un ordre fixe."""
    etat = Etat()
    alea = random.Random(GRAINE)
    fournisseurs(etat, alea)
    factures_rangees(etat, alea)
    clients(etat, alea)
    devis(etat, alea)
    direction_et_rh(etat)
    commun(etat)
    messagerie = Messagerie(etat)
    boite_comptabilite(messagerie)
    boite_contact(messagerie, alea)
    boite_julie(messagerie)
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
    analyse = argparse.ArgumentParser(description=(__doc__ or "Génère les données v1.").splitlines()[0])
    analyse.add_argument("--verifier", action="store_true", help="contrôle sans rien écrire")
    args = analyse.parse_args()
    etat = construire()
    if args.verifier:
        messages = ecarts(etat)
        if messages:
            print(f"Données v1 à régénérer ({len(messages)} écart(s)) :", file=sys.stderr)
            for message in messages[:20]:
                print(f"  {message}", file=sys.stderr)
            return 1
        print(f"Données v1 à jour ({len(etat.fichiers)} fichiers).")
        return 0
    for partie in GENERES:
        shutil.rmtree(V1 / partie, ignore_errors=True)
    ecrire(etat, V1)
    print(f"Données v1 générées : {len(etat.fichiers)} fichiers dans {V1.relative_to(RACINE)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
