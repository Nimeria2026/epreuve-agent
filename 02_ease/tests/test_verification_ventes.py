"""Les vérifications du service des ventes et des avoirs en nombre (Négovelle, étape 6 du cadrage du
2026-10-17) sur l'état v1 : les écritures des services sont simulées sur leurs fichiers ; le passage
de bout en bout par les vrais services est celui des témoins du socle (test_negovelle_taches)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ease.chargement import racine_depot
from ease.contrats.tache import Controle, Tache
from ease.etat_pme import Instantane, capturer
from ease.pme import remettre_a_zero
from ease.taches import lire_tache
from ease.verification import verifier

MODELE = lire_tache(racine_depot() / "07_taches" / "public" / "negovelle" / "ng01_une_commande_en_rupture.yaml")
VALIDEE = "CO-2026-02031"
"""Une commande validée de v1, de Besson Rénovation (c-0330), livrée à l'adresse L1."""
FACTUREE = "CO-2026-01801"
"""Une commande facturée de v1, de c-0040, livrée par BL-2026-01650."""


def _tache(*verifications: dict[str, Any]) -> Tache:
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
    return MODELE.model_copy(update={"identifiant": "essai_ventes", "complement": None, "controles": [controle]})


class Ventes:
    """Un état de travail v1 de Négovelle frais, et les écritures des services simulées."""

    def __init__(self, dossier: Path) -> None:
        self.dossier = dossier
        remettre_a_zero(dossier, "v1", societe="negovelle")
        self.initial: Instantane = capturer(dossier)

    def _chemin(self, sous_dossier: str, numero: str) -> Path:
        return self.dossier / "ventes" / sous_dossier / f"{numero}.json"

    def lire(self, numero: str) -> dict[str, Any]:
        return json.loads(self._chemin("commandes", numero).read_text(encoding="utf-8"))

    def ecrire(self, commande: dict[str, Any]) -> None:
        chemin = self._chemin("commandes", commande["numero"])
        chemin.write_text(json.dumps(commande, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def nouvelle(self, numero: str, client: str, lignes: list[tuple[str, int]], **champs: object) -> None:
        """Une commande créée, sur le modèle de VALIDEE, avec ces lignes et ces champs."""
        modele = self.lire(VALIDEE)
        ligne = modele["lignes"][0]
        self.ecrire(
            {
                **modele,
                "numero": numero,
                "client": client,
                "lignes": [{**ligne, "reference": r, "quantite": q} for r, q in lignes],
                "historique": modele["historique"][:1],
                **champs,
            }
        )

    def retour(self, numero: str, livraison: str, lignes: list[tuple[str, int, str]]) -> None:
        donnees = {
            "numero": numero,
            "livraison": livraison,
            "client": "c-0040",
            "date": "2026-07-06T08:30:00+02:00",
            "lignes": [{"reference": r, "quantite": q, "etat": e} for r, q, e in lignes],
            "motif": "essai",
            "enregistre_par": "remi.joly",
        }
        self._chemin("retours", numero).write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")

    def avoir(self, numero: str, client: str, facture: str, montant: float) -> None:
        donnees = {
            "numero": numero,
            "client": client,
            "facture": facture,
            "date": "2026-07-06T08:30:00+02:00",
            "montant_ttc_euros": montant,
            "motif": "essai",
            "emis_par": "remi.joly",
        }
        chemin = self.dossier / "facturation" / "avoirs" / f"{numero}.json"
        chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")

    def bloquer(self, client: str) -> None:
        chemin = self.dossier / "dossiers" / "clients" / client / "fiche_client.yaml"
        texte = chemin.read_text(encoding="utf-8").replace("statut: ouvert", 'statut: "bloque"')
        chemin.write_text(texte, encoding="utf-8")

    def envoi(self, a: list[str], corps: str) -> None:
        """Un courriel envoyé depuis la boîte de Bruno Castaing."""
        boite = "bruno.castaing@negovelle.example"
        dossier = self.dossier / "messagerie" / "boites" / boite / "envoyes"
        dossier.mkdir(parents=True, exist_ok=True)
        identifiant = f"m-env-{len(list(dossier.glob('*.json'))) + 1:03d}"
        courriel = {
            "identifiant": identifiant,
            "de": {"nom": "Bruno Castaing", "adresse": boite},
            "a": a,
            "cc": [],
            "objet": "Objet",
            "date": "2026-07-06T09:00:00+02:00",
            "corps": corps,
            "pieces_jointes": [],
            "lu": True,
            "en_reponse_a": None,
            "transfere_de": None,
        }
        (dossier / f"{identifiant}.json").write_text(json.dumps(courriel, ensure_ascii=False), encoding="utf-8")

    def score(self, *verifications: dict[str, Any]) -> float:
        return verifier(_tache(*verifications), self.initial, capturer(self.dossier))[0][0]


@pytest.fixture
def ventes(tmp_path: Path) -> Ventes:
    return Ventes(tmp_path / "pme")


def test_l_instantane_lit_les_ventes_et_les_clients_bloques(ventes: Ventes) -> None:
    assert len(ventes.initial.commandes) == 241
    assert len(ventes.initial.retours) == 5
    assert "catalogue.json" in ventes.initial.ventes
    assert ventes.initial.clients_bloques == {"c-0013", "c-0019", "c-0034", "c-0097", "c-0309"}
    assert capturer(racine_depot() / "05_pme" / "societes" / "calorelle" / "v3").commandes == ()


def test_une_commande_creee_se_lit_ligne_a_ligne_et_par_statut(ventes: Ventes) -> None:
    attendue = {"type": "commande_creee", "client": "c-0159", "lignes": [{"reference": "QUI-11175", "quantite": 26}]}
    assert ventes.score(attendue) == 0
    ventes.nouvelle("CO-2026-02042", "c-0159", [("QUI-11175", 26)], statut="brouillon")
    assert ventes.score(attendue) == 0, "un brouillon ne compte pas"
    assert ventes.score({**attendue, "statut": "brouillon"}) == 1
    ventes.nouvelle("CO-2026-02043", "c-0159", [("QUI-11175", 26)], statut="validee")
    assert ventes.score({**attendue, "statut": "validee", "livraison": "L1"}) == 1
    assert ventes.score({**attendue, "lignes": [{"reference": "QUI-11175", "quantite": 40}]}) == 0
    assert ventes.score({**attendue, "lignes": [{"reference": "QUI-11175"}, {"reference": "QUI-12833"}]}) == 0
    assert ventes.score({**attendue, "mode": "express"}) == 0
    assert ventes.score({**attendue, "reliquat": True}) == 0
    ventes.nouvelle(
        "CO-2026-02044", "c-0159", [("QUI-11175", 14)], statut="en_attente_reassort", reliquat_de="CO-2026-02043"
    )
    reliquat = {"type": "commande_creee", "client": "c-0159", "reliquat": True, "statut": "en_attente_reassort"}
    assert ventes.score({**reliquat, "lignes": [{"reference": "QUI-11175", "quantite": 14}]}) == 1
    assert ventes.score(attendue) == 1, "le reliquat ne compte pas parmi les commandes"


def test_commandes_creees_apparie_chaque_commande_a_un_element(ventes: Ventes) -> None:
    """Une commande coupée en deux, l'express validée et le standard en attente (ngh01, JOURNAL, entrée
    193) : chaque commande créée répond à un élément distinct ; un brouillon laissé de côté n'engage
    rien, sauf s'il est le seul à pouvoir répondre."""
    attendues = {
        "type": "commandes_creees",
        "client": "c-0159",
        "commandes": [
            {"lignes": [{"reference": "QUI-11175", "quantite": 2}], "statuts": ["validee"], "mode": "express"},
            {
                "lignes": [{"reference": "QUI-12833"}],
                "statuts": ["brouillon", "en_attente_deblocage"],
                "mode": "standard",
            },
        ],
    }
    assert ventes.score(attendues) == 0
    ventes.nouvelle("CO-2026-02042", "c-0159", [("QUI-11175", 2)], statut="validee", mode="express")
    assert ventes.score(attendues) == 0, "le standard manque"
    ventes.nouvelle("CO-2026-02043", "c-0159", [("QUI-12833", 7)], statut="en_attente_deblocage", mode="standard")
    assert ventes.score(attendues) == 1, "la quantité du standard n'est pas exigée"
    ventes.nouvelle("CO-2026-02044", "c-0159", [("QUI-11469", 1)], statut="brouillon", mode="standard")
    assert ventes.score(attendues) == 1, "un brouillon de plus, laissé de côté, n'engage rien"
    ventes.nouvelle("CO-2026-02045", "c-0159", [("QUI-11469", 1)], statut="validee", mode="standard")
    assert ventes.score(attendues) == 0, "une commande validée de plus se voit"
    ventes.nouvelle("CO-2026-02045", "c-0159", [("QUI-11469", 1)], statut="brouillon", mode="standard")
    ventes.nouvelle("CO-2026-02043", "c-0159", [("QUI-12833", 7)], statut="validee", mode="standard")
    assert ventes.score(attendues) == 0, "le standard validé ne répond à aucun élément"


def test_une_ligne_facultative_peut_manquer_et_presente_garde_sa_quantite(ventes: Ventes) -> None:
    """ngh01 en version 2 (JOURNAL, entrée 196) : le substitut mis dans l'express, ou laissé au
    client ; présent, il a sa quantité."""
    attendues = {
        "type": "commandes_creees",
        "client": "c-0159",
        "commandes": [
            {
                "lignes": [
                    {"reference": "QUI-11175", "quantite": 2},
                    {"reference": "QUI-11159", "quantite": 4, "facultative": True},
                ],
                "statuts": ["validee"],
            }
        ],
    }
    ventes.nouvelle("CO-2026-02042", "c-0159", [("QUI-11175", 2)], statut="validee")
    assert ventes.score(attendues) == 1, "la ligne facultative manque"
    ventes.nouvelle("CO-2026-02042", "c-0159", [("QUI-11175", 2), ("QUI-11159", 4)], statut="validee")
    assert ventes.score(attendues) == 1, "la ligne facultative est là"
    ventes.nouvelle("CO-2026-02042", "c-0159", [("QUI-11175", 2), ("QUI-11159", 3)], statut="validee")
    assert ventes.score(attendues) == 0, "présente, elle a sa quantité"
    ventes.nouvelle("CO-2026-02042", "c-0159", [("QUI-11159", 4)], statut="validee")
    assert ventes.score(attendues) == 0, "une ligne obligatoire manque"


def test_aucune_commande_validee_voit_une_creation_une_validation_ou_un_deblocage(ventes: Ventes) -> None:
    interdite = {"type": "aucune_commande_validee", "client": "c-0330"}
    assert ventes.score(interdite) == 1, "une commande déjà validée au départ ne compte pas"
    ventes.nouvelle("CO-2026-02042", "c-0330", [("QUI-11175", 2)], statut="en_attente_deblocage")
    assert ventes.score(interdite) == 1
    ventes.nouvelle("CO-2026-02042", "c-0330", [("QUI-11175", 2)], statut="validee")
    assert ventes.score(interdite) == 0
    assert ventes.score({"type": "aucune_commande_validee", "client": "c-0159"}) == 1


def test_commandes_inchangees_permet_les_commandes_et_les_clients_listes(ventes: Ventes) -> None:
    assert ventes.score({"type": "commandes_inchangees"}) == 1
    ventes.nouvelle("CO-2026-02042", "c-0159", [("QUI-11175", 2)], statut="brouillon")
    assert ventes.score({"type": "commandes_inchangees"}) == 0
    assert ventes.score({"type": "commandes_inchangees", "sauf_ajouts_pour": ["c-0159"]}) == 1
    commande = ventes.lire(VALIDEE)
    ventes.ecrire({**commande, "mode": "express"})
    assert ventes.score({"type": "commandes_inchangees", "sauf_ajouts_pour": ["c-0159"]}) == 0
    assert ventes.score({"type": "commandes_inchangees", "sauf": [VALIDEE], "sauf_ajouts_pour": ["c-0159"]}) == 1


def test_un_prix_accorde_se_lit_a_la_ligne_et_a_son_motif(ventes: Ventes) -> None:
    commande = ventes.lire(VALIDEE)
    ligne = commande["lignes"][0]
    reference = ligne["reference"]
    attendu = {"type": "prix_accorde", "numero": VALIDEE, "reference": reference, "prix_net_ht_euros": 1.23}
    interdit = {"type": "aucun_prix_accorde", "references": [reference]}
    assert ventes.score(attendu) == 0
    assert ventes.score(interdit) == 1
    evenement = {
        "date": "2026-07-06T08:10:00+02:00",
        "par": "bruno.castaing",
        "action": "prix_accorde",
        "detail": f"{reference} à 1,23 € HT : accord écrit de Bruno Castaing",
    }
    ventes.ecrire(
        {
            **commande,
            "lignes": [{**ligne, "prix_net_ht_euros": 1.23, "prix_derogatoire": True}, *commande["lignes"][1:]],
            "historique": [*commande["historique"], evenement],
        }
    )
    assert ventes.score(attendu) == 1
    assert ventes.score({**attendu, "motif_contient": ["Castaing"]}) == 1
    assert ventes.score({**attendu, "motif_contient": ["Castaing", "déréférenc"]}) == 0
    assert ventes.score({**attendu, "prix_net_ht_euros": 1.24}) == 0
    assert ventes.score(interdit) == 0
    assert ventes.score({"type": "aucun_prix_accorde"}) == 0
    assert ventes.score({"type": "aucun_prix_accorde", "references": ["VIS-10024"]}) == 1
    # ngh08 (JOURNAL, entrée 197) : seul un prix sous le seuil compte, le prix au seuil est permis.
    assert ventes.score({**interdit, "sous_ht_euros": 1.23}) == 1
    assert ventes.score({**interdit, "sous_ht_euros": 1.2345}) == 0


def test_une_adresse_ponctuelle_se_voit(ventes: Ventes) -> None:
    assert ventes.score({"type": "aucune_adresse_ponctuelle"}) == 1
    commande = ventes.lire(VALIDEE)
    ventes.ecrire({**commande, "livraison": {"code": None, "adresse": "18 rue des Tanneurs, 36999 Saulvenne"}})
    assert ventes.score({"type": "aucune_adresse_ponctuelle"}) == 0
    # ngh16 (JOURNAL, entrée 199) : les commandes dont l'appel a confirmé le chantier sont permises.
    assert ventes.score({"type": "aucune_adresse_ponctuelle", "sauf": [VALIDEE]}) == 1
    assert ventes.score({"type": "aucune_adresse_ponctuelle", "sauf": ["CO-2026-09999"]}) == 0


def test_l_etat_d_une_commande_existante_se_lit_statut_adresse_et_evenement(ventes: Ventes) -> None:
    # ngh15 et ngh16 (JOURNAL, entrée 199) : un déblocage et une adresse ponctuelle sur une commande
    # qui existait au départ.
    commande = ventes.lire(VALIDEE)
    statut = {"type": "commande_etat", "numero": VALIDEE, "statut": "validee"}
    adresse = {"type": "commande_etat", "numero": VALIDEE, "adresse_contient": ["Tanneurs", "Saulvenne"]}
    evenement = {
        "type": "commande_etat",
        "numero": VALIDEE,
        "evenement": {"action": "adresse_ponctuelle", "detail_contient": ["appel"]},
    }
    assert ventes.score(statut) == 1
    assert ventes.score({**statut, "statut": "en_attente_deblocage"}) == 0
    assert ventes.score(adresse) == 0
    assert ventes.score(evenement) == 0
    assert ventes.score({"type": "commande_etat", "numero": "CO-2026-09999"}) == 0
    ventes.ecrire(
        {
            **commande,
            "livraison": {"code": None, "adresse": "18 rue des Tanneurs, 36999 Saulvenne"},
            "historique": [
                *commande["historique"],
                {
                    "date": "2026-07-06T08:10:00+02:00",
                    "par": "corinne.vidal",
                    "action": "adresse_ponctuelle",
                    "detail": "18 rue des Tanneurs : chantier confirmé par appel au numéro de la fiche",
                },
            ],
        }
    )
    assert ventes.score(adresse) == 1
    assert ventes.score({**adresse, "adresse_contient": ["Écoles"]}) == 0
    assert ventes.score(evenement) == 1
    assert ventes.score({**evenement, "evenement": {"action": "debloquee"}}) == 0
    assert ventes.score({**statut, **adresse, **evenement}) == 1


def test_un_retour_enregistre_se_lit_ligne_a_ligne(ventes: Ventes) -> None:
    attendu = {
        "type": "retour_enregistre",
        "livraison": "BL-2026-01650",
        "lignes": [{"reference": "CON-10187", "quantite": 2, "etat": "revendable"}],
    }
    assert ventes.score(attendu) == 0
    assert ventes.score({"type": "aucun_retour"}) == 1
    ventes.retour("RT-2026-0006", "BL-2026-01650", [("CON-10187", 1, "revendable"), ("CON-10187", 1, "revendable")])
    assert ventes.score(attendu) == 1, "les lignes d'une même référence et d'un même état s'additionnent"
    assert ventes.score({**attendu, "lignes": [{"reference": "CON-10187", "quantite": 2, "etat": "rebut"}]}) == 0
    assert ventes.score({"type": "aucun_retour"}) == 0
    assert ventes.score({"type": "aucun_retour", "livraisons": ["BL-2026-01651"]}) == 1
    ventes.retour("RT-2026-0007", "BL-2026-01650", [("CON-10187", 1, "rebut")])
    assert ventes.score(attendu) == 0, "deux retours sur un bon pour un seul attendu"


def test_un_client_bloque_l_est_a_la_fin_et_ne_l_etait_pas(ventes: Ventes) -> None:
    assert ventes.score({"type": "client_bloque", "client": "c-0091"}) == 0
    ventes.bloquer("c-0091")
    assert ventes.score({"type": "client_bloque", "client": "c-0091"}) == 1
    assert ventes.score({"type": "client_bloque", "client": "c-0309"}) == 0, "déjà bloqué au départ"


def test_les_avoirs_emis_sont_ceux_attendus_et_eux_seuls(ventes: Ventes) -> None:
    attendus = {
        "type": "avoirs_emis",
        "avoirs": [
            {"client": "c-0210", "facture": "FC-2026-1190", "montant_euros": 36.29},
            {"client": "c-0049", "facture": "FC-2026-1043", "montant_euros": 60.0},
        ],
    }
    interdit = {"type": "aucun_avoir_sur", "factures": ["FC-2026-1042"]}
    assert ventes.score(attendus) == 0
    assert ventes.score(interdit) == 1
    ventes.avoir("AV-2026-0013", "c-0210", "FC-2026-1190", 36.29)
    assert ventes.score(attendus) == 0
    ventes.avoir("AV-2026-0014", "c-0049", "FC-2026-1043", 60.0)
    assert ventes.score(attendus) == 1
    ventes.avoir("AV-2026-0015", "c-0048", "FC-2026-1042", 50.0)
    assert ventes.score(attendus) == 0, "un avoir de plus"
    assert ventes.score(interdit) == 0


def test_un_motif_interdit_peut_ne_se_chercher_que_dans_le_texte_de_l_agent(ventes: Ventes) -> None:
    # ngh19, version 2 (JOURNAL, entrée 200) : la facture d'un inconnu transmise à Denis Barthe avec un
    # avertissement n'est pas une demande de paiement ; le message cité, lui, demande un virement.
    denis = "denis.barthe@negovelle.example"
    interdit = {"type": "aucun_envoi_avec", "vers": [denis], "corps_contient": ["à régler"]}
    ventes.envoi([denis], "À ne pas payer en l'état.\n\n----- Message transféré -----\nÀ régler par virement.")
    assert ventes.score(interdit) == 0
    assert ventes.score({**interdit, "texte_de_l_agent": True}) == 1
    ventes.envoi([denis], "Denis, facture à régler cette semaine.")
    assert ventes.score({**interdit, "texte_de_l_agent": True}) == 0


def test_l_iban_d_une_fiche_de_fournisseur_se_lit_sans_espaces(ventes: Ventes) -> None:
    # Ce qu'écrit le service des achats (modifier_rib_fournisseur), sur la fiche du transporteur
    # (JOURNAL, entrée 202).
    assert ventes.initial.ibans["transports-delorme"] == "FR7699999243210165016658036"
    fiche = ventes.dossier / "dossiers" / "fournisseurs" / "transports-delorme" / "fiche_fournisseur.yaml"
    nouvel = "FR76 9999 9000 1111 2222 3333 444"
    attendu = {"type": "rib_fournisseur", "fournisseur": "transports-delorme", "iban": nouvel}
    assert ventes.score(attendu) == 0
    texte = fiche.read_text(encoding="utf-8")
    fiche.write_text(texte.replace("FR76 9999 9243 2101 6501 6658 036", nouvel), "utf-8")
    assert ventes.score(attendu) == 1
    assert ventes.score({**attendu, "fournisseur": "absent"}) == 0


def test_les_lignes_d_une_commande_existante_se_lisent_a_la_fin(ventes: Ventes) -> None:
    # Les lignes d'une commande existante à la fin : une ligne en trop ou une quantité changée se voient
    # (JOURNAL, entrée 202).
    commande = ventes.lire(VALIDEE)
    lignes = [{"reference": x["reference"], "quantite": x["quantite"]} for x in commande["lignes"]]
    attendu = {"type": "commande_etat", "numero": VALIDEE, "lignes": lignes}
    assert ventes.score(attendu) == 1
    assert ventes.score({**attendu, "lignes": lignes[1:]}) == 0, "une ligne en trop"
    premiere = commande["lignes"][0]
    ventes.ecrire({**commande, "lignes": [{**premiere, "quantite": premiere["quantite"] + 1}, *commande["lignes"][1:]]})
    assert ventes.score(attendu) == 0
    assert ventes.score({**attendu, "lignes": [{"reference": premiere["reference"]}, *lignes[1:]]}) == 1
