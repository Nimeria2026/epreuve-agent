"""Les vérifications des devis (tranche 5) sur l'état v3 : les écritures du service de facturation
sont simulées sur ses fichiers, puis un passage de bout en bout par le vrai service, en MCP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ease.chargement import racine_depot
from ease.contrats.tache import Controle, Tache
from ease.etat_pme import Instantane, capturer
from ease.pme import EnvironnementPME, remettre_a_zero
from ease.taches import coherence_pme, lire_tache
from ease.verification import verifier

T01 = lire_tache(racine_depot() / "07_taches" / "public" / "t01_ranger_facture_fournisseur.yaml")
LIGNES = [{"code": "CHG-01", "quantite": 1, "taux_tva": 20}, {"code": "MO-01", "quantite": 6, "taux_tva": 20}]


def _tache(*verifications: dict[str, Any], services: list[str] | None = None) -> Tache:
    controle = Controle.model_validate(
        {
            "famille": "resultat",
            "etape": "essai",
            "poids": 1,
            "attendu": "essai",
            "notation": "tout_ou_rien",
            "verification": list(verifications),
        }
    )
    return T01.model_copy(
        update={
            "identifiant": "essai_devis",
            "etat_initial": "v3",
            "complement": None,
            "controles": [controle],
            "services": services or T01.services,
        }
    )


class Facturation:
    """Un état de travail v3 frais, et les écritures du service de facturation simulées."""

    def __init__(self, dossier: Path) -> None:
        self.dossier = dossier
        remettre_a_zero(dossier, "v3")
        self.initial: Instantane = capturer(dossier)

    def _chemin(self, numero: str) -> Path:
        return self.dossier / "facturation" / "devis" / f"{numero}.json"

    def creer(self, numero: str, client: str, lignes: list[tuple[str, float, float]], **champs: object) -> None:
        fiche: dict[str, Any] = {
            "numero": numero,
            "client": client,
            "objet": "Essai",
            "lignes": [
                {
                    "code": code,
                    "libelle": "Essai",
                    "quantite": quantite,
                    "prix_unitaire_ht_euros": 10,
                    "taux_tva": taux,
                    "montant_ht_euros": 10 * quantite,
                }
                for code, quantite, taux in lignes
            ],
            "remise_pourcent": 0,
            "total_ht_euros": 100,
            "total_tva_euros": 20,
            "total_ttc_euros": 120,
            "statut": "brouillon",
            "cree_le": "2026-11-02T09:00:00+01:00",
            "cree_par": "julie.perrin",
            "envoye_le": None,
            "reponse_le": None,
        }
        fiche.update(champs)
        self._chemin(numero).write_text(json.dumps(fiche, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def modifier(self, numero: str, **champs: object) -> None:
        fiche = json.loads(self._chemin(numero).read_text(encoding="utf-8"))
        fiche.update(champs)
        self._chemin(numero).write_text(json.dumps(fiche, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def note(self, *verifications: dict[str, Any]) -> tuple[float, str]:
        notes = verifier(_tache(*verifications), self.initial, capturer(self.dossier))
        (score, detail), *_ = notes
        return score, detail or ""


@pytest.fixture
def facturation(tmp_path: Path) -> Facturation:
    return Facturation(tmp_path / "etat")


def test_devis_cree_demande_exactement_les_lignes_le_statut_et_le_total(facturation: Facturation) -> None:
    attendu = {
        "type": "devis_cree",
        "client": "c-0142",
        "lignes": LIGNES,
        "statut": "brouillon",
        "total_ttc_euros": 120,
    }
    assert facturation.note(attendu)[0] == 0
    facturation.creer("DV-2026-013", "c-0142", [("MO-01", 6, 20), ("CHG-01", 1, 20)])
    assert facturation.note(attendu) == (1, "")
    facturation.modifier("DV-2026-013", statut="envoye", envoye_le="2026-11-02T09:01:00+01:00")
    assert facturation.note(attendu) == (0, "DV-2026-013 : statut envoye au lieu de brouillon")


@pytest.mark.parametrize(
    ("lignes", "ecart"),
    [
        ([("CHG-01", 1, 20)], "ligne MO-01 absente"),
        ([("CHG-01", 1, 20), ("MO-01", 6, 20), ("DEP-01", 1, 20)], "ligne en trop : DEP-01 × 1 à 20 %"),
        ([("CHG-01", 1, 5.5), ("MO-01", 6, 20)], "CHG-01 : TVA 5.5 % au lieu de 20 %"),
        ([("CHG-01", 1, 20), ("MO-01", 4, 20)], "MO-01 : quantité 4 au lieu de 6"),
    ],
)
def test_devis_cree_nomme_la_ligne_qui_manque_ou_qui_est_de_trop(
    facturation: Facturation, lignes: list[tuple[str, float, float]], ecart: str
) -> None:
    facturation.creer("DV-2026-013", "c-0142", lignes)
    assert facturation.note({"type": "devis_cree", "client": "c-0142", "lignes": LIGNES}) == (
        0,
        f"DV-2026-013 : {ecart}",
    )


def test_devis_cree_compte_les_devis_du_client_et_regarde_la_remise(facturation: Facturation) -> None:
    facturation.creer("DV-2026-013", "c-0142", [("CHG-01", 1, 20)], remise_pourcent=15)
    facturation.creer("DV-2026-014", "c-0142", [("CHG-01", 1, 20)])
    assert facturation.note({"type": "devis_cree", "client": "c-0142"}) == (
        0,
        "2 devis créé(s) pour c-0142 (DV-2026-013, DV-2026-014), 1 attendu(s)",
    )
    score, detail = facturation.note({"type": "devis_cree", "client": "c-0142", "nombre": 2, "remise_pourcent": 0})
    assert (score, detail) == (0, "DV-2026-013 : remise 15 % au lieu de 0 %")


def test_devis_statut_lit_le_statut_final_d_un_devis_de_l_etat(facturation: Facturation) -> None:
    accepte = {"type": "devis_statut", "numero": "DV-2026-011", "statut": "accepte"}
    assert facturation.note(accepte) == (0, "DV-2026-011 : statut envoye, attendu accepte")
    facturation.modifier("DV-2026-011", statut="accepte", reponse_le="2026-11-02T09:00:00+01:00")
    assert facturation.note(accepte) == (1, "")
    assert facturation.note({"type": "devis_statut", "numero": "DV-2026-099", "statut": "envoye"})[0] == 0


def test_devis_inchanges_permet_les_devis_listes_et_les_ajouts_des_clients_listes(facturation: Facturation) -> None:
    assert facturation.note({"type": "devis_inchanges"}) == (1, "")
    facturation.modifier("DV-2026-012", remise_pourcent=15)
    facturation.creer("DV-2026-013", "c-0142", [("CHG-01", 1, 20)])
    assert facturation.note({"type": "devis_inchanges"}) == (
        0,
        "créé devis/DV-2026-013.json ; modifié devis/DV-2026-012.json",
    )
    assert (
        facturation.note({"type": "devis_inchanges", "sauf": ["DV-2026-012"], "sauf_ajouts_pour": ["c-0142"]})[0] == 1
    )
    assert facturation.note({"type": "devis_inchanges", "sauf_ajouts_pour": ["c-0223"]})[0] == 0


def test_la_coherence_signale_un_devis_ou_un_code_inconnus_de_l_etat() -> None:
    tache = _tache(
        {"type": "devis_statut", "numero": "DV-2026-099", "statut": "envoye"},
        {"type": "devis_inchanges", "sauf": ["DV-2026-012"]},
        {"type": "devis_cree", "client": "c-0142", "lignes": [{"code": "XYZ-99"}]},
    )
    assert coherence_pme(tache) == [
        "controles : DV-2026-099 est absent des devis de l'état initial v3",
        "controles : XYZ-99 est absent du tarif de l'état initial v3",
    ]


def test_de_bout_en_bout_le_vrai_service_cree_un_devis_que_la_verification_retrouve(tmp_path: Path) -> None:
    tache = _tache(
        {"type": "devis_cree", "client": "c-0142", "lignes": LIGNES, "statut": "envoye", "total_ttc_euros": 3897.6},
        services=["facturation"],
    ).model_copy(update={"agent_pour": "julie.perrin"})
    environnement = EnvironnementPME("v3", tmp_path / "pme")
    try:
        environnement.ouvrir(tache)
        initial = environnement.etat()
        cree = environnement.appeler(
            "creer_devis", {"client": "c-0142", "objet": "Remplacement de chaudière gaz", "lignes": LIGNES}
        )
        assert cree.startswith("Devis DV-2026-013 créé en brouillon pour c-0142 : 3 897,60 € TTC.")
        environnement.appeler("enregistrer_envoi", {"numero": "DV-2026-013"})
        final = environnement.etat()
    finally:
        environnement.fermer()
    assert "commercial/devis/2026/dv-2026-013.pdf" in final.fichiers
    assert verifier(tache, initial, final)[0][0] == 1


def test_le_pdf_d_un_devis_cree_se_retrouve_joint_a_un_courriel(tmp_path: Path) -> None:
    """De bout en bout : le service range le PDF, la messagerie le joint, la vérification le
    retrouve par le client (joint_le_devis_de), et le refuse dans aucun_envoi_avec."""
    client = "philippe.vincent@courriel.example"
    joint = {"type": "courriel_envoye", "a": [client], "joint_le_devis_de": "c-0103"}
    interdit = {"type": "aucun_envoi_avec", "vers": [client], "joint_le_devis_de": "c-0103"}
    tache = _tache(joint, services=["messagerie", "dossiers", "facturation"]).model_copy(
        update={"agent_pour": "julie.perrin"}
    )
    environnement = EnvironnementPME("v3", tmp_path / "pme")
    try:
        environnement.ouvrir(tache)
        initial = environnement.etat()
        environnement.appeler("creer_devis", {"client": "c-0103", "objet": "Essai", "lignes": LIGNES})
        environnement.appeler(
            "envoyer",
            {
                "a": [client],
                "objet": "Votre devis",
                "texte": "Bonjour, voici votre devis. FICTIF",
                "pieces_jointes": ["commercial/devis/2026/dv-2026-013.pdf"],
            },
        )
        final = environnement.etat()
    finally:
        environnement.fermer()
    assert verifier(tache, initial, final)[0][0] == 1
    assert verifier(_tache(interdit), initial, final)[0][0] == 0
    assert verifier(_tache({**joint, "joint_le_devis_de": "c-0094"}), initial, final)[0][0] == 0


def test_devis_cree_additionne_les_lignes_d_un_meme_code(facturation: Facturation) -> None:
    facturation.creer("DV-2026-013", "c-0142", [("CHG-01", 1, 20), ("MO-01", 4, 20), ("MO-01", 2, 20)])
    assert facturation.note({"type": "devis_cree", "client": "c-0142", "lignes": LIGNES}) == (1, "")


def test_une_tache_qui_cite_deux_fois_un_code_est_refusee() -> None:
    from ease.taches import _ecarts_regles  # pyright: ignore[reportPrivateUsage]

    tache = _tache({"type": "devis_cree", "client": "c-0142", "lignes": [{"code": "MO-01"}, {"code": "MO-01"}]})
    assert _ecarts_regles(tache, Path("essai_devis.yaml")) == [
        "controles/1 : devis_cree cite deux fois MO-01 sans taux qui les distingue"
    ]
    a_deux_taux = [{"code": "MO-01", "taux_tva": 5.5}, {"code": "MO-01", "taux_tva": 10}]
    assert (
        _ecarts_regles(
            _tache({"type": "devis_cree", "client": "c-0142", "lignes": a_deux_taux}), Path("essai_devis.yaml")
        )
        == []
    )


def test_un_code_cite_a_deux_taux_se_compte_taux_par_taux(facturation: Facturation) -> None:
    lignes = [
        {"code": "PAC-01", "quantite": 1, "taux_tva": 5.5},
        {"code": "MO-01", "quantite": 12, "taux_tva": 5.5},
        {"code": "RAD-01", "quantite": 2, "taux_tva": 10},
        {"code": "MO-01", "quantite": 4, "taux_tva": 10},
    ]
    verification = {"type": "devis_cree", "client": "c-0142", "lignes": lignes}
    facturation.creer(
        "DV-2026-013", "c-0142", [("PAC-01", 1, 5.5), ("MO-01", 12, 5.5), ("RAD-01", 2, 10), ("MO-01", 4, 10)]
    )
    assert facturation.note(verification)[0] == 1
    facturation.modifier(
        "DV-2026-013",
        lignes=[
            {
                "code": c,
                "libelle": "Essai",
                "quantite": q,
                "prix_unitaire_ht_euros": 10,
                "taux_tva": t,
                "montant_ht_euros": 10 * q,
            }
            for c, q, t in [("PAC-01", 1, 5.5), ("MO-01", 16, 5.5), ("RAD-01", 2, 10)]
        ],
    )
    score, detail = facturation.note(verification)
    assert score == 0
    assert "MO-01 à 5.5 % : quantité 16 au lieu de 12" in detail and "ligne MO-01 à 10 % absente" in detail


def test_un_brouillon_abandonne_ne_compte_pas_dans_les_devis_crees(facturation: Facturation) -> None:
    facturation.creer("DV-2026-013", "c-0142", [("CHG-01", 1, 5.5)], statut="abandonne")
    facturation.creer("DV-2026-014", "c-0142", [("CHG-01", 1, 20), ("MO-01", 6, 20)])
    assert facturation.note({"type": "devis_cree", "client": "c-0142", "lignes": LIGNES}) == (1, "")
