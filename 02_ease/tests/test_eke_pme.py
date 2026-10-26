"""EKE dans la PME (étape 6) : lancé par EASE ou par le gardien pour les seules tâches qui le
déclarent, par le Python de l'environnement du dépôt ; ses trois outils sont en lecture seule."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from ease.chargement import racine_depot
from ease.contrats.tache import Tache
from ease.pme import REGLES_GARDIEN, EnvironnementPME, commande_du_service
from ease.taches import coherence_pme, lire_tache

TACHES = racine_depot() / "07_taches" / "public"
OUTILS_EKE = {"lire_document", "extraire_valeurs", "citer"}
DEVIS = "commercial/devis/2026/dv-2026-001.pdf"


def _tache_documentaire(services: list[str]) -> Tache:
    """Une tâche de v3 pour la gérante, faite à partir de t01 : seuls comptent l'état, les services
    et la personne servie."""
    t01 = lire_tache(TACHES / "t01_ranger_facture_fournisseur.yaml")
    return t01.model_copy(
        update={
            "identifiant": "essai_eke",
            "etat_initial": "v3",
            "services": services,
            "agent_pour": "helene.marchal",
            "complement": None,
        }
    )


def test_les_services_existants_se_lancent_comme_avant() -> None:
    principal = racine_depot() / "05_pme" / "dossiers" / "src" / "principal.ts"
    assert commande_du_service("dossiers") == ["node", str(principal)]
    assert commande_du_service("eke") == [sys.executable, "-m", "eke"]
    with pytest.raises(ValueError, match="service inconnu de la PME : inconnu"):
        commande_du_service("inconnu")


@pytest.mark.parametrize("avec_gardien", [False, True], ids=["sans_gardien", "avec_gardien"])
def test_eke_se_lance_pour_la_tache_qui_le_declare(tmp_path: Path, avec_gardien: bool) -> None:
    environnement = EnvironnementPME("v3", tmp_path / "pme", gardien=REGLES_GARDIEN if avec_gardien else None)
    try:
        environnement.ouvrir(_tache_documentaire(["dossiers", "eke"]))
        outils = {o.nom: o for o in environnement.outils()}
        assert set(outils) >= OUTILS_EKE and "lire" in outils
        assert all(outils[nom].lecture_seule is True for nom in OUTILS_EKE)
        lecture = json.loads(environnement.appeler("lire_document", {"chemin": DEVIS}))
        assert lecture["lignes"][0]["texte"] == "DEVIS DV-2026-001"
    finally:
        environnement.fermer()
    if avec_gardien:
        lignes = [json.loads(ligne) for ligne in environnement.journal_gardien.read_text(encoding="utf-8").splitlines()]
        assert [(ligne["outil"], ligne["verdict"]) for ligne in lignes] == [("lire_document", "autorise")]


def test_une_tache_sans_eke_ne_le_voit_pas(tmp_path: Path) -> None:
    environnement = EnvironnementPME("v3", tmp_path / "pme")
    try:
        environnement.ouvrir(_tache_documentaire(["dossiers"]))
        assert not OUTILS_EKE & {o.nom for o in environnement.outils()}
    finally:
        environnement.fermer()


def test_le_contrat_de_tache_accepte_eke_et_refuse_un_service_inconnu() -> None:
    assert coherence_pme(_tache_documentaire(["dossiers", "eke"])) == []
    ecarts = coherence_pme(_tache_documentaire(["dossiers", "inconnu"]))
    assert ecarts == ["services : « inconnu » n'est pas un service de la PME"]
