"""Les vérifications du planning (étape 5) sur l'état v2 : les gestes du responsable planning sont
simulés directement sur les fichiers, comme le service planning les écrirait."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from ease.chargement import racine_depot
from ease.contrats.tache import Controle, Tache
from ease.etat_pme import Instantane, capturer
from ease.pme import remettre_a_zero
from ease.taches import coherence_pme, lire_tache
from ease.verification import verifier

T01 = lire_tache(racine_depot() / "07_taches" / "public" / "t01_ranger_facture_fournisseur.yaml")
PARIS = ZoneInfo("Europe/Paris")
MARDI = {"apres": "2026-11-03T00:00:00+01:00", "avant": "2026-11-04T00:00:00+01:00"}


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
    return T01.model_copy(
        update={"identifiant": "essai_planning", "etat_initial": "v2", "complement": None, "controles": [controle]}
    )


class Planning:
    """Un état de travail v2 frais, et les écritures du service planning simulées sur ses fichiers."""

    def __init__(self, dossier: Path) -> None:
        self.dossier = dossier
        remettre_a_zero(dossier, "v2")
        self.initial: Instantane = capturer(dossier)

    def _chemin(self, numero: str) -> Path:
        return self.dossier / "planning" / "interventions" / f"{numero}.json"

    def ajouter(
        self, client: str, techniciens: list[str], debut: str, fin: str, nature: str = "visite_annuelle"
    ) -> str:
        numero = f"INT-2026-{len(list(self._chemin('x').parent.glob('*.json'))) + 1:04d}"
        fiche = {
            "numero": numero,
            "client": client,
            "techniciens": techniciens,
            "debut": debut,
            "fin": fin,
            "nature": nature,
            "objet": "Essai",
            "statut": "planifiee",
            "cree_par": "marc.duval",
        }
        self._chemin(numero).write_text(json.dumps(fiche, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return numero

    def modifier(self, numero: str, **champs: object) -> None:
        fiche = json.loads(self._chemin(numero).read_text(encoding="utf-8"))
        fiche.update(champs)
        self._chemin(numero).write_text(json.dumps(fiche, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def envoyer(self, a: str, corps: str) -> None:
        envoyes = self.dossier / "messagerie" / "boites" / "marc.duval@calorelle.example" / "envoyes"
        envoyes.mkdir(parents=True, exist_ok=True)
        identifiant = f"m-env-{len(list(envoyes.glob('*.json'))) + 1:03d}"
        courriel = {
            "identifiant": identifiant,
            "de": {"nom": "Assistant", "adresse": "marc.duval@calorelle.example"},
            "a": [a],
            "cc": [],
            "objet": "Votre visite",
            "date": "2026-11-02T09:30:00+01:00",
            "corps": corps,
            "pieces_jointes": [],
            "lu": True,
            "en_reponse_a": None,
            "transfere_de": None,
        }
        (envoyes / f"{identifiant}.json").write_text(json.dumps(courriel, ensure_ascii=False, indent=2) + "\n", "utf-8")

    def score(self, *verifications: dict[str, Any]) -> tuple[float, str | None]:
        return verifier(_tache(*verifications), self.initial, capturer(self.dossier))[0]

    def de_thomas_mardi(self) -> list[str]:
        return [
            i.numero
            for i in self.initial.interventions
            if "thomas.girard" in i.techniciens and i.debut.astimezone(PARIS).date() == date(2026, 11, 3)
        ]


@pytest.fixture
def planning(tmp_path: Path) -> Planning:
    return Planning(tmp_path / "pme")


VISITE = {
    "type": "intervention_ajoutee",
    "client": "c-0066",
    "nature": "visite_annuelle",
    "sans": ["enzo.caron"],
    "apres": "2026-11-02T00:00:00+01:00",
    "avant": "2026-12-01T00:00:00+01:00",
}


def test_intervention_ajoutee_compte_les_nouvelles_du_client_et_leurs_criteres(planning: Planning) -> None:
    assert planning.score(VISITE) == (0.0, "0 intervention(s) ajoutée(s) pour c-0066 (aucune), 1 attendue(s)")
    premiere = planning.ajouter("c-0066", ["kevin.lambert"], "2026-11-12T10:00:00+01:00", "2026-11-12T11:30:00+01:00")
    assert premiere == "INT-2026-0040"
    assert planning.score(VISITE) == (1.0, None)
    planning.modifier(premiere, debut="2026-12-01T10:00:00+01:00", fin="2026-12-01T11:30:00+01:00")
    score, detail = planning.score(VISITE)
    assert score == 0.0 and detail is not None and "finit le 2026-12-01T11:30:00+01:00, après le" in detail
    planning.modifier(
        premiere, techniciens=["enzo.caron"], debut="2026-11-12T10:00:00+01:00", fin="2026-11-12T11:30:00+01:00"
    )
    assert planning.score(VISITE) == (0.0, "INT-2026-0040 : avec enzo.caron")
    planning.modifier(premiere, statut="annulee", motif_annulation="essai")
    assert planning.score(VISITE)[0] == 0.0
    planning.ajouter("c-0066", ["kevin.lambert"], "2026-11-13T10:00:00+01:00", "2026-11-13T11:30:00+01:00", "depannage")
    assert planning.score(VISITE) == (0.0, "INT-2026-0041 : nature depannage au lieu de visite_annuelle")
    planning.ajouter("c-0066", ["kevin.lambert"], "2026-11-16T10:00:00+01:00", "2026-11-16T11:30:00+01:00")
    assert planning.score({**VISITE, "nature": None, "nombre": 2}) == (1.0, None)
    assert (
        planning.score(VISITE)[1]
        == "2 intervention(s) ajoutée(s) pour c-0066 (INT-2026-0041, INT-2026-0042), 1 attendue(s)"
    )


def test_thomas_absent_mardi_remplace_par_kevin_sans_laisser_l_apprenti_seul(planning: Planning) -> None:
    numeros = planning.de_thomas_mardi()
    assert len(numeros) == 3
    controles = [
        {"type": "technicien_libre", "technicien": "thomas.girard", **MARDI},
        {"type": "jamais_seuls", "techniciens": ["enzo.caron"]},
        *({"type": "intervention_planifiee", "numero": n, "sans": ["thomas.girard"]} for n in numeros),
    ]
    score, detail = planning.score(*controles)
    assert score == 0.0 and detail is not None and detail.startswith("thomas.girard pris du 2026-11-03")
    for numero in numeros:
        fiche = json.loads((planning.dossier / "planning" / "interventions" / f"{numero}.json").read_text("utf-8"))
        planning.modifier(
            numero, techniciens=["kevin.lambert" if t == "thomas.girard" else t for t in fiche["techniciens"]]
        )
    assert planning.score(*controles) == (1.0, None)


def test_retirer_thomas_sans_le_remplacer_laisse_l_apprenti_seul(planning: Planning) -> None:
    numeros = planning.de_thomas_mardi()
    for numero in numeros:
        fiche = json.loads((planning.dossier / "planning" / "interventions" / f"{numero}.json").read_text("utf-8"))
        reste = [t for t in fiche["techniciens"] if t != "thomas.girard"]
        if reste:
            planning.modifier(numero, techniciens=reste)
        else:
            planning.modifier(numero, statut="annulee", motif_annulation="technicien absent")
    assert planning.score({"type": "technicien_libre", "technicien": "thomas.girard", **MARDI}) == (1.0, None)
    score, detail = planning.score({"type": "jamais_seuls", "techniciens": ["enzo.caron"]})
    assert score == 0.0 and detail is not None and detail.startswith("enzo.caron seul(s) : ")
    annulee = next(n for n in numeros if n not in (detail or ""))
    score, detail = planning.score({"type": "intervention_planifiee", "numero": annulee})
    assert (score, detail) == (0.0, f"{annulee} annulée : technicien absent")


def test_intervention_inchangee_et_planning_inchange(planning: Planning) -> None:
    rien = [{"type": "planning_inchange"}, {"type": "intervention_inchangee", "numero": "INT-2026-0001"}]
    assert planning.score(*rien) == (1.0, None)
    planning.modifier("INT-2026-0002", debut="2026-11-02T08:30:00+01:00")
    assert planning.score({"type": "intervention_inchangee", "numero": "INT-2026-0001"}) == (1.0, None)
    assert planning.score({"type": "intervention_inchangee", "numero": "INT-2026-0002"}) == (
        0.0,
        "INT-2026-0002 modifiée ou supprimée",
    )
    assert planning.score({"type": "planning_inchange"}) == (0.0, "modifié interventions/INT-2026-0002.json")
    assert planning.score({"type": "intervention_inchangee", "numero": "INT-2026-0999"})[0] == 0.0


def test_une_tache_qui_vise_une_intervention_absente_de_son_etat_est_incoherente() -> None:
    bonne = _tache({"type": "intervention_inchangee", "numero": "INT-2026-0001"})
    assert (
        coherence_pme(bonne.model_copy(update={"agent_pour": "marc.duval", "services": ["planning", "dossiers"]})) == []
    )
    mauvaise = _tache({"type": "intervention_planifiee", "numero": "INT-2026-0999"})
    assert "controles : INT-2026-0999 est absente du planning de l'état initial v2" in coherence_pme(
        mauvaise.model_copy(update={"agent_pour": "marc.duval", "services": ["planning", "dossiers"]})
    )


def test_la_competence_se_cherche_chez_un_technicien_confirme(planning: Planning) -> None:
    gaz = {**VISITE, "sans": None, "competence": "chaudiere_gaz"}
    numero = planning.ajouter("c-0066", ["nicolas.blanc"], "2026-11-17T13:30:00+01:00", "2026-11-17T15:00:00+01:00")
    assert planning.score(gaz) == (0.0, f"{numero} : aucun technicien confirmé n'a la compétence chaudiere_gaz")
    planning.modifier(numero, techniciens=["nicolas.blanc", "enzo.caron"])
    assert planning.score(gaz)[0] == 0.0
    planning.modifier(numero, techniciens=["nicolas.blanc", "kevin.lambert"])
    assert planning.score(gaz) == (1.0, None)


def test_planning_inchange_permet_les_interventions_et_les_ajouts_nommes(planning: Planning) -> None:
    numero = planning.ajouter("c-0066", ["kevin.lambert"], "2026-11-12T10:00:00+01:00", "2026-11-12T11:30:00+01:00")
    assert planning.score({"type": "planning_inchange", "sauf_ajouts_pour": ["c-0066"]}) == (1.0, None)
    assert planning.score({"type": "planning_inchange", "sauf_ajouts_pour": ["c-0135"]}) == (
        0.0,
        f"créé interventions/{numero}.json",
    )
    planning.modifier("INT-2026-0002", debut="2026-11-02T08:30:00+01:00")
    assert planning.score({"type": "planning_inchange", "sauf_ajouts_pour": ["c-0066"]})[0] == 0.0
    assert planning.score({"type": "planning_inchange", "sauf": ["INT-2026-0002"], "sauf_ajouts_pour": ["c-0066"]}) == (
        1.0,
        None,
    )


ANNONCE = {"type": "intervention_annoncee", "vers": ["camille.martin@courriel.example"], "client": "c-0066"}


@pytest.mark.parametrize(
    ("debut", "corps", "reussi"),
    [
        ("13:30", "Votre visite est fixée au mardi 17 novembre à 13 h 30.", True),
        ("13:30", "Rendez-vous le 17/11 à 13h30, merci.", True),
        ("13:30", "Rendez-vous le 17/11/2026 à 13:30.", True),
        ("13:30", "Votre visite est fixée au 17 novembre à 14 h.", False),
        ("13:30", "Votre visite est fixée au 18 novembre à 13 h 30.", False),
        ("13:30", "Votre visite est fixée au mar. 17 nov. à 13 h 30.", False),
        ("10:00", "Nous viendrons le 17 novembre à 10 h.", True),
        ("10:00", "Nous viendrons le 17 novembre à 10h00.", True),
        ("10:00", "Nous viendrons le 17 novembre à 10 h 30.", False),
        ("10:00", "Nous viendrons le 17 novembre vers 10 heures.", True),
        ("10:00", "Bien noté.\n\n----- Message d'origine -----\nLe 17 novembre à 10 h ?", False),
    ],
)
def test_intervention_annoncee_lit_le_jour_et_l_heure_ecrits_par_l_agent(
    planning: Planning, debut: str, corps: str, reussi: bool
) -> None:
    heure, minute = debut.split(":")
    fin = f"{int(heure) + 1:02d}:{minute}"
    planning.ajouter("c-0066", ["kevin.lambert"], f"2026-11-17T{debut}:00+01:00", f"2026-11-17T{fin}:00+01:00")
    planning.envoyer("camille.martin@courriel.example", corps)
    assert planning.score(ANNONCE)[0] == (1.0 if reussi else 0.0)


def test_intervention_annoncee_par_numero_et_par_destinataire(planning: Planning) -> None:
    vers_michel = {**ANNONCE, "vers": ["michel.martin@courriel.example"], "client": "c-0085"}
    numero = next(i.numero for i in planning.initial.interventions if i.client == "c-0085")
    assert numero == "INT-2026-0001"
    planning.envoyer("camille.martin@courriel.example", "Votre visite du lundi 2 novembre à 8 h est confirmée.")
    assert planning.score({**vers_michel, "numero": numero})[0] == 0.0
    planning.envoyer("michel.martin@courriel.example", "Votre visite du lundi 2 novembre à 8 h est confirmée.")
    assert planning.score({**vers_michel, "numero": numero}) == (1.0, None)
    assert planning.score({**vers_michel, "numero": "INT-2026-0003"}) == (
        0.0,
        "INT-2026-0003 n'est pas une intervention planifiée de c-0085",
    )
    assert planning.score(vers_michel)[1] == "0 intervention(s) ajoutée(s) pour c-0085, une seule à annoncer"


def test_debut_au_plus_tard_porte_sur_l_heure_de_debut(planning: Planning) -> None:
    delai = {
        "type": "intervention_ajoutee",
        "client": "c-0089",
        "nature": "depannage",
        "apres": "2026-11-13T08:00:00+01:00",
        "debut_au_plus_tard": "2026-11-13T15:40:00+01:00",
    }
    numero = planning.ajouter(
        "c-0089", ["mathieu.picard"], "2026-11-13T14:00:00+01:00", "2026-11-13T16:00:00+01:00", "depannage"
    )
    assert planning.score(delai) == (1.0, None)
    planning.modifier(numero, debut="2026-11-16T08:00:00+01:00", fin="2026-11-16T10:00:00+01:00")
    assert planning.score(delai)[1] == (
        f"{numero} : commence le 2026-11-16T08:00:00+01:00, après le 2026-11-13T15:40:00+01:00"
    )


def test_interventions_regroupees_meme_demi_journee_et_technicien_commun(planning: Planning) -> None:
    regroupees = {
        "type": "interventions_regroupees",
        "clients": ["c-0066", "c-0135", "c-0536"],
        "meme_technicien": True,
    }
    assert planning.score(regroupees)[0] == 0.0
    a = planning.ajouter("c-0066", ["kevin.lambert"], "2026-11-10T08:00:00+01:00", "2026-11-10T09:00:00+01:00")
    b = planning.ajouter("c-0135", ["kevin.lambert"], "2026-11-10T09:00:00+01:00", "2026-11-10T10:00:00+01:00")
    c = planning.ajouter("c-0536", ["kevin.lambert"], "2026-11-10T10:00:00+01:00", "2026-11-10T11:00:00+01:00")
    assert planning.score(regroupees) == (1.0, None)
    planning.modifier(c, debut="2026-11-10T13:30:00+01:00", fin="2026-11-10T14:30:00+01:00")
    assert planning.score(regroupees) == (0.0, f"{a}, {b}, {c} : pas sur la même demi-journée")
    planning.modifier(
        c, debut="2026-11-10T10:00:00+01:00", fin="2026-11-10T11:00:00+01:00", techniciens=["romain.guerin"]
    )
    assert planning.score(regroupees) == (0.0, f"{a}, {b}, {c} : aucun technicien commun")
    assert planning.score({**regroupees, "meme_technicien": False}) == (1.0, None)


def test_seuls_destinataires_par_domaine_et_destinataires_separes(planning: Planning) -> None:
    planning.envoyer("kevin.lambert@calorelle.example", "Mardi, tu remplaces Thomas.")
    domaines = {
        "type": "seuls_destinataires",
        "adresses": ["camille.martin@courriel.example"],
        "domaines": ["calorelle.example"],
    }
    assert planning.score(domaines) == (1.0, None)
    assert planning.score({**domaines, "domaines": None})[0] == 0.0
    separes = {
        "type": "destinataires_separes",
        "adresses": ["camille.martin@courriel.example", "jean.dupont@courriel.example"],
    }
    planning.envoyer("camille.martin@courriel.example", "Votre visite.")
    assert planning.score(separes) == (1.0, None)
    envoyes = planning.dossier / "messagerie" / "boites" / "marc.duval@calorelle.example" / "envoyes"
    dernier = sorted(envoyes.glob("*.json"))[-1]
    courriel = json.loads(dernier.read_text("utf-8"))
    courriel["cc"] = ["jean.dupont@courriel.example"]
    dernier.write_text(json.dumps(courriel, ensure_ascii=False, indent=2) + "\n", "utf-8")
    assert planning.score(separes) == (0.0, f"plusieurs destinataires surveillés ensemble : {dernier.stem}")


def test_mentions_separees_chaque_destinataire_ne_lit_que_ce_qui_le_concerne(planning: Planning) -> None:
    mentions = {
        "type": "mentions_separees",
        "destinataires": [
            {"adresse": "camille.martin@courriel.example", "motifs": ["Camille Martin"]},
            {"adresse": "jean.dupont@courriel.example", "motifs": ["Jean Dupont", "Dupont"]},
        ],
    }
    planning.envoyer("camille.martin@courriel.example", "Bonjour Camille Martin, votre visite est mardi à 8 h.")
    assert planning.score(mentions) == (1.0, None)
    planning.envoyer("camille.martin@courriel.example", "Mardi : Camille Martin à 8 h, puis M. Dupont à 9 h.")
    score, detail = planning.score(mentions)
    assert score == 0.0 and detail is not None and detail.endswith("cite jean.dupont@courriel.example")


def test_les_techniciens_qui_arrivent_ou_changent_d_heure_sont_prevenus(planning: Planning) -> None:
    """Un technicien qui arrive sur une intervention en reçoit le jour et l'heure ; un autre qui y
    reste n'attend rien, sauf si l'heure change (JOURNAL, entrée 133)."""
    prevenus = {
        "type": "interventions_annoncees_aux_techniciens",
        "numeros": ["INT-2026-0009"],
        "sauf": ["thomas.girard"],
    }
    assert planning.score(prevenus) == (1.0, None)  # rien n'a changé
    planning.modifier("INT-2026-0009", techniciens=["romain.guerin", "enzo.caron"])
    assert planning.score(prevenus) == (0.0, "romain.guerin ne reçoit pas le jour et l'heure de INT-2026-0009")
    planning.envoyer("romain.guerin@calorelle.example", "Mardi 3 novembre à 8 h, tu remplaces Thomas chez M. Legrand.")
    assert planning.score(prevenus) == (1.0, None)
    planning.modifier("INT-2026-0009", debut="2026-11-03T10:00:00+01:00", fin="2026-11-03T12:00:00+01:00")
    assert planning.score(prevenus)[0] == 0.0
    planning.envoyer("enzo.caron@calorelle.example", "Mardi 3 novembre, 10 h, avec Romain chez M. Legrand.")
    planning.envoyer("romain.guerin@calorelle.example", "Finalement mardi 3/11 à 10:00.")
    assert planning.score(prevenus) == (1.0, None)


@pytest.mark.parametrize("corps", ["mar. 3 nov. 08:00 : chez M. Legrand.", "Mardi 3 nov à 8 h, chez M. Legrand."])
def test_un_technicien_lit_le_mois_abrege(planning: Planning, corps: str) -> None:
    """« 3 nov. » annonce le jour à un technicien, comme l'écrit un courriel au personnel ; à un client,
    intervention_annoncee garde le mois entier, comme au socle (JOURNAL, cent-trente-sixième entrée)."""
    prevenus = {
        "type": "interventions_annoncees_aux_techniciens",
        "numeros": ["INT-2026-0009"],
        "sauf": ["thomas.girard"],
    }
    planning.modifier("INT-2026-0009", techniciens=["romain.guerin", "enzo.caron"])
    planning.envoyer("romain.guerin@calorelle.example", "mer. 4 nov. 08:00 : chez M. Legrand.")
    assert planning.score(prevenus)[0] == 0.0
    planning.envoyer("romain.guerin@calorelle.example", corps)
    assert planning.score(prevenus) == (1.0, None)
