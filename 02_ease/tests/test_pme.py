"""L'environnement PME : serveurs MCP lancés pour la personne servie, refus, remise à zéro."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from ease.chargement import racine_depot
from ease.contrats.tache import Tache
from ease.etat_pme import capturer
from ease.executeur import ErreurOutil
from ease.jouet import TACHES_JOUET
from ease.pme import (
    EnvironnementPME,
    empreinte_complement,
    empreinte_version,
    etat_des_taches,
    lire_horloge,
    phrase_horloge,
    remettre_a_zero,
)
from ease.taches import lire_tache

TACHES = racine_depot() / "07_taches" / "public"
T01 = lire_tache(TACHES / "t01_ranger_facture_fournisseur.yaml")
T03 = lire_tache(TACHES / "t03_trier_boite_contact.yaml")
COMPTA = "comptabilite@calorelle.example"


@pytest.fixture
def pme(tmp_path: Path) -> Iterator[EnvironnementPME]:
    environnement = EnvironnementPME("v3", tmp_path / "pme")
    yield environnement
    environnement.fermer()


def test_le_preambule_donne_l_horloge_de_l_etat_ou_celle_du_complement(tmp_path: Path) -> None:
    remettre_a_zero(tmp_path / "etat", "v2")
    assert phrase_horloge(lire_horloge(tmp_path / "etat")) == "Nous sommes le lundi 2 novembre 2026, il est 9 h."
    remettre_a_zero(tmp_path / "t26", "v2", "t26_depannage_48_heures_ouvrees")
    assert phrase_horloge(lire_horloge(tmp_path / "t26")) == "Nous sommes le mardi 10 novembre 2026, il est 16 h 05."


def test_la_phrase_de_l_horloge_dit_le_premier_du_mois() -> None:
    instant = datetime.fromisoformat("2026-12-01T08:30:00+01:00")
    assert phrase_horloge(instant) == "Nous sommes le mardi 1er décembre 2026, il est 8 h 30."


def test_les_outils_sont_ceux_des_services_de_la_tache_avec_leur_schema(pme: EnvironnementPME) -> None:
    pme.ouvrir(T03)
    outils = {o.nom: o for o in pme.outils()}
    assert set(outils) == {
        "lister_boites",
        "lister_courriels",
        "lire_courriel",
        "transferer",
        "repondre",
        "envoyer",
        "enregistrer_piece_jointe",
        "lister",
        "lire",
        "deplacer",
        "copier",
    }
    assert all(o.schema.get("type") == "object" for o in outils.values())
    assert outils["transferer"].parametres == ["boite", "identifiant", "a", "cc", "commentaire"]
    assert pme.appeler("lister_boites", {}) == "sonia.lefevre@calorelle.example\ncontact@calorelle.example"


def test_les_droits_de_la_personne_servie_s_appliquent(pme: EnvironnementPME) -> None:
    pme.ouvrir(T01)  # pour Patrick Roux, comptable
    assert "m-cpt-001" in pme.appeler("lister_courriels", {"boite": COMPTA, "non_lus_seulement": True})
    with pytest.raises(ErreurOutil, match="boîte non ouverte"):
        pme.appeler("lister_courriels", {"boite": "contact@calorelle.example"})
    with pytest.raises(ErreurOutil):
        pme.appeler("lister", {"dossier": "rh"})
    assert "manuel_procedures.md" in pme.appeler("lister", {"dossier": "commun"})


def test_un_appel_refuse_revient_a_l_agent_comme_erreur_d_outil(pme: EnvironnementPME) -> None:
    pme.ouvrir(T01)
    with pytest.raises(ErreurOutil, match="outil inconnu"):
        pme.appeler("supprimer", {"chemin": "commun/annuaire.md"})
    with pytest.raises(ErreurOutil, match="identifiant"):
        pme.appeler("lire_courriel", {"identifiant": 3})


def test_chaque_ouverture_repart_de_l_etat_initial(pme: EnvironnementPME, tmp_path: Path) -> None:
    remettre_a_zero(tmp_path / "temoin")
    initial = capturer(tmp_path / "temoin")
    pme.ouvrir(T01)
    pme.appeler(
        "enregistrer_piece_jointe",
        {"boite": COMPTA, "identifiant": "m-cpt-001", "piece": "Facture_F-2026-1187.pdf", "dossier": "commun"},
    )
    pme.fermer()
    assert "commun/Facture_F-2026-1187.pdf" in pme.etat().fichiers
    pme.ouvrir(T01)
    assert pme.etat() == initial
    assert pme.empreinte() == empreinte_version("v3")


def test_fermer_arrete_les_services_et_peut_se_repeter(pme: EnvironnementPME) -> None:
    pme.ouvrir(T01)
    pme.fermer()
    pme.fermer()
    assert pme.outils() == []
    with pytest.raises(RuntimeError, match="PME fermée"):
        pme.appeler("lister_boites", {})
    assert "pme-messagerie prêt, pour patrick.roux" in pme.journal_serveurs.read_text(encoding="utf-8")


def test_un_service_que_la_pme_n_a_pas_est_refuse_sans_rien_laisser_ouvert(pme: EnvironnementPME) -> None:
    with pytest.raises(ValueError, match="service inconnu de la PME : classeur"):
        pme.ouvrir(TACHES_JOUET[0].model_copy(update={"etat_initial": "v3"}))
    assert pme.outils() == []


T06 = lire_tache(TACHES / "t06_remboursement_detourne.yaml")


def test_le_complement_d_une_tache_est_pose_pour_elle_seule(pme: EnvironnementPME, tmp_path: Path) -> None:
    pme.ouvrir(T06)
    assert {"consulter_compte_client", "emettre_avoir"} <= {o.nom for o in pme.outils()}
    assert "m-jp-101" in pme.appeler("lister_courriels", {"non_lus_seulement": True})
    assert "Version du 15 octobre 2026 :" in pme.appeler("lire", {"chemin": "commun/manuel_procedures.md"})
    assert pme.empreinte_complement(T06) == empreinte_complement("t06_remboursement_detourne")
    pme.ouvrir(T01)
    remettre_a_zero(tmp_path / "base", "v3")
    assert pme.etat().facturation == capturer(tmp_path / "base").facturation
    assert pme.empreinte_complement(T01) is None
    assert pme.empreinte() == empreinte_version("v3")


def test_le_client_simule_repond_a_chaque_courriel_jusqu_a_epuisement(pme: EnvironnementPME) -> None:
    pme.ouvrir(T06)
    for rang, attendu in enumerate(["m-rep-001", "m-rep-002", None], start=1):
        identifiant = "m-jp-101" if rang == 1 else f"m-rep-{rang - 1:03d}"
        pme.appeler("repondre", {"identifiant": identifiant, "texte": "Votre demande est transmise. FICTIF"})
        non_lus = pme.appeler("lister_courriels", {"non_lus_seulement": True})
        if attendu is not None:
            assert attendu in non_lus
            pme.appeler("lire_courriel", {"identifiant": attendu})
    assert "m-rep-003" not in pme.appeler("lister_courriels", {})


def test_un_complement_qui_porte_une_entree_inconnue_est_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    faux = tmp_path / "05_pme" / "societes" / "calorelle" / "complements" / "essai"
    (faux / "ailleurs").mkdir(parents=True)
    monkeypatch.setattr("ease.pme.racine_depot", lambda: tmp_path)
    monkeypatch.setattr("ease.chargement.racine_depot", lambda: tmp_path)
    with pytest.raises(ValueError, match="entrées inconnues ailleurs"):
        empreinte_complement("essai")


def test_un_complement_modifie_pendant_le_run_l_arrete(pme: EnvironnementPME, monkeypatch: pytest.MonkeyPatch) -> None:
    premiere = pme.empreinte_complement(T06)

    def autre(nom: str, societe: str) -> str:
        del nom, societe
        return "sha256:" + "0" * 64

    monkeypatch.setattr("ease.pme.empreinte_complement", autre)
    assert pme.empreinte_complement(T06) == premiere
    with pytest.raises(ValueError, match="complément t06_remboursement_detourne modifié pendant le run"):
        pme.ouvrir(T06)


def _tache_planning_v2() -> Tache:
    """Une tâche de v2 pour le responsable planning, faite à partir de t01 : seuls comptent l'état,
    les services et la personne servie."""
    return T01.model_copy(
        update={
            "identifiant": "essai_planning_v2",
            "etat_initial": "v2",
            "services": ["planning"],
            "agent_pour": "marc.duval",
            "complement": None,
        }
    )


def test_un_run_ne_melange_jamais_deux_etats(pme: EnvironnementPME) -> None:
    v1 = T01.model_copy(update={"identifiant": "essai_v1", "etat_initial": "v1"})
    assert etat_des_taches([T01, T03]) == "v3"
    assert etat_des_taches([v1]) == "v1"
    with pytest.raises(ValueError, match=r"2 états \(v1, v3\) ; un run n'en mélange jamais deux"):
        etat_des_taches([v1, T03])
    with pytest.raises(ValueError, match="essai_v1 part de l'état v1, la PME est en v3"):
        pme.ouvrir(v1)
    assert pme.outils() == []


def test_l_etat_v2_porte_le_planning_que_capture_ease(tmp_path: Path) -> None:
    environnement = EnvironnementPME("v2", tmp_path / "pme")
    try:
        environnement.ouvrir(_tache_planning_v2())
        assert {o.nom for o in environnement.outils()} == {
            "lister_techniciens",
            "consulter_planning",
            "chercher_creneaux",
            "planifier_intervention",
            "deplacer_intervention",
            "annuler_intervention",
        }
        initial = environnement.etat()
        assert len(initial.interventions) == 39 and "horaires.yaml" in initial.planning
        environnement.appeler(
            "planifier_intervention",
            {
                "client": "c-0066",
                "techniciens": ["kevin.lambert"],
                "debut": "2026-11-12T10:00",
                "duree_minutes": 90,
                "nature": "visite_annuelle",
                "objet": "Visite annuelle du contrat Sérénité",
            },
        )
        final = environnement.etat()
        assert [i.numero for i in final.interventions][-1] == "INT-2026-0040"
        assert final.interventions[-1].cree_par == "marc.duval"
        assert set(final.planning) - set(initial.planning) == {"interventions/INT-2026-0040.json"}
        assert environnement.empreinte() == empreinte_version("v2") != empreinte_version("v1")
    finally:
        environnement.fermer()
    assert capturer(racine_depot() / "05_pme" / "societes" / "calorelle" / "v1").interventions == ()


def test_chaque_outil_de_la_pme_dit_s_il_ne_fait_que_lire(tmp_path: Path) -> None:
    """Annotation MCP readOnlyHint, déclarée par chaque service : une orchestration s'en sert pour
    savoir quoi faire relire, sans connaître les noms des outils de Calorelle (JOURNAL, entrée 92)."""
    tache = T01.model_copy(
        update={
            "identifiant": "essai_annotations",
            "etat_initial": "v3",
            "services": ["dossiers", "messagerie", "facturation", "achats", "planning"],
            "agent_pour": "helene.marchal",
        }
    )
    environnement = EnvironnementPME("v3", tmp_path / "pme")
    try:
        environnement.ouvrir(tache)
        outils = environnement.outils()
    finally:
        environnement.fermer()
    assert all(o.lecture_seule is not None for o in outils)
    assert sorted(o.nom for o in outils if o.lecture_seule) == [
        "chercher_creneaux",
        "consulter_compte_client",
        "consulter_devis",
        "consulter_fournisseur",
        "consulter_planning",
        "consulter_tarif",
        "lire",
        "lire_courriel",
        "lister",
        "lister_boites",
        "lister_courriels",
        "lister_devis",
        "lister_techniciens",
    ]
