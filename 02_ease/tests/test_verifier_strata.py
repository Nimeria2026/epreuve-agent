"""La fiche du moteur de Flash-Next (02_ease/src/ease/moteurs/) et sa vérification par make strata
(09_outillage/scripts/verifier_strata.py ; JOURNAL, entrée 296)."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from types import ModuleType
from typing import Any

import yaml
from ease.candidats import DOSSIER as DOSSIER_CANDIDATS
from ease.chargement import racine_depot
from ease.donnees_publication import DOSSIER_TAU2


def _module() -> ModuleType:
    chemin = racine_depot() / "09_outillage" / "scripts" / "verifier_strata.py"
    spec = importlib.util.spec_from_file_location("verifier_strata", chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verifier_strata"] = module
    spec.loader.exec_module(module)
    return module


VERIF = _module()
PRESET = racine_depot() / "02_ease" / "src" / "ease" / "moteurs" / "strata_flash_next.json"
MAISON = "/maison/essai"


def _reference() -> dict[str, Any]:
    return json.loads(PRESET.read_text(encoding="utf-8"))


def test_le_preregle_du_depot_n_a_ni_chemin_personnel_ni_cle() -> None:
    texte = PRESET.read_text(encoding="utf-8")
    assert re.search(r"/(?:home|Users)/", texte) is None and "api_key" not in texte.lower()
    assert _reference()["choices"]["context"] == 131072


def test_le_preregle_identique_au_chemin_personnel_pres_est_conforme() -> None:
    vivant = copy.deepcopy(_reference())
    vivant["choices"]["model_file"] = vivant["choices"]["model_file"].replace("~", MAISON, 1)
    vivant["recheck"]["last_ok"] = "2026-11-02"
    vivant["measured"]["decode_tok_s"] = 110.0
    assert VERIF.ecarts(_reference(), vivant, MAISON) == []
    assert VERIF.deballer({"preset": vivant}) == vivant


def test_un_reglage_un_moteur_ou_un_contexte_changes_sont_refuses() -> None:
    vivant = copy.deepcopy(_reference())
    vivant["settings"]["args"] = {"--prefill": "auto:32768"}
    vivant["identity"]["engine"]["sha256"] = "0" * 64
    vivant["choices"]["context"] = 65536
    assert VERIF.ecarts(_reference(), vivant, MAISON) == ["choices", "settings", "identity.engine.sha256"]


def test_le_preregle_compte_dans_l_empreinte_des_deux_declarations() -> None:
    chemin = "02_ease/src/ease/moteurs/strata_flash_next.json"
    declarations = (
        DOSSIER_CANDIDATS / "agent_seul_qwen_flash_next_strata.yaml",
        DOSSIER_TAU2 / "reproduction_tau2_qwen_flash_next_strata.yaml",
    )
    for declaration in declarations:
        lue: dict[str, Any] = yaml.safe_load(declaration.read_text(encoding="utf-8"))
        assert chemin in lue["lancement"]["empreinte_de"]
