"""Tests de la garde d'arborescence. Lancer : make tests-garde"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

DOSSIER_GARDE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOSSIER_GARDE))

import verifier_arborescence as va  # noqa: E402

SCRIPT = DOSSIER_GARDE / "verifier_arborescence.py"

PLAN_TEST = {
    "version": 1,
    "adr": "0001",
    "nommage": {"motif": r"^[a-z0-9_][a-z0-9_.-]*$", "exceptions": ["README.md"], "libre": ["05_pme/donnees"]},
    "ignorer": {
        "chemins": [".git", "99_local"],
        "noms": ["node_modules", "__pycache__"],
        "suffixes": [".egg-info"],
    },
    "racine": {
        "fichiers": ["README.md", "arborescence.toml"],
        "dossiers": ["00_docs", "02_ease", "05_pme", "99_local"],
    },
    "zones": {
        "00_docs": {
            "entrees": ["README.md", "adr/"],
            "obligatoires": ["README.md", "adr/"],
            "extensions": [".md"],
        },
        "02_ease": {
            "entrees": ["README.md", "pyproject.toml", "src/", "tests/"],
            "obligatoires": ["README.md"],
            "extensions": [".py", ".toml", ".md"],
        },
        "05_pme": {
            "entrees": ["README.md", "*/"],
            "obligatoires": ["README.md"],
            "extensions": [".ts", ".json", ".md"],
        },
    },
}

DEPOT_CONFORME = [
    "README.md",
    "arborescence.toml",
    "00_docs/README.md",
    "00_docs/adr/2026-10-05_0001_arborescence_initiale.md",
    "02_ease/README.md",
    "02_ease/src/ease/__init__.py",
    "02_ease/tests/test_rien.py",
    "05_pme/README.md",
    "05_pme/messagerie/src/serveur.ts",
]


def creer(racine: Path, chemins: list[str]) -> None:
    for chemin in chemins:
        cible = racine / chemin
        if chemin.endswith("/"):
            cible.mkdir(parents=True, exist_ok=True)
        else:
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_text("x", encoding="utf-8")


class TestGarde(unittest.TestCase):
    """Cas synthétiques, sur un dépôt temporaire et un plan réduit."""

    def setUp(self) -> None:
        self.temporaire = tempfile.TemporaryDirectory()
        self.racine = Path(self.temporaire.name)
        creer(self.racine, DEPOT_CONFORME)
        self.garde = va.Garde(PLAN_TEST, self.racine)

    def tearDown(self) -> None:
        self.temporaire.cleanup()

    def test_depot_conforme(self) -> None:
        self.assertEqual(self.garde.parcourir(), [])

    def test_dossier_racine_non_prevu(self) -> None:
        creer(self.racine, ["scripts/outil.py"])
        ecarts = self.garde.parcourir()
        self.assertEqual(len(ecarts), 1)
        self.assertIn("scripts", ecarts[0])

    def test_fichier_racine_non_prevu(self) -> None:
        creer(self.racine, ["notes.txt"])
        ecarts = self.garde.parcourir()
        self.assertEqual(len(ecarts), 1)
        self.assertIn("racine", ecarts[0])

    def test_entree_de_zone_non_prevue(self) -> None:
        creer(self.racine, ["02_ease/divers/a.py"])
        ecarts = self.garde.parcourir()
        self.assertEqual(len(ecarts), 1)
        self.assertIn("divers/", ecarts[0])

    def test_langage_hors_de_son_territoire(self) -> None:
        creer(self.racine, ["02_ease/src/ease/client.ts"])
        ecarts = self.garde.parcourir()
        self.assertEqual(len(ecarts), 1)
        self.assertIn(".ts", ecarts[0])

    def test_nom_avec_accent_ou_espace(self) -> None:
        creer(self.racine, ["02_ease/src/ease/étape un.py"])
        ecarts = self.garde.parcourir()
        self.assertEqual(len(ecarts), 1)
        self.assertIn("nommage", ecarts[0])

    def test_nommage_libre_sous_le_chemin_declare_seulement(self) -> None:
        libre = PurePosixPath("05_pme/donnees/boites/contact@calorelle.example/Facture F-12.json")
        self.assertEqual(self.garde.controler(libre, est_fichier=True), [])
        ailleurs = PurePosixPath("05_pme/messagerie/contact@calorelle.example.json")
        self.assertTrue(self.garde.controler(ailleurs, est_fichier=True))
        self.assertTrue(self.garde.controler(PurePosixPath("05_pme/Donnees/x.json"), est_fichier=True))

    def test_nommage_libre_garde_le_controle_des_extensions(self) -> None:
        ecarts = self.garde.controler(PurePosixPath("05_pme/donnees/Outil Pratique.exe"), est_fichier=True)
        self.assertTrue(any("extension" in e for e in ecarts))

    def test_chemins_ignores(self) -> None:
        creer(
            self.racine,
            [
                "99_local/runs/brut.bin",
                "05_pme/messagerie/node_modules/Paquet/index.js",
                "02_ease/src/ease/__pycache__/a.pyc",
                "02_ease/src/ease.egg-info/PKG-INFO",
            ],
        )
        self.assertEqual(self.garde.parcourir(), [])

    def test_obligatoire_absent(self) -> None:
        (self.racine / "02_ease/README.md").unlink()
        ecarts = self.garde.parcourir()
        self.assertEqual(len(ecarts), 1)
        self.assertIn("obligatoire", ecarts[0])

    def test_adr_cite_introuvable(self) -> None:
        (self.racine / "00_docs/adr/2026-10-05_0001_arborescence_initiale.md").unlink()
        self.assertTrue(any("ADR" in ecart for ecart in self.garde.parcourir()))

    def test_adr_mal_nomme(self) -> None:
        creer(self.racine, ["00_docs/adr/nouvelle_decision.md"])
        self.assertTrue(any("AAAA-MM-JJ_NNNN" in ecart for ecart in self.garde.parcourir()))

    def test_chemin_a_creer(self) -> None:
        self.assertEqual(self.garde.controler(PurePosixPath("02_ease/src/ease/nouveau.py"), est_fichier=True), [])
        self.assertNotEqual(self.garde.controler(PurePosixPath("02_ease/brouillon.py"), est_fichier=True), [])


class TestDepotReel(unittest.TestCase):
    """Le dépôt réel respecte son propre plan, et le crochet Claude Code bloque ce qu'il faut."""

    def setUp(self) -> None:
        try:
            self.plan = va.charger_plan(va.RACINE)
        except va.PlanIllisible as erreur:
            self.skipTest(str(erreur))

    def test_depot_reel_conforme(self) -> None:
        self.assertEqual(va.Garde(self.plan, va.RACINE).parcourir(), [])

    def crochet(self, chemin: Path) -> int:
        appel = {"tool_name": "Write", "tool_input": {"file_path": str(chemin), "content": "x"}}
        resultat = subprocess.run(
            [sys.executable, str(SCRIPT), "--hook-claude"],
            input=json.dumps(appel),
            capture_output=True,
            text=True,
        )
        return resultat.returncode

    def test_crochet_laisse_passer_un_chemin_prevu(self) -> None:
        self.assertEqual(self.crochet(va.RACINE / "02_ease/src/ease/executeur.py"), 0)

    def test_crochet_bloque_un_chemin_hors_plan(self) -> None:
        self.assertEqual(self.crochet(va.RACINE / "brouillon/notes.md"), 2)
        self.assertEqual(self.crochet(va.RACINE / "02_ease/src/ease/client.ts"), 2)

    def test_crochet_ignore_les_ecritures_hors_depot(self) -> None:
        self.assertEqual(self.crochet(Path(tempfile.gettempdir()) / "ailleurs.txt"), 0)


if __name__ == "__main__":
    unittest.main()
