"""Les données initiales v2 de Calorelle : v1 et les ajouts de l'étape 5 (JOURNAL, entrées 81 et
82), à jour, conformes aux contrats, et cohérentes avec le manuel de v2."""

from __future__ import annotations

import calendar
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import yaml
from ease.chargement import racine_depot
from ease.contrats.intervention import Intervention
from ease.contrats.technicien import Technicien

RACINE = racine_depot()
V1 = RACINE / "05_pme" / "societes" / "calorelle" / "v1"
V2 = RACINE / "05_pme" / "societes" / "calorelle" / "v2"
PLANNING = V2 / "planning"
PARIS = ZoneInfo("Europe/Paris")

CONDITIONS_CHANGEES = {
    "papeterie-du-val",
    "informatique-des-greves",
    "garage-bessiere",
    "robinetterie-des-greves",
    "outillage-de-mirelande",
    "electricite-du-val-mauvoir",
    "fumisterie-des-hautes-fresnes",
    "transports-de-sablonnet",
    "gaines-et-conduits-de-la-courtine",
    "nettoyage-de-mirelande",
}


def _fichiers(racine: Path, partie: str) -> dict[str, bytes]:
    return {p.relative_to(racine).as_posix(): p.read_bytes() for p in (racine / partie).rglob("*") if p.is_file()}


def _yaml(chemin: Path) -> dict[str, object]:
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def _personnes(chemin: Path) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], _yaml(chemin)["personnes"])


def _techniciens() -> list[Technicien]:
    return [
        Technicien.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(PLANNING.glob("techniciens/*.json"))
    ]


def _interventions() -> list[Intervention]:
    return [
        Intervention.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(PLANNING.glob("interventions/*.json"))
    ]


def test_les_donnees_v2_sont_celles_du_generateur() -> None:
    script = RACINE / "09_outillage" / "scripts" / "generer_donnees_v2.py"
    resultat = subprocess.run([sys.executable, str(script), "--verifier"], capture_output=True, text=True, cwd=RACINE)
    assert resultat.returncode == 0, resultat.stderr


def test_v2_garde_tout_v1_sauf_les_changements_annonces() -> None:
    changes = {
        "dossiers/commun/manuel_procedures.md",
        "dossiers/commun/annuaire.md",
        "dossiers/rh/conges_2026.txt",
        *(f"dossiers/administration/fournisseurs/{f}/fiche_fournisseur.yaml" for f in CONDITIONS_CHANGEES),
    }
    for partie in ("dossiers", "messagerie"):
        avant, apres = _fichiers(V1, partie), _fichiers(V2, partie)
        assert set(avant) <= set(apres), partie
        assert {c for c in avant if avant[c] != apres[c]} == {c for c in changes if c.startswith(partie)}
    ajoutes = set(_fichiers(V2, "dossiers")) - set(_fichiers(V1, "dossiers"))
    assert "dossiers/administration/echeancier_fournisseurs.md" in ajoutes
    assert len(ajoutes) == 9
    assert all(
        c.startswith("dossiers/administration/factures_fournisseurs/")
        for c in ajoutes - {"dossiers/administration/echeancier_fournisseurs.md"}
    )
    for nom in ("acces_dossiers.yaml", "fiche_entreprise.md", "horloge.yaml"):
        assert (V2 / "entreprise" / nom).read_bytes() == (V1 / "entreprise" / nom).read_bytes(), nom


def test_l_organigramme_v2_ajoute_les_neuf_techniciens_et_rien_d_autre() -> None:
    avant = _yaml(V1 / "entreprise" / "organigramme.yaml")
    apres = _yaml(V2 / "entreprise" / "organigramme.yaml")
    assert apres["boites_partagees"] == avant["boites_partagees"]
    personnes_avant = _personnes(V1 / "entreprise" / "organigramme.yaml")
    personnes_apres = _personnes(V2 / "entreprise" / "organigramme.yaml")
    assert personnes_apres[: len(personnes_avant)] == personnes_avant
    nouvelles = personnes_apres[len(personnes_avant) :]
    assert len(nouvelles) == 9 and len(personnes_apres) == 18
    telephones = [str(p["telephone"]) for p in personnes_apres]
    assert len(set(telephones)) == 18 and all(t.startswith("06 39 98 10 ") for t in telephones[9:])
    for p in nouvelles:
        assert p["role"] == "Technicien"
        assert p["droits"] == ["lire_planning", "rediger_compte_rendu"]
        assert p["courriel"] == f"{p['id']}@calorelle.example"
    lecteurs = {str(p["id"]) for p in personnes_apres if "lire_planning" in p["droits"]}
    assert {t.id for t in _techniciens()} == lecteurs


def test_le_manuel_v2_porte_les_six_regles_et_garde_la_numerotation() -> None:
    manuel = (V2 / "entreprise" / "manuel_procedures.md").read_text(encoding="utf-8")
    assert (V2 / "dossiers" / "commun" / "manuel_procedures.md").read_text(encoding="utf-8") == manuel
    titres = re.findall(r"^## (\d+)\. ", manuel, flags=re.MULTILINE)
    assert titres == [str(n) for n in range(1, 10)]
    for regle in [
        "du lundi au vendredi, de 8 h à 12 h et de 13 h 30 à 17 h 30",
        "48 heures ouvrées font deux\n  jours ouvrés",
        "Un apprenti n'intervient jamais seul.",
        "au plus tard un mois avant sa date anniversaire ; sinon, il est\n  reconduit pour un an",
        "multiplié par le nombre de mois entiers restant avant la\n  date anniversaire, divisé par 12",
        "Les mois entiers se comptent de date à\n  date, à partir du jour où commence la nouvelle formule.",
        "au moins un mois à l'avance et sont validés par la gérante. Jamais plus de\ndeux techniciens",
    ]:
        assert regle in manuel, regle
    annuaire = (V2 / "dossiers" / "commun" / "annuaire.md").read_text(encoding="utf-8")
    assert "| Sébastien Noël | Technicien | sebastien.noel@calorelle.example | 06 39 98 10 16 |" in annuaire


# Dates des fêtes mobiles vérifiées le 2026-10-07 sur calendrier-365.fr (jours fériés 2026 et 2027).
FERIES_ATTENDUS = [
    "2026-01-01", "2026-04-06", "2026-05-01", "2026-05-08", "2026-05-14", "2026-05-25",
    "2026-07-14", "2026-08-15", "2026-11-01", "2026-11-11", "2026-12-25",
    "2027-01-01", "2027-03-29", "2027-05-01", "2027-05-06", "2027-05-08", "2027-05-17",
    "2027-07-14", "2027-08-15", "2027-11-01", "2027-11-11", "2027-12-25",
]  # fmt: skip


def test_les_heures_d_intervention_et_les_jours_feries() -> None:
    horaires = _yaml(PLANNING / "horaires.yaml")
    assert horaires["jours"] == [1, 2, 3, 4, 5]
    assert horaires["plages"] == ["08:00-12:00", "13:30-17:30"]
    assert horaires["feries"] == FERIES_ATTENDUS


def _plage(debut: datetime, fin: datetime) -> bool:
    minutes = (debut.hour * 60 + debut.minute, fin.hour * 60 + fin.minute)
    return any(a <= minutes[0] and minutes[1] <= b for a, b in ((480, 720), (810, 1050))) and debut.date() == fin.date()


def test_le_planning_de_depart_respecte_le_logiciel_et_le_manuel() -> None:
    techniciens = {t.id: t for t in _techniciens()}
    interventions = _interventions()
    feries = {date.fromisoformat(j) for j in FERIES_ATTENDUS}
    assert [i.numero for i in interventions] == [f"INT-2026-{n:04d}" for n in range(1, len(interventions) + 1)]
    assert [i.debut for i in interventions] == sorted(i.debut for i in interventions)
    occupe: dict[str, list[tuple[datetime, datetime]]] = {t: [] for t in techniciens}
    for i in interventions:
        assert (V2 / "dossiers" / "clients" / i.client / "fiche_client.yaml").is_file(), i.numero
        assert i.cree_par == "donnees_initiales"
        assert (i.statut == "annulee") == (i.motif_annulation is not None), i.numero
        if i.statut == "annulee":
            continue
        debut, fin = i.debut.astimezone(PARIS), i.fin.astimezone(PARIS)
        assert debut.weekday() < 5 and debut.date() not in feries, i.numero
        assert _plage(debut, fin), i.numero
        assert not all(techniciens[t].apprenti for t in i.techniciens), f"{i.numero} : apprenti seul"
        for t in i.techniciens:
            for absence in techniciens[t].indisponibilites:
                assert fin <= absence.debut or absence.fin <= debut, f"{i.numero} : {t} indisponible"
            for autre in occupe[t]:
                assert fin <= autre[0] or autre[1] <= debut, f"{i.numero} : {t} déjà pris"
            occupe[t].append((debut, fin))
    mardi = [i for i in interventions if i.debut.astimezone(PARIS).date() == date(2026, 11, 3)]
    assert len(mardi) == 9
    assert sum("thomas.girard" in i.techniciens for i in mardi) == 3
    assert sum("enzo.caron" in i.techniciens for i in mardi) == 2


def test_quatre_clients_de_novembre_attendent_leur_visite_et_les_anciennes_taches_sont_a_l_ecart() -> None:
    planifies = {i.client for i in _interventions() if i.nature == "visite_annuelle" and i.statut == "planifiee"}
    novembre: set[str] = set()
    for fiche in (V2 / "dossiers" / "clients").glob("*/fiche_client.yaml"):
        contenu = cast(dict[str, Any], _yaml(fiche))
        contrat = cast(dict[str, str], contenu.get("contrat") or {})
        if contrat.get("mois_anniversaire") == "novembre":
            novembre.add(str(contenu["code"]))
    assert planifies <= novembre
    assert novembre - planifies == {"c-0066", "c-0135", "c-0307", "c-0405", "c-0536"}
    anciennes = {"c-0010", "c-0088", "c-0124", "c-0137", "c-0142", "c-0217", "c-0311", "c-0405"}
    assert not anciennes & {i.client for i in _interventions()}


def test_jamais_plus_de_deux_techniciens_absents_le_meme_jour_et_le_dossier_rh_concorde() -> None:
    absents: Counter[date] = Counter()
    noms = {t.id: t.nom for t in _techniciens()}
    conges = (V2 / "dossiers" / "rh" / "conges_2026.txt").read_text(encoding="utf-8")
    lignes = [ligne for ligne in conges.splitlines() if ligne.startswith("- ")]
    periodes = [(t.id, p) for t in _techniciens() for p in t.indisponibilites]
    assert len(lignes) == len(periodes)
    for identifiant, periode in periodes:
        assert any(ligne.startswith(f"- {noms[identifiant]} : ") for ligne in lignes), identifiant
        jour = periode.debut.astimezone(PARIS).date()
        while jour < periode.fin.astimezone(PARIS).date():
            absents[jour] += 1
            jour += timedelta(days=1)
    assert max(absents.values()) == 2


def _echeance(jour: date, conditions: str) -> date:
    if conditions == "paiement à réception":
        return jour
    plus_30 = jour + timedelta(days=30)
    if conditions == "paiement à 30 jours":
        return plus_30
    assert conditions == "paiement à 30 jours fin de mois", conditions
    return plus_30.replace(day=calendar.monthrange(plus_30.year, plus_30.month)[1])


def test_l_echeancier_concorde_avec_les_factures_et_les_fiches() -> None:
    texte = (V2 / "dossiers" / "administration" / "echeancier_fournisseurs.md").read_text(encoding="utf-8")
    lignes = [
        ligne for ligne in texte.splitlines() if ligne.startswith("| ") and not ligne.startswith("| Fournisseur |")
    ]
    factures = sorted((V2 / "dossiers" / "administration" / "factures_fournisseurs").rglob("*.pdf"))
    assert len(lignes) == len(factures) == 18
    nommage = {p.name: p for p in factures}
    for ligne in lignes:
        fournisseur, numero, jour, montant, conditions, echeance, reglee, _ = (
            c.strip() for c in ligne.strip("|").split("|")
        )
        dossier = next(
            p.parent.name
            for p in (V2 / "dossiers" / "administration" / "fournisseurs").glob("*/fiche_fournisseur.yaml")
            if _yaml(p)["nom"] == fournisseur
        )
        fiche = _yaml(V2 / "dossiers" / "administration" / "fournisseurs" / dossier / "fiche_fournisseur.yaml")
        assert fiche["conditions"] == conditions, numero
        pdf = nommage[f"{dossier}_{numero.lower()}.pdf"]
        emise = datetime.strptime(jour, "%d/%m/%Y").date()
        assert pdf.parent.name == emise.strftime("%Y-%m"), numero
        assert f"Total TTC : {montant}".encode("cp1252") in pdf.read_bytes(), numero
        assert datetime.strptime(echeance, "%d/%m/%Y").date() == _echeance(emise, conditions), numero
        if reglee != "non réglée":
            payee = datetime.strptime(reglee, "%d/%m/%Y").date()
            assert emise <= payee <= date(2026, 10, 29), numero
            assert payee.weekday() in (0, 1, 3), f"{numero} : réglée un jour où le comptable ne travaille pas"
    assert not (
        V2 / "dossiers/administration/factures_fournisseurs/2026-10/thermopieces-loire_f-2026-1187.pdf"
    ).exists()
