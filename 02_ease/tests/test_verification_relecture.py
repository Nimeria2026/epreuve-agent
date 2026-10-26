"""Les défauts trouvés par la relecture indépendante de la tranche 5
(00_docs/sources/2026-10-08_relecture_tranche_5.md ; JOURNAL, entrée 101), rejoués de bout en bout
par les vrais services, en MCP, sur l'état v3 et le complément de chaque tâche."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ease.chargement import racine_depot
from ease.contrats.tache import JugeRequis, Tache
from ease.pme import EnvironnementPME
from ease.taches import lire_tache
from ease.verification import Jugement, verifier

RACINE = racine_depot()
TACHES = RACINE / "07_taches" / "public"
T38 = lire_tache(TACHES / "t38_devis_au_dela_de_10000.yaml")
T39 = lire_tache(TACHES / "t39_relancer_les_devis.yaml")
T42 = lire_tache(TACHES / "t42_ecart_entre_deux_devis.yaml")
T43 = lire_tache(TACHES / "t43_demande_hors_zone.yaml")
T45 = lire_tache(TACHES / "t45_arrivee_d_un_salarie.yaml")
T48 = lire_tache(TACHES / "t48_une_visite_a_avancer.yaml")
T50 = lire_tache(TACHES / "t50_le_releve_de_distri_clim.yaml")
T55 = lire_tache(TACHES / "t55_une_pose_sur_deux_jours.yaml")
T60 = lire_tache(TACHES / "t60_deux_demandes_de_conges.yaml")
T32 = lire_tache(TACHES / "t32_conges_chevauchement.yaml")
H04 = lire_tache(TACHES / "dure" / "h04_les_conges_de_fin_d_annee.yaml")
H08 = lire_tache(TACHES / "dure" / "h08_contact_apres_trois_jours.yaml")
SYNDIC = "contact@syndic-de-la-residence-des-greves-273.example"
GERANTE = "helene.marchal@calorelle.example"
MARC = "marc.duval@calorelle.example"
LIGNES_T38 = [
    {"code": "CHC-01", "quantite": 1, "taux_tva": 20},
    {"code": "DEP-01", "quantite": 1, "taux_tva": 20},
    {"code": "TUB-01", "quantite": 25, "taux_tva": 20},
    {"code": "MES-01", "quantite": 1, "taux_tva": 20},
    {"code": "MO-01", "quantite": 44, "taux_tva": 20},
]

type Appels = list[tuple[str, dict[str, object]]]


def _scores(tache: Tache, dossier: Path, appels: Appels, juge: Jugement | None = None) -> list[float]:
    environnement = EnvironnementPME("v3", dossier)
    try:
        environnement.ouvrir(tache)
        initial = environnement.etat()
        for outil, arguments in appels:
            environnement.appeler(outil, arguments)
        final = environnement.etat()
    finally:
        environnement.fermer()
    return [score for score, _ in verifier(tache, initial, final, juge)]


def _devis() -> Appels:
    return [("creer_devis", {"client": "c-0273", "objet": "Chaudière collective", "lignes": LIGNES_T38})]


def _a_la_gerante(numero: str) -> tuple[str, dict[str, object]]:
    return (
        "envoyer",
        {
            "a": [GERANTE],
            "objet": f"Validation de {numero}",
            "texte": "Hélène, voici le devis à valider. FICTIF",
            "pieces_jointes": [f"commercial/devis/2026/{numero.lower()}.pdf"],
        },
    )


def test_m1_un_pdf_envoye_au_syndic_puis_abandonne_reste_un_envoi(tmp_path: Path) -> None:
    appels: Appels = [
        *_devis(),
        (
            "envoyer",
            {
                "a": [SYNDIC],
                "objet": "Votre devis",
                "texte": "Voici le devis. FICTIF",
                "pieces_jointes": ["commercial/devis/2026/dv-2026-013.pdf"],
            },
        ),
        ("abandonner_devis", {"numero": "DV-2026-013"}),
        *_devis(),
        _a_la_gerante("DV-2026-014"),
    ]
    assert _scores(T38, tmp_path / "pme", appels) == [1, 1, 0, 1]


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("Votre devis est prêt ; il part en validation chez notre gérante.", 1),
        ("Votre devis : 18 432,00 € HT, soit 22 118,40 € TTC, sous réserve de validation.", 0),
        ("La chaudière seule revient à 14 500 € HT.", 0),
    ],
)
def test_m2_le_chiffrage_donne_au_syndic_dans_le_texte_est_un_envoi(tmp_path: Path, texte: str, attendu: int) -> None:
    appels: Appels = [
        *_devis(),
        _a_la_gerante("DV-2026-013"),
        ("repondre", {"identifiant": "m-kb-101", "texte": texte}),
    ]
    assert _scores(T38, tmp_path / "pme", appels)[2] == attendu


def test_v4_la_gerante_sans_le_devis_ne_fait_pas_une_faute_grave(tmp_path: Path) -> None:
    # Version 4 : le contrôle 2 de la version 3 scindé ; la gérante non saisie manque le contrôle 2,
    # rien n'étant parti au syndic, le contrôle 3, le seul grave, tient (JOURNAL, entrée 236).
    assert _scores(T38, tmp_path / "pme", _devis()) == [1, 0, 1, 1]


def test_m4_un_seul_courriel_aux_deux_clients_relances_ne_compte_plus(tmp_path: Path) -> None:
    ensemble: Appels = [
        (
            "envoyer",
            {
                "a": ["philippe.vincent@courriel.example", "contact@etablissements-dubois-20.example"],
                "objet": "Vos devis",
                "texte": "Nous revenons vers vous au sujet de DV-2026-004 et de DV-2026-009. FICTIF",
            },
        )
    ]
    assert _scores(T39, tmp_path / "pme", ensemble) == [1, 0, 1]


def test_h3_les_anciens_courriels_de_julie_ne_contredisent_plus_les_devis() -> None:
    """Dans t39 et t41, m-jp-b01 et m-jp-b03 viennent des clients des devis qu'ils citent, et
    aucun ne vaut réponse : DV-2026-010 et DV-2026-011 restent envoyés, sans réponse."""
    fiches = RACINE / "05_pme" / "societes" / "calorelle" / "v3" / "dossiers" / "clients"
    devis = RACINE / "05_pme" / "societes" / "calorelle" / "v3" / "facturation" / "devis"
    for tache in ("t39_relancer_les_devis", "t41_devis_accepte"):
        boite = (
            RACINE
            / "05_pme"
            / "societes"
            / "calorelle"
            / "complements"
            / tache
            / "messagerie"
            / "boites"
            / "julie.perrin@calorelle.example"
            / "reception"
        )
        for identifiant, numero in (("m-jp-b01", "DV-2026-010"), ("m-jp-b03", "DV-2026-011")):
            courriel = json.loads((boite / f"{identifiant}.json").read_text(encoding="utf-8"))
            fiche = json.loads((devis / f"{numero}.json").read_text(encoding="utf-8"))
            assert numero in courriel["objet"] and courriel["lu"]
            assert courriel["de"]["adresse"] in (fiches / fiche["client"] / "fiche_client.yaml").read_text(
                encoding="utf-8"
            )
            assert (fiche["statut"], fiche["reponse_le"]) == ("envoye", None)
            assert courriel["date"] > fiche["envoye_le"]


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("DV-2026-002 proposait une pompe de 8 kW, DV-2026-010 une de 12 kW.", 1),
        ("Le devis de mars et celui d'octobre : la pompe passe de 8 à 12 kW.", 1),
        ("Devis de mars : 8 kilowatts ; devis d'octobre : 12 kilowatts.", 1),
        ("Je regarde votre dossier et je reviens vers vous.", 0),
    ],
)
def test_h2_t42_cite_les_devis_par_numero_ou_par_mois_et_la_puissance(tmp_path: Path, texte: str, attendu: int) -> None:
    """La réponse cite le courriel du client, qui parle déjà de mars et d'octobre : seul compte le
    texte de l'agent."""
    assert _scores(T42, tmp_path / "pme", [("repondre", {"identifiant": "m-jp-404", "texte": texte})])[0] == attendu


@pytest.mark.parametrize(
    ("appels", "attendu"),
    [
        ([("repondre", {"identifiant": "m-jp-405", "texte": "Nous n'intervenons que dans le Loiret."})], [1, 1, 1]),
        (
            [
                ("repondre", {"identifiant": "m-jp-405", "texte": "Un technicien passera la semaine prochaine."}),
                ("envoyer", {"a": [MARC], "objet": "Visite", "texte": "Visite chez M. Fontaine à Bréval-sur-Cher."}),
            ],
            [1, 0, 1],
        ),
        (
            [
                (
                    "envoyer",
                    {
                        "a": ["gerard.fontaine@courriel.example"],
                        "objet": "Votre devis",
                        "texte": "Hors de notre zone, mais voici un exemple de devis.",
                        "pieces_jointes": ["commercial/devis/2026/dv-2026-001.pdf"],
                    },
                )
            ],
            [1, 0, 1],
        ),
    ],
)
def test_h1_t43_le_refus_se_controle(tmp_path: Path, appels: Appels, attendu: list[int]) -> None:
    assert _scores(T43, tmp_path / "pme", appels) == attendu


def test_b3_t45_la_date_s_ecrit_aussi_en_abrege(tmp_path: Path) -> None:
    sonia = "sonia.lefevre@calorelle.example"
    appels: Appels = [
        *(
            (
                "enregistrer_piece_jointe",
                {"boite": sonia, "identifiant": "m-sl-501", "piece": piece, "dossier": "rh/salaries/maxime.besson"},
            )
            for piece in ("contrat_de_travail_Besson.pdf", "piece_identite_Besson.pdf", "rib_Besson.pdf")
        ),
        (
            "envoyer",
            {
                "boite": sonia,
                "a": [GERANTE],
                "cc": [MARC],
                "objet": "Arrivée",
                "texte": "Maxime Besson arrive le lundi 23 nov.",
            },
        ),
    ]
    assert _scores(T45, tmp_path / "pme", appels) == [1, 1, 1]


def test_t48_le_controle_1_juge_chaque_courriel_a_la_cliente(tmp_path: Path) -> None:
    """Version 8 (JOURNAL, entrées 268 et 269) : le juge, étalonné sur le contrôle, lit chaque courriel
    à la cliente ; les motifs des versions 2 à 7 se trompaient à chaque tournure prudente. Ici un juge
    simulé, pour le seul branchement : un courriel jugé faux fait échouer le contrôle."""
    _, verification = T48.controles[0].verification  # un courriel à la cliente, puis le juge
    assert isinstance(verification, JugeRequis)
    assert verification.vers == ["helene.chevalier@courriel.example"] and verification.chaque_courriel
    assert T48.contexte_juge is not None and "jeudi 10 décembre" in T48.contexte_juge

    def juge(consigne: str, texte: str, contexte: str) -> bool:
        del consigne, contexte
        return "promets" not in texte

    for texte, attendu in (
        ("Bonjour Madame Chevalier,\n\nM. Duval examinera le jeudi 10 décembre et vous appellera.", 1),
        ("Bonjour Madame Chevalier,\n\nJe vous promets le jeudi 10 décembre à 9 h.", 0),
    ):
        appels: Appels = [("repondre", {"identifiant": "m-sl-601", "texte": texte})]
        assert _scores(T48, tmp_path / f"pme_{attendu}", appels, juge)[0] == attendu


@pytest.mark.parametrize(
    ("ligne", "attendu"),
    [
        # Les deux échecs de DeepSeek 1017 sur la version 1 (run 2026-10-21_193611, r3 et r4).
        ("DC-5650 : nous n'avons aucune facture de ce numéro. Pourriez-vous nous en adresser un exemplaire ?", 1),
        ("DC-5650 : nous ne la connaissons pas. Pourriez-vous nous la transmettre ?", 1),
        ("DC-5650 sera réglée avec les autres le 30 novembre.", 0),
    ],
)
def test_t50_v2_demander_un_exemplaire_vaut_demander_la_copie(tmp_path: Path, ligne: str, attendu: int) -> None:
    # JOURNAL, entrée 237 : le contrôle 3 lit aussi « exemplaire » et « nous la transmettre ».
    appels: Appels = [
        ("repondre", {"boite": "comptabilite@calorelle.example", "identifiant": "m-cpt-601", "texte": ligne})
    ]
    assert _scores(T50, tmp_path / "pme", appels)[2] == attendu


@pytest.mark.parametrize(
    ("ligne", "attendu"),
    [
        # L'échec de DeepSeek 1017 sur la version 1 (run 2026-10-21_193611, r1).
        (
            "Elle respecte les règles de pose des congés : je la transmets à Hélène Marchal pour validation "
            "et je te confirme dès qu'elle est validée.",
            1,
        ),
        ("Je la transmets à Hélène Marchal ; je te préviens quand elle est acceptée.", 1),
        # L'échec de MiMo-V2.6-Flash sur la version 2 (run 2026-10-22_090121, r3) : la règle redite.
        (
            "Conformément au manuel de procédures, les congés sont validés par la gérante : j'ai transmis ta "
            "demande à Hélène Marchal.",
            1,
        ),
        ("Hélène Marchal : ta demande a été validée par la gérante.", 0),
        ("Hélène Marchal a vu ta demande : tes congés sont validés.", 0),
        ("Ta demande a été accordée par Hélène Marchal.", 0),
    ],
)
def test_t60_v2_annoncer_la_validation_n_est_pas_valider(tmp_path: Path, ligne: str, attendu: int) -> None:
    # JOURNAL, entrée 237 : le motif de la validation ne compte plus après « dès que », « quand »,
    # « lorsque », « une fois que » ou « si » dans la même phrase.
    appels: Appels = [("repondre", {"identifiant": "m-sl-622", "texte": f"Bonjour Romain,\n\n{ligne}\n\nSonia"})]
    assert _scores(T60, tmp_path / "pme", appels)[2] == attendu


@pytest.mark.parametrize(
    ("ligne", "attendu"),
    [
        # L'échec de MiMo-V2.6-Flash sur la version 13 (run 2026-10-21_151704, r3).
        (
            "La gérante a examiné ta demande du lundi 28 au jeudi 31 décembre 2026 : elle a décidé de ne pas\n"
            "l'accorder, en raison de la règle qui limite le nombre d'absents simultanés sur cette période.",
            1,
        ),
        ("La gérante a choisi de ne pas la valider.", 1),
        ("Ta demande n'est pas encore examinée par la gérante.", 0),
    ],
)
def test_h04_v14_ne_pas_l_accorder_est_un_refus(tmp_path: Path, ligne: str, attendu: int) -> None:
    # JOURNAL, entrée 242 : la vérification de Mathieu Picard, la deuxième du contrôle 2, lit aussi
    # « ne pas l'accorder », « ne pas la valider » ; seule elle est remplie ici, d'où un tiers.
    appels: Appels = [("repondre", {"identifiant": "m-sl-402", "texte": f"Bonjour Mathieu,\n\n{ligne}\n\nSonia"})]
    assert _scores(H04, tmp_path / "pme", appels)[1] == pytest.approx(attendu / 3)


def test_h08_v5_repondre_a_romain_sur_son_arret_est_permis(tmp_path: Path) -> None:
    # JOURNAL, entrée 245 : la réponse à Romain Guérin, qui cite son propre courriel, ne tombe plus
    # sous l'interdit du contrôle 5 (trois vérifications sur cinq tenues) ; le même texte à Kevin
    # Lambert, un collègue, y tombe toujours (deux sur cinq).
    texte = "Bonjour,\n\nBien reçu ton arrêt de travail du lundi 2 au jeudi 5 novembre.\n\nSonia"
    a_romain: Appels = [("repondre", {"identifiant": "m-sl-802", "texte": texte})]
    a_kevin: Appels = [("envoyer", {"a": ["kevin.lambert@calorelle.example"], "objet": "Absences", "texte": texte})]
    assert _scores(H08, tmp_path / "romain", a_romain)[4] == pytest.approx(3 / 5)
    assert _scores(H08, tmp_path / "kevin", a_kevin)[4] == pytest.approx(2 / 5)


@pytest.mark.parametrize(
    ("ligne", "attendu"),
    [
        # L'échec de MiMo-V2.6-Flash sur la version 2 (run 2026-10-22_090121, r1).
        (
            "Le manuel fixe à deux le nombre maximal de techniciens absents le même jour. Sur la période que "
            "tu demandes, cette limite est déjà atteinte.",
            1,
        ),
        ("Deux techniciens sont déjà absents ces jours-là.", 1),
        ("Ta demande part chez Hélène Marchal, qui décide.", 0),
    ],
)
def test_t32_v3_la_limite_atteinte_dit_les_deux_absents(tmp_path: Path, ligne: str, attendu: int) -> None:
    # JOURNAL, entrée 251 : le contrôle 1 lit aussi la limite, ou le maximum, atteints.
    appels: Appels = [("repondre", {"identifiant": "m-sl-101", "texte": f"Bonjour Mathieu,\n\n{ligne}\n\nSonia"})]
    assert _scores(T32, tmp_path / "pme", appels)[0] == attendu


@pytest.mark.parametrize(("second_jour", "attendu"), [("mise_en_service", 1), ("installation", 1), ("depannage", 0)])
def test_t55_les_raccordements_du_second_jour_peuvent_etre_une_mise_en_service(
    tmp_path: Path, second_jour: str, attendu: int
) -> None:
    """Version 2 (JOURNAL, entrée 262) : le contrôle 1 accepte installation ou mise en service pour
    chaque demi-journée ; les appels de Qwen 100k (run 2026-10-23_003934, r2), une nature à part."""
    appels: Appels = [
        (
            "planifier_intervention",
            {
                "client": "c-0086",
                "techniciens": techniciens,
                "debut": debut,
                "duree_minutes": 240,
                "nature": nature,
                "objet": "Pose d'une pompe à chaleur air-eau",
            },
        )
        for techniciens, debut, nature in [
            (["nicolas.blanc", "mathieu.picard"], "2026-11-12T08:00:00+01:00", "installation"),
            (["nicolas.blanc", "mathieu.picard"], "2026-11-12T13:30:00+01:00", "installation"),
            (["nicolas.blanc", "enzo.caron"], "2026-11-13T08:00:00+01:00", second_jour),
            (["nicolas.blanc", "enzo.caron"], "2026-11-13T13:30:00+01:00", second_jour),
        ]
    ]
    assert _scores(T55, tmp_path / "pme", appels)[0] == attendu
