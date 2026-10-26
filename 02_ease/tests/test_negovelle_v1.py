"""L'état initial v1 de Négovelle (cadrage du 2026-10-17, sections 4 à 6) : à jour, conforme à ses
contrats, fictif, à la taille du cadrage, lisible par EASE, et copié en entier à la remise à zéro,
la partie ventes/ comprise."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from ease.chargement import parametres_societe, racine_depot
from ease.contrats.avoir import Avoir
from ease.contrats.bon_de_livraison import BonDeLivraison
from ease.contrats.catalogue import Catalogue
from ease.contrats.commande import Commande
from ease.contrats.facture_client import FactureClient
from ease.contrats.fiche_client_negoce import FicheClientNegoce
from ease.contrats.retour import Retour
from ease.courriels import lire_courriel
from ease.etat_pme import capturer
from ease.pme import dossier_version, empreinte_version, remettre_a_zero

RACINE = racine_depot()
V1 = RACINE / "05_pme" / "societes" / "negovelle" / "v1"
DOSSIERS = V1 / "dossiers"
BOITES = V1 / "messagerie" / "boites"
COURRIELS = sorted(BOITES.glob("*/*/*.json"))
LISIBLES = {".md", ".yaml", ".csv", ".txt", ".json"}


def _organigramme(societe: str, version: str) -> dict[str, Any]:
    chemin = RACINE / "05_pme" / "societes" / societe / version / "entreprise" / "organigramme.yaml"
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def _fiches() -> list[FicheClientNegoce]:
    return [
        FicheClientNegoce.model_validate(yaml.safe_load(chemin.read_text(encoding="utf-8")))
        for chemin in sorted((DOSSIERS / "clients").glob("*/fiche_client.yaml"))
    ]


def test_l_etat_est_celui_du_generateur() -> None:
    script = RACINE / "09_outillage" / "scripts" / "generer_negovelle_v1.py"
    resultat = subprocess.run([sys.executable, str(script), "--verifier"], capture_output=True, text=True, cwd=RACINE)
    assert resultat.returncode == 0, resultat.stderr


def test_la_societe_se_declare_aux_services_et_a_ease() -> None:
    assert dossier_version("v1", "negovelle") == V1
    parametres = parametres_societe(V1)
    assert (parametres.nom, parametres.domaine, parametres.dossier_fiches_fournisseurs) == (
        "Négovelle",
        "negovelle.example",
        "fournisseurs",
    )
    assert capturer(V1).domaine == "negovelle.example"
    for fournisseur in (DOSSIERS / "fournisseurs").iterdir():
        assert (fournisseur / "fiche_fournisseur.yaml").is_file(), fournisseur.name


def test_la_remise_a_zero_copie_les_ventes(tmp_path: Path) -> None:
    remettre_a_zero(tmp_path / "pme", "v1", societe="negovelle")
    for partie in ("entreprise", "dossiers", "messagerie", "facturation", "ventes"):
        assert (tmp_path / "pme" / partie).is_dir(), partie
    assert (tmp_path / "pme" / "ventes" / "catalogue.json").read_bytes() == (
        V1 / "ventes" / "catalogue.json"
    ).read_bytes()
    assert empreinte_version("v1", "negovelle") != empreinte_version("v1", "domivelle")


def test_les_donnees_des_services_respectent_leurs_contrats() -> None:
    catalogue = Catalogue.model_validate_json((V1 / "ventes" / "catalogue.json").read_text(encoding="utf-8"))
    assert len(catalogue.articles) == 4000
    for dossier, modele in (
        ("ventes/commandes", Commande),
        ("ventes/livraisons", BonDeLivraison),
        ("ventes/retours", Retour),
        ("facturation/factures", FactureClient),
        ("facturation/avoirs", Avoir),
    ):
        fichiers = sorted((V1 / dossier).glob("*.json"))
        assert fichiers, dossier
        for chemin in fichiers:
            texte = chemin.read_text(encoding="utf-8")
            modele.model_validate_json(texte)
            assert json.loads(texte)["numero"] == chemin.stem
    assert len(_fiches()) == 350


@pytest.mark.parametrize("chemin", COURRIELS, ids=lambda c: c.stem)
def test_chaque_courriel_respecte_son_contrat(chemin: Path) -> None:
    courriel = lire_courriel(chemin)
    assert courriel.identifiant == chemin.stem
    assert courriel.lu, "v1 n'a aucun non lu : ceux d'une tâche sont dans son complément"
    assert courriel.de.adresse.endswith(".example")
    assert courriel.de.adresse not in courriel.a, "personne ne s'écrit à soi-même"


def test_chaque_boite_de_l_organigramme_existe() -> None:
    organigramme = _organigramme("negovelle", "v1")
    attendues = set(organigramme["boites_partagees"]) | {p["courriel"] for p in organigramme["personnes"]}
    assert {b.name for b in BOITES.iterdir()} == attendues


def test_tout_est_fictif() -> None:
    adresses = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    telephones = re.compile(r"\b0\d(?: \d\d){4}\b")
    for fichier in sorted(V1.rglob("*")):
        if not fichier.is_file():
            continue
        contenu = fichier.read_bytes()
        if fichier.suffix == ".pdf":
            assert b"FICTIF" in contenu, fichier
            continue
        assert fichier.suffix in LISIBLES, fichier
        texte = contenu.decode("utf-8")
        for adresse in adresses.findall(texte):
            assert adresse.endswith(".example"), (fichier, adresse)
        for numero in telephones.findall(texte):
            assert numero.startswith(("02 61 91", "06 39 98")), (fichier, numero)
        for iban in re.findall(r"FR76 \d{4} \d", texte):
            assert iban.startswith("FR76 9999 9"), (fichier, iban)


def test_la_societe_a_la_taille_du_cadrage() -> None:
    organigramme = _organigramme("negovelle", "v1")
    assert len(organigramme["personnes"]) == 22
    fiches = _fiches()
    assert Counter(f.type for f in fiches) == {"artisan": 210, "entreprise": 70, "pme": 42, "collectivite": 28}
    assert all(f.adresse.endswith("(FICTIF)") and "36999" in f.adresse for f in fiches)
    assert Counter(f.statut for f in fiches) == {"ouvert": 345, "bloque": 5}
    catalogue = json.loads((V1 / "ventes" / "catalogue.json").read_text(encoding="utf-8"))
    assert len({a["famille"] for a in catalogue["articles"]}) == 10
    assert len({a["reference"] for a in catalogue["articles"]}) == 4000
    assert catalogue["conditions"]["remises_categories"] == {"A": 0.0, "B": 4.0, "C": 8.0}


def test_aucune_personne_de_negovelle_ne_porte_le_nom_d_une_personne_des_autres_societes() -> None:
    autres = {
        p["nom"].split(" ", 1)[1]
        for s, v in (("calorelle", "v3"), ("domivelle", "v1"))
        for p in _organigramme(s, v)["personnes"]
    }
    siens = {p["nom"].split(" ", 1)[1] for p in _organigramme("negovelle", "v1")["personnes"]}
    contacts = {c.nom.split(" ", 1)[1] for f in _fiches() for c in f.contacts}
    assert not (siens | contacts) & autres
