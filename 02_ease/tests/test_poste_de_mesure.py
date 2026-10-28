"""Le poste de mesure (09_outillage/scripts/poste_de_mesure.py ; JOURNAL, entrée 108) : une copie
du dépôt figée sur un commit, ses liens vers le dossier de travail, et ses refus."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from ease.chargement import racine_depot

SCRIPT = racine_depot() / "09_outillage" / "scripts" / "poste_de_mesure.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("poste_de_mesure", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


POSTE = _module()


def _git(*arguments: str, dans: Path) -> str:
    environnement = POSTE.environnement_git() | {
        "GIT_AUTHOR_NAME": "essai",
        "GIT_AUTHOR_EMAIL": "essai@example",
        "GIT_COMMITTER_NAME": "essai",
        "GIT_COMMITTER_EMAIL": "essai@example",
    }
    sortie = subprocess.run(["git", *arguments], cwd=dans, env=environnement, capture_output=True, text=True)
    sortie.check_returncode()
    return sortie.stdout.strip()


@pytest.fixture
def depot(tmp_path: Path) -> Path:
    """Un petit dépôt : un fichier suivi, le .gitignore du projet, un .env, 99_local et prive."""
    principal = tmp_path / "Depot"
    principal.mkdir()
    _git("init", "--quiet", "--initial-branch=main", dans=principal)
    (principal / "arborescence.toml").write_text("version = 1\n", encoding="utf-8")
    (principal / ".gitignore").write_text((racine_depot() / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    _git("add", ".", dans=principal)
    _git("commit", "--quiet", "-m", "premier", dans=principal)
    (principal / ".env").write_text("CLE=fictive\n", encoding="utf-8")
    (principal / "99_local" / "runs").mkdir(parents=True)
    (principal / "07_taches" / "prive").mkdir(parents=True)
    return principal


def test_la_copie_se_cree_au_commit_avec_ses_liens_et_reste_propre(depot: Path) -> None:
    copie = depot.parent / "Depot_mesure"
    premier = _git("rev-parse", "HEAD", dans=depot)
    assert POSTE.preparer(depot, copie, "HEAD", installer=False) == premier
    assert _git("rev-parse", "HEAD", dans=copie) == premier
    for lien in (".env", "99_local", "07_taches/prive"):
        assert (copie / lien).is_symlink() and (copie / lien).resolve() == (depot / lien).resolve()
    assert _git("status", "--porcelain", dans=copie) == ""
    assert POSTE.dossier_principal(copie) == depot.resolve()


def test_une_copie_donnee_par_un_chemin_relatif_a_cote_du_depot_est_acceptee(depot: Path) -> None:
    # make poste-mesure DOSSIER=../Depot_confirmation, tapé depuis le dossier de travail.
    premier = _git("rev-parse", "HEAD", dans=depot)
    assert POSTE.preparer(depot, depot / ".." / "Depot_confirmation", "HEAD", installer=False) == premier
    assert _git("rev-parse", "HEAD", dans=depot.parent / "Depot_confirmation") == premier


def test_la_copie_change_de_commit_sans_toucher_au_dossier_de_travail(depot: Path) -> None:
    copie = depot.parent / "Depot_mesure"
    premier = POSTE.preparer(depot, copie, "HEAD", installer=False)
    (depot / "nouveau.txt").write_text("suite\n", encoding="utf-8")
    _git("add", "nouveau.txt", dans=depot)
    _git("commit", "--quiet", "-m", "second", dans=depot)
    (depot / "brouillon.txt").write_text("en cours\n", encoding="utf-8")  # le travail continue
    second = POSTE.preparer(depot, copie, "HEAD", installer=False)
    assert second != premier and (copie / "nouveau.txt").is_file() and not (copie / "brouillon.txt").exists()
    assert POSTE.preparer(depot, copie, premier, installer=False) == premier
    assert not (copie / "nouveau.txt").exists()


def test_une_copie_modifiee_ou_un_run_en_cours_empechent_de_la_deplacer(
    depot: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copie = depot.parent / "Depot_mesure"
    POSTE.preparer(depot, copie, "HEAD", installer=False)
    (copie / "arborescence.toml").write_text("version = 2\n", encoding="utf-8")
    with pytest.raises(POSTE.PosteImpossible, match="a des modifications"):
        POSTE.preparer(depot, copie, "HEAD", installer=False)
    _git("checkout", "--", "arborescence.toml", dans=copie)

    def un_run(dossier: Path) -> list[int]:
        return [4242]

    monkeypatch.setattr(POSTE, "runs_en_cours", un_run)
    with pytest.raises(POSTE.PosteImpossible, match=r"un run tourne .*4242"):
        POSTE.preparer(depot, copie, "HEAD", installer=False)
    with pytest.raises(POSTE.PosteImpossible, match="hors du dossier de travail"):
        POSTE.preparer(depot, depot / "mesure", "HEAD", installer=False)


def test_un_run_se_reconnait_a_sa_commande_et_a_son_dossier(tmp_path: Path) -> None:
    proc, copie = tmp_path / "proc", tmp_path / "copie"
    copie.mkdir()
    for numero, commande, dossier in [
        ("11", b"python\0-m\0ease.mesure\0agent_seul_deepseek_flash\0", copie),
        ("12", b"python\0-m\0ease.temoins\0", copie),
        ("13", b"python\0-m\0ease.mesure\0agent_seul_qwen_local\0", tmp_path),
    ]:
        (proc / numero).mkdir(parents=True)
        (proc / numero / "cmdline").write_bytes(commande)
        (proc / numero / "cwd").symlink_to(dossier)
    assert POSTE.runs_en_cours(copie, proc) == [11]


def test_un_run_ne_part_que_d_un_des_deux_postes_propre_et_dans_main(depot: Path) -> None:
    # Cadrage du dépôt public et de l'organisation, section 10 : api et local, dans <dépôt>_postes/.
    from ease.poste import POSTES, postes_de, refus_hors_poste

    assert POSTES == POSTE.POSTES
    api = postes_de(depot) / "api"
    POSTE.preparer(depot, api, "HEAD", installer=False)
    assert refus_hors_poste(api) is None
    refus = refus_hors_poste(depot)
    assert refus is not None and "n'est pas un poste" in refus
    autre = postes_de(depot) / "nuit"
    POSTE.preparer(depot, autre, "HEAD", installer=False)
    refus = refus_hors_poste(autre)
    assert refus is not None and "n'est pas un poste" in refus
    (api / "arborescence.toml").write_text("version = 2\n", encoding="utf-8")
    refus = refus_hors_poste(api)
    assert refus is not None and "a des modifications" in refus
    _git("checkout", "--", "arborescence.toml", dans=api)
    _git("checkout", "--quiet", "-b", "essai", dans=depot)
    (depot / "essai.txt").write_text("hors de main\n", encoding="utf-8")
    _git("add", "essai.txt", dans=depot)
    _git("commit", "--quiet", "-m", "essai", dans=depot)
    POSTE.preparer(depot, api, "essai", installer=False)
    refus = refus_hors_poste(api)
    assert refus is not None and "n'est pas dans main" in refus


def test_l_image_du_banc_tient_lieu_de_poste(depot: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # L'image : l'archive d'un commit, sans dépôt git, son commit dans POA_COMMIT_IMAGE (entrée 304).
    from ease.poste import refus_hors_poste

    image = tmp_path / "image"
    image.mkdir()
    monkeypatch.delenv("POA_COMMIT_IMAGE", raising=False)
    refus = refus_hors_poste(image)
    assert refus is not None and "pas dans un dépôt git" in refus
    monkeypatch.setenv("POA_COMMIT_IMAGE", "0" * 40)
    assert refus_hors_poste(image) is None
    # La variable seule n'ouvre pas l'atelier : il a son dépôt git.
    refus = refus_hors_poste(depot)
    assert refus is not None and "n'est pas un poste" in refus
