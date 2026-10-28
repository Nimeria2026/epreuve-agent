"""La clôture d'une campagne (09_outillage/scripts/cloture.py ; cadrage des interventions, annexe
D ; JOURNAL, entrée 316) : l'attestation d'abord, la suppression après la confirmation, rien sans
elle."""

from __future__ import annotations

import datetime
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from ease.chargement import racine_depot

SCRIPTS = racine_depot() / "09_outillage" / "scripts"
JOUR = datetime.date(2026, 11, 30)


def _module(nom: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(nom, SCRIPTS / f"{nom}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


CAMPAGNE = _module("campagne")
CLOTURE = _module("cloture")


def _oui(_: str) -> bool:
    return True


def _non(_: str) -> bool:
    return False


@pytest.fixture(autouse=True)
def _identite(monkeypatch: pytest.MonkeyPatch) -> None:
    for cle in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(cle, "essai")
    for cle in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(cle, "essai@example")


@pytest.fixture
def atelier(tmp_path: Path) -> Path:
    """Un atelier, une campagne ouverte, avec un poste, deux runs, un rapport et un .env."""
    racine = tmp_path / "Atelier"
    (racine / "00_docs" / "sources").mkdir(parents=True)
    CAMPAGNE.git("init", "--quiet", "--initial-branch=main", dans=racine)
    (racine / CAMPAGNE.CADRAGE).write_text(
        "# Cadrage\n\n## Annexe A, la fiche de demande\n\n## Annexe E, la proposition\n\n"
        "[//]: # (proposition)\nLe modèle.\n[//]: # (fin de la proposition)\n",
        encoding="utf-8",
    )
    (racine / "opencode.json").write_text(json.dumps({"agent": {}}), encoding="utf-8")
    (racine / ".gitignore").write_text(".env\n99_local/\n", encoding="utf-8")
    CAMPAGNE.git("add", ".", dans=racine)
    CAMPAGNE.git("commit", "--quiet", "-m", "premier", dans=racine)
    campagne = CAMPAGNE.ouvrir(racine, "essai", jour=datetime.date(2026, 11, 2))
    fiche = campagne / "00_docs" / "sources" / "2026-11-02_campagne_essai.md"
    fiche.write_text(
        fiche.read_text(encoding="utf-8").replace("| Entreprise | ? |", "| Entreprise | Société d'essai |"),
        encoding="utf-8",
    )
    for run in ("2026-11-20_101500_campagne_essai", "2026-11-21_090000_agent_seul_qwen_local"):
        (campagne / "99_local" / "runs" / run).mkdir(parents=True)
    (campagne / "99_local" / "rapports").mkdir(parents=True)
    (campagne / "99_local" / "rapports" / "2026-11-22_rapport_campagne.md").write_text("rapport\n", encoding="utf-8")
    (campagne / ".env").write_text("CLE=fictive\n", encoding="utf-8")
    (campagne.parent / "essai_postes" / "api").mkdir(parents=True)
    return racine


def test_la_cloture_atteste_puis_supprime_la_campagne_et_ses_postes(atelier: Path) -> None:
    demandes: list[str] = []

    def confirmer(nom: str) -> bool:
        demandes.append(nom)
        return True

    chemin = CLOTURE.clore(atelier, "essai", confirmer, jour=JOUR)
    campagnes = atelier.parent / "Atelier_campagnes"
    assert demandes == ["essai"]
    assert chemin == campagnes / "2026-11-30_attestation_suppression_essai.md"
    assert sorted(p.name for p in campagnes.iterdir()) == [chemin.name]
    texte = chemin.read_text(encoding="utf-8")
    assert "Campagne `essai`, menée pour Société d'essai. Ouverte le 2026-11-02" in texte
    assert "`2026-11-20_101500_campagne_essai`, `2026-11-21_090000_agent_seul_qwen_local`" in texte
    assert "`2026-11-22_rapport_campagne.md`" in texte and "`essai_postes/`" in texte
    assert "son fichier de clés (`.env`) : supprimé" in texte and "Alexandre Do" in texte


def test_sans_confirmation_rien_ne_bouge(atelier: Path) -> None:
    with pytest.raises(CAMPAGNE.CampagneImpossible) as refus:
        CLOTURE.clore(atelier, "essai", _non, jour=JOUR)
    assert refus.value.code == 6
    campagnes = atelier.parent / "Atelier_campagnes"
    assert sorted(p.name for p in campagnes.iterdir()) == ["essai", "essai_postes"]


def test_les_refus(atelier: Path) -> None:
    for nom, code in (("Essai Client", 2), ("absente", 3)):
        with pytest.raises(CAMPAGNE.CampagneImpossible) as refus:
            CLOTURE.clore(atelier, nom, _oui, jour=JOUR)
        assert refus.value.code == code
    campagne = atelier.parent / "Atelier_campagnes" / "essai"
    with pytest.raises(CAMPAGNE.CampagneImpossible) as refus:
        CLOTURE.clore(campagne, "essai", _oui, jour=JOUR)
    assert refus.value.code == 5
    (atelier.parent / "Atelier_campagnes" / "2026-11-30_attestation_suppression_essai.md").write_text("", "utf-8")
    with pytest.raises(CAMPAGNE.CampagneImpossible) as refus:
        CLOTURE.clore(atelier, "essai", _oui, jour=JOUR)
    assert refus.value.code == 7
    assert campagne.is_dir()


def test_un_run_en_cours_se_reconnait(tmp_path: Path) -> None:
    assert not CLOTURE.run_en_cours([tmp_path])
