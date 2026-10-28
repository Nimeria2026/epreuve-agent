"""L'ouverture d'une campagne (09_outillage/scripts/campagne.py ; cadrage des interventions,
section 5 ; JOURNAL, entrée 311) : un clone privé de l'atelier, hors de lui, sans dépôt distant."""

from __future__ import annotations

import datetime
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from ease.chargement import racine_depot

SCRIPT = racine_depot() / "09_outillage" / "scripts" / "campagne.py"
JOUR = datetime.date(2026, 10, 27)


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("campagne", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["campagne"] = module
    spec.loader.exec_module(module)
    return module


CAMPAGNE = _module()


@pytest.fixture(autouse=True)
def _identite(monkeypatch: pytest.MonkeyPatch) -> None:
    for cle in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(cle, "essai")
    for cle in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(cle, "essai@example")


def _git(*arguments: str, dans: Path) -> str:
    return str(CAMPAGNE.git(*arguments, dans=dans))


@pytest.fixture
def atelier(tmp_path: Path) -> Path:
    """Un petit atelier : le cadrage et ses annexes, opencode.json, un .env et des tâches cachées."""
    racine = tmp_path / "Atelier"
    (racine / "00_docs" / "sources").mkdir(parents=True)
    _git("init", "--quiet", "--initial-branch=main", dans=racine)
    (racine / CAMPAGNE.CADRAGE).write_text(
        "# Cadrage\n\n## 10. Choix\n\n## Annexe A, la fiche de demande\n\n- l'entreprise\n\n"
        "## Annexe D, l'attestation de suppression\n\nLa signature.\n\n## Annexe E, la proposition\n\n"
        "[//]: # (proposition)\n**Proposition : mesurer votre agent**\n\nTVA non applicable.\n"
        "[//]: # (fin de la proposition)\n",
        encoding="utf-8",
    )
    configuration = {"instructions": ["ATELIER.md"], "agent": {"title": {"model": "opencode/autre"}}}
    (racine / "opencode.json").write_text(json.dumps(configuration), encoding="utf-8")
    (racine / ".gitignore").write_text(".env\n07_taches/prive/\n99_local/\n", encoding="utf-8")
    _git("add", ".", dans=racine)
    _git("commit", "--quiet", "-m", "premier", dans=racine)
    (racine / ".env").write_text("CLE=fictive\n", encoding="utf-8")
    (racine / "07_taches" / "prive").mkdir(parents=True)
    (racine / "07_taches" / "prive" / "c01_secret.yaml").write_text("secret\n", encoding="utf-8")
    return racine


def test_la_campagne_est_un_clone_prive_hors_de_l_atelier(atelier: Path) -> None:
    commit = _git("rev-parse", "HEAD", dans=atelier)
    campagne = CAMPAGNE.ouvrir(atelier, "essai", jour=JOUR)
    assert campagne == atelier.parent / "Atelier_campagnes" / "essai"
    assert CAMPAGNE.est_campagne(campagne) and not CAMPAGNE.est_campagne(atelier)
    assert _git("remote", dans=campagne) == ""
    assert _git("rev-parse", "HEAD~1", dans=campagne) == commit
    assert _git("status", "--porcelain", dans=campagne) == ""
    assert not (campagne / ".env").exists()
    assert not (campagne / "07_taches" / "prive").exists()


def test_la_fiche_porte_les_regles_et_les_annexes(atelier: Path) -> None:
    campagne = CAMPAGNE.ouvrir(atelier, "essai", jour=JOUR)
    fiche = (campagne / "00_docs" / "sources" / "2026-10-27_campagne_essai.md").read_text(encoding="utf-8")
    assert fiche.startswith("# Campagne essai\n")
    assert "### Annexe A, la fiche de demande" in fiche and "### Annexe D" in fiche
    assert "## 10. Choix" not in fiche
    assert "juge_requis" in fiche and "make sauvegarder" in fiche
    assert f"git pull --no-rebase --no-edit {atelier.resolve()} main" in fiche
    assert "2026-10-27_proposition_essai.md" in fiche
    proposition = (campagne / "00_docs" / "sources" / "2026-10-27_proposition_essai.md").read_text(encoding="utf-8")
    assert proposition == "**Proposition : mesurer votre agent**\n\nTVA non applicable.\n"
    assert _git("status", "--porcelain", dans=campagne) == ""


def test_tous_les_agents_d_opencode_sont_sur_un_modele_admis(atelier: Path) -> None:
    campagne = CAMPAGNE.ouvrir(atelier, "essai", jour=JOUR)
    configuration = json.loads((campagne / "opencode.json").read_text(encoding="utf-8"))
    assert configuration["model"] == CAMPAGNE.MODELE_ADMIS
    assert configuration["instructions"] == ["ATELIER.md"]
    assert set(CAMPAGNE.AGENTS) <= set(configuration["agent"])
    assert {a["model"] for a in configuration["agent"].values()} == {CAMPAGNE.MODELE_ADMIS}


def test_les_refus(atelier: Path) -> None:
    CAMPAGNE.ouvrir(atelier, "essai", jour=JOUR)
    cas = [("essai", "HEAD", 3), ("Essai Client", "HEAD", 2), ("../dehors", "HEAD", 2)]
    _git("checkout", "--quiet", "-b", "branche", dans=atelier)
    (atelier / "a.txt").write_text("hors de main\n", encoding="utf-8")
    _git("add", "a.txt", dans=atelier)
    _git("commit", "--quiet", "-m", "hors de main", dans=atelier)
    cas.append(("autre", "branche", 4))
    for nom, commit, code in cas:
        with pytest.raises(CAMPAGNE.CampagneImpossible) as refus:
            CAMPAGNE.ouvrir(atelier, nom, commit, jour=JOUR)
        assert refus.value.code == code, nom
    campagne = atelier.parent / "Atelier_campagnes" / "essai"
    with pytest.raises(CAMPAGNE.CampagneImpossible) as refus:
        CAMPAGNE.ouvrir(campagne, "sous_campagne", jour=JOUR)
    assert refus.value.code == 5


def test_le_cadrage_du_depot_a_ses_annexes_et_le_modele_est_admis() -> None:
    if not (racine_depot() / CAMPAGNE.CADRAGE).is_file():
        pytest.skip("les sources restent dans l'atelier, hors de l'export public")
    cadrage = (racine_depot() / CAMPAGNE.CADRAGE).read_text(encoding="utf-8")
    assert "### Annexe A" in CAMPAGNE.annexes(cadrage)
    modele = CAMPAGNE.proposition(cadrage)
    assert modele.startswith("**Proposition : mesurer votre agent**") and "Bon pour accord" in modele
    releve = (racine_depot() / "00_docs" / "sources" / "2026-10-26_politiques_de_donnees_opencode.md").read_text(
        encoding="utf-8"
    )
    assert CAMPAGNE.MODELE_ADMIS.removeprefix("opencode-go/") in releve
