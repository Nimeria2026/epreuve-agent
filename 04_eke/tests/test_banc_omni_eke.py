"""EKE sur OmniExtractBench : la forme canonique, la vérité notée, le plafond de lecture, le texte
lu et les agrégats, sur des cas écrits à la main (la comparaison à l'original est dans
`test_banc_omni_reference_eke.py`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eke.banc_public.conversion import markdown_flux
from eke.banc_public.omni.conversion import lire_flux
from eke.banc_public.omni.jeu import Document, charger, chemin_manifeste_lu, garder
from eke.banc_public.omni.mesure import ResultatDocument, bootstrap, bootstrap_unifie, scores
from eke.banc_public.omni.plafond import chercher, sans_bords, tailles
from eke.banc_public.omni.valeurs import cle, ne_dit_rien
from eke.banc_public.omni.verite import Adresse, valeurs_de_la_verite
from eke.banc_public.telechargement import EcartJeu, Entree, Manifeste, chemin_manifeste
from fabrique_pdf import PageDeTest, Texte, fabriquer_pdf


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("1,234", "1234"), ("$1,234.56", "1234.56"), ("12.34%", "12.34"), ("5.00", "5"),
        ("(1,234.56)", "-1234.56"), ("1234.56-", "-1234.56"), ("−1234.56", "-1234.56"),
        ("31/10/2024", "2024-10-31"), ("Oct 31, 2024", "2024-10-31"), ("2024-10-31T00:00:00Z", "2024-10-31"),
        ("ACME CORP", "Acme Corp"), ("Acme  Corp.", "Acme Corp"), ("TRUE", True), ("31-1440073", "311440073"),
    ],
)  # fmt: skip
def test_ce_que_le_banc_replie(a: object, b: object) -> None:
    """La liste « Folded » de METRIC_SPEC, §2."""
    assert cle(a) == cle(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [("USD 1234.56", "1234.56"), ("1.234,56", "1234.56"), ("2024-10-31T09:00:00Z", "2024-10-31"), ("yes", True)],
)
def test_ce_que_le_banc_ne_replie_pas(a: object, b: object) -> None:
    """La liste « Not folded » de METRIC_SPEC, §2."""
    assert cle(a) != cle(b)


def test_un_identifiant_reste_exact() -> None:
    assert cle("02000") != cle("2000")
    assert cle("8303911426") != cle("8303911427")


def test_ce_qui_ne_dit_rien() -> None:
    assert [ne_dit_rien(v) for v in (None, "", "   ", 0, False, "n/a", "0")] == [
        True, True, True, False, False, False, False,
    ]  # fmt: skip


def test_la_verite_notee() -> None:
    schema = {"properties": {"ouvert": {"type": "object", "additionalProperties": True}}}
    verite = {"date": "2024-03-31", "lignes": [{"x": 1}, {"x": None}], "note": None, "ouvert": {"a": 1}}
    assert valeurs_de_la_verite(verite, schema) == {
        (("k", "date"),): "2024-03-31",
        (("k", "lignes"), ("i", 0), ("k", "x")): 1,
    }
    with pytest.raises(ValueError, match="schéma"):
        valeurs_de_la_verite(verite, {})


def test_le_plafond_cherche_les_valeurs_dans_le_texte() -> None:
    texte = "Invoice INV-4417 issued Mar 31, 2024\nTotal due $1,240.00\nMale 29,023 +/-678 52.3%"
    valeurs: dict[Adresse, object] = {
        (("k", "id"),): "INV-4417",
        (("k", "date"),): "2024-03-31",
        (("k", "total"),): 1240.0,
        (("k", "marge"),): 678,
        (("k", "part"),): 52.3,
        (("k", "absent"),): "Hex bolt",
        (("k", "calcule"),): True,
    }
    trouvees = {a[0][1]: v.trouvee for a, v in zip(valeurs, chercher(texte, valeurs), strict=True)}
    assert trouvees == {
        "id": True, "date": True, "total": True, "marge": True, "part": True, "absent": False, "calcule": False,
    }  # fmt: skip


def test_les_bords_et_les_tailles() -> None:
    assert sans_bords("+/-678") == "678"
    assert sans_bords("(N/A)") == "N/A"
    assert sans_bords("--") == ""
    assert list(tailles(1)) == [1, 2]
    assert list(tailles(3)) == [2, 3, 4]
    assert list(tailles(1, "#d2024-10-31")) == [1, 2, 3]
    assert list(tailles(5, "#t2024-10-31T09:00:00.000000")) == [1, 2, 3, 4, 5, 6]


def test_le_texte_lu_est_celui_de_lire_document() -> None:
    pages = [
        PageDeTest([Texte(56, 760, "Total due"), Texte(300, 760, "1,240.00")]),
        PageDeTest([]),
        PageDeTest([Texte(56, 760, "Seconde page.")]),
    ]
    donnees = fabriquer_pdf(pages)
    lu = lire_flux(donnees)
    assert lu.texte == markdown_flux(donnees)
    assert (lu.pages, lu.pages_sans_texte, lu.illisible) == (3, 1, False)
    assert lire_flux(b"pas un PDF").illisible


def _resultat(suite: str, valeurs: int, trouvees: int) -> ResultatDocument:
    return ResultatDocument("d", suite, 1, 0, False, valeurs, trouvees)


def test_les_agregats() -> None:
    resultats = [
        _resultat("extractbench", 10, 10),
        _resultat("extractbench", 10, 0),
        _resultat("internal", 4, 3),
        _resultat("longarray", 100, 50),
        _resultat("micro1", 1000, 900),
    ]
    lignes = {s.categorie: s for s in scores(resultats)}
    assert lignes["extractbench"].plafond == 0.5
    assert lignes["toutes"].plafond == pytest.approx((1 + 0 + 0.75 + 0.5 + 0.9) / 5)
    assert lignes["unifie"].plafond == pytest.approx((0.5 + 0.75 + 0.5 + 0.9) / 4)
    assert lignes["toutes"].part_des_valeurs == pytest.approx(963 / 1124)
    assert bootstrap([0.5] * 4) == (0.5, 0.5)
    assert bootstrap_unifie({"a": [1.0], "b": [0.0]}) == (0.5, 0.5)


def test_le_manifeste_lu_doit_venir_du_parquet_range(tmp_path: Path) -> None:
    revision = "725aaa6e04f3097383527beca6640015b395772d"
    manifeste = Manifeste(
        "datalab-to/omni_extract_bench",
        revision,
        "api",
        "2026-10-10T00:00:00Z",
        (
            Entree("manifest.parquet", "s", revision, 1, "a" * 64),
            Entree("pdfs/d.pdf", "s", revision, 1, "b" * 64),
            Entree("gold/d.json", "s", revision, 1, "c" * 64),
        ),
    )
    chemin_manifeste(tmp_path, revision).write_text(manifeste.en_json(), encoding="utf-8")
    ligne = {"doc_id": "d", "doc_path": "pdfs/d.pdf", "gt_path": "gold/d.json", "suite": "internal", "schema": "{}"}
    lu = {"source_sha256": "a" * 64, "documents": [ligne]}
    chemin_manifeste_lu(tmp_path, revision).write_text(json.dumps(lu), encoding="utf-8")
    documents = charger(tmp_path, revision)
    assert documents == [
        Document("d", "internal", tmp_path / "725aaa6" / "pdfs/d.pdf", tmp_path / "725aaa6" / "gold/d.json", {})
    ]
    lu["source_sha256"] = "f" * 64
    chemin_manifeste_lu(tmp_path, revision).write_text(json.dumps(lu), encoding="utf-8")
    with pytest.raises(EcartJeu, match="ne vient pas"):
        charger(tmp_path, revision)


def test_ce_qu_eke_range() -> None:
    assert garder("pdfs/a b.pdf") and garder("gold/a.json") and garder("manifest.parquet")
    assert not garder("assets/charts.svg") and not garder("manifests/sample40.parquet")
