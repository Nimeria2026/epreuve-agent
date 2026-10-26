"""Le serveur MCP d'EKE de bout en bout : lancé en stdio, interrogé par un client MCP comme celui
d'EASE, sur l'état v3 de la PME."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from eke.contrat import ecarts, racine_depot, schema
from eke.droits import Dossiers, RefusEke
from eke.pdfium import DocumentIllisible
from eke.serveur import appeler
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, Implementation, ListToolsResult, TextContent

V3 = racine_depot() / "05_pme" / "societes" / "calorelle" / "v3"
FACTURE = "administration/factures_fournisseurs/2026-10/thermopieces-loire_f-2026-1151.pdf"


def _session(pour: str, appels: list[tuple[str, dict[str, Any]]]) -> tuple[ListToolsResult, list[CallToolResult]]:
    """Lance EKE pour cette personne, liste ses outils, puis fait les appels dans l'ordre."""

    async def deroule() -> tuple[ListToolsResult, list[CallToolResult]]:
        parametres = StdioServerParameters(
            command=sys.executable, args=["-m", "eke", "--etat", str(V3), "--pour", pour]
        )
        async with Client(
            stdio_client(parametres),
            mode="legacy",
            cache=None,
            read_timeout_seconds=60,
            client_info=Implementation(name="test-eke", version="0.1.0"),
        ) as client:
            outils = await client.list_tools()
            resultats = [await client.call_tool(nom, arguments) for nom, arguments in appels]
            return outils, resultats

    return anyio.run(deroule)


def _texte(resultat: CallToolResult) -> str:
    return "\n".join(bloc.text for bloc in resultat.content if isinstance(bloc, TextContent))


def test_trois_outils_en_lecture_seule_qui_declarent_le_contrat() -> None:
    outils, _ = _session("patrick.roux", [])
    assert [o.name for o in outils.tools] == ["lire_document", "extraire_valeurs", "citer"]
    for outil in outils.tools:
        assert outil.annotations is not None and outil.annotations.read_only_hint is True
        assert outil.output_schema == schema()
        assert outil.input_schema["required"] == (["chemin", "texte"] if outil.name == "citer" else ["chemin"])


def test_les_outils_rendent_le_contrat_structure_et_en_texte() -> None:
    _, resultats = _session(
        "patrick.roux",
        [
            ("lire_document", {"chemin": FACTURE}),
            ("extraire_valeurs", {"chemin": FACTURE}),
            ("citer", {"chemin": FACTURE, "texte": "512,40 €"}),
        ],
    )
    for resultat in resultats:
        assert resultat.is_error is not True, _texte(resultat)
        assert resultat.structured_content is not None
        assert ecarts(resultat.structured_content) == []
        assert json.loads(_texte(resultat)) == resultat.structured_content
        assert resultat.structured_content["document"]["chemin"] == FACTURE
    lignes, valeurs, citations = (cast(dict[str, Any], r.structured_content) for r in resultats)
    assert lignes["lignes"][0]["texte"] == "FACTURE F-2026-1151"
    total = next(v for v in valeurs["valeurs"] if v["etiquette"] == "Total TTC")
    assert (total["type"], total["valeur"], total["unite"]) == ("montant", "512.40", "EUR")
    assert citations["citations"] == [total["citation"]]


def test_un_refus_revient_comme_une_erreur_d_outil() -> None:
    _, resultats = _session(
        "enzo.caron",
        [
            ("lire_document", {"chemin": FACTURE}),
            ("lire_document", {"chemin": "commun/manuel_procedures.md"}),
            ("citer", {"chemin": "commun/annuaire.md", "texte": " "}),
            ("lire_document", {"chemin": "../entreprise/organigramme.yaml"}),
        ],
    )
    assert [r.is_error for r in resultats] == [True, True, True, True]
    assert [_texte(r) for r in resultats] == [
        "accès refusé à administration/ pour Enzo Caron",
        "EKE ne lit que les PDF : commun/manuel_procedures.md",
        "argument manquant ou vide : texte",
        "chemin hors des dossiers partagés : ../entreprise/organigramme.yaml",
    ]


def test_appeler_refuse_un_outil_inconnu_et_un_pdf_abime(tmp_path: Path) -> None:
    etat = tmp_path / "etat"
    shutil.copytree(V3 / "entreprise", etat / "entreprise")
    (etat / "dossiers" / "commun").mkdir(parents=True)
    (etat / "dossiers" / "commun" / "abime.pdf").write_bytes(b"%PDF-1.4\nrien de lisible\n")
    dossiers = Dossiers.pour(etat, "enzo.caron")
    with pytest.raises(RefusEke, match="outil inconnu : supprimer"):
        appeler(dossiers, "supprimer", {"chemin": "commun/abime.pdf"})
    with pytest.raises(DocumentIllisible, match="PDF illisible"):
        appeler(dossiers, "lire_document", {"chemin": "commun/abime.pdf"})


def test_eke_ne_demarre_pas_pour_une_personne_inconnue() -> None:
    sortie = subprocess.run(
        [sys.executable, "-m", "eke", "--etat", str(V3), "--pour", "intrus"],
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    assert sortie.returncode == 2
    assert "personne inconnue dans l'organigramme : intrus" in sortie.stderr


def test_des_appels_simultanes_rendent_la_meme_lecture() -> None:
    """Le serveur lance ses appels dans des fils ; PDFium, lui, n'en supporte qu'un à la fois."""
    dossiers = Dossiers.pour(V3, "patrick.roux")
    chemins = sorted(
        p.relative_to(dossiers.racine).as_posix() for p in (dossiers.racine / "administration").rglob("*.pdf")
    )
    attendu = {c: appeler(dossiers, "extraire_valeurs", {"chemin": c}) for c in chemins}

    def lire(chemin: str) -> tuple[str, dict[str, Any]]:
        return chemin, appeler(dossiers, "extraire_valeurs", {"chemin": chemin})

    with ThreadPoolExecutor(max_workers=8) as fils:
        obtenu = list(fils.map(lire, chemins * 3))
    assert all(sortie == attendu[chemin] for chemin, sortie in obtenu)
