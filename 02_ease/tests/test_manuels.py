"""Les manuels (00_docs/manuels/ ; ADR 0012) restent vrais : chaque commande make qu'ils citent
existe, chaque fichier du dépôt qu'ils nomment existe, et leur texte suit le style de l'atelier.
Les manuels ne sortent pas dans l'export public : hors de l'atelier, ces tests passent leur tour."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ease.chargement import racine_depot

RACINE = racine_depot()
MANUELS = RACINE / "00_docs" / "manuels"
PAGES = sorted(MANUELS.rglob("*.md")) if MANUELS.is_dir() else []
DOSSIERS = (
    "00_docs",
    "01_contrats",
    "02_ease",
    "03_orchestrations",
    "04_eke",
    "05_pme",
    "06_gardien",
    "07_taches",
    "08_publications",
    "09_outillage",
    "10_deploiement",
    "11_bancs_publics",
    "12_coffre",
)
RACINES = ("AGENTS.md", "ATELIER.md", "BRIEF.md", "PLAN.md", "JOURNAL.md", "JOURNAL_PUBLIC.md", "Makefile")
HORS_GIT = ("07_taches/prive", "99_local")
"""Ce qui manque à un clone neuf ou à une campagne, sans que le manuel soit faux."""

pytestmark = pytest.mark.skipif(not PAGES, reason="les manuels restent dans l'atelier, hors de l'export public")


def _cibles() -> set[str]:
    texte = (RACINE / "Makefile").read_text(encoding="utf-8")
    return set(re.findall(r"^([a-z0-9-]+):", texte, re.MULTILINE))


def test_les_manuels_existent_et_chaque_dossier_a_son_sommaire() -> None:
    assert {p.parent.name for p in PAGES} >= {"manuels", "utilisation"}
    for dossier in {p.parent for p in PAGES}:
        assert (dossier / "README.md").is_file(), dossier


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(MANUELS)))
def test_chaque_commande_make_citee_existe(page: Path) -> None:
    cibles = _cibles()
    citees = set(re.findall(r"\bmake ([a-z0-9][a-z0-9-]*)", page.read_text(encoding="utf-8")))
    assert citees - cibles == set()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(MANUELS)))
def test_chaque_fichier_nomme_existe(page: Path) -> None:
    absents: list[str] = []
    for nom in re.findall(r"`([^`\s]+)`", page.read_text(encoding="utf-8")):
        chemin = nom.rstrip("/")
        if any(c in chemin for c in "<*?") or chemin.startswith(HORS_GIT):
            continue
        du_depot = chemin.split("/")[0] in DOSSIERS or chemin in RACINES
        if du_depot and not (RACINE / chemin).exists():
            absents.append(nom)
    assert absents == []


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(MANUELS)))
def test_le_style_de_l_atelier(page: Path) -> None:
    texte = page.read_text(encoding="utf-8")
    assert not re.search(r"[–—…!]|\.\.\.", texte)
    assert not re.search(r"« | »", texte), "les guillemets veulent des espaces insécables"
