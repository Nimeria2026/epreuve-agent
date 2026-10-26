"""Le coffre (09_outillage/scripts/coffre.py, ADR 0008) et la sauvegarde sur la clé
(09_outillage/scripts/sauvegarder.py) : rien ne s'efface, seul ce qui change se rechiffre."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from ease.chargement import racine_depot

SCRIPTS = racine_depot() / "09_outillage" / "scripts"


def _module(nom: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(nom, SCRIPTS / f"{nom}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module  # ses dataclasses relisent leur module
    spec.loader.exec_module(module)
    return module


COFFRE = _module("coffre")
SAUVEGARDE = _module("sauvegarder")


class Chiffreur:
    """Un faux age : réversible, et il compte ses appels."""

    def __init__(self) -> None:
        self.appels = 0

    def __call__(self, donnees: bytes) -> bytes:
        self.appels += 1
        return b"chiffre:" + donnees[::-1]


def _atelier(racine: Path) -> Path:
    prive = racine / "07_taches" / "prive"
    (prive / "dure").mkdir(parents=True)
    (prive / "x01_cachee.yaml").write_text("tâche cachée\n", encoding="utf-8")
    (prive / "dure" / "x02_cachee.yaml").write_text("tranche cachée\n", encoding="utf-8")
    juge = racine / "99_local" / "juge"
    juge.mkdir(parents=True)
    (juge / "verdicts.json").write_text("{}\n", encoding="utf-8")
    run = racine / "99_local" / "runs" / "2026-10-21_120000_ref_a"
    (run / "resultats").mkdir(parents=True)
    (run / "resultats" / "x01_cachee_r1.json").write_text("{}\n", encoding="utf-8")
    publication = racine / "08_publications" / "2026-11-02_constat"
    publication.mkdir(parents=True)
    runs = [
        {"run": run.name, "banc": "PME", "taches_non_publiees": 1},
        {"run": "2026-10-21_130000_ref_a", "banc": "PME", "taches_non_publiees": 0},
    ]
    (publication / "manifeste.json").write_text(json.dumps({"runs": runs}), encoding="utf-8")
    return racine


def test_un_dossier_s_archive_toujours_aux_memes_octets(tmp_path: Path) -> None:
    racine = _atelier(tmp_path)
    dossier = racine / "07_taches" / "prive" / "dure"
    premiere = COFFRE.archive_reproductible(dossier)
    assert COFFRE.archive_reproductible(dossier) == premiere
    (dossier / "x02_cachee.yaml").write_text("tranche cachée, corrigée\n", encoding="utf-8")
    assert COFFRE.archive_reproductible(dossier) != premiere


def test_seul_ce_qui_change_se_rechiffre_et_rien_ne_s_efface(tmp_path: Path) -> None:
    racine = _atelier(tmp_path)
    chiffrer = Chiffreur()
    bilan = COFFRE.mettre_a_jour(racine, chiffrer, "2026-10-26T10:00:00+00:00")
    assert (bilan.nouveaux, bilan.changes, bilan.inchanges, bilan.absents) == (4, 0, 0, 0)
    coffre = racine / "12_coffre"
    assert sorted(p.name for p in coffre.iterdir()) == ["00001.age", "00002.age", "00003.age", "00004.age", "index.age"]
    index = json.loads((racine / "99_local" / "coffre" / "index.json").read_text(encoding="utf-8"))
    assert sorted(index) == [
        "07_taches/prive/dure",
        "07_taches/prive/x01_cachee.yaml",
        "99_local/juge/verdicts.json",
        "99_local/runs/2026-10-21_120000_ref_a",
    ]
    assert chiffrer.appels == 5
    bilan = COFFRE.mettre_a_jour(racine, chiffrer)
    assert (bilan.nouveaux, bilan.changes, bilan.inchanges, chiffrer.appels) == (0, 0, 4, 5)
    (racine / "07_taches" / "prive" / "x01_cachee.yaml").write_text("tâche cachée, v2\n", encoding="utf-8")
    numero = index["07_taches/prive/x01_cachee.yaml"]["numero"]
    bilan = COFFRE.mettre_a_jour(racine, chiffrer)
    assert (bilan.changes, bilan.inchanges, chiffrer.appels) == (1, 3, 7)
    texte = (coffre / f"{numero:05d}.age").read_bytes()
    assert texte == b"chiffre:" + "tâche cachée, v2\n".encode()[::-1]
    (racine / "99_local" / "juge" / "verdicts.json").unlink()
    (racine / "99_local" / "juge" / "neufs.json").write_text("[]\n", encoding="utf-8")
    bilan = COFFRE.mettre_a_jour(racine, chiffrer, "2026-10-27T10:00:00+00:00")
    assert (bilan.nouveaux, bilan.absents) == (1, 1)
    index = json.loads((racine / "99_local" / "coffre" / "index.json").read_text(encoding="utf-8"))
    assert index["99_local/juge/verdicts.json"]["absent_depuis"] == "2026-10-27T10:00:00+00:00"
    assert index["99_local/juge/neufs.json"]["numero"] == 5
    assert (coffre / "00003.age").is_file() and (coffre / "00005.age").is_file()


def test_le_coffre_refuse_sans_index_en_clair_ni_cle_publique(tmp_path: Path) -> None:
    racine = _atelier(tmp_path)
    COFFRE.mettre_a_jour(racine, Chiffreur())
    (racine / "99_local" / "coffre" / "index.json").unlink()
    with pytest.raises(COFFRE.CoffreImpossible, match="index en clair manque"):
        COFFRE.mettre_a_jour(racine, Chiffreur())
    with pytest.raises(COFFRE.CoffreImpossible, match="age-keygen"):
        COFFRE.destinataire(racine)
    (racine / "12_coffre" / "destinataire.txt").write_text("# clé d'Alexandre\nage1exemple\n", encoding="utf-8")
    assert COFFRE.destinataire(racine) == "age1exemple"


def test_age_absent_se_dit(monkeypatch: pytest.MonkeyPatch) -> None:
    def introuvable(nom: str) -> None:
        return None

    monkeypatch.setattr(COFFRE.shutil, "which", introuvable)
    with pytest.raises(COFFRE.CoffreImpossible, match="apt install age"):
        COFFRE.chiffreur_age("age1exemple")


def _monte(_: Path) -> bool:
    return True


def _demonte(_: Path) -> bool:
    return False


class FauxGocryptfs:
    """Un faux gocryptfs : le dossier « chiffré » garde le clair dans clair/, recopié à l'ouverture et
    rendu à la fermeture, qui vide le point d'ouverture comme un vrai démontage."""

    def creer(self, chiffre: Path) -> None:
        (chiffre / "clair").mkdir(parents=True)
        (chiffre / "gocryptfs.conf").write_text("{}\n", encoding="utf-8")

    def ouvrir(self, chiffre: Path, ouvert: Path) -> None:
        self.chiffre = chiffre
        shutil.copytree(chiffre / "clair", ouvert, dirs_exist_ok=True)

    def fermer(self, ouvert: Path) -> None:
        shutil.copytree(ouvert, self.chiffre / "clair", dirs_exist_ok=True)
        shutil.rmtree(ouvert)
        ouvert.mkdir()


def test_la_sauvegarde_va_en_archives_dans_un_dossier_chiffre_d_une_cle_montee(tmp_path: Path) -> None:
    racine = _atelier(tmp_path / "atelier")
    (racine / "99_local" / "travail" / "pme_x").mkdir(parents=True)
    (racine / "99_local" / "travail" / "pme_x" / "etat.json").write_text("{}\n", encoding="utf-8")
    cle, age = tmp_path / "cle", tmp_path / "poa.txt"
    cle.mkdir()
    age.write_text("CLE-PRIVEE-FICTIVE\n", encoding="utf-8")
    faux = FauxGocryptfs()

    def sauvegarder(initialiser: bool = False, maintenant: str | None = None) -> Any:
        return SAUVEGARDE.sauvegarder(
            racine, cle, initialiser, _monte, faux.creer, faux.ouvrir, faux.fermer, age, maintenant
        )

    with pytest.raises(SAUVEGARDE.SauvegardeImpossible, match="point de montage"):
        SAUVEGARDE.sauvegarder(racine, cle, est_monte=_demonte)
    with pytest.raises(SAUVEGARDE.SauvegardeImpossible, match="INITIALISER=1"):
        sauvegarder()
    premiere = sauvegarder(initialiser=True, maintenant="2026-10-26T10:00:00+00:00")
    assert (premiere.precedente, premiere.ecrits, premiere.inchanges, premiere.en_clair) == (None, 4, 0, None)
    clair = cle / SAUVEGARDE.CHIFFRE / "clair"
    ecrits = sorted(p.relative_to(clair).as_posix() for p in clair.rglob("*") if p.is_file())
    assert ecrits == [
        ".derniere_sauvegarde",
        "07_taches/prive/dure.tar.gz",
        "07_taches/prive/x01_cachee.yaml",
        "99_local/juge.tar.gz",
        "99_local/runs/2026-10-21_120000_ref_a.tar.gz",
        "cle_age_poa.txt",
        "index.json",
    ]
    with tarfile.open(clair / "07_taches/prive/dure.tar.gz") as archive:
        assert archive.getnames() == ["dure", "dure/x02_cachee.yaml"]
    assert sorted(p.name for p in cle.iterdir()) == [SAUVEGARDE.CHIFFRE]
    shutil.rmtree(racine / "99_local" / "runs" / "2026-10-21_120000_ref_a")
    (racine / "99_local" / "juge" / "neufs.json").write_text("[]\n", encoding="utf-8")
    (cle / SAUVEGARDE.EN_CLAIR).mkdir()
    seconde = sauvegarder()
    assert (seconde.precedente, seconde.ecrits, seconde.inchanges) == ("2026-10-26T10:00:00+00:00", 1, 2)
    assert seconde.en_clair == cle / SAUVEGARDE.EN_CLAIR
    assert (clair / "99_local/runs/2026-10-21_120000_ref_a.tar.gz").is_file()
    with tarfile.open(clair / "99_local/juge.tar.gz") as archive:
        assert "juge/neufs.json" in archive.getnames()
    assert not list(Path(tempfile.gettempdir()).glob("poa_sauvegarde_*"))
