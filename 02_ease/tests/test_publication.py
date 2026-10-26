"""Images d'une publication : écrites depuis les données seules, aucun nombre qui n'en vienne."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from ease import publication
from ease.donnees_publication import chiffre
from ease.publication import (
    POLICES,
    PublicationImpossible,
    chiffres_hors_donnees,
    dossier_polices,
    nombres_affiches,
    pages,
)

DS, QW = "agent_seul_deepseek_flash", "agent_seul_qwen_local"


def _groupe(cle: str, libelle: str, taches: int, ds: tuple[int, int], qw: tuple[int, int]) -> dict[str, Any]:
    """Un métier fictif : essais et « 5 sur 5 » de chaque candidat, fourchettes posées à la main."""
    essais = taches * 5
    return {
        "cle": cle,
        "libelle": libelle,
        "taches": taches,
        "par_candidat": {
            DS: {"essais": chiffre(ds[0], essais, (0.8, 1.0)), "cinq_sur_cinq": chiffre(ds[1], taches, (0.5, 1.0))},
            QW: {"essais": chiffre(qw[0], essais, (0.6, 0.95)), "cinq_sur_cinq": chiffre(qw[1], taches, (0.25, 0.75))},
        },
    }


def _donnees() -> dict[str, Any]:
    """Des données du premier post, au format de ease.donnees_publication, sur deux métiers fictifs."""
    return {
        "sujet": "premier_post",
        "numero": 1,
        "version": 1,
        "produit_le": "2026-10-20",
        "mois": "octobre 2026",
        "pme": "Calorelle",
        "taches": 12,
        "repetitions": 5,
        "graduations": [
            {"valeur": 0.0, "pourcent": "0"},
            {"valeur": 0.5, "pourcent": "50"},
            {"valeur": 1.0, "pourcent": "100"},
        ],
        "taches_par_metier": {"min": 4, "max": 8},
        "candidats": [
            {"identifiant": DS, "nom": "DeepSeek V4.1 Flash", "detail": "par API"},
            {"identifiant": QW, "nom": "Qwen 3.8 27B", "detail": "en local, une carte RTX 3090"},
        ],
        "metiers": [
            _groupe("comptabilite", "Comptabilité", 8, (38, 6), (31, 3)),
            _groupe("planning", "Planning", 4, (20, 4), (17, 2)),
        ],
        "ensemble": _groupe("ensemble", "Les deux", 12, (58, 10), (48, 5)),
        "exemple": {
            "tache": "t10_rib_par_un_collegue",
            "court": "t10",
            "famille": "comptabilite",
            "candidat": QW,
            "essai": 1,
            "controle": 1,
            "run": "2026-10-09_220655_agent_seul_qwen_local",
            "essais": {DS: 5, QW: 5},
            "echecs_du_controle": {DS: 0, QW: 2},
        },
        "tau2": {
            DS: chiffre(189, 250, (0.699, 0.805))
            | {"publie": {"valeur": 0.768, "pourcent": "76,8", "source": "OpenRouter, relevé le 2026-10-13"}},
            QW: chiffre(187, 250, (0.691, 0.798))
            | {"publie": {"valeur": 0.776, "pourcent": "77,6", "source": "OpenRouter, relevé le 2026-10-13"}},
        },
        "graduations_tau2": [
            {"valeur": 0.5, "pourcent": "50"},
            {"valeur": 0.75, "pourcent": "75"},
            {"valeur": 1.0, "pourcent": "100"},
        ],
    }


@pytest.fixture
def polices(tmp_path: Path) -> Path:
    """Un dépôt Nimeria voisin, avec ses polices (vides : seule leur présence compte ici)."""
    dossier = tmp_path / "Nimeria" / "site" / "public" / "fonts"
    dossier.mkdir(parents=True)
    for police in POLICES:
        (dossier / police).write_bytes(b"")
    return dossier_polices(tmp_path / "Nimeria_poa")


def test_les_quatre_images_n_affichent_que_des_nombres_des_donnees(polices: Path) -> None:
    donnees = _donnees()
    ecrites = pages("premier_post", donnees, polices)
    assert len(ecrites) == 4
    for page in ecrites:
        assert chiffres_hors_donnees(page, donnees) == []
    assert {"97", "58", "60", "83"} <= set(nombres_affiches(ecrites[0]))
    assert "Sur 5 essais, Qwen 3.8 27B fait cette erreur 2 fois ; DeepSeek V4.1 Flash, jamais." in ecrites[2]


def test_un_nombre_absent_des_donnees_est_refuse(polices: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    donnees = _donnees()
    page = pages("premier_post", donnees, polices)[0].replace("en local, une carte RTX 3090", "en local, 24 Go")
    assert chiffres_hors_donnees(page, donnees) == ["24"]
    images = publication.IMAGES["premier_post"]
    monkeypatch.setitem(publication.IMAGES, "premier_post", (lambda _: "<p>777 tâches</p>", *images[1:]))
    with pytest.raises(PublicationImpossible, match="image 1 : nombres absents des données, 777"):
        pages("premier_post", copy.deepcopy(donnees), polices)


def test_les_nombres_de_mise_en_page_ne_comptent_pas() -> None:
    page = '<div>1 234 essais, 96,4 %</div><span class="hors-donnees">2/4</span><style>.a{width:1080px}</style>'
    assert nombres_affiches(page) == ["1 234", "96,4"]


def test_sans_les_polices_de_nimeria_rien_ne_s_ecrit(tmp_path: Path) -> None:
    with pytest.raises(PublicationImpossible, match="polices absentes"):
        dossier_polices(tmp_path / "Nimeria_poa")


def test_des_donnees_d_une_autre_publication_sont_refusees(polices: Path) -> None:
    donnees = _donnees() | {"sujet": "constat"}
    with pytest.raises(PublicationImpossible, match="pas de « premier_post »"):
        pages("premier_post", donnees, polices)


def _donnees_constat() -> dict[str, Any]:
    """Des données du constat, au format de ease.donnees_publication, posées à la main."""
    socle = _groupe("socle", "Le socle", 10, (48, 9), (42, 6))
    socle |= {"publiques": 8, "cachees": 2}
    socle["par_candidat"][DS]["duree_mediane"] = {"secondes": 28.4, "texte": "28\u00a0s"}
    socle["par_candidat"][QW]["duree_mediane"] = {"secondes": 173.6, "texte": "3\u00a0min"}
    socle["ecarts"] = {
        "essais": {"points": "12", "etabli": True},
        "cinq_sur_cinq": {"points": "30", "etabli": False},
        "duree_mediane": {"etabli": True},
    }
    grille = [16.0, 32.0, 64.0]
    courbe = {
        "texte": "au-delà de 64,0\u00a0min",
        "essais": 15,
        "fourchette_texte": ["30,5\u00a0min", "plus de 64,0\u00a0min"],
        "courbe": [0.9, 0.85, 0.8],
        "bande": [[0.7, 1.0], [0.6, 0.95], [0.5, 0.9]],
        "points": [{"minutes": 16.0, "reussis": 5, "sur": 5}, {"minutes": 64.0, "reussis": 4, "sur": 5}],
    }
    return {
        "sujet": "constat",
        "version": 1,
        "produit_le": "2026-10-20",
        "mois": "octobre 2026",
        "pme": "Calorelle",
        "repetitions": 5,
        "candidats": [
            {"identifiant": DS, "nom": "DeepSeek V4.1 Flash", "detail": "par API, en heures creuses"},
            {"identifiant": QW, "nom": "Qwen 3.8 27B", "detail": "en local, une carte RTX 3090"},
        ],
        "socle": socle,
        "horizon": {
            "taches": 3,
            "cachees": 1,
            "plage": [{"minutes": 16.0, "texte": "16,0\u00a0min"}, {"minutes": 64.0, "texte": "64,0\u00a0min"}],
            "graduations_minutes": [{"minutes": 30.0, "texte": "30,0\u00a0min"}],
            "grille_minutes": grille,
            "par_candidat": {DS: courbe, QW: courbe | {"texte": "20,1\u00a0min"}},
            "etabli": True,
        },
        "graves": {
            "taches": 4,
            "gardien": "v1",
            "sans_gardien": {
                DS: chiffre(0, 20, (0.0, 0.16)),
                QW: chiffre(3, 20, (0.05, 0.36)),
                "ecart": {"points": "15", "etabli": True},
            },
            "avec_gardien": {
                DS: chiffre(0, 20, (0.0, 0.16)),
                QW: chiffre(1, 20, (0.01, 0.24)),
                "ecart": {"points": "5", "etabli": False},
            },
        },
        "graduations": [
            {"valeur": 0.0, "pourcent": "0"},
            {"valeur": 0.5, "pourcent": "50"},
            {"valeur": 1.0, "pourcent": "100"},
        ],
        "tau2": _donnees()["tau2"]
        | {
            DS: _donnees()["tau2"][DS] | {"dans_la_fourchette": True},
            QW: _donnees()["tau2"][QW] | {"dans_la_fourchette": True},
        },
    }


def test_les_trois_images_du_constat_n_affichent_que_des_nombres_des_donnees(polices: Path) -> None:
    donnees = _donnees_constat()
    ecrites = pages("constat", donnees, polices)
    assert len(ecrites) == 3
    for page in ecrites:
        assert chiffres_hors_donnees(page, donnees) == []
    tableau = ecrites[0]
    assert tableau.count('<div class="egal">≈</div>') == 2
    assert "Les scores publiés tombent dans nos fourchettes." in ecrites[2]


def test_un_score_publie_hors_de_la_fourchette_se_dit(polices: Path) -> None:
    donnees = _donnees_constat()
    donnees["tau2"][QW]["dans_la_fourchette"] = False
    assert "Un score publié sort de notre fourchette" in pages("constat", donnees, polices)[2]
