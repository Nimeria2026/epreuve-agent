"""La fiche du moteur de Qwen 3.8 27B sous vLLM (02_ease/src/ease/moteurs/) et sa vérification par
make qwen (09_outillage/scripts/verifier_qwen.py ; JOURNAL, entrée 301)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from ease.chargement import racine_depot


def _module() -> ModuleType:
    chemin = racine_depot() / "09_outillage" / "scripts" / "verifier_qwen.py"
    spec = importlib.util.spec_from_file_location("verifier_qwen", chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verifier_qwen"] = module
    spec.loader.exec_module(module)
    return module


VERIF = _module()
FICHE = racine_depot() / "02_ease" / "src" / "ease" / "moteurs" / "vllm_qwen_27b.json"
REVISION = "1" * 40


def _faux_modele(dossier: Path) -> dict[str, Any]:
    """Un dossier de modèle tel que le laisse un téléchargement de Hugging Face, et sa fiche."""
    contenus = {
        "config.json": b'{"model_type": "qwen3_5"}',
        "tokenizer.json": b'{"version": "1.0"}',
        "model-00001-of-00002.safetensors": b"poids-un",
        "model-00002-of-00002.safetensors": b"poids-deux",
    }
    meta = dossier / ".cache" / "huggingface" / "download"
    meta.mkdir(parents=True)
    fichiers: dict[str, dict[str, Any]] = {}
    for nom, contenu in contenus.items():
        (dossier / nom).write_bytes(contenu)
        if nom == "config.json":
            etag = hashlib.sha1(b"blob %d\0" % len(contenu) + contenu, usedforsecurity=False).hexdigest()
            fichiers[nom] = {"octets": len(contenu), "git_sha1": etag}
        else:
            etag = hashlib.sha256(contenu).hexdigest()
            fichiers[nom] = {"octets": len(contenu), "sha256": etag}
        (meta / f"{nom}.metadata").write_text(f"{REVISION}\n{etag}\n1787050931.0\n", encoding="utf-8")
    return {"depot": "essai/qwen", "revision": REVISION, "fichiers": fichiers}


def test_la_fiche_du_depot_nomme_le_modele_sans_chemin_personnel() -> None:
    texte = FICHE.read_text(encoding="utf-8")
    assert re.search(r"/(?:home|Users)/", texte) is None
    fiche = json.loads(texte)
    assert fiche["paquets"]["vllm"] == "0.27.1"
    assert fiche["modele"]["depot"] == "dbirks/Qwen3.8-27B-W4A16-AutoRound"
    assert len(fiche["modele"]["revision"]) == 40
    poids = [nom for nom in fiche["modele"]["fichiers"] if nom.endswith(".safetensors")]
    assert len(poids) == 8
    assert all(len(fiche["modele"]["fichiers"][nom]["sha256"]) == 64 for nom in poids)


def test_un_modele_identique_est_conforme(tmp_path: Path) -> None:
    attendu = _faux_modele(tmp_path)
    assert VERIF.ecarts_modele(attendu, tmp_path) == []
    assert VERIF.ecarts_modele(attendu, tmp_path, empreintes=True) == []


def test_une_configuration_une_revision_une_taille_ou_un_fichier_changes_sont_refuses(tmp_path: Path) -> None:
    attendu = _faux_modele(tmp_path)
    (tmp_path / "config.json").write_bytes(b'{"model_type": "qwen3_6"}')
    meta = tmp_path / ".cache" / "huggingface" / "download" / "tokenizer.json.metadata"
    meta.write_text(meta.read_text(encoding="utf-8").replace(REVISION, "2" * 40), encoding="utf-8")
    (tmp_path / "model-00001-of-00002.safetensors").write_bytes(b"poids-un-plus-long")
    (tmp_path / "model-00002-of-00002.safetensors").unlink()
    assert VERIF.ecarts_modele(attendu, tmp_path) == [
        "config.json : contenu modifié",
        "tokenizer.json : révision 22222222, la fiche dit 11111111",
        "model-00001-of-00002.safetensors : 18 octets, la fiche en dit 8",
        "model-00002-of-00002.safetensors absent",
    ]


def test_des_poids_modifies_a_taille_egale_ne_se_voient_qu_avec_les_empreintes(tmp_path: Path) -> None:
    attendu = _faux_modele(tmp_path)
    (tmp_path / "model-00002-of-00002.safetensors").write_bytes(b"poids-DEUX")
    assert VERIF.ecarts_modele(attendu, tmp_path) == []
    assert VERIF.ecarts_modele(attendu, tmp_path, empreintes=True) == [
        "model-00002-of-00002.safetensors : contenu modifié"
    ]


def test_une_version_de_paquet_differente_ou_absente_est_refusee() -> None:
    attendus = {"vllm": "0.27.1", "torch": "2.13.0", "triton": "3.7.1"}
    installes = {"vllm": "0.28.0", "torch": "2.13.0", "triton": None}
    assert VERIF.ecarts_paquets(attendus, installes) == [
        "vllm 0.28.0 (fiche : 0.27.1)",
        "triton absent (fiche : 3.7.1)",
    ]


def test_les_versions_se_lisent_dans_l_environnement_donne(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    python = tmp_path / "bin" / "python"
    python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    python.chmod(0o755)
    versions = VERIF.versions_du_venv(tmp_path, ["pyyaml", "paquet-qui-n-existe-pas"])
    assert isinstance(versions["pyyaml"], str)
    assert versions["paquet-qui-n-existe-pas"] is None
