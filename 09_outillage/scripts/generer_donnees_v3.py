"""Génère l'état initial v3 de la PME fictive Calorelle : v2 et les ajouts de la tranche 5.

v3 part de la génération de v2 (generer_donnees_v2.py) et ajoute ce que la tranche 5 demande
(JOURNAL, entrée 91 ; 00_docs/sources/2026-10-08_plan_tranche_5.md) :
- dans commun/, le manuel et l'annuaire recalculés depuis v3/entreprise/ ;
- facturation/tarif.json, la grille de prix que le service de facturation lit pour chiffrer ;
- facturation/devis/, les 22 devis de 2025 et 2026 avec leur client, leurs lignes, leur statut et
  leurs dates ; leurs PDF de commercial/devis/ sont refaits à l'identique de ceux qu'écrit le
  service (05_pme/facturation/src/serveur.ts, lignesPdfDevis).
Le chiffrage reprend exactement celui du service (05_pme/facturation/src/chiffrage.ts) : centimes
entiers, arrondi au plus proche, la moitié vers le haut. Le dossier entreprise/ reste écrit à la
main. Rejouable à l'octet près, comme v1 et v2. Tout est fictif.

Usage, depuis la racine du dépôt :
    uv run python 09_outillage/scripts/generer_donnees_v3.py              # régénère
    uv run python 09_outillage/scripts/generer_donnees_v3.py --verifier   # contrôle sans écrire

Codes de sortie : 0 à jour ou régénéré, 1 données périmées.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import generer_donnees_v1 as v1
import generer_donnees_v2 as v2
import yaml

RACINE = v1.RACINE
V3 = RACINE / "05_pme" / "societes" / "calorelle" / "v3"
GENERES = ("dossiers", "messagerie", "planning", "facturation")


# --- commun : manuel et annuaire de v3 -------------------------------------------------------


def commun(etat: v1.Etat) -> None:
    """Le manuel et l'annuaire de v3, et la fiche de l'entreprise, que tout le personnel lit : sa zone
    d'intervention décide d'un refus (manuel, section 6 ; JOURNAL, entrée 99)."""
    for chemin in ("dossiers/commun/manuel_procedures.md", "dossiers/commun/annuaire.md"):
        if chemin not in etat.fichiers:
            raise ValueError(f"fichier absent de v2 : {chemin}")
        del etat.fichiers[chemin]
    v1.commun(etat, V3 / "entreprise")
    etat.ecrire("dossiers/commun/fiche_entreprise.md", (V3 / "entreprise" / "fiche_entreprise.md").read_bytes())


# --- tarif -----------------------------------------------------------------------------------

TARIF: list[tuple[str, str, str, float]] = [
    ("CHG-01", "Chaudière gaz à condensation 25 kW", "unité", 2900.00),
    ("CHG-02", "Chaudière gaz à condensation 35 kW, eau chaude intégrée", "unité", 3600.00),
    ("CHC-01", "Chaudière collective gaz à condensation 150 kW", "unité", 14500.00),
    ("PAC-01", "Pompe à chaleur air-eau 8 kW", "unité", 7800.00),
    ("PAC-02", "Pompe à chaleur air-eau 12 kW", "unité", 9900.00),
    ("CLI-01", "Climatiseur réversible mono-split 3,5 kW, classe A++, pilotable à distance", "unité", 1450.00),
    ("CLI-02", "Unité intérieure supplémentaire du climatiseur réversible", "unité", 690.00),
    ("BAL-01", "Ballon thermodynamique 200 litres", "unité", 2300.00),
    ("RAD-01", "Radiateur à eau chaude", "unité", 380.00),
    ("THE-01", "Thermostat d'ambiance connecté", "unité", 210.00),
    ("DEP-01", "Dépose et évacuation de l'ancien appareil", "forfait", 180.00),
    ("MES-01", "Mise en service", "forfait", 150.00),
    ("TUB-01", "Tuyauterie cuivre posée", "mètre", 42.00),
    ("DES-01", "Désembouage de l'installation de chauffage", "forfait", 420.00),
    ("ELE-01", "Raccordement électrique", "forfait", 160.00),
    ("MO-01", "Main-d'œuvre de technicien", "heure", 58.00),
    ("DEPL-01", "Déplacement hors contrat d'entretien", "forfait", 45.00),
]
ANNEE_TARIF = 2026


def tarif(etat: v1.Etat) -> None:
    lignes = [{"code": c, "libelle": nom, "unite": u, "prix_ht_euros": _nombre(p)} for c, nom, u, p in TARIF]
    etat.ecrire("facturation/tarif.json", v2.json_texte({"annee": ANNEE_TARIF, "lignes": lignes}))


# --- chiffrage, à l'identique de 05_pme/facturation/src/chiffrage.ts -------------------------


def _diviser_arrondi(n: int, d: int) -> int:
    """n / d arrondi au plus proche, la moitié vers le haut (entiers positifs)."""
    return (2 * n + d) // (2 * d)


def _nombre(valeur: float) -> int | float:
    """Un montant tel que JSON.stringify l'écrit : 3200, pas 3200.0."""
    return int(valeur) if float(valeur).is_integer() else valeur


type LigneDemandee = tuple[str, float, float]
"""Code du tarif, quantité, taux de TVA en pour cent."""


def chiffrer(lignes: list[LigneDemandee], remise_pourcent: float = 0) -> dict[str, Any]:
    prix = {c: (nom, round(p * 100)) for c, nom, _, p in TARIF}
    remise = round(remise_pourcent * 100)
    bases: dict[int, int] = {}
    sorties: list[dict[str, Any]] = []
    for code, quantite, taux in lignes:
        libelle, centimes = prix[code]
        centiemes = round(quantite * 100)
        montant = _diviser_arrondi(centiemes * centimes, 100)
        base = montant - _diviser_arrondi(montant * remise, 10000)
        pour_mille = round(taux * 10)
        bases[pour_mille] = bases.get(pour_mille, 0) + base
        sorties.append(
            {
                "code": code,
                "libelle": libelle,
                "quantite": _nombre(centiemes / 100),
                "prix_unitaire_ht_euros": _nombre(centimes / 100),
                "taux_tva": _nombre(taux),
                "montant_ht_euros": _nombre(montant / 100),
            }
        )
    ht = sum(bases.values())
    tva = sum(_diviser_arrondi(base * pour_mille, 1000) for pour_mille, base in bases.items())
    return {
        "lignes": sorties,
        "total_ht_euros": _nombre(ht / 100),
        "total_tva_euros": _nombre(tva / 100),
        "total_ttc_euros": _nombre((ht + tva) / 100),
    }


# --- devis de 2025 et 2026 -------------------------------------------------------------------


@dataclass(frozen=True)
class DevisHistorique:
    numero: str
    client: str
    objet: str
    cree: date
    lignes: list[LigneDemandee]
    statut: str
    envoye: date | None = None
    reponse: date | None = None


CHAUDIERE = "Remplacement de chaudière gaz"
PAC = "Pompe à chaleur air-eau"
CLIM = "Climatisation réversible"
CHAUFFERIE = "Rénovation de chaufferie collective"


def chaudiere(modele: str = "CHG-01", metres: float = 4, heures: float = 6) -> list[LigneDemandee]:
    """Chaudière au gaz : 20 % sur tout (manuel, section 6)."""
    return [(modele, 1, 20), ("DEP-01", 1, 20), ("TUB-01", metres, 20), ("MES-01", 1, 20), ("MO-01", heures, 20)]


def pac(modele: str = "PAC-01", metres: float = 10, heures: float = 12) -> list[LigneDemandee]:
    """Pompe à chaleur air-eau : 5,5 % sur la pose et les travaux liés (manuel, section 6)."""
    return [
        (modele, 1, 5.5),
        ("DEP-01", 1, 5.5),
        ("TUB-01", metres, 5.5),
        ("ELE-01", 1, 5.5),
        ("MES-01", 1, 5.5),
        ("MO-01", heures, 5.5),
    ]


def clim(unites: int = 2, heures: float = 8) -> list[LigneDemandee]:
    """Climatisation dans un local professionnel : 20 % sur tout (manuel, section 6)."""
    return [("CLI-01", 1, 20), ("CLI-02", unites, 20), ("ELE-01", 1, 20), ("TUB-01", 6, 20), ("MO-01", heures, 20)]


def clim_avant_juillet_2026(unites: int = 2, heures: float = 8) -> list[LigneDemandee]:
    """Climatisation chez un particulier avant le 18 juillet 2026 : l'appareil à 20 %, exclu du
    taux réduit, et son installation à 10 % (article 279-0 bis du CGI ; BOFiP,
    BOI-TVA-LIQ-30-20-90-20, § 50 et § 100, lu le 2026-10-08). Depuis, l'arrêté du 13 juillet 2026
    la met à 5,5 % (manuel, section 6)."""
    return [("CLI-01", 1, 20), ("CLI-02", unites, 20), ("ELE-01", 1, 10), ("TUB-01", 6, 10), ("MO-01", heures, 10)]


def chaufferie(chaudieres: int = 1, heures: float = 40) -> list[LigneDemandee]:
    """Chaudière collective au gaz : 20 % sur tout (manuel, section 6)."""
    return [
        ("CHC-01", chaudieres, 20),
        ("DEP-01", chaudieres, 20),
        ("TUB-01", 20 * chaudieres, 20),
        ("MES-01", 1, 20),
        ("MO-01", heures, 20),
    ]


J = date
HISTORIQUE = [
    # 2025 : tous ont reçu leur réponse.
    DevisHistorique(
        "DV-2025-001",
        "c-0003",
        CHAUFFERIE,
        J(2025, 4, 14),
        chaufferie(2, 64),
        "accepte",
        J(2025, 4, 15),
        J(2025, 5, 12),
    ),
    DevisHistorique(
        "DV-2025-002", "c-0025", CHAUFFERIE, J(2025, 5, 20), chaufferie(1, 40), "refuse", J(2025, 5, 21), J(2025, 6, 30)
    ),
    DevisHistorique(
        "DV-2025-003", "c-0076", CHAUFFERIE, J(2025, 6, 9), chaufferie(2, 60), "accepte", J(2025, 6, 10), J(2025, 7, 1)
    ),
    DevisHistorique(
        "DV-2025-004",
        "c-0032",
        CLIM,
        J(2025, 6, 16),
        clim_avant_juillet_2026(2),
        "accepte",
        J(2025, 6, 16),
        J(2025, 6, 25),
    ),
    DevisHistorique(
        "DV-2025-005",
        "c-0036",
        CHAUDIERE,
        J(2025, 7, 7),
        chaudiere("CHG-02", 6, 7),
        "accepte",
        J(2025, 7, 7),
        J(2025, 7, 15),
    ),
    DevisHistorique(
        "DV-2025-006", "c-0092", CHAUFFERIE, J(2025, 9, 1), chaufferie(1, 36), "refuse", J(2025, 9, 2), J(2025, 10, 20)
    ),
    DevisHistorique(
        "DV-2025-007", "c-0043", CHAUDIERE, J(2025, 9, 22), chaudiere(), "refuse", J(2025, 9, 22), J(2025, 10, 6)
    ),
    DevisHistorique(
        "DV-2025-008",
        "c-0059",
        CHAUDIERE,
        J(2025, 10, 13),
        chaudiere("CHG-02"),
        "accepte",
        J(2025, 10, 13),
        J(2025, 10, 27),
    ),
    DevisHistorique(
        "DV-2025-009",
        "c-0180",
        CHAUFFERIE,
        J(2025, 11, 3),
        chaufferie(1, 44),
        "accepte",
        J(2025, 11, 4),
        J(2025, 12, 15),
    ),
    DevisHistorique(
        "DV-2025-010", "c-0086", CHAUDIERE, J(2025, 12, 1), chaudiere(), "accepte", J(2025, 12, 1), J(2025, 12, 10)
    ),
    # 2026, numérotés dans l'ordre de leur création, comme le fait le service. Sans réponse depuis
    # plus de 30 jours au 2 novembre : 004, 008, 009. Envoyés depuis moins de 30 jours : 010, 011,
    # 012. Jamais envoyé : 007. Pour c-0094, 010 suit 002, refusé.
    DevisHistorique("DV-2026-001", "c-0093", PAC, J(2026, 1, 19), pac(), "accepte", J(2026, 1, 19), J(2026, 2, 2)),
    DevisHistorique("DV-2026-002", "c-0094", PAC, J(2026, 3, 2), pac(), "refuse", J(2026, 3, 2), J(2026, 3, 30)),
    DevisHistorique(
        "DV-2026-003", "c-0097", PAC, J(2026, 4, 13), pac("PAC-02", 12, 14), "accepte", J(2026, 4, 14), J(2026, 4, 27)
    ),
    DevisHistorique("DV-2026-004", "c-0103", CHAUDIERE, J(2026, 6, 15), chaudiere(), "envoye", J(2026, 6, 15)),
    DevisHistorique(
        "DV-2026-005",
        "c-0115",
        CLIM,
        J(2026, 6, 29),
        clim_avant_juillet_2026(1, 6),
        "refuse",
        J(2026, 6, 29),
        J(2026, 7, 20),
    ),
    DevisHistorique("DV-2026-006", "c-0117", PAC, J(2026, 7, 6), pac(), "accepte", J(2026, 7, 6), J(2026, 8, 31)),
    DevisHistorique("DV-2026-007", "c-0017", CLIM, J(2026, 9, 7), clim(3, 10), "brouillon"),
    DevisHistorique("DV-2026-008", "c-0207", CHAUFFERIE, J(2026, 9, 14), chaufferie(1, 40), "envoye", J(2026, 9, 15)),
    DevisHistorique("DV-2026-009", "c-0020", CLIM, J(2026, 9, 21), clim(2, 8), "envoye", J(2026, 9, 28)),
    DevisHistorique("DV-2026-010", "c-0094", PAC, J(2026, 10, 12), pac("PAC-02", 12, 16), "envoye", J(2026, 10, 12)),
    DevisHistorique(
        "DV-2026-011", "c-0126", CHAUDIERE, J(2026, 10, 19), chaudiere("CHG-02", 5, 6), "envoye", J(2026, 10, 20)
    ),
    DevisHistorique("DV-2026-012", "c-0223", CHAUFFERIE, J(2026, 10, 26), chaufferie(2, 70), "envoye", J(2026, 10, 27)),
]


def _horodatage(jour: date | None, heure: int) -> str | None:
    return None if jour is None else v2.instant(jour, heure).isoformat(timespec="seconds")


def _fiche_client(etat: v1.Etat, code: str) -> dict[str, str]:
    contenu = etat.fichiers[f"dossiers/clients/{code}/fiche_client.yaml"].decode("utf-8")
    return cast(dict[str, str], yaml.safe_load(contenu))


def _euros_long(montant: float) -> str:
    entier, decimales = f"{montant:,.2f}".split(".")
    return f"{entier.replace(',', ' ')},{decimales} €"


def _nombre_fr(valeur: float) -> str:
    return str(_nombre(valeur)).replace(".", ",")


def lignes_pdf(devis: dict[str, Any], client: dict[str, str]) -> list[str]:
    """Les lignes du PDF d'un devis, à l'identique de lignesPdfDevis (05_pme/facturation)."""
    jour = date.fromisoformat(str(devis["cree_le"])[:10])
    return [
        f"DEVIS {devis['numero']}",
        f"Client : {client['nom']} ({devis['client']})",
        *([f"Adresse : {client['adresse']}"] if client.get("adresse") else []),
        f"Date : {jour.day} {v1.MOIS[jour.month - 1]} {jour.year}",
        f"Objet : {devis['objet']}",
        "",
        *(
            f"{ligne['code']} {ligne['libelle']} : {_nombre_fr(ligne['quantite'])} × "
            f"{_euros_long(ligne['prix_unitaire_ht_euros'])} = {_euros_long(ligne['montant_ht_euros'])} HT, "
            f"TVA {_nombre_fr(ligne['taux_tva'])} %"
            for ligne in devis["lignes"]
        ),
        *([f"Remise : {_nombre_fr(devis['remise_pourcent'])} % sur chaque ligne"] if devis["remise_pourcent"] else []),
        "",
        f"Total HT : {_euros_long(devis['total_ht_euros'])}",
        f"TVA : {_euros_long(devis['total_tva_euros'])}",
        f"Total TTC : {_euros_long(devis['total_ttc_euros'])}",
    ]


def charge_d_affaires(etat: v1.Etat, code: str) -> str:
    return _fiche_client(etat, code)["charge_d_affaires"]


def devis(etat: v1.Etat) -> None:
    for h in HISTORIQUE:
        chiffrage = chiffrer(h.lignes)
        fiche = {
            "numero": h.numero,
            "client": h.client,
            "objet": h.objet,
            "lignes": chiffrage["lignes"],
            "remise_pourcent": 0,
            "total_ht_euros": chiffrage["total_ht_euros"],
            "total_tva_euros": chiffrage["total_tva_euros"],
            "total_ttc_euros": chiffrage["total_ttc_euros"],
            "statut": h.statut,
            "cree_le": _horodatage(h.cree, 10),
            "cree_par": charge_d_affaires(etat, h.client),
            "envoye_le": _horodatage(h.envoye, 11),
            "reponse_le": _horodatage(h.reponse, 15),
        }
        etat.ecrire(f"facturation/devis/{h.numero}.json", v2.json_texte(fiche))
        annee = h.numero[3:7]
        v2.remplacer(
            etat,
            f"dossiers/commercial/devis/{annee}/{h.numero.lower()}.pdf",
            v1.pdf(lignes_pdf(fiche, _fiche_client(etat, h.client))),
        )


# --- assemblage ------------------------------------------------------------------------------


def construire() -> v1.Etat:
    """v2 en mémoire, puis les ajouts de v3, dans un ordre fixe."""
    etat = v2.construire()
    commun(etat)
    tarif(etat)
    devis(etat)
    return etat


def ecarts(etat: v1.Etat) -> list[str]:
    """Différences entre les données présentes dans v3 et une génération fraîche."""
    with tempfile.TemporaryDirectory() as dossier:
        frais = Path(dossier)
        v1.ecrire(etat, frais)
        messages: list[str] = []
        for partie in GENERES:
            attendus = {p.relative_to(frais) for p in (frais / partie).rglob("*") if p.is_file()}
            presents: set[Path] = set()
            if (V3 / partie).exists():
                presents = {p.relative_to(V3) for p in (V3 / partie).rglob("*") if p.is_file()}
            messages += [f"absent : {p}" for p in sorted(attendus - presents)]
            messages += [f"en trop : {p}" for p in sorted(presents - attendus)]
            messages += [
                f"différent : {p}"
                for p in sorted(attendus & presents)
                if not filecmp.cmp(frais / p, V3 / p, shallow=False)
            ]
        return messages


def main() -> int:
    analyse = argparse.ArgumentParser(description=(__doc__ or "Génère les données v3.").splitlines()[0])
    analyse.add_argument("--verifier", action="store_true", help="contrôle sans rien écrire")
    args = analyse.parse_args()
    etat = construire()
    if args.verifier:
        messages = ecarts(etat)
        if messages:
            print(f"Données v3 à régénérer ({len(messages)} écart(s)) :", file=sys.stderr)
            for message in messages[:20]:
                print(f"  {message}", file=sys.stderr)
            return 1
        print(f"Données v3 à jour ({len(etat.fichiers)} fichiers).")
        return 0
    for partie in GENERES:
        shutil.rmtree(V3 / partie, ignore_errors=True)
    v1.ecrire(etat, V3)
    print(f"Données v3 générées : {len(etat.fichiers)} fichiers dans {V3.relative_to(RACINE)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
