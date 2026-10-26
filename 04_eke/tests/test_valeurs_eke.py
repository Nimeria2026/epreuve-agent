"""Paires étiquette-valeur : types et normalisation à la française, puis les quatre règles."""

from __future__ import annotations

import pytest
from eke.geometrie import Zone
from eke.mise_en_page import Morceau
from eke.valeurs import Valeur, typer, valeurs_de_ligne


def _morceau(texte: str, x: float = 56.0) -> Morceau:
    """Un morceau fictif : un caractère tous les 6 points, rien pour une espace."""
    zones = tuple(None if c == " " else Zone(x + 6 * i, 100, x + 6 * (i + 1), 112) for i, c in enumerate(texte))
    return Morceau(1, texte, zones)


def _ligne(*textes: str) -> list[Morceau]:
    """Des morceaux sur une ligne, chacun 200 points plus à droite que le précédent."""
    return [_morceau(t, 56 + 200 * rang) for rang, t in enumerate(textes)]


def _paires(ligne: list[Morceau]) -> list[tuple[str, str, str, str | None, str]]:
    return [(v.etiquette, v.type, v.valeur, v.unite, v.texte) for v in valeurs_de_ligne(ligne)]


@pytest.mark.parametrize(
    ("texte", "type_", "valeur"),
    [
        ("512,40 €", "montant", "512.40"),
        ("1 284,00 €", "montant", "1284.00"),
        ("1 284,00 €", "montant", "1284.00"),
        ("1.284,00 €", "montant", "1284.00"),
        ("12,5 EUR", "montant", "12.50"),
        ("-120,00 €", "montant", "-120.00"),
        ("1 450 000 €", "montant", "1450000.00"),
        ("427,00 € HT", "montant", "427.00"),
        ("7 840,00 € TTC", "montant", "7840.00"),
        ("17 octobre 2026", "date", "2026-10-17"),
        ("1er décembre 2026", "date", "2026-12-01"),
        ("lundi 2 novembre 2026", "date", "2026-11-02"),
        ("17/10/2026", "date", "2026-10-17"),
        ("2026-10-17", "date", "2026-10-17"),
        ("FR76 9999 9473 4676 8262 5560 200", "iban", "FR7699999473467682625560200"),
        ("20 %", "pourcentage", "20"),
        ("5,5 %", "pourcentage", "5.5"),
    ],
)
def test_typer_reconnait_et_normalise(texte: str, type_: str, valeur: str) -> None:
    typage = typer(texte)
    assert typage is not None
    assert (typage.type, typage.valeur) == (type_, valeur)
    assert typage.unite == {"montant": "EUR", "pourcentage": "%"}.get(type_)


@pytest.mark.parametrize(
    "texte",
    [
        "512.40 €",  # point décimal ou séparateur de milliers : on ne sait pas
        "31 février 2026",  # date impossible
        "45999 Valmont-sur-Loire",
        "FR76 9999",  # trop court pour un IBAN
        "Thermopièces Loire",
        "1 × 2 900,00 € = 2 900,00 € HT",  # plusieurs valeurs : du texte
    ],
)
def test_typer_laisse_le_reste_en_texte(texte: str) -> None:
    assert typer(texte) is None


def test_regle_1_deux_points() -> None:
    assert _paires(_ligne("Total TTC : 512,40 €")) == [("Total TTC", "montant", "512.40", "EUR", "512,40 €")]
    assert _paires(_ligne("Fournisseur : Thermopièces Loire")) == [
        ("Fournisseur", "texte", "Thermopièces Loire", None, "Thermopièces Loire")
    ]
    assert _paires(_ligne("TVA 20 % : 85,40 €")) == [("TVA 20 %", "montant", "85.40", "EUR", "85,40 €")]
    assert _paires(_ligne("Heure : 9:30")) == [("Heure", "texte", "9:30", None, "9:30")]
    assert _paires(_ligne("Rendez-vous à 9:30")) == []


def test_regle_1_etiquette_seule_prend_le_morceau_suivant() -> None:
    assert _paires(_ligne("Total TTC :", "189,90 €")) == [("Total TTC", "montant", "189.90", "EUR", "189,90 €")]


def test_regle_2_colonne_de_droite() -> None:
    assert _paires(_ligne("Total HT", "180,00 €")) == [("Total HT", "montant", "180.00", "EUR", "180,00 €")]
    assert _paires(_ligne("Thermostat d'ambiance", "2", "180,00 €")) == [
        ("Thermostat d'ambiance", "montant", "180.00", "EUR", "180,00 €")
    ]
    assert _paires(_ligne("TVA 5,5 %", "9,90 €")) == [("TVA 5,5 %", "montant", "9.90", "EUR", "9,90 €")]
    assert _paires(_ligne("Désignation", "Qté", "Montant HT")) == []
    assert _paires(_ligne("17 octobre 2026")) == []


def test_regle_3_fin_typee() -> None:
    assert _paires(_ligne("Règlement par virement, IBAN FR76 9999 9473 4676 8262 5560 200")) == [
        (
            "Règlement par virement, IBAN",
            "iban",
            "FR7699999473467682625560200",
            None,
            "FR76 9999 9473 4676 8262 5560 200",
        )
    ]
    assert _paires(_ligne("Fait à Valmont-sur-Loire, le 12 juin 2026")) == [
        ("Fait à Valmont-sur-Loire, le", "date", "2026-06-12", None, "12 juin 2026")
    ]
    assert _paires(_ligne("Taux de TVA 10 %")) == [("Taux de TVA", "pourcentage", "10", "%", "10 %")]


def test_regle_4_reference_ou_numero() -> None:
    assert _paires(_ligne("FACTURE F-2026-1151")) == [("FACTURE", "texte", "F-2026-1151", None, "F-2026-1151")]
    assert _paires(_ligne("DEVIS DV-2026-004")) == [("DEVIS", "texte", "DV-2026-004", None, "DV-2026-004")]
    assert _paires(_ligne("Facture n° 2026-123")) == [("Facture n°", "texte", "2026-123", None, "2026-123")]
    assert _paires(_ligne("BUDGET PRÉVISIONNEL 2027")) == []
    assert _paires(_ligne("CURRICULUM VITAE")) == []


def test_la_citation_situe_la_valeur_dans_son_morceau() -> None:
    ligne = _ligne("Total TTC : 512,40 €")
    (valeur,) = valeurs_de_ligne(ligne)
    assert isinstance(valeur, Valeur)
    assert valeur.morceau is ligne[0]
    assert valeur.morceau.texte[valeur.debut : valeur.fin] == "512,40 €"
    assert valeur.morceau.zone_de(valeur.debut, valeur.fin) == Zone(56 + 6 * 12, 100, 56 + 6 * 20, 112)
