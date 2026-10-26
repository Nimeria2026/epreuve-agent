"""L'état initial v1 de Domivelle : à jour, conforme, fictif, lisible par les services et par EASE, et
prêt pour les objets que les tâches du socle y attendent (inventaire.yaml)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from ease.chargement import parametres_societe, racine_depot
from ease.courriels import lire_courriel
from ease.etat_pme import capturer
from ease.pme import dossier_version

RACINE = racine_depot()
V1 = RACINE / "05_pme" / "societes" / "domivelle" / "v1"
DOSSIERS = V1 / "dossiers"
BOITES = V1 / "messagerie" / "boites"
COURRIELS = sorted(BOITES.glob("*/*/*.json"))
LISIBLES = {".md", ".yaml", ".csv", ".txt", ".json"}


def _yaml(relatif: str) -> dict[str, Any]:
    return yaml.safe_load((DOSSIERS / relatif).read_text(encoding="utf-8"))


def _registres() -> list[dict[str, Any]]:
    return [
        yaml.safe_load(c.read_text(encoding="utf-8")) for c in sorted((DOSSIERS / "gerance").glob("*/registre.yaml"))
    ]


def _lot(code: str) -> dict[str, Any]:
    registre = _yaml(f"gerance/{code.split('-')[0]}/registre.yaml")
    return next(lot for lot in registre["lots"] if lot["lot"] == code)


def test_l_etat_est_celui_du_generateur() -> None:
    script = RACINE / "09_outillage" / "scripts" / "generer_domivelle_v1.py"
    resultat = subprocess.run([sys.executable, str(script), "--verifier"], capture_output=True, text=True, cwd=RACINE)
    assert resultat.returncode == 0, resultat.stderr


def test_la_societe_se_declare_aux_services_et_a_ease() -> None:
    assert dossier_version("v1", "domivelle") == V1
    parametres = parametres_societe(V1)
    assert (parametres.nom, parametres.domaine, parametres.dossier_fiches_fournisseurs) == (
        "Domivelle",
        "domivelle.example",
        "artisans",
    )
    assert capturer(V1).domaine == "domivelle.example"
    for artisan in (DOSSIERS / "artisans").iterdir():
        assert (artisan / "fiche_fournisseur.yaml").is_file(), artisan.name


@pytest.mark.parametrize("chemin", COURRIELS, ids=lambda c: c.stem)
def test_chaque_courriel_respecte_son_contrat(chemin: Path) -> None:
    courriel = lire_courriel(chemin)
    assert courriel.identifiant == chemin.stem
    assert courriel.lu, "v1 n'a aucun non lu : ceux d'une tâche sont dans son complément"
    assert courriel.de.adresse.endswith(".example")
    assert courriel.de.adresse not in courriel.a, "personne ne s'écrit à soi-même"


def test_chaque_boite_de_l_organigramme_existe() -> None:
    organigramme = yaml.safe_load((V1 / "entreprise" / "organigramme.yaml").read_text(encoding="utf-8"))
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


def test_le_portefeuille_a_la_taille_du_cadrage() -> None:
    registres = _registres()
    lots = [lot for registre in registres for lot in registre["lots"]]
    assert len(lots) == 1200
    par_secteur = {s: sum(len(r["lots"]) for r in registres if r["secteur"] == s) for s in ("nord", "centre", "sud")}
    assert par_secteur == {"nord": 400, "centre": 420, "sud": 380}
    assert len({lot["lot"] for lot in lots}) == 1200
    proprietaires = {lot["proprietaire"] for lot in lots}
    assert 600 <= len(proprietaires) <= 800
    assert len(list((DOSSIERS / "coproprietes").glob("cp*/fiche_copropriete.yaml"))) == 45


def test_les_tantiemes_tombent_juste() -> None:
    for liste in sorted((DOSSIERS / "coproprietes").glob("cp*/coproprietaires.csv")):
        lignes = [ligne.split(";") for ligne in liste.read_text(encoding="utf-8").splitlines()]
        colonnes, valeurs = lignes[0], lignes[1:]
        assert sum(int(v[colonnes.index("tantiemes_generaux")]) for v in valeurs) == 10000, liste
        if "tantiemes_ascenseur" in colonnes:
            assert sum(int(v[colonnes.index("tantiemes_ascenseur")]) for v in valeurs) == 10000, liste


def test_les_objets_reserves_aux_taches_sont_en_place() -> None:
    # dv02 : quatre baux du centre à réviser
    assert (_lot("c01-03")["loyer_hors_charges"], _lot("c01-03")["trimestre_irl"]) == ("684,00 €", "T1")
    assert (_lot("c01-07")["loyer_hors_charges"], _lot("c01-07")["trimestre_irl"]) == ("615,00 €", "T2")
    assert _lot("c01-09")["dpe"] == "F"
    assert (_lot("c01-12")["loyer_hors_charges"], _lot("c01-12")["revision"]) == ("552,00 €", "chaque 1er mars")
    assert {_lot(c)["revision"] for c in ("c01-03", "c01-07", "c01-09")} == {"chaque 1er juillet"}
    # dv03 : le lot rendu le 22 mai, dépôt d'un mois de loyer
    fiche = _yaml("gerance/n01/n01-06/fiche_lot.yaml")
    assert _lot("n01-06")["locataire"] == "vacant"
    assert fiche["locataire"]["cles_rendues"] == "2026-05-22"
    assert fiche["bail"]["loyer_hors_charges"] == fiche["bail"]["depot_de_garantie"] == "610,00 €"
    assert (DOSSIERS / "gerance/n01/n01-06/etat_des_lieux_entree.md").is_file()
    # dv16 : les distances du registre, et la note d'avril de Quentin Mallet
    distances = {r["immeuble"]: r["distance_agence_km"] for r in _registres()}
    assert {c: distances[c] for c in ("n01", "n02", "n03", "s01", "s02")} == {
        "n01": 9,
        "n02": 12,
        "n03": 22,
        "s01": 18,
        "s02": 15,
    }
    note = (DOSSIERS / "direction/notes_de_frais/2026-04/quentin.mallet.md").read_text(encoding="utf-8")
    assert "| 28 avril 2026 | visite | s02 | 30 |" in note
    # dv15 : le dossier du personnel de Gaëlle Fournel
    assert (DOSSIERS / "rh/gaelle.fournel").is_dir()
