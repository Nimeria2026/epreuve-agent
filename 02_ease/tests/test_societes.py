"""Plusieurs sociétés fictives dans 05_pme/societes/ (ADR 0006) : le champ societe d'une tâche,
les paramètres d'une société, et Calorelle inchangée, empreintes comprises."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from ease.chargement import (
    PARAMETRES_CALORELLE,
    SOCIETE,
    ContratInvalide,
    dossier_complements_caches,
    parametres_societe,
    racine_depot,
)
from ease.contrats.tache import Tache
from ease.empreintes import empreinte_json
from ease.etat_pme import capturer
from ease.pme import REGLES_GARDIEN, EnvironnementPME, dossier_version, regles_gardien
from ease.taches import (
    donnees_empreinte,
    lire_taches,
    societe_de,
    societe_des_taches,
    taches_documents,
    taches_dure,
    taches_dure_v2,
)

RACINE = racine_depot()
TACHES_CALORELLE = [
    *lire_taches(RACINE / "07_taches" / "public"),
    *taches_documents(),
    *taches_dure(),
    *taches_dure_v2(),
]


def _autre(tache: Tache, societe: str) -> Tache:
    return tache.model_copy(update={"societe": societe})


def test_les_taches_de_calorelle_sont_de_calorelle() -> None:
    assert TACHES_CALORELLE
    assert {societe_de(t) for t in TACHES_CALORELLE} == {SOCIETE}


def test_empreinte_du_jeu_de_calorelle_inchangee() -> None:
    """Le champ societe ne compte pas pour Calorelle : l'empreinte d'un jeu est celle qu'il avait
    avant le champ, quand model_dump ne le portait pas (choix d'Alexandre du 2026-10-15)."""
    for tache in TACHES_CALORELLE:
        sans_champ = {k: v for k, v in tache.model_dump(mode="json").items() if k != "societe"}
        assert donnees_empreinte(tache) == sans_champ
    explicite = [_autre(t, SOCIETE) for t in TACHES_CALORELLE]
    assert empreinte_json([donnees_empreinte(t) for t in explicite]) == empreinte_json(
        [donnees_empreinte(t) for t in TACHES_CALORELLE]
    )


def test_le_champ_societe_compte_pour_une_autre_societe() -> None:
    tache = TACHES_CALORELLE[0]
    autre = _autre(tache, "domivelle")
    assert donnees_empreinte(autre)["societe"] == "domivelle"
    assert empreinte_json([donnees_empreinte(autre)]) != empreinte_json([donnees_empreinte(tache)])


def test_un_run_ne_melange_pas_deux_societes() -> None:
    assert societe_des_taches(TACHES_CALORELLE[:3]) == SOCIETE
    with pytest.raises(ValueError, match="2 sociétés"):
        societe_des_taches([TACHES_CALORELLE[0], _autre(TACHES_CALORELLE[1], "domivelle")])


def test_l_environnement_refuse_une_tache_d_une_autre_societe(tmp_path: Path) -> None:
    environnement = EnvironnementPME("v3", tmp_path / "pme")
    assert environnement.societe == SOCIETE
    with pytest.raises(ValueError, match="deux sociétés"):
        environnement.ouvrir(_autre(TACHES_CALORELLE[0], "domivelle"))


def test_chemins_par_societe() -> None:
    caches = RACINE / "07_taches" / "prive" / "complements"
    assert dossier_complements_caches() == caches
    assert dossier_complements_caches("domivelle") == caches / "domivelle"
    assert regles_gardien() == REGLES_GARDIEN == RACINE / "06_gardien" / "regles" / "v2.yaml"
    assert regles_gardien("domivelle") == RACINE / "06_gardien" / "regles" / "domivelle" / "v2.yaml"


def test_parametres_de_calorelle_par_defaut() -> None:
    for version in ("v1", "v2", "v3"):
        etat = dossier_version(version)
        assert not (etat / "entreprise" / "societe.yaml").exists()
        assert parametres_societe(etat) == PARAMETRES_CALORELLE
    assert capturer(dossier_version("v3")).domaine == "calorelle.example"


def test_parametres_lus_et_controles(tmp_path: Path) -> None:
    etat = tmp_path / "etat"
    shutil.copytree(dossier_version("v1") / "entreprise", etat / "entreprise")
    fichier = etat / "entreprise" / "societe.yaml"
    fichier.write_text("nom: Essai\ndomaine: essai.example\ndossier_fiches_fournisseurs: artisans\n", encoding="utf-8")
    parametres = parametres_societe(etat)
    assert (parametres.nom, parametres.domaine, parametres.dossier_fiches_fournisseurs) == (
        "Essai",
        "essai.example",
        "artisans",
    )
    assert capturer(etat).domaine == "essai.example"
    fichier.write_text("nom: Essai\ndomaine: essai.fr\ndossier_fiches_fournisseurs: artisans\n", encoding="utf-8")
    with pytest.raises(ContratInvalide):
        parametres_societe(etat)
