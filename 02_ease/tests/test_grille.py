"""La grille de la durée humaine estimée : ses quatre parts, les sections utiles du manuel, et le refus
d'un outil qu'elle ne classe pas (JOURNAL, cent-vingt-cinquième entrée)."""

from __future__ import annotations

import pytest
from ease.chargement import dossier_societe
from ease.grille import (
    MANUEL,
    MOTIFS_BALAYES,
    MOTS_BALAYES_PAR_MINUTE,
    MOTS_ECRITS_PAR_MINUTE,
    MOTS_LUS_PAR_MINUTE,
    OUVRIR_S,
    POINTAGE_S,
    PREPARATION_S,
    TOUCHE_S,
    Appel,
    OutilInconnu,
    Parts,
    balaye,
    estimer,
    geste,
    sections,
)

MANUEL_JOUET = """# Manuel (fictif)

Introduction qui ne compte pas.

## 1. Ranger

un deux trois

## 2. Trier

quatre cinq

## 10. Planning

six
"""


def test_les_sections_gardent_leur_titre_et_suivent_leur_numero() -> None:
    assert sections(MANUEL_JOUET, [2]) == "## 2. Trier\n\nquatre cinq"
    assert sections(MANUEL_JOUET, [10, 1, 1]).startswith("## 1. Ranger")
    assert sections(MANUEL_JOUET, []) == ""
    with pytest.raises(ValueError, match="absente"):
        sections(MANUEL_JOUET, [3])


def test_un_geste_compte_les_champs_que_la_page_ne_remplit_pas() -> None:
    parts = geste({"boite": "contact@x", "identifiant": "m-1", "a": ["ab@c", "d@e"], "commentaire": "un deux trois"})
    pointer = POINTAGE_S + TOUCHE_S
    assert parts.agir == pytest.approx(PREPARATION_S + pointer + 2 * pointer + (4 + 3) * TOUCHE_S + pointer)
    assert parts.ecrire == pytest.approx(3 / MOTS_ECRITS_PAR_MINUTE * 60)
    assert parts.lire == parts.chercher == 0.0


def test_un_devis_se_remplit_ligne_par_ligne() -> None:
    parts = geste({"client": "c-1", "lignes": [{"code": "RAD-01", "quantite": 2}], "objet": "deux mots"})
    pointer = POINTAGE_S + TOUCHE_S
    tapes = len("c-1") + len("RAD-01") + len("2")
    assert parts.agir == pytest.approx(PREPARATION_S + pointer + 3 * pointer + tapes * TOUCHE_S + pointer)
    assert parts.ecrire == pytest.approx(2 / MOTS_ECRITS_PAR_MINUTE * 60)


def test_le_chemin_se_lit_se_balaie_et_le_manuel_ne_compte_que_ses_sections() -> None:
    appels = [
        Appel("lire", {"chemin": MANUEL}, MANUEL_JOUET),
        Appel("lire_courriel", {"identifiant": "m-1"}, "mot " * 238),
        Appel("lire", {"chemin": "clients/liste_clients.md"}, "ligne " * 667),
        Appel("lister", {"dossier": "clients"}, "c-1 c-2"),
        Appel("transferer", {"identifiant": "m-1", "a": ["x@y"]}, "Transféré"),
    ]
    parts = estimer(appels, MANUEL_JOUET, [1])
    manuel = 6 / MOTS_LUS_PAR_MINUTE * 60  # « ## 1. Ranger » puis « un deux trois »
    assert parts.lire == pytest.approx(manuel + 60.0)
    assert parts.chercher == pytest.approx(60.0 + 2 / MOTS_BALAYES_PAR_MINUTE * 60)
    assert parts.agir == pytest.approx(4 * OUVRIR_S + geste({"identifiant": "m-1", "a": ["x@y"]}).agir)
    assert parts.total == pytest.approx(parts.lire + parts.chercher + parts.ecrire + parts.agir)


def test_les_listes_de_domivelle_se_balaient_sans_toucher_a_calorelle() -> None:
    for chemin in (
        "commun/immeubles.md",
        "gerance/n02/registre.yaml",
        "coproprietes/cp10/coproprietaires.csv",
        "proprietaires/liste_nord.csv",
    ):
        assert balaye(chemin), chemin
    assert not balaye("commun/pieces_exigibles.md")
    assert not balaye("coproprietes/cp21/proces_verbal_2026-05-12.md")
    calorelle = dossier_societe()
    touches = [
        str(f.relative_to(etat / "dossiers"))
        for etat in calorelle.glob("v*")
        for f in (etat / "dossiers").rglob("*")
        if f.is_file() and any(f.relative_to(etat / "dossiers").match(m) for m in MOTIFS_BALAYES)
    ]
    assert touches == []


def test_sans_section_utile_le_manuel_ne_coute_rien() -> None:
    assert estimer([Appel("lire", {"chemin": MANUEL}, MANUEL_JOUET)], MANUEL_JOUET, []) == Parts()


def test_un_outil_que_la_grille_ne_classe_pas_est_refuse() -> None:
    with pytest.raises(OutilInconnu, match="effacer_tout"):
        estimer([Appel("effacer_tout", {}, "")], MANUEL_JOUET, [])
