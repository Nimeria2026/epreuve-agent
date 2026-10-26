"""Le téléchargement de fr-bench-pdf2md sous manifeste, contre un dépôt simulé : aucun réseau.

Ce qui est vérifié : un fichier n'est rangé que s'il correspond à l'annonce du dépôt (taille,
sha256 LFS ou blob git) ; le manifeste note source, version, taille et sha256 ; tout écart entre
le disque et le manifeste (fichier manquant, en trop, modifié) arrête tout.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import pytest
from eke.banc_public.telechargement import (
    API,
    DEPOT,
    Annonce,
    EcartJeu,
    blob_git,
    chemin_manifeste,
    dossier_donnees,
    lire_manifeste,
    source,
    telecharger,
    verifier,
    verifier_annonce,
)

REVISION = "0123456789abcdef0123456789abcdef01234567"
FICHIERS = {
    "README.md": b"---\nlicense: mit\n---\n",
    "pdfs/charts/page 1/page 1.pdf": b"%PDF-1.4 faux\n",
    "pdfs/charts/page 1/metadata.json": b'{"pdf": "page 1.pdf", "page": 0}',
    "pdfs/charts/page 1/tests.jsonl": b'{"id": "t1", "type": "present", "text": "a"}\n',
    "figures/barplot.png": b"\x89PNG",
}


class DepotSimule:
    """Le dépôt tel que l'API de Hugging Face le décrit, et ses fichiers ; compte les appels."""

    def __init__(self, fichiers: dict[str, bytes], revision: str = REVISION) -> None:
        self.fichiers = dict(fichiers)
        self.revision = revision
        self.appels: list[str] = []
        self.annonce: dict[str, bytes] = dict(fichiers)

    def __call__(self, url: str) -> bytes:
        self.appels.append(url)
        if url == API.format(depot=DEPOT, revision=REVISION):
            freres: list[dict[str, object]] = []
            for chemin, contenu in self.annonce.items():
                frere: dict[str, object] = {"rfilename": chemin, "size": len(contenu), "blobId": blob_git(contenu)}
                if chemin.endswith(".pdf"):
                    frere["lfs"] = {"sha256": hashlib.sha256(contenu).hexdigest(), "size": len(contenu)}
                freres.append(frere)
            return json.dumps({"sha": self.revision, "siblings": freres}).encode()
        for chemin, contenu in self.fichiers.items():
            if url == source(chemin, REVISION):
                return contenu
        raise AssertionError(f"URL inattendue : {url}")


def _telecharger(dossier: Path, depot: DepotSimule) -> None:
    telecharger(dossier, depot, REVISION, dire=lambda _: None, fils=2)


def test_blob_git_comme_git_hash_object() -> None:
    # `printf 'hello\n' | git hash-object --stdin`
    assert blob_git(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_source_echappe_le_chemin() -> None:
    url = source("pdfs/a b/à[1].pdf", REVISION)
    assert url.endswith("/resolve/" + REVISION + "/" + quote("pdfs/a b/à[1].pdf"))
    assert " " not in url


def test_le_manifeste_note_chaque_fichier_retenu(tmp_path: Path) -> None:
    depot = DepotSimule(FICHIERS)
    _telecharger(tmp_path, depot)
    manifeste = lire_manifeste(tmp_path, REVISION)
    assert manifeste.revision == REVISION
    assert [e.chemin for e in manifeste.fichiers] == sorted(c for c in FICHIERS if not c.startswith("figures/"))
    for entree in manifeste.fichiers:
        assert entree.revision == REVISION
        assert entree.source == source(entree.chemin, REVISION)
        assert entree.taille == len(FICHIERS[entree.chemin])
        assert entree.sha256 == hashlib.sha256(FICHIERS[entree.chemin]).hexdigest()
    assert (dossier_donnees(tmp_path, REVISION) / "pdfs/charts/page 1/page 1.pdf").read_bytes() == FICHIERS[
        "pdfs/charts/page 1/page 1.pdf"
    ]


def test_relance_sans_reseau_si_le_jeu_est_conforme(tmp_path: Path) -> None:
    _telecharger(tmp_path, DepotSimule(FICHIERS))
    depot = DepotSimule(FICHIERS)
    _telecharger(tmp_path, depot)
    assert depot.appels == []


def test_un_contenu_qui_n_est_pas_celui_annonce_arrete_tout(tmp_path: Path) -> None:
    depot = DepotSimule(FICHIERS)
    depot.fichiers["pdfs/charts/page 1/page 1.pdf"] = b"%PDF-1.4 vrai\n"
    with pytest.raises(EcartJeu, match="sha256"):
        _telecharger(tmp_path, depot)
    assert not chemin_manifeste(tmp_path, REVISION).exists()


def test_un_petit_fichier_se_verifie_par_son_blob_git() -> None:
    contenu = b'{"pdf": "x.pdf"}'
    annonce = Annonce("pdfs/x/metadata.json", len(contenu), None, blob_git(contenu))
    verifier_annonce(annonce, contenu)
    with pytest.raises(EcartJeu, match="blob git"):
        verifier_annonce(annonce, b'{"pdf": "y.pdf"}')
    with pytest.raises(EcartJeu, match="octets"):
        verifier_annonce(annonce, contenu + b" ")


def test_une_autre_version_rendue_par_l_api_arrete_tout(tmp_path: Path) -> None:
    with pytest.raises(EcartJeu, match="version"):
        _telecharger(tmp_path, DepotSimule(FICHIERS, revision="f" * 40))


def test_un_chemin_qui_sort_du_dossier_est_refuse(tmp_path: Path) -> None:
    depot = DepotSimule(FICHIERS)
    depot.annonce["pdfs/../../ailleurs.pdf"] = b"%PDF-"
    with pytest.raises(EcartJeu, match="chemin refusé"):
        _telecharger(tmp_path, depot)


@pytest.mark.parametrize("ecart", ["modifie", "manquant", "en_trop"])
def test_tout_ecart_au_manifeste_arrete_tout(tmp_path: Path, ecart: str) -> None:
    _telecharger(tmp_path, DepotSimule(FICHIERS))
    donnees = dossier_donnees(tmp_path, REVISION)
    cible = donnees / "pdfs/charts/page 1/tests.jsonl"
    if ecart == "modifie":
        cible.write_bytes(b'{"id": "t1", "type": "present", "text": "b"}\n')
    elif ecart == "manquant":
        cible.unlink()
    else:
        (donnees / "pdfs/charts/page 1/notes.txt").write_text("ajout")
    with pytest.raises(EcartJeu):
        verifier(tmp_path, REVISION)
    with pytest.raises(EcartJeu):
        _telecharger(tmp_path, DepotSimule(FICHIERS))
