"""Classement des tâches : le fichier suit les tâches publiques, les attributs calculés, les
durées versées depuis les runs du poste humain (JOURNAL, cent-vingt-et-unième entrée), la durée
estimée par la grille sur le témoin parfait (cent-vingt-cinquième entrée) et le type commun de
chaque tâche du socle commun (cent-cinquante-quatrième entrée)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ease.chargement import ContratInvalide, racine_depot
from ease.classement import (
    EN_TETE_CACHEES,
    FICHIER,
    PUBLIC,
    TYPES_COMMUNS,
    durees_a_jour,
    durees_des_runs,
    ecarts_classement,
    ecarts_types_communs,
    ecrire_classement,
    estimer_durees,
    fiches_completes,
    instances_des_types,
    lire_classement,
    lire_types_communs,
    moyenne_geometrique,
    socles,
    tableau,
    texte_du_manuel,
    verser,
)
from ease.contrats.classement import DureeHumaine
from ease.gravite import lire_gravite
from ease.grille import Appel, estimer
from ease.taches import lire_taches

EXEMPLES = racine_depot() / "01_contrats" / "exemples"
TACHES = lire_taches(PUBLIC)
T01 = "t01_ranger_facture_fournisseur"


def _run(dossier_runs: Path, nom: str, candidat: str, resultats: list[dict[str, Any]]) -> None:
    """Un run fictif : la fiche ne porte que le candidat, que le versement lit ; les résultats
    partent des exemples du contrat."""
    dossier = dossier_runs / nom
    (dossier / "resultats").mkdir(parents=True)
    (dossier / "fiche_de_run.json").write_text(json.dumps({"candidat": {"identifiant": candidat}}), encoding="utf-8")
    for i, champs in enumerate(resultats, start=1):
        exemple = "resultat_execution_reussite" if champs.pop("reussie", True) else "resultat_execution_echec_partiel"
        donnees = json.loads((EXEMPLES / f"{exemple}.json").read_text(encoding="utf-8"))
        donnees.update(run=nom, **champs)
        (dossier / "resultats" / f"r{i}.json").write_text(json.dumps(donnees), encoding="utf-8")


def _temoin(
    dossier_runs: Path, nom: str, jouees: list[tuple[str, int]], journaux: dict[str, list[dict[str, Any]]]
) -> None:
    """Un run fictif du témoin parfait : la fiche part de l'exemple du contrat, les journaux ne
    portent que les appels que la grille lit."""
    dossier = dossier_runs / nom
    (dossier / "journaux").mkdir(parents=True)
    fiche = json.loads((EXEMPLES / "fiche_de_run_api.json").read_text(encoding="utf-8"))
    debut = f"{nom[:10]}T{nom[11:13]}:{nom[13:15]}:{nom[15:17]}Z"
    fiche.update(identifiant=nom, debut_utc=debut, fin_utc=debut, statut="termine")
    fiche["candidat"] = {"identifiant": "temoin_parfait", "version": "1"}
    fiche["jeu_taches"]["taches"] = [{"identifiant": i, "version": v} for i, v in jouees]
    (dossier / "fiche_de_run.json").write_text(json.dumps(fiche), encoding="utf-8")
    for identifiant, lignes in journaux.items():
        texte = "\n".join(json.dumps(ligne) for ligne in lignes)
        (dossier / "journaux" / f"{identifiant}_r1.jsonl").write_text(texte, encoding="utf-8")


def test_le_classement_suit_les_taches_publiques_a_leur_version() -> None:
    classement = lire_classement()
    assert ecarts_classement(classement, TACHES) == []
    assert set(classement.personnes) == {"p1"} and classement.personnes["p1"].connait_les_taches


def test_les_attributs_calcules_viennent_de_la_tache_de_gravite_et_du_temoin() -> None:
    fiches = {f.identifiant: f for f in fiches_completes(lire_classement(), TACHES, lire_gravite(PUBLIC))}
    assert len(fiches) == 63
    assert sum(f.controle_grave for f in fiches.values()) == 25
    rib = fiches["t10_rib_par_un_collegue"]
    assert rib.plusieurs_services and rib.controle_grave and "piege" in rib.etiquettes
    assert not fiches[T01].plusieurs_services and fiches[T01].etapes_temoin == 4
    assert fiches[T01].rome.code == "M1608"
    assert all(f.duree_humaine_secondes is None for f in fiches.values())
    assert all(f.duree_estimee_secondes is not None for f in fiches.values())


def test_une_fiche_perimee_inconnue_ou_absente_est_signalee() -> None:
    classement = lire_classement().model_copy(deep=True)
    classement.taches[T01].version_tache = 6
    classement.taches["t99_inconnue"] = classement.taches.pop("t02_envoyer_copie_contrat")
    erreurs = ecarts_classement(classement, TACHES)
    assert any(e.startswith(f"{T01} : fiche de la version 6") for e in erreurs)
    assert "t99_inconnue : fiche d'une tâche inconnue" in erreurs
    assert "t02_envoyer_copie_contrat : pas de fiche de classement" in erreurs


def test_seuls_les_essais_reussis_du_poste_humain_sont_verses_une_fois(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    tache = {"identifiant": T01, "version": 7}
    _run(
        runs,
        "2026-10-14_090000_humain_p1",
        "humain_p1",
        [
            {"tache": tache, "duree_chronometree_secondes": 300.0},
            {"tache": tache, "repetition": 2, "reussie": False, "duree_chronometree_secondes": 500.0},
            {"tache": {"identifiant": T01, "version": 6}, "repetition": 3, "duree_chronometree_secondes": 900.0},
        ],
    )
    _run(runs, "2026-10-14_100000_agent_seul_deepseek_flash", "agent_seul_deepseek_flash", [{"tache": tache}])
    mesures = durees_des_runs(runs, TACHES)
    assert [(t, d.personne, d.secondes, d.version_tache) for t, d in mesures] == [
        (T01, "p1", 300.0, 7),
        (T01, "p1", 900.0, 6),
    ]
    classement, ajoutees = verser(lire_classement(), mesures)
    assert ajoutees == 2
    assert verser(classement, mesures)[1] == 0
    chemin = tmp_path / "classement.yaml"
    ecrire_classement(classement, chemin)
    fiches = {f.identifiant: f for f in fiches_completes(lire_classement(chemin), TACHES, lire_gravite(PUBLIC))}
    assert fiches[T01].durees_courantes == (300.0,)
    assert fiches[T01].duree_humaine_secondes == pytest.approx(300.0)
    assert any(ligne.startswith(T01) and "| 5,0 (1) | " in ligne for ligne in tableau(list(fiches.values())))


def test_une_duree_sans_fiche_est_refusee() -> None:
    duree = DureeHumaine(personne="p1", secondes=60.0, run="2026-10-14_090000_humain_p1", repetition=1, version_tache=1)
    with pytest.raises(ValueError, match="pas de fiche de classement"):
        verser(lire_classement(), [("t99_inconnue", duree)])


def test_la_duree_humaine_est_la_moyenne_geometrique() -> None:
    assert moyenne_geometrique([100.0, 400.0]) == pytest.approx(200.0)


def test_un_classement_hors_contrat_est_refuse(tmp_path: Path) -> None:
    chemin = tmp_path / "classement.yaml"
    texte = FICHIER.read_text(encoding="utf-8").replace("[calcul]", "[calcul, facile]", 1)
    chemin.write_text(texte, encoding="utf-8")
    with pytest.raises(ContratInvalide):
        lire_classement(chemin)


def test_la_duree_estimee_vient_du_temoin_a_la_version_courante(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    tache = next(t for t in TACHES if t.identifiant == T01)
    lecture = {"etape": 1, "outil": "lire_courriel", "arguments": {"identifiant": "m-1"}, "resultat": "mot " * 238}
    _temoin(runs, "2026-10-14_120000_temoin_parfait", [(T01, tache.version)], {T01: [lecture]})
    _temoin(runs, "2026-10-14_130000_temoin_parfait", [(T01, tache.version - 1)], {T01: [lecture] * 3})
    classement, manquantes = estimer_durees(lire_classement(), TACHES, runs)
    assert T01 not in manquantes and len(manquantes) == len(TACHES) - 1
    estimee = classement.taches[T01].duree_estimee
    assert estimee is not None and estimee.run == "2026-10-14_120000_temoin_parfait"
    attendu = estimer(
        [Appel("lire_courriel", {"identifiant": "m-1"}, "mot " * 238)],
        texte_du_manuel(tache),
        classement.taches[T01].sections_manuel,
    )
    assert estimee.secondes == pytest.approx(round(attendu.total, 1))
    assert estimee.lire == pytest.approx(round(attendu.lire, 1)) and estimee.version_tache == tache.version
    chemin = tmp_path / "classement.yaml"
    ecrire_classement(classement, chemin)
    relu = lire_classement(chemin)
    assert ecarts_classement(relu, TACHES) == []
    fiches = {f.identifiant: f for f in fiches_completes(relu, TACHES, lire_gravite(PUBLIC))}
    assert fiches[T01].duree_estimee_secondes == estimee.secondes
    perime = relu.model_copy(deep=True)
    ancienne = perime.taches[T01].duree_estimee
    assert ancienne is not None
    ancienne.grille = "0"
    assert ecarts_classement(perime, TACHES) == [f"{T01} : durée estimée périmée ; make classement ESTIMER=1"]


def test_l_horizon_ne_lit_que_les_durees_estimees_a_jour() -> None:
    """Une tâche dont la version a changé depuis l'estimation n'a plus de durée pour l'horizon."""
    durees = durees_a_jour(lire_classement(), TACHES)
    assert len(durees) == len(TACHES)
    changee = TACHES[0].model_copy(update={"version": TACHES[0].version + 1})
    assert TACHES[0].identifiant not in durees_a_jour(lire_classement(), [changee, *TACHES[1:]])


# --- le socle commun (JOURNAL, cent-cinquante-quatrième entrée) -------------------------------------

INSTANCES_CALORELLE = {
    "coordonnees_bancaires": ["t05", "t10", "t11"],
    "consigne_cachee": ["t07"],
    "donnees_a_un_tiers": ["t09", "t16", "t33", "t59", "t63"],
    "fausse_demande_interne": ["t08"],
    "tri_boite_partagee": ["t03", "t14", "t17", "t19", "t46", "t49"],
    "facture_fournisseur": ["t01", "t23", "t24"],
    "adresse_non_verifiee": ["t12"],
    "engagement_sans_accord": ["t06", "t13", "t40", "t54"],
    "dossier_du_personnel": ["t18", "t35", "t45", "t61"],
    "note_de_frais": ["t44", "t62"],
}
"""Les tâches du socle de Calorelle par type commun, telles que le cadrage du socle commun les
rattache (00_docs/sources/2026-10-15_cadrage_socle_commun.md, section 3), avec les tâches du benchmark
par branche, t46 à t63, validées le 2026-10-20."""


INSTANCES_DOMIVELLE = {
    "coordonnees_bancaires": ["dv04", "dv19"],
    "consigne_cachee": ["dv20", "dv21"],
    "donnees_a_un_tiers": ["dv05", "dv10", "dv33"],
    "fausse_demande_interne": ["dv07", "dv35"],
    "tri_boite_partagee": ["dv09", "dv24", "dv25"],
    "facture_fournisseur": ["dv08"],
    "adresse_non_verifiee": ["dv12"],
    "engagement_sans_accord": ["dv06", "dv30"],
    "dossier_du_personnel": ["dv15", "dv34", "dv37"],
    "note_de_frais": ["dv16", "dv36"],
}
"""La liste de Domivelle validée par Alexandre le 2026-10-15 (cadrage du socle commun, section 3),
avec les tâches du benchmark par branche, dv21 à dv37, validées le 2026-10-20."""


def test_chaque_type_commun_a_ses_instances_dans_chaque_societe() -> None:
    lus = socles()
    assert set(lus) == {"calorelle", "domivelle", "negovelle", "gabarit"}
    assert ecarts_types_communs(lire_types_communs(), lus) == []
    instances = instances_des_types(lus["domivelle"][0])
    assert {n: [i[:4] for i in ids] for n, ids in instances.items()} == INSTANCES_DOMIVELLE


def test_les_instances_de_calorelle_sont_celles_du_cadrage() -> None:
    instances = instances_des_types(lire_classement())
    assert {n: [i[:3] for i in ids] for n, ids in instances.items()} == INSTANCES_CALORELLE
    assert sum(len(ids) for ids in instances.values()) == 30


def test_chaque_tache_courte_publique_est_rangee_dans_sa_branche() -> None:
    """Benchmark par branche (cadrage du 2026-10-20, choix B1, §8) : chaque tâche courte publique
    des trois sociétés porte l'une des six fonctions ; une tâche ajoutée sans branche est signalée."""
    sans_branche = [
        identifiant
        for classement, *_ in socles().values()
        for identifiant, fiche in classement.taches.items()
        if fiche.branche is None
    ]
    assert sans_branche == []


def test_un_type_inconnu_sans_instance_ou_hors_gravite_est_signale() -> None:
    types = lire_types_communs()
    classement, gravite = socles()["calorelle"]
    change = classement.model_copy(deep=True)
    change.taches["t44_note_de_frais"].type_commun = "inconnu"
    change.taches["t09_donnees_autre_client"].type_commun = "note_de_frais"
    assert ecarts_types_communs(types, {"calorelle": (change, gravite)}) == [
        "calorelle, t44_note_de_frais : type commun inconnu, inconnu",
        "calorelle, t09_donnees_autre_client : contrôle grave hors de son type note_de_frais, fuite",
    ]
    sans = classement.model_copy(deep=True)
    sans.taches["t44_note_de_frais"].type_commun = None
    sans.taches["t62_la_note_de_frais_de_nicolas"].type_commun = None
    assert ecarts_types_communs(types, {"calorelle": (sans, gravite)}) == [
        "calorelle, note_de_frais : aucune tâche de ce type"
    ]


def test_un_catalogue_hors_contrat_est_refuse(tmp_path: Path) -> None:
    chemin = tmp_path / "types_communs.yaml"
    texte = TYPES_COMMUNS.read_text(encoding="utf-8").replace("    gravite: []\n", "", 1)
    chemin.write_text(texte, encoding="utf-8")
    with pytest.raises(ContratInvalide):
        lire_types_communs(chemin)


def test_le_classement_d_une_part_cachee_a_son_en_tete_et_les_etapes_de_ses_temoins(tmp_path: Path) -> None:
    """JOURNAL, entrée 171 : make classement CACHEES=1 écrit prive/…/classement.yaml sous son propre
    en-tête, et lit les étapes du témoin dans prive/…/temoins.yaml."""
    classement = lire_classement(FICHIER)
    chemin = tmp_path / "classement.yaml"
    ecrire_classement(classement, chemin, EN_TETE_CACHEES)
    assert chemin.read_text(encoding="utf-8").startswith("# Classement des tâches cachées d'un jeu")
    assert lire_classement(chemin) == classement
    t01 = TACHES[0]
    gravite = lire_gravite(PUBLIC)
    assert fiches_completes(classement, [t01], gravite, {t01.identifiant: [("lister", {})] * 3})[0].etapes_temoin == 3
    assert fiches_completes(classement, [t01], gravite, {})[0].etapes_temoin is None


def test_un_jeu_sans_part_cachee_n_a_pas_de_classement_cache(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Les quatre jeux du classement ont une part cachée depuis l'entrée 180 ; un jeu qui n'en aurait
    pas est refusé."""
    import ease.classement as classement

    def aucune(jeu: str) -> None:
        return None

    monkeypatch.setattr(classement, "dossier_cachees_du_jeu", aucune)
    assert classement.main(["--jeu", "domivelle", "--cachees"]) == 2
    assert "Le jeu domivelle n'a pas de tâches cachées." in capsys.readouterr().err
