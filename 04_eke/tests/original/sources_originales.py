"""Le code original de la métrique de fr-bench-pdf2md, téléchargé et vérifié, pour la comparaison.

Trois fichiers, chacun vérifié par son sha256 avant usage, rangés hors git sous
`99_local/bancs_documents/fr_bench_pdf2md/original/` :

- `benchpdf2md/bench_tests/benchmark_tsts.py` et `benchpdf2md/create_dataset.py`, du dépôt GitHub
  `ld-lab-pulsia/benchpdf2md` au commit `ceab1548` (licence MIT) ;
- `vlmparse/clients/pipe_utils/html_to_md_conversion.py`, tiré de la roue PyPI de vlmparse 0.1.8
  (licence MIT), elle-même vérifiée par son sha256.

Bibliothèque standard seule ; s'exécute dans l'environnement jetable décrit dans `README.md`.
"""

# pyright: basic

from __future__ import annotations

import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
DOSSIER = RACINE / "99_local" / "bancs_documents" / "fr_bench_pdf2md" / "original"
COMMIT = "ceab1548ac914bff6585fa5c6227e2b24c35cfdb"
BRUT = "https://raw.githubusercontent.com/ld-lab-pulsia/benchpdf2md/" + COMMIT + "/"
ROUE = (
    "https://files.pythonhosted.org/packages/ed/da/6f27d0dee0615cf46824742c1206d5f07b4f6151e9ca53df042609f0f5b9/"
    "vlmparse-0.1.8-py3-none-any.whl"
)
SHA_ROUE = "e69d141b4d8a646e2bf664d67c812b6530d8b2695c6df81e536810674e89788d"
FICHIERS = {
    "benchpdf2md/bench_tests/benchmark_tsts.py": "a43792a3aa0562a99882a59a8920c6f95df7b02790098bd3fb124a870138ae32",
    "benchpdf2md/create_dataset.py": "d28e08d0ede91e6d56ecd60e4e75b526f3e683124cf0a2c494a16f01b3c02227",
    "vlmparse/clients/pipe_utils/html_to_md_conversion.py": (
        "70516acc3da308dc3ff7af3f7aedd6b7ef8ec7b8898f6467e54a0ffc3656a2c5"
    ),
}


def _lire(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as reponse:
        return reponse.read()


def _verifie(chemin: str, contenu: bytes) -> bytes:
    trouve = hashlib.sha256(contenu).hexdigest()
    if trouve != FICHIERS[chemin]:
        raise SystemExit(f"{chemin} : sha256 {trouve}, attendu {FICHIERS[chemin]} ; tout s'arrête")
    return contenu


def preparer() -> Path:
    """Range les trois fichiers s'ils manquent, vérifie les trois ; rend le dossier à mettre en tête
    de `sys.path`."""
    for chemin in FICHIERS:
        cible = DOSSIER / chemin
        if cible.exists():
            _verifie(chemin, cible.read_bytes())
            continue
        if chemin.startswith("benchpdf2md/"):
            contenu = _lire(BRUT + chemin)
        else:
            roue = _lire(ROUE)
            if hashlib.sha256(roue).hexdigest() != SHA_ROUE:
                raise SystemExit("roue de vlmparse 0.1.8 : sha256 inattendu ; tout s'arrête")
            contenu = zipfile.ZipFile(io.BytesIO(roue)).read(chemin)
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(_verifie(chemin, contenu))
    return DOSSIER
