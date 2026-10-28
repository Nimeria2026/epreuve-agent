"""Les textes écrits d'une publication : aucun nombre écrit à la main, chaque nombre renvoie à son
endroit dans donnees.json, et ce qu'ils affirment sans nombre se contrôle sur les données (cadrage de
la page Épreuve d'agent du 2026-10-23, choix P2 ; cadrage du 2026-10-28, figer la publication v1,
section 3 ; JOURNAL, entrée 355)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from ease.textes_publies import (
    ALIAS,
    DOSSIER,
    RENVOI,
    SUPPOSE,
    TextesImpossibles,
    atteindre,
    ecrits_a_la_main,
    en_lettres,
    lire_textes,
    rendre,
    textes_controles,
    valeur,
)

QW, FN = ALIAS["QW"], ALIAS["FN"]
DONNEES: dict[str, Any] = {
    "repetitions": 5,
    "candidats": [{"identifiant": QW, "court": "Qwen 27B"}, {"identifiant": FN, "court": "Flash-Next"}],
    "socle": {
        "taches": 83,
        "par_candidat": {QW: {"cinq_sur_cinq": {"reussis": 61, "pourcent": "73,5"}}},
        "paires": [{"a": QW, "b": FN, "duree_mediane": {"fois": 3, "etabli": True, "devant": QW}}],
    },
    "graves": {
        "categories": [{"cle": "fuite", "taches": 15}],
        "taches_bloquees": [{"tache": "t33_attestation_banque", "par_candidat": {QW: {"avec": 0}}}],
    },
    "tau2": {QW: {"ecart": "-3,2"}, FN: {"publie": None}},
}


def _ecrire(dossier: Path, contenu: str) -> Path:
    (dossier / "constat.yaml").write_text(contenu, encoding="utf-8")
    return dossier


def _feuilles(valeur: object) -> list[str]:
    if isinstance(valeur, dict):
        return [f for sous in cast(dict[str, Any], valeur).values() for f in _feuilles(sous)]
    if isinstance(valeur, list):
        return [f for sous in cast(list[Any], valeur) for f in _feuilles(sous)]
    return [cast(str, valeur)]


def test_un_renvoi_s_ecrit_avec_la_valeur_des_donnees() -> None:
    texte = (
        "{candidats.QW.court} réussit {socle.par_candidat.QW.cinq_sur_cinq.reussis} tâches sur {socle.taches}, "
        "{socle.par_candidat.QW.cinq_sur_cinq.pourcent} %."
    )
    assert rendre(texte, DONNEES) == "Qwen 27B réussit 61 tâches sur 83, 73,5 %."
    # Un moins s'écrit comme sur la page, pas comme un trait d'union.
    assert valeur(DONNEES, "tau2.QW.ecart") == "−3,2"


def test_un_chemin_passe_par_les_cles_les_rangs_les_paires_et_les_comptes() -> None:
    assert atteindre(DONNEES, "graves.categories.fuite.taches") == 15
    assert atteindre(DONNEES, "graves.categories.0.taches") == 15
    assert atteindre(DONNEES, "graves.taches_bloquees.t33_attestation_banque.par_candidat.QW.avec") == 0
    assert atteindre(DONNEES, "socle.paires.QW-FN.duree_mediane.fois") == 3
    assert atteindre(DONNEES, "socle.paires.FN-QW.duree_mediane.fois") == 3
    assert atteindre(DONNEES, "candidats.nombre") == 2
    assert atteindre(DONNEES, "socle.par_candidat.nombre") == 1


def test_un_renvoi_qui_ne_mene_a_rien_est_refuse() -> None:
    for chemin in (
        "socle.tache",
        "socle.paires.QW-QW.duree_mediane",
        "graves.categories.argent.taches",
        "graves.categories.3",
        "socle.taches.nombre",
    ):
        with pytest.raises(TextesImpossibles, match="ne mène à rien"):
            atteindre(DONNEES, chemin)
    # Un vrai, un nombre à virgule flottante ou un dictionnaire ne s'écrivent pas dans une phrase.
    for chemin in ("socle.paires.QW-FN.duree_mediane.etabli", "socle.par_candidat"):
        with pytest.raises(TextesImpossibles, match="un texte ou un entier est attendu"):
            valeur(DONNEES, chemin)


def test_un_entier_s_ecrit_en_lettres_sur_demande() -> None:
    texte = (
        "{socle.paires.QW-FN.duree_mediane.fois:lettres} fois ; {candidats.nombre:Lettres} modèles ; "
        "{graves.taches_bloquees.nombre:lettres_f} tâche ; {graves.taches_bloquees.nombre:lettres} essai"
    )
    assert rendre(texte, DONNEES) == "trois fois ; Deux modèles ; une tâche ; un essai"
    assert en_lettres(0, "lettres") == "zéro"
    assert en_lettres(17, "lettres") == "dix-sept"
    assert en_lettres(1, "Lettres_f") == "Une"
    with pytest.raises(TextesImpossibles, match="au-delà de vingt"):
        en_lettres(21, "lettres")
    with pytest.raises(TextesImpossibles, match="un entier est attendu"):
        rendre("{socle.par_candidat.QW.cinq_sur_cinq.pourcent:lettres}", DONNEES)


def test_un_nombre_ecrit_a_la_main_est_refuse_en_chiffres_comme_en_lettres() -> None:
    assert ecrits_a_la_main("L'agent réussit 61 tâches sur {socle.taches}.") == ["61"]
    assert ecrits_a_la_main("Trois modèles, cinq essais, la moitié des tâches.") == ["Trois", "cinq", "moitié"]
    # « Un » et « une » sont d'abord des articles ; un nombre de méthode se marque hors données.
    hors = '<span class="hors-donnees">95</span> %, une chance sur <span class="hors-donnees">deux</span>'
    assert ecrits_a_la_main(f"Une fourchette à {hors}.") == []
    with pytest.raises(TextesImpossibles, match="nombre écrit à la main : 61"):
        rendre("L'agent réussit 61 tâches sur {socle.taches}.", DONNEES)
    with pytest.raises(TextesImpossibles, match="nombre écrit à la main : trois"):
        rendre("Flash-Next va trois fois plus vite.", DONNEES)


def test_une_supposition_dementie_par_les_donnees_arrete_les_textes(tmp_path: Path) -> None:
    _ecrire(
        tmp_path,
        "titre: Flash-Next va {socle.paires.QW-FN.duree_mediane.fois:lettres} fois plus vite.\n"
        "suppose:\n"
        "  socle.paires.QW-FN.duree_mediane.devant: QW\n"
        "  socle.paires.QW-FN.duree_mediane.etabli: true\n"
        "  tau2.FN.publie: null\n",
    )
    # Les suppositions se contrôlent et ne vont pas dans les textes rendus.
    assert textes_controles("constat", DONNEES, tmp_path) == {"titre": "Flash-Next va trois fois plus vite."}
    _ecrire(
        tmp_path,
        "titre: Flash-Next va plus lentement.\n"
        "suppose:\n"
        "  socle.paires.QW-FN.duree_mediane.devant: FN\n"
        "  socle.paires.QW-FN.duree_mediane.etabli: 1\n"
        "  socle.paires.QW-FN.vitesse: lente\n",
    )
    with pytest.raises(TextesImpossibles) as refus:
        textes_controles("constat", DONNEES, tmp_path)
    message = str(refus.value)
    assert f"{SUPPOSE} socle.paires.QW-FN.duree_mediane.devant = 'FN', les données disent '{QW}'" in message
    # Un vrai n'est pas un : la supposition dit la valeur telle que les données la portent.
    assert "duree_mediane.etabli = 1, les données disent True" in message
    assert "« vitesse » ne mène à rien" in message


def test_tous_les_refus_sont_dits_ensemble(tmp_path: Path) -> None:
    _ecrire(tmp_path, "titre: L'agent réussit 77 tâches.\nconstats:\n- phrase: '{socle.inconnu} tâches.'\n")
    with pytest.raises(TextesImpossibles) as refus:
        textes_controles("constat", DONNEES, tmp_path)
    message = str(refus.value)
    assert "titre : nombre écrit à la main : 77" in message
    assert "constats[0].phrase : {socle.inconnu} : « inconnu » ne mène à rien" in message


def test_les_textes_manquants_ou_mal_formes_sont_refuses(tmp_path: Path) -> None:
    with pytest.raises(TextesImpossibles, match="manque"):
        lire_textes("constat", tmp_path)
    _ecrire(tmp_path, "- une liste\n")
    with pytest.raises(TextesImpossibles, match="dictionnaire"):
        lire_textes("constat", tmp_path)
    _ecrire(tmp_path, "titre: 77\n")
    with pytest.raises(TextesImpossibles, match=r"titre : un texte est attendu"):
        lire_textes("constat", tmp_path)
    for suppose in ("- une liste", "  socle.taches: 8.3"):
        _ecrire(tmp_path, f"titre: un texte\nsuppose:\n{suppose}\n")
        with pytest.raises(TextesImpossibles, match="un chemin par valeur attendue"):
            lire_textes("constat", tmp_path)


def test_les_textes_livres_ne_portent_aucun_nombre_ecrit_a_la_main() -> None:
    # Leurs renvois et leurs suppositions se contrôlent sur les données de la publication, à make publier.
    for sujet in ("constat", "premier_post"):
        textes = lire_textes(sujet, DOSSIER)
        assert textes.pop(SUPPOSE)
        feuilles = _feuilles(textes)
        assert textes["titre"]
        assert [f for f in feuilles if ecrits_a_la_main(f)] == []
        assert all("{" not in RENVOI.sub("", f) for f in feuilles), sujet
