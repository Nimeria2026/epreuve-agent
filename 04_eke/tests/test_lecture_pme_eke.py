"""EKE sur les PDF de la PME, états v2 et v3, vérifié contre des vérités qui ne viennent pas de lui :

- le texte que le PDF trace (chaînes des opérateurs Tj de son flux), ligne pour ligne ;
- la relecture de chaque zone citée par PDFium, indépendante de la mise en page d'EKE ;
- l'échéancier des factures fournisseurs que tient le comptable (v3) ;
- les fiches JSON des devis que garde le service de facturation (v3).

Les étiquettes de Calorelle (« Total TTC », « Date de facture ») ne sont écrites qu'ici, dans
les tests : EKE ne les connaît pas.
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from eke.contrat import ecarts, racine_depot, schema
from eke.geometrie import Zone
from eke.lecture import Lecture, lire, sortie_citations, sortie_lignes, sortie_valeurs
from eke.pdfium import texte_dans_zone
from jsonschema import Draft202012Validator

DONNEES = racine_depot() / "05_pme" / "societes" / "calorelle"
ETATS = ["v2", "v3"]
CHAINE_TJ = re.compile(rb"\(((?:\\[\\()]|[^\\()])*)\) Tj")
DEBORDENT = {
    "v3/dossiers/commercial/devis/2025/dv-2025-004.pdf",
    "v3/dossiers/commercial/devis/2025/dv-2025-005.pdf",
    "v3/dossiers/commercial/devis/2025/dv-2025-008.pdf",
    "v3/dossiers/commercial/devis/2026/dv-2026-005.pdf",
    "v3/dossiers/commercial/devis/2026/dv-2026-007.pdf",
    "v3/dossiers/commercial/devis/2026/dv-2026-009.pdf",
    "v3/dossiers/commercial/devis/2026/dv-2026-011.pdf",
}
"""Devis de v3 dont la première ligne sort de la page à droite (jusqu'à 669,83 points pour 595) :
la fin, taux de TVA compris, ne s'affiche pas. Défaut des données de la PME, trouvé par ces tests
le 2026-10-08 et signalé (journal de l'étape 6) ; EKE rend la zone telle qu'elle est. Une fois les
données corrigées, ce test échoue tant que la liste n'est pas vidée."""


def _pdfs(etat: str) -> list[Path]:
    return sorted((DONNEES / etat / "dossiers").rglob("*.pdf"))


@cache
def _lecture(chemin: Path) -> Lecture:
    return lire(chemin.relative_to(DONNEES).as_posix(), chemin.read_bytes())


def _chaines_tracees(donnees: bytes) -> list[str]:
    """Les textes que le flux du PDF trace, dans l'ordre, sans les chaînes vides.

    PDFium lit l'octet 0xA0 de WinAnsi (espace insécable) comme une espace simple : la PME en met
    dans ses montants (« 1 070,00 € »), le texte attendu suit PDFium sur ce point.
    """
    brutes = [
        m.group(1).replace(rb"\(", b"(").replace(rb"\)", b")").replace(rb"\\", b"\\")
        for m in CHAINE_TJ.finditer(donnees)
    ]
    return [b.decode("cp1252").replace("\u00a0", " ") for b in brutes if b]


def _valeurs(chemin: Path) -> dict[str, dict[str, Any]]:
    """Les valeurs d'un document, par étiquette ; une étiquette en double fait échouer le test."""
    valeurs = sortie_valeurs(_lecture(chemin))["valeurs"]
    par_etiquette = {v["etiquette"]: v for v in valeurs}
    assert len(par_etiquette) == len(valeurs), chemin
    return par_etiquette


def _euros(texte: str) -> str:
    """« 1 284,00 € » de l'échéancier, en décimal à point, calculé sans EKE."""
    nombre = re.sub(r"[\s  €]", "", texte).replace(",", ".")
    return str(Decimal(nombre).quantize(Decimal("0.01")))


def test_le_contrat_est_un_schema_valide() -> None:
    Draft202012Validator.check_schema(schema())
    assert schema()["title"] == "LectureDocument"


@pytest.mark.parametrize("etat", ETATS)
def test_chaque_pdf_se_lit_comme_il_est_trace(etat: str) -> None:
    pdfs = _pdfs(etat)
    assert len(pdfs) > 200
    for chemin in pdfs:
        sortie = sortie_lignes(_lecture(chemin))
        assert ecarts(sortie) == []
        assert [ligne["texte"] for ligne in sortie["lignes"]] == _chaines_tracees(chemin.read_bytes()), chemin
        assert sortie["document"]["pages"] == [{"numero": 1, "largeur": 595.0, "hauteur": 842.0}]


def _blancs_simples(texte: str) -> str:
    return " ".join(texte.split())


@pytest.mark.parametrize("etat", ETATS)
def test_chaque_zone_citee_est_relue_par_pdfium(etat: str) -> None:
    """Le texte que PDFium trouve dans la zone est celui qu'EKE cite, aux blancs près."""
    debordent: set[str] = set()
    for chemin in _pdfs(etat):
        lecture = _lecture(chemin)
        page = lecture.pages[0]
        citations = [*sortie_lignes(lecture)["lignes"], *(v["citation"] for v in sortie_valeurs(lecture)["valeurs"])]
        for citation in citations:
            zone = Zone(**citation["zone"])
            if not Zone(0, 0, page.largeur, page.hauteur).contient(zone):
                assert zone.x0 >= 0 and zone.y0 >= 0 and zone.y1 <= page.hauteur < zone.x1 + page.hauteur
                debordent.add(lecture.chemin)
            relu = texte_dans_zone(chemin.read_bytes(), citation["page"], zone)
            assert _blancs_simples(relu) == _blancs_simples(citation["texte"]), (chemin, citation)
    assert debordent == {c for c in DEBORDENT if c.startswith(f"{etat}/")}


def _echeancier() -> list[dict[str, str]]:
    texte = (DONNEES / "v3" / "dossiers" / "administration" / "echeancier_fournisseurs.md").read_text(encoding="utf-8")
    lignes = [ligne for ligne in texte.splitlines() if ligne.startswith("| ") and not ligne.startswith("| Fournisseur")]
    colonnes = ["fournisseur", "facture", "date", "ttc"]
    return [dict(zip(colonnes, [c.strip() for c in ligne.strip("|").split("|")][:4], strict=True)) for ligne in lignes]


def test_factures_fournisseurs_contre_l_echeancier_du_comptable() -> None:
    lignes = _echeancier()
    assert len(lignes) == 18
    for ligne in lignes:
        (chemin,) = (DONNEES / "v3" / "dossiers" / "administration" / "factures_fournisseurs").glob(
            f"*/*_{ligne['facture'].lower()}.pdf"
        )
        valeurs = _valeurs(chemin)
        jour, mois, annee = (int(x) for x in ligne["date"].split("/"))
        assert valeurs["FACTURE"]["valeur"] == ligne["facture"]
        assert valeurs["Fournisseur"]["valeur"] == ligne["fournisseur"]
        assert valeurs["Date de facture"]["type"] == "date"
        assert valeurs["Date de facture"]["valeur"] == date(annee, mois, jour).isoformat()
        assert valeurs["Total TTC"]["type"] == "montant"
        assert valeurs["Total TTC"]["valeur"] == _euros(ligne["ttc"])
        assert valeurs["Règlement par virement, IBAN"]["type"] == "iban"


@pytest.mark.parametrize("etat", ETATS)
def test_chaque_facture_fournisseur_tombe_juste(etat: str) -> None:
    """Somme des lignes qui finissent par « HT » égale au total hors taxes ; hors taxes et TVA égaux au TTC."""
    dossier = DONNEES / etat / "dossiers" / "administration" / "factures_fournisseurs"
    factures = sorted(dossier.rglob("*.pdf"))
    assert len(factures) == 18
    for chemin in factures:
        valeurs = _valeurs(chemin)
        lignes = [
            Decimal(v["valeur"])
            for v in valeurs.values()
            if v["type"] == "montant" and v["citation"]["texte"].endswith("HT")
        ]
        (tva,) = (v for e, v in valeurs.items() if e.startswith("TVA "))
        hors_taxes = Decimal(valeurs["Total hors taxes"]["valeur"])
        assert lignes and sum(lignes) == hors_taxes, chemin
        assert hors_taxes + Decimal(tva["valeur"]) == Decimal(valeurs["Total TTC"]["valeur"]), chemin


def test_devis_contre_le_service_de_facturation() -> None:
    fiches = sorted((DONNEES / "v3" / "facturation" / "devis").glob("DV-*.json"))
    assert len(fiches) == 22
    for fiche_json in fiches:
        fiche = json.loads(fiche_json.read_text(encoding="utf-8"))
        numero: str = fiche["numero"]
        chemin = DONNEES / "v3" / "dossiers" / "commercial" / "devis" / numero[3:7] / f"{numero.lower()}.pdf"
        valeurs = _valeurs(chemin)
        assert valeurs["DEVIS"]["valeur"] == numero
        assert valeurs["Objet"]["valeur"] == fiche["objet"]
        assert valeurs["Date"]["valeur"] == fiche["cree_le"][:10]
        for etiquette, champ in (
            ("Total HT", "total_ht_euros"),
            ("TVA", "total_tva_euros"),
            ("Total TTC", "total_ttc_euros"),
        ):
            assert valeurs[etiquette]["type"] == "montant"
            assert Decimal(valeurs[etiquette]["valeur"]) == Decimal(str(fiche[champ])), (numero, etiquette)


def test_citer_retrouve_une_valeur_et_rien_d_autre() -> None:
    chemin = (
        DONNEES
        / "v3"
        / "dossiers"
        / "administration"
        / "factures_fournisseurs"
        / "2026-10"
        / "thermopieces-loire_f-2026-1151.pdf"
    )
    lecture = _lecture(chemin)
    total = _valeurs(chemin)["Total TTC"]["citation"]
    assert sortie_citations(lecture, "512,40 €")["citations"] == [total]
    assert sortie_citations(lecture, "  512,40 € ")["citations"] == [total]
    assert sortie_citations(lecture, "512,41 €")["citations"] == []
    assert sortie_citations(lecture, "total ttc")["citations"] == []
    assert len(sortie_citations(lecture, "427,00 €")["citations"]) == 2
