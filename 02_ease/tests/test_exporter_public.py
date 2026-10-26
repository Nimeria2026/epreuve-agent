"""L'export public (09_outillage/scripts/exporter_public.py, ADR 0010) : seul ce qui est commité et
prévu sort ; une tâche cachée, une clé ou un texte interdit arrêtent tout, sans être cités."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from ease.chargement import racine_depot


def _module() -> ModuleType:
    chemin = racine_depot() / "09_outillage" / "scripts" / "exporter_public.py"
    spec = importlib.util.spec_from_file_location("exporter_public", chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["exporter_public"] = module  # ses dataclasses relisent leur module
    spec.loader.exec_module(module)
    return module


EXPORT = _module()
CACHEE = "zz01_tache_cachee_fictive"
CLE = "valeur-de-cle-fictive-0123456789"


def _git(dossier: Path, *arguments: str) -> None:
    environnement = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", *arguments], cwd=dossier, check=True, capture_output=True, env=environnement)


def _ecrire(racine: Path, chemin: str, texte: str) -> Path:
    fichier = racine / chemin
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(texte, encoding="utf-8")
    return fichier


def _atelier(racine: Path) -> Path:
    """Un atelier miniature : ce qui sort, ce qui reste, une tâche cachée et un .env hors git."""
    racine.mkdir()
    _git(racine, "init", "-q", "-b", "main")
    _git(racine, "config", "user.email", "essai@exemple.fr")
    _git(racine, "config", "user.name", "Essai")
    fichiers = {
        ".gitignore": ".env\n99_local/\n07_taches/prive/\n",
        "AGENTS.md": "# Pour toute IA\n",
        "JOURNAL_PUBLIC.md": "# Journal public\n",
        "JOURNAL.md": "# Journal de l'atelier\n",
        "BRIEF.md": "# Brief\n",
        "ATELIER.md": "# Atelier\n",
        "CLAUDE.md": "@AGENTS.md\n@ATELIER.md\n",
        "README.md": "# Atelier privé\n",
        "LICENSE": "Apache License\n",
        "02_ease/a.py": "x = 1\n",
        "07_taches/public/t01_fictive.yaml": "identifiant: t01_fictive\n",
        "00_docs/sources/note.md": "note de travail\n",
        "12_coffre/00001.age": "chiffré\n",
        "09_outillage/scripts/export/readme_public.md": "# Épreuve d'agent, en public\n",
        "09_outillage/scripts/export/interdits.md": "- motinterdit\n",
    }
    for chemin, texte in fichiers.items():
        _ecrire(racine, chemin, texte)
    _ecrire(racine, "09_outillage/scripts/lancer.sh", "#!/usr/bin/env bash\n").chmod(0o755)
    _ecrire(racine, f"07_taches/prive/{CACHEE}.yaml", f"identifiant: {CACHEE}\nenonce: secret\n")
    _ecrire(racine, ".env", f"CLE_API={CLE}\nPORT=30100\n")
    _git(racine, "add", ".")
    _git(racine, "commit", "-q", "-m", "atelier")
    return racine


def test_seul_ce_qui_est_prevu_et_commite_sort(tmp_path: Path) -> None:
    racine = _atelier(tmp_path / "atelier")
    _ecrire(racine, "02_ease/a.py", "x = 2  # pas commité\n")
    sortie = tmp_path / "export"
    EXPORT.exporter(racine, sortie)
    sortis = sorted(p.relative_to(sortie).as_posix() for p in sortie.rglob("*") if p.is_file())
    assert sortis == [
        ".gitignore",
        "02_ease/a.py",
        "07_taches/public/t01_fictive.yaml",
        "09_outillage/scripts/lancer.sh",
        "AGENTS.md",
        "CLAUDE.md",
        "JOURNAL.md",
        "LICENSE",
        "README.md",
    ]
    assert (sortie / "02_ease/a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (sortie / "JOURNAL.md").read_text(encoding="utf-8") == "# Journal public\n"
    assert (sortie / "README.md").read_text(encoding="utf-8") == "# Épreuve d'agent, en public\n"
    claude = (sortie / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in claude and "ATELIER" not in claude
    assert os.access(sortie / "09_outillage/scripts/lancer.sh", os.X_OK)
    with pytest.raises(EXPORT.ExportImpossible, match="existe déjà"):
        EXPORT.exporter(racine, sortie)


@pytest.mark.parametrize(
    ("texte", "nature"),
    [
        (f"voir {CACHEE}\n", "cite une tâche cachée"),
        (f"cle = '{CLE}'\n", "contient une valeur du .env"),
        ("un MotInterdit ici\n", "contient un texte interdit"),
    ],
)
def test_une_tache_cachee_une_cle_ou_un_interdit_arretent_tout_sans_etre_cites(
    tmp_path: Path, texte: str, nature: str
) -> None:
    racine = _atelier(tmp_path / "atelier")
    _ecrire(racine, "02_ease/fuite.py", texte)
    _git(racine, "add", "02_ease/fuite.py")
    _git(racine, "commit", "-q", "-m", "fuite")
    sortie = tmp_path / "export"
    with pytest.raises(EXPORT.ExportImpossible) as erreur:
        EXPORT.exporter(racine, sortie)
    message = str(erreur.value)
    assert f"02_ease/fuite.py : {nature}" in message
    assert CACHEE not in message and CLE not in message
    assert not sortie.exists()
