"""Droits d'EKE : ce qu'une personne ouvre dans les dossiers partagés, et rien hors d'eux."""

from __future__ import annotations

from pathlib import Path

import pytest
from eke.contrat import racine_depot
from eke.droits import Dossiers, RefusEke, charger_personne

V3 = racine_depot() / "05_pme" / "societes" / "calorelle" / "v3"


def _etat(tmp_path: Path) -> Path:
    """Un état fictif minimal : deux personnes, quatre dossiers dont un ouvert à tous et un à personne."""
    etat = tmp_path / "etat"
    (etat / "entreprise").mkdir(parents=True)
    (etat / "entreprise" / "organigramme.yaml").write_text(
        "personnes:\n"
        "  - {id: ada.martin, nom: Ada Martin, droits: [compta]}\n"
        "  - {id: leo.petit, nom: Léo Petit, droits: []}\n",
        encoding="utf-8",
    )
    (etat / "entreprise" / "acces_dossiers.yaml").write_text(
        "commun: [tous]\nfactures: [compta, direction]\ndirection: [direction]\n", encoding="utf-8"
    )
    for dossier in ("commun", "factures", "direction", "archives"):
        (etat / "dossiers" / dossier).mkdir(parents=True)
        (etat / "dossiers" / dossier / "piece.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "dehors.pdf").write_bytes(b"%PDF-1.4\n")
    return etat


def test_une_personne_ouvre_ce_que_ses_droits_ouvrent(tmp_path: Path) -> None:
    etat = _etat(tmp_path)
    ada, leo = Dossiers.pour(etat, "ada.martin"), Dossiers.pour(etat, "leo.petit")
    assert ada.fichier("factures/piece.pdf").name == "piece.pdf"
    assert ada.fichier("commun/piece.pdf") == leo.fichier("commun/piece.pdf")
    assert ada.fichier("./commun//piece.pdf").name == "piece.pdf"
    with pytest.raises(RefusEke, match="accès refusé à factures/ pour Léo Petit"):
        leo.fichier("factures/piece.pdf")
    with pytest.raises(RefusEke, match="accès refusé à direction/ pour Ada Martin"):
        ada.fichier("direction/piece.pdf")
    with pytest.raises(RefusEke, match="accès refusé à archives/"):
        ada.fichier("archives/piece.pdf")  # absent de acces_dossiers.yaml : fermé par défaut


@pytest.mark.parametrize(
    ("chemin", "message"),
    [
        ("/etc/passwd", "chemin absolu refusé"),
        ("../dehors.pdf", "hors des dossiers partagés"),
        ("../../dehors.pdf", "hors des dossiers partagés"),
        ("commun/../../dehors.pdf", "hors des dossiers partagés"),
        ("commun/../direction/piece.pdf", "accès refusé à direction/"),
        ("commun/absente.pdf", "fichier introuvable"),
        ("commun", "fichier introuvable"),
        ("commun/\0.pdf", "chemin invalide"),
    ],
)
def test_aucun_chemin_ne_sort_des_dossiers_partages(tmp_path: Path, chemin: str, message: str) -> None:
    dossiers = Dossiers.pour(_etat(tmp_path), "ada.martin")
    with pytest.raises(RefusEke, match=message):
        dossiers.fichier(chemin)


def test_un_lien_n_ouvre_rien_de_plus(tmp_path: Path) -> None:
    etat = _etat(tmp_path)
    (etat / "dossiers" / "commun" / "vers_direction.pdf").symlink_to(etat / "dossiers" / "direction" / "piece.pdf")
    (etat / "dossiers" / "commun" / "vers_dehors.pdf").symlink_to(tmp_path / "dehors.pdf")
    leo = Dossiers.pour(etat, "leo.petit")
    with pytest.raises(RefusEke, match="accès refusé à direction/"):
        leo.fichier("commun/vers_direction.pdf")
    with pytest.raises(RefusEke, match="hors des dossiers partagés"):
        leo.fichier("commun/vers_dehors.pdf")


def test_une_personne_inconnue_est_refusee(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="personne inconnue"):
        Dossiers.pour(_etat(tmp_path), "intrus")


def test_les_droits_de_calorelle() -> None:
    """Sur l'état v3 : le comptable lit les factures, pas la direction ; l'apprenti lit commun/."""
    patrick, enzo = Dossiers.pour(V3, "patrick.roux"), Dossiers.pour(V3, "enzo.caron")
    facture = "administration/factures_fournisseurs/2026-10/thermopieces-loire_f-2026-1151.pdf"
    assert patrick.fichier(facture).is_file()
    with pytest.raises(RefusEke, match="accès refusé à direction/ pour Patrick Roux"):
        patrick.fichier("direction/budget_previsionnel_2027.pdf")
    with pytest.raises(RefusEke, match="accès refusé à administration/ pour Enzo Caron"):
        enzo.fichier(facture)
    assert enzo.ouvre("commun") and not enzo.ouvre("rh")
    assert "acces_direction" in charger_personne(V3, "helene.marchal").droits
