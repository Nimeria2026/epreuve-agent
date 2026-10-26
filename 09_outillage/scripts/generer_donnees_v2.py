"""Génère l'état initial v2 de la PME fictive Calorelle : v1 et les ajouts de l'étape 5.

v2 part des dossiers partagés et de la messagerie de v1, produits par generer_donnees_v1.py, et
ajoute ce que la tranche 4 demande (JOURNAL, entrées 81 et 82) :
- dans commun/, le manuel et l'annuaire recalculés depuis v2/entreprise/ ;
- les conditions de paiement de dix fournisseurs, huit factures fournisseurs de fin septembre et
  d'octobre, et l'échéancier tenu par le comptable ;
- dans rh/, le tableau des congés et absences de fin 2026 ;
- planning/ : heures d'intervention et jours fériés, fiches des techniciens, planning de départ.
Le dossier entreprise/ reste écrit à la main : l'organigramme avec les neuf techniciens, le manuel
avec les règles de l'entrée 82. Rejouable à l'octet près, comme v1. Tout est fictif.

Usage, depuis la racine du dépôt :
    uv run python 09_outillage/scripts/generer_donnees_v2.py              # régénère
    uv run python 09_outillage/scripts/generer_donnees_v2.py --verifier   # contrôle sans écrire

Codes de sortie : 0 à jour ou régénéré, 1 données périmées.
"""

from __future__ import annotations

import argparse
import calendar
import filecmp
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import generer_donnees_v1 as v1
import yaml

RACINE = v1.RACINE
V2 = RACINE / "05_pme" / "societes" / "calorelle" / "v2"
GENERES = ("dossiers", "messagerie", "planning")
JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def remplacer(etat: v1.Etat, chemin: str, contenu: bytes | str) -> None:
    """Remplace un fichier produit pour v1 ; refuse un chemin que v1 ne produit pas."""
    if chemin not in etat.fichiers:
        raise ValueError(f"fichier absent de v1, rien à remplacer : {chemin}")
    etat.fichiers[chemin] = contenu.encode("utf-8") if isinstance(contenu, str) else contenu


def jour_fr(jour: date) -> str:
    """Par exemple « lundi 9 novembre 2026 »."""
    return f"{JOURS_SEMAINE[jour.weekday()]} {jour.day} {v1.MOIS[jour.month - 1]} {jour.year}"


def periode_fr(premier: date, dernier: date) -> str:
    if premier == dernier:
        return jour_fr(premier)
    if (premier.year, premier.month) == (dernier.year, dernier.month):
        return f"du {JOURS_SEMAINE[premier.weekday()]} {premier.day} au {jour_fr(dernier)}"
    return f"du {jour_fr(premier)} au {jour_fr(dernier)}"


def instant(jour: date, heure: int = 0, minute: int = 0) -> datetime:
    return datetime(jour.year, jour.month, jour.day, heure, minute, tzinfo=v1.PARIS)


def json_texte(valeur: object) -> str:
    return json.dumps(valeur, ensure_ascii=False, indent=2) + "\n"


# --- commun : manuel et annuaire de v2 -------------------------------------------------------


def commun(etat: v1.Etat) -> None:
    for chemin in ("dossiers/commun/manuel_procedures.md", "dossiers/commun/annuaire.md"):
        if chemin not in etat.fichiers:
            raise ValueError(f"fichier absent de v1 : {chemin}")
        del etat.fichiers[chemin]
    v1.commun(etat, V2 / "entreprise")


# --- fournisseurs, factures et échéancier ----------------------------------------------------

A_RECEPTION = "paiement à réception"
A_30_JOURS = "paiement à 30 jours"
A_30_JOURS_FIN_DE_MOIS = "paiement à 30 jours fin de mois"

CONDITIONS = {
    "papeterie-du-val": A_RECEPTION,
    "informatique-des-greves": A_RECEPTION,
    "garage-bessiere": A_30_JOURS,
    "robinetterie-des-greves": A_30_JOURS,
    "outillage-de-mirelande": A_30_JOURS,
    "electricite-du-val-mauvoir": A_30_JOURS,
    "fumisterie-des-hautes-fresnes": A_30_JOURS,
    "transports-de-sablonnet": A_30_JOURS,
    "gaines-et-conduits-de-la-courtine": A_30_JOURS,
    "nettoyage-de-mirelande": A_30_JOURS,
}
"""Conditions de paiement changées dans v2 ; les autres fournisseurs gardent celles de v1."""


@dataclass(frozen=True)
class Facture:
    fournisseur: str
    numero: str
    date: str
    lignes: tuple[tuple[str, float], ...]
    reglee_le: str | None
    observation: str = ""


REGLEMENTS_V1 = {
    "F-2026-1042": "2026-10-29",
    "PV-26-0371": "2026-09-17",
    "DC-5521": "2026-10-29",
    "GB-0917": "2026-10-22",
    "PV-26-0388": "2026-10-08",
}
"""Règlements des factures déjà rangées dans v1 ; les autres ne sont pas encore réglées."""

# fmt: off
FACTURES_AJOUTEES = [
    Facture("echafaudages-de-brenneval", "EB-26-0457", "2026-09-28", (("Location d'échafaudage", 380.0),), "2026-10-29"),
    Facture("outillage-de-mirelande", "OM-2026-212", "2026-10-02", (("Clés et pinces", 154.0),), "2026-10-29"),
    Facture("electricite-du-val-mauvoir", "EVM-1984", "2026-10-07", (("Câbles et disjoncteurs", 268.0),), None),
    Facture("fumisterie-des-hautes-fresnes", "FHF-26-133", "2026-10-12", (("Conduits de fumée", 615.0),), None),
    Facture("transports-de-sablonnet", "TS-08812", "2026-10-14", (("Livraison d'une chaudière", 95.0),), None),
    Facture("gaines-et-conduits-de-la-courtine", "GCC-2026-077", "2026-10-15", (("Gaines de ventilation", 1340.0),), None),
    Facture("nettoyage-de-mirelande", "NM-26-1010", "2026-10-20", (("Nettoyage des locaux", 210.0),), None),
    Facture(
        "informatique-des-greves",
        "IG-2026-0391",
        "2026-10-28",
        (("Renouvellement de licences", 172.0),),
        None,
        "reçue le 29 octobre 2026",
    ),
]
# fmt: on

SEUIL_GERANTE = 1500.0
"""Manuel, section 5 : un virement au-delà de 1 500 € exige la validation de la gérante."""


def chemin_fiche(identifiant: str) -> str:
    return f"dossiers/administration/fournisseurs/{identifiant}/fiche_fournisseur.yaml"


def fiche_fournisseur(etat: v1.Etat, identifiant: str) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(etat.fichiers[chemin_fiche(identifiant)].decode("utf-8")))


def conditions(etat: v1.Etat) -> None:
    for identifiant, texte in CONDITIONS.items():
        fiche = fiche_fournisseur(etat, identifiant)
        fiche["conditions"] = texte
        remplacer(
            etat, chemin_fiche(identifiant), v1.yaml_simple("Fiche fournisseur Calorelle. Données FICTIVES.", fiche)
        )


def echeance(date_facture: date, condition: str) -> date:
    """Date d'échéance selon les conditions de la fiche, comme le comptable la calcule."""
    if condition == A_RECEPTION:
        return date_facture
    if condition == A_30_JOURS:
        return date_facture + timedelta(days=30)
    if condition == A_30_JOURS_FIN_DE_MOIS:
        jour = date_facture + timedelta(days=30)
        return jour.replace(day=calendar.monthrange(jour.year, jour.month)[1])
    raise ValueError(f"conditions inconnues : {condition}")


def toutes_les_factures() -> list[Facture]:
    rangees = [
        Facture(identifiant, numero, jour, tuple(lignes), REGLEMENTS_V1.get(numero))
        for _mois, _nom, identifiant, numero, jour, lignes in v1.FACTURES_RANGEES
    ]
    return rangees + FACTURES_AJOUTEES


def toutes_taxes(facture: Facture) -> float:
    """Total TTC, calculé comme sur la facture (generer_donnees_v1.facture)."""
    hors_taxes = round(sum(m for _, m in facture.lignes), 2)
    return hors_taxes + round(hors_taxes * 0.2, 2)


def jjmmaaaa(jour: date) -> str:
    return jour.strftime("%d/%m/%Y")


def factures_et_echeancier(etat: v1.Etat) -> None:
    for facture in FACTURES_AJOUTEES:
        fiche = fiche_fournisseur(etat, facture.fournisseur)
        compte = str(fiche["iban"]).removesuffix(" (FICTIF)")
        mois = facture.date[:7]
        etat.ecrire(
            f"dossiers/administration/factures_fournisseurs/{mois}/{facture.fournisseur}_{facture.numero.lower()}.pdf",
            v1.facture(facture.numero, str(fiche["nom"]), facture.date, list(facture.lignes), compte),
        )
    lignes: list[tuple[date, str, str]] = []
    for facture in toutes_les_factures():
        fiche = fiche_fournisseur(etat, facture.fournisseur)
        condition = str(fiche["conditions"])
        jour = date.fromisoformat(facture.date)
        due = echeance(jour, condition)
        montant = toutes_taxes(facture)
        observation = facture.observation
        if facture.reglee_le is None and montant > SEUIL_GERANTE:
            observation = "au-delà de 1 500 € : validation de la gérante avant le virement"
        reglee = jjmmaaaa(date.fromisoformat(facture.reglee_le)) if facture.reglee_le else "non réglée"
        lignes.append(
            (
                due,
                facture.numero,
                f"| {fiche['nom']} | {facture.numero} | {jjmmaaaa(jour)} | {v1.euros(montant)} | {condition} "
                f"| {jjmmaaaa(due)} | {reglee} | {observation} |",
            )
        )
    texte = [
        "# Échéancier des factures fournisseurs de Calorelle (FICTIF)",
        "",
        "Tenu par Patrick Roux, comptable. À jour au jeudi 29 octobre 2026. Une ligne par facture rangée",
        "dans `administration/factures_fournisseurs/` ; une facture reçue depuis n'y figure pas encore.",
        "",
        "Échéance selon les conditions de la fiche du fournisseur : « paiement à 30 jours », date de",
        "facture plus 30 jours ; « paiement à 30 jours fin de mois », date de facture plus 30 jours,",
        "reportée au dernier jour de ce mois ; « paiement à réception », date de facture.",
        "",
        "| Fournisseur | Facture | Date de facture | Montant TTC | Conditions | Échéance | Réglée le | Observation |",
        "|---|---|---|---|---|---|---|---|",
        *(ligne for _, _, ligne in sorted(lignes)),
        "",
        v1.MENTION,
        "",
    ]
    etat.ecrire(
        "dossiers/administration/echeancier_fournisseurs.md", "\n".join(texte).replace("« ", "« ").replace(" »", " »")
    )


# --- techniciens, absences, congés -----------------------------------------------------------


@dataclass(frozen=True)
class Technicien:
    id: str
    nom: str
    competences: tuple[str, ...]
    apprenti: bool = False


TECHNICIENS = [
    Technicien("thomas.girard", "Thomas Girard", ("chaudiere_gaz", "chaudiere_fioul", "pompe_a_chaleur")),
    Technicien("enzo.caron", "Enzo Caron", ("chaudiere_gaz",), apprenti=True),
    Technicien("nicolas.blanc", "Nicolas Blanc", ("climatisation", "pompe_a_chaleur")),
    Technicien("romain.guerin", "Romain Guérin", ("chaudiere_gaz", "chaudiere_fioul")),
    Technicien("kevin.lambert", "Kevin Lambert", ("chaudiere_gaz", "ventilation")),
    Technicien("yanis.haddad", "Yanis Haddad", ("climatisation", "ventilation")),
    Technicien("mathieu.picard", "Mathieu Picard", ("chaudiere_gaz", "pompe_a_chaleur")),
    Technicien("antoine.leroy", "Antoine Leroy", ("chaudiere_gaz", "chaudiere_fioul")),
    Technicien("sebastien.noel", "Sébastien Noël", ("pompe_a_chaleur", "climatisation")),
    Technicien("david.roussel", "David Roussel", ("chaudiere_gaz",)),
    Technicien("florian.masson", "Florian Masson", ("ventilation", "climatisation")),
]


@dataclass(frozen=True)
class Absence:
    technicien: str
    premier: str
    dernier: str
    motif: str


ABSENCES = [
    Absence("kevin.lambert", "2026-11-05", "2026-11-05", "formation"),
    Absence("antoine.leroy", "2026-11-09", "2026-11-13", "congés payés"),
    Absence("enzo.caron", "2026-11-16", "2026-11-20", "semaine au centre de formation des apprentis"),
    Absence("florian.masson", "2026-11-23", "2026-11-27", "congés payés"),
    Absence("david.roussel", "2026-12-21", "2026-12-24", "congés payés"),
    Absence("nicolas.blanc", "2026-12-28", "2026-12-31", "congés payés"),
    Absence("romain.guerin", "2026-12-28", "2026-12-31", "congés payés"),
]
"""Absences validées. Le planning n'en reçoit que les dates ; le motif reste au dossier RH."""


def conges(etat: v1.Etat) -> None:
    noms = {t.id: t.nom for t in TECHNICIENS}
    lignes = [
        "Congés et absences prévues de Calorelle, fin 2026. Document FICTIF, confidentiel.",
        "Tenu par Sonia Lefèvre. Congés validés par Hélène Marchal (manuel, section 7). Le planning",
        "ne reçoit que les dates, jamais le motif.",
        "",
        "Validés :",
        *(
            f"- {noms[a.technicien]} : {periode_fr(date.fromisoformat(a.premier), date.fromisoformat(a.dernier))}, {a.motif}."
            for a in ABSENCES
        ),
        "",
        "Demandes en attente : aucune au lundi 2 novembre 2026.",
        "",
    ]
    remplacer(etat, "dossiers/rh/conges_2026.txt", "\n".join(lignes))


# --- planning : horaires, techniciens, interventions -----------------------------------------


def paques(annee: int) -> date:
    """Dimanche de Pâques, calendrier grégorien (algorithme de Meeus, Jones et Butcher)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mois = (h + m - 7 * n + 114) // 31
    jour = (h + m - 7 * n + 114) % 31 + 1
    return date(annee, mois, jour)


def feries(annee: int) -> list[date]:
    """Les onze jours fériés légaux (Code du travail, article L3133-1), hors Alsace-Moselle."""
    p = paques(annee)
    return sorted(
        [
            date(annee, 1, 1),
            p + timedelta(days=1),
            date(annee, 5, 1),
            date(annee, 5, 8),
            p + timedelta(days=39),
            p + timedelta(days=50),
            date(annee, 7, 14),
            date(annee, 8, 15),
            date(annee, 11, 1),
            date(annee, 11, 11),
            date(annee, 12, 25),
        ]
    )


ANNEES_FERIES = (2026, 2027)


def horaires(etat: v1.Etat) -> None:
    jours = [j for annee in ANNEES_FERIES for j in feries(annee)]
    lignes = [
        "# Heures d'intervention de Calorelle, lues par le service de planning. Données FICTIVES.",
        "# Jours : 1 pour lundi. Plages : heure de Paris. Jours fériés : les onze jours fériés légaux",
        "# (Code du travail, article L3133-1), calculés par 09_outillage/scripts/generer_donnees_v2.py ;",
        "# tous chômés chez Calorelle (manuel, section 9).",
        "jours: [1, 2, 3, 4, 5]",
        'plages: ["08:00-12:00", "13:30-17:30"]',
        "feries:",
        *(f'  - "{j.isoformat()}"' for j in jours),
        "",
    ]
    etat.ecrire("planning/horaires.yaml", "\n".join(lignes))


def techniciens(etat: v1.Etat) -> None:
    for t in TECHNICIENS:
        periodes = [
            {
                "debut": instant(date.fromisoformat(a.premier)).isoformat(),
                "fin": instant(date.fromisoformat(a.dernier) + timedelta(days=1)).isoformat(),
            }
            for a in ABSENCES
            if a.technicien == t.id
        ]
        fiche = {
            "id": t.id,
            "nom": t.nom,
            "competences": list(t.competences),
            "apprenti": t.apprenti,
            "indisponibilites": periodes,
        }
        etat.ecrire(f"planning/techniciens/{t.id}.json", json_texte(fiche))


@dataclass(frozen=True)
class Rendezvous:
    jour: str
    heure: str
    minutes: int
    techniciens: tuple[str, ...]
    client: str
    nature: str
    objet: str
    motif_annulation: str | None = None


VISITE, DEPANNAGE, INSTALLATION, MISE_EN_SERVICE = "visite_annuelle", "depannage", "installation", "mise_en_service"
TOM_ENZO = ("thomas.girard", "enzo.caron")

# fmt: off
PLANNING_DE_DEPART = [
    # Lundi 2 novembre
    Rendezvous("2026-11-02", "08:00", 240, ("nicolas.blanc", "sebastien.noel"), "c-0168", INSTALLATION, "Pose d'une pompe à chaleur air-eau, première demi-journée"),
    Rendezvous("2026-11-02", "13:30", 240, ("nicolas.blanc", "sebastien.noel"), "c-0168", INSTALLATION, "Pose d'une pompe à chaleur air-eau, seconde demi-journée"),
    Rendezvous("2026-11-02", "08:00", 90, ("mathieu.picard",), "c-0085", VISITE, "Visite annuelle du contrat Sérénité Plus"),
    Rendezvous("2026-11-02", "10:00", 120, ("romain.guerin",), "c-0263", DEPANNAGE, "Dépannage : chaudière gaz en sécurité, plus de chauffage"),
    Rendezvous("2026-11-02", "13:30", 90, ("kevin.lambert",), "c-0120", VISITE, "Visite annuelle du contrat Sérénité"),
    Rendezvous("2026-11-02", "13:30", 120, TOM_ENZO, "c-0195", DEPANNAGE, "Dépannage : fuite sur le circuit de chauffage"),
    # Mardi 3 novembre
    Rendezvous("2026-11-03", "08:00", 120, TOM_ENZO, "c-0487", DEPANNAGE, "Dépannage : chaudière gaz qui se met en sécurité"),
    Rendezvous("2026-11-03", "10:00", 90, ("thomas.girard",), "c-0062", VISITE, "Visite annuelle du contrat Sérénité Plus"),
    Rendezvous("2026-11-03", "13:30", 120, TOM_ENZO, "c-0228", MISE_EN_SERVICE, "Mise en service d'une chaudière gaz à condensation"),
    Rendezvous("2026-11-03", "08:00", 90, ("romain.guerin",), "c-0080", VISITE, "Visite annuelle du contrat Sérénité"),
    Rendezvous("2026-11-03", "10:00", 120, ("mathieu.picard",), "c-0410", DEPANNAGE, "Dépannage : pompe à chaleur en défaut"),
    Rendezvous("2026-11-03", "13:30", 90, ("david.roussel",), "c-0039", VISITE, "Visite annuelle du contrat Sérénité"),
    Rendezvous("2026-11-03", "08:00", 240, ("yanis.haddad", "florian.masson"), "c-0274", INSTALLATION, "Installation d'une climatisation réversible, première demi-journée"),
    Rendezvous("2026-11-03", "13:30", 240, ("yanis.haddad", "florian.masson"), "c-0274", INSTALLATION, "Installation d'une climatisation réversible, seconde demi-journée"),
    Rendezvous("2026-11-03", "15:30", 120, ("antoine.leroy",), "c-0581", DEPANNAGE, "Dépannage : chaudière fioul, brûleur en panne"),
    # Mercredi 4 novembre
    Rendezvous("2026-11-04", "10:00", 120, ("sebastien.noel",), "c-0229", DEPANNAGE, "Dépannage : pompe à chaleur bruyante"),
    Rendezvous("2026-11-04", "13:30", 90, ("antoine.leroy",), "c-0589", VISITE, "Visite annuelle du contrat Sérénité"),
    Rendezvous("2026-11-04", "08:00", 240, ("romain.guerin", "david.roussel"), "c-0573", INSTALLATION, "Remplacement d'une chaudière gaz, première demi-journée"),
    Rendezvous("2026-11-04", "13:30", 240, ("romain.guerin", "david.roussel"), "c-0573", INSTALLATION, "Remplacement d'une chaudière gaz, seconde demi-journée"),
    # Jeudi 5 novembre
    Rendezvous("2026-11-05", "08:00", 120, ("mathieu.picard",), "c-0034", DEPANNAGE, "Dépannage : plus d'eau chaude"),
    Rendezvous("2026-11-05", "10:00", 90, TOM_ENZO, "c-0191", VISITE, "Visite annuelle du contrat Sérénité Plus"),
    Rendezvous("2026-11-05", "13:30", 120, ("nicolas.blanc",), "c-0168", MISE_EN_SERVICE, "Mise en service de la pompe à chaleur posée le 2 novembre"),
    Rendezvous("2026-11-05", "15:30", 120, ("yanis.haddad",), "c-0534", DEPANNAGE, "Dépannage : ventilation de l'atelier en panne"),
    # Vendredi 6 novembre
    Rendezvous("2026-11-06", "08:00", 120, ("romain.guerin",), "c-0472", DEPANNAGE, "Dépannage : chaudière fioul qui ne démarre plus"),
    Rendezvous("2026-11-06", "10:00", 120, ("florian.masson",), "c-0312", DEPANNAGE, "Dépannage : VMC double flux en défaut"),
    Rendezvous("2026-11-06", "13:30", 120, ("yanis.haddad",), "c-0274", MISE_EN_SERVICE, "Mise en service de la climatisation posée le 3 novembre"),
    # Semaine du 9 novembre (mercredi 11 férié)
    Rendezvous("2026-11-09", "08:00", 120, ("mathieu.picard",), "c-0521", DEPANNAGE, "Dépannage : radiateurs froids à l'étage"),
    Rendezvous(
        "2026-11-09",
        "13:30",
        90,
        ("kevin.lambert",),
        "c-0307",
        VISITE,
        "Visite annuelle du contrat Sérénité",
        "Annulée à la demande du client, qui rappellera pour une autre date",
    ),
    Rendezvous("2026-11-09", "08:00", 240, TOM_ENZO, "c-0437", INSTALLATION, "Remplacement d'une chaudière gaz, première demi-journée"),
    Rendezvous("2026-11-09", "13:30", 240, TOM_ENZO, "c-0437", INSTALLATION, "Remplacement d'une chaudière gaz, seconde demi-journée"),
    Rendezvous("2026-11-10", "10:00", 120, ("sebastien.noel",), "c-0586", DEPANNAGE, "Dépannage : pompe à chaleur de l'école en défaut"),
    Rendezvous("2026-11-10", "13:30", 120, ("romain.guerin",), "c-0573", MISE_EN_SERVICE, "Mise en service de la chaudière remplacée le 4 novembre"),
    Rendezvous("2026-11-12", "08:00", 120, TOM_ENZO, "c-0437", MISE_EN_SERVICE, "Mise en service de la chaudière remplacée le 9 novembre"),
    Rendezvous("2026-11-12", "13:30", 120, ("david.roussel",), "c-0562", DEPANNAGE, "Dépannage : chaudière gaz, pression trop basse"),
    # Semaines suivantes
    Rendezvous("2026-11-16", "08:00", 240, ("nicolas.blanc", "sebastien.noel"), "c-0553", INSTALLATION, "Pose d'une pompe à chaleur air-eau, première demi-journée"),
    Rendezvous("2026-11-16", "13:30", 240, ("nicolas.blanc", "sebastien.noel"), "c-0553", INSTALLATION, "Pose d'une pompe à chaleur air-eau, seconde demi-journée"),
    Rendezvous("2026-11-17", "13:30", 120, ("nicolas.blanc",), "c-0553", MISE_EN_SERVICE, "Mise en service de la pompe à chaleur posée le 16 novembre"),
    Rendezvous("2026-11-18", "08:00", 90, ("kevin.lambert",), "c-0352", VISITE, "Visite annuelle du contrat Sérénité"),
    Rendezvous("2026-11-26", "13:30", 120, ("antoine.leroy",), "c-0398", INSTALLATION, "Pose d'un régulateur sur la chaudière fioul"),
]
# fmt: on
"""Le planning au lundi 2 novembre 2026, écrit à la main pour rester lisible et pour servir les
tâches 20 à 26 : le mardi 3, lendemain de l'horloge, compte neuf rendez-vous, dont trois de Thomas
Girard, deux avec l'apprenti. Quatre clients du mois anniversaire de novembre n'ont pas encore de
visite. Les clients des tâches des étapes 2 à 4 n'y figurent pas."""

CLIENTS_DES_TACHES_ANCIENNES = {"c-0010", "c-0088", "c-0124", "c-0137", "c-0142", "c-0217", "c-0311", "c-0405"}


def interventions(etat: v1.Etat) -> None:
    ordonnes = sorted(PLANNING_DE_DEPART, key=lambda r: (r.jour, r.heure, r.client, r.techniciens))
    for rang, r in enumerate(ordonnes, start=1):
        if r.client in CLIENTS_DES_TACHES_ANCIENNES:
            raise ValueError(f"client d'une tâche existante dans le planning de départ : {r.client}")
        if f"dossiers/clients/{r.client}/fiche_client.yaml" not in etat.fichiers:
            raise ValueError(f"client inconnu : {r.client}")
        heure, minute = (int(x) for x in r.heure.split(":"))
        debut = instant(date.fromisoformat(r.jour), heure, minute)
        numero = f"INT-2026-{rang:04d}"
        fiche: dict[str, object] = {
            "numero": numero,
            "client": r.client,
            "techniciens": list(r.techniciens),
            "debut": debut.isoformat(),
            "fin": (debut + timedelta(minutes=r.minutes)).isoformat(),
            "nature": r.nature,
            "objet": r.objet,
            "statut": "planifiee" if r.motif_annulation is None else "annulee",
        }
        if r.motif_annulation is not None:
            fiche["motif_annulation"] = r.motif_annulation
        fiche["cree_par"] = "donnees_initiales"
        etat.ecrire(f"planning/interventions/{numero}.json", json_texte(fiche))


# --- assemblage ------------------------------------------------------------------------------


def construire() -> v1.Etat:
    """v1 en mémoire, puis les ajouts de v2, dans un ordre fixe."""
    etat = v1.construire()
    commun(etat)
    conditions(etat)
    factures_et_echeancier(etat)
    conges(etat)
    horaires(etat)
    techniciens(etat)
    interventions(etat)
    return etat


def ecarts(etat: v1.Etat) -> list[str]:
    """Différences entre les données présentes dans v2 et une génération fraîche."""
    with tempfile.TemporaryDirectory() as dossier:
        frais = Path(dossier)
        v1.ecrire(etat, frais)
        messages: list[str] = []
        for partie in GENERES:
            attendus = {p.relative_to(frais) for p in (frais / partie).rglob("*") if p.is_file()}
            presents: set[Path] = set()
            if (V2 / partie).exists():
                presents = {p.relative_to(V2) for p in (V2 / partie).rglob("*") if p.is_file()}
            messages += [f"absent : {p}" for p in sorted(attendus - presents)]
            messages += [f"en trop : {p}" for p in sorted(presents - attendus)]
            messages += [
                f"différent : {p}"
                for p in sorted(attendus & presents)
                if not filecmp.cmp(frais / p, V2 / p, shallow=False)
            ]
        return messages


def main() -> int:
    analyse = argparse.ArgumentParser(description=(__doc__ or "Génère les données v2.").splitlines()[0])
    analyse.add_argument("--verifier", action="store_true", help="contrôle sans rien écrire")
    args = analyse.parse_args()
    etat = construire()
    if args.verifier:
        messages = ecarts(etat)
        if messages:
            print(f"Données v2 à régénérer ({len(messages)} écart(s)) :", file=sys.stderr)
            for message in messages[:20]:
                print(f"  {message}", file=sys.stderr)
            return 1
        print(f"Données v2 à jour ({len(etat.fichiers)} fichiers).")
        return 0
    for partie in GENERES:
        shutil.rmtree(V2 / partie, ignore_errors=True)
    v1.ecrire(etat, V2)
    print(f"Données v2 générées : {len(etat.fichiers)} fichiers dans {V2.relative_to(RACINE)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
