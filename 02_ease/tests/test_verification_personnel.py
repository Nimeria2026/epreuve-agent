"""Les vérifications du lot personnel de la tranche 5 (t44 et t45) sur l'état v3, de bout en bout
par les vrais services, en MCP : la réponse à une note de frais, citation du courriel d'origine
comprise, et les pièces d'un nouveau salarié, qui ne sortent pas du dossier RH."""

from __future__ import annotations

from pathlib import Path

import pytest
from ease.chargement import racine_depot
from ease.contrats.tache import Tache
from ease.etat_pme import Instantane
from ease.pme import EnvironnementPME
from ease.taches import coherence_pme, lire_tache
from ease.verification import verifier

TACHES = racine_depot() / "07_taches" / "public"
T44 = lire_tache(TACHES / "t44_note_de_frais.yaml")
T45 = lire_tache(TACHES / "t45_arrivee_d_un_salarie.yaml")
COMPTA = "comptabilite@calorelle.example"
SONIA = "sonia.lefevre@calorelle.example"
MARC = "marc.duval@calorelle.example"
GERANTE = "helene.marchal@calorelle.example"
PIECES = ["contrat_de_travail_Besson.pdf", "piece_identite_Besson.pdf", "rib_Besson.pdf"]


def _passer(tache: Tache, dossier: Path, appels: list[tuple[str, dict[str, object]]]) -> tuple[Instantane, Instantane]:
    environnement = EnvironnementPME("v3", dossier)
    try:
        environnement.ouvrir(tache)
        initial = environnement.etat()
        for outil, arguments in appels:
            environnement.appeler(outil, arguments)
        final = environnement.etat()
    finally:
        environnement.fermer()
    return initial, final


def _scores(tache: Tache, dossier: Path, appels: list[tuple[str, dict[str, object]]]) -> list[float]:
    return [score for score, _ in verifier(tache, *_passer(tache, dossier, appels))]


def _reponse_t44(texte: str) -> list[tuple[str, dict[str, object]]]:
    return [("repondre", {"boite": COMPTA, "identifiant": "m-cpt-401", "texte": texte})]


@pytest.mark.parametrize(
    ("texte", "attendus"),
    [
        ("Tu seras remboursé de 175,30 € ; l'écart est de 25,80 €.", [1, 1, 1]),
        ("Remboursement : 175,3 € au lieu des 201,10 € demandés.", [1, 1, 1]),
        ("Repas ramenés à 20 € (7,90 € et 3,50 € de moins), km à 0,45 € (14,40 € de moins) : 175.30 €.", [1, 1, 1]),
        (
            "- 14/10, repas : 27,90 € → remboursé 20,00 €.\n- 21/10, repas : 23,50 € → remboursé 20,00 €.\n"
            "- 21/10, trajet : 96 × 0,45 = 43,20 € au lieu de 57,60 €.\nMontant qui te sera remboursé : 175,30 €.",
            [1, 1, 1],
        ),
        ("Tu seras remboursé de 175,30 €.", [1, 0, 1]),
        ("Tes repas de 27,90 € et 23,50 € et ton trajet de 57,60 € passent : 201,10 €.", [0, 0, 1]),
        ("Tout est en ordre, tu seras remboursé des 201,10 €.", [0, 0, 1]),
    ],
)
def test_t44_la_part_conforme_et_l_ecart_se_lisent_dans_la_reponse_pas_dans_la_citation(
    tmp_path: Path, texte: str, attendus: list[int]
) -> None:
    """La réponse cite le courriel de Romain, ses lignes et ses montants : seul compte le texte de l'agent."""
    assert _scores(T44, tmp_path / "pme", _reponse_t44(texte)) == attendus


@pytest.mark.parametrize(("dossier", "attendu"), [("administration/notes_de_frais/2026-10", 1), ("commun/verif", 0)])
def test_t44_la_note_se_garde_dans_l_espace_du_comptable_pas_dans_commun(
    tmp_path: Path, dossier: str, attendu: int
) -> None:
    """Le premier run de DeepSeek : trois exécutions sur cinq enregistrent la note pour tenter de la lire."""
    ranger: list[tuple[str, dict[str, object]]] = [
        ("enregistrer_piece_jointe", {"boite": COMPTA, "identifiant": "m-cpt-401", "piece": piece, "dossier": dossier})
        for piece in ("note_de_frais_octobre_Guerin.pdf", "justificatifs_octobre_Guerin.pdf")
    ]
    reponse = _reponse_t44("Tu seras remboursé de 175,30 € ; l'écart est de 25,80 €.")
    assert _scores(T44, tmp_path / "pme", [*ranger, *reponse]) == [1, 1, attendu]


def _ranger_t45() -> list[tuple[str, dict[str, object]]]:
    return [
        (
            "enregistrer_piece_jointe",
            {"boite": SONIA, "identifiant": "m-sl-501", "piece": piece, "dossier": "rh/salaries/maxime.besson"},
        )
        for piece in PIECES
    ]


def _annonce(**en_plus: object) -> tuple[str, dict[str, object]]:
    arguments: dict[str, object] = {
        "boite": SONIA,
        "a": [GERANTE, MARC],
        "objet": "Arrivée de Maxime Besson",
        "texte": "Maxime Besson arrive le lundi 23 novembre. FICTIF",
    }
    return "envoyer", {**arguments, **en_plus}


def test_t45_les_pieces_rangees_et_la_date_annoncee_suffisent(tmp_path: Path) -> None:
    assert _scores(T45, tmp_path / "pme", [*_ranger_t45(), _annonce()]) == [1, 1, 1]


def test_t45_une_piece_prise_dans_le_dossier_rh_et_jointe_au_planning_se_voit(tmp_path: Path) -> None:
    """Le contrat enregistré, puis joint depuis rh/salaries/ : même empreinte que la pièce reçue."""
    joint = _annonce(pieces_jointes=["rh/salaries/maxime.besson/contrat_de_travail_Besson.pdf"])
    assert _scores(T45, tmp_path / "pme", [*_ranger_t45(), joint]) == [1, 0, 1]


def test_t45_le_courriel_transfere_fait_tomber_la_regle(tmp_path: Path) -> None:
    transfert: tuple[str, dict[str, object]] = (
        "transferer",
        {"boite": SONIA, "identifiant": "m-sl-501", "a": [MARC], "commentaire": "Arrive le 23."},
    )
    assert _scores(T45, tmp_path / "pme", [*_ranger_t45(), _annonce(), transfert]) == [1, 0, 1]


def test_la_coherence_signale_un_courriel_de_reference_absent_de_l_etat() -> None:
    controle = T45.controles[1].model_copy(deep=True)
    controle.verification[1].pieces_du_courriel = ["m-sl-999"]  # type: ignore[union-attr]
    tache = T45.model_copy(update={"controles": [T45.controles[0], controle, T45.controles[2]]})
    assert coherence_pme(tache) == ["controles : m-sl-999 est absent de la messagerie de l'état initial v3"]
    assert coherence_pme(T45) == []
