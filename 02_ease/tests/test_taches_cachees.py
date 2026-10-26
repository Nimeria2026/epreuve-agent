"""Les tâches cachées (ease.cachees ; JOURNAL, entrées 80 et 95). D'abord la forme de leurs
fichiers, sur un exemple écrit ici ; puis, s'il y en a dans 07_taches/prive/, les vraies, par les
tests seuls ; puis de même la part cachée de la tranche dure, dans 07_taches/prive/dure/ (entrée
171), et celles de Domivelle et de Négovelle (entrées 180 et 202). Les messages d'échec de ces
derniers tests ne citent que des identifiants : rien du contenu des tâches cachées ne doit remonter
dans la séance qui les lance."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest
from ease import pme
from ease.cachees import (
    cachees_du_jeu,
    dossier_cachees_du_jeu,
    dossier_prive_dure,
    taches_cachees,
    taches_cachees_dure,
    temoins_caches,
)
from ease.chargement import racine_depot
from ease.classement import ecarts_classement, lire_classement
from ease.contrats.tache import JugeRequis, Tache
from ease.gravite import Gravite, ecarts, lire_gravite, numeros_graves
from ease.pme import REGLES_GARDIEN, dossier_complement, dossier_version, etat_des_taches, regles_gardien
from ease.rapport import notes_de_l_inaction
from ease.taches import (
    budget_etapes,
    coherence_pme,
    dossier_domivelle,
    dossier_du_jeu,
    dossier_dure,
    lire_taches,
    societe_de,
    societe_des_taches,
    taches_domivelle,
    taches_domivelle_dure,
    taches_du_jeu,
    taches_dure,
    taches_negovelle,
    taches_negovelle_dure,
)
from ease.temoins import (
    TemoinInerte,
    TemoinParfait,
    TemoinToujoursFaux,
    Terrain,
    ce_que_le_temoin_n_a_pas_vu,
    passer,
    terrain_cachees,
    terrain_domivelle_cachees,
    terrain_domivelle_dure_cachees,
    terrain_dure_cachees,
    terrain_negovelle_cachees,
    terrain_negovelle_dure_cachees,
)

PUBLIQUES = racine_depot() / "07_taches" / "public"
CACHEES = taches_cachees()
pas_de_cachees = pytest.mark.skipif(not CACHEES, reason="aucune tâche cachée dans 07_taches/prive/")
CACHEES_DURE = taches_cachees_dure()
pas_de_cachees_dure = pytest.mark.skipif(not CACHEES_DURE, reason="aucune tâche cachée dans 07_taches/prive/dure/")


def _prive(racine: Path) -> Path:
    """Un 07_taches/prive/ d'exemple : une tâche, son complément, ses témoins."""
    prive = racine / "07_taches" / "prive"
    (prive / "complements" / "c01_essai" / "dossiers").mkdir(parents=True)
    source = (PUBLIQUES / "t01_ranger_facture_fournisseur.yaml").read_text(encoding="utf-8")
    texte = source.replace("identifiant: t01_ranger_facture_fournisseur", "identifiant: c01_essai")
    (prive / "c01_essai.yaml").write_text(texte, encoding="utf-8")
    (prive / "temoins.yaml").write_text(
        "c01_essai:\n  solution: [[lister, {}], [lire, {chemin: commun/manuel_procedures.md}]]\n  erreur: []\n",
        encoding="utf-8",
    )
    return prive


def test_les_fichiers_caches_se_lisent_au_meme_contrat_que_les_publics(tmp_path: Path) -> None:
    prive = _prive(tmp_path)
    assert [t.identifiant for t in taches_cachees(prive)] == ["c01_essai"]
    solutions, erreurs = temoins_caches(prive)
    assert solutions == {"c01_essai": [("lister", {}), ("lire", {"chemin": "commun/manuel_procedures.md"})]}
    assert erreurs == {"c01_essai": []}
    assert taches_cachees(tmp_path / "absent") == []
    assert temoins_caches(tmp_path / "absent") == ({}, {})


def test_un_temoin_mal_forme_est_refuse(tmp_path: Path) -> None:
    prive = _prive(tmp_path)
    (prive / "temoins.yaml").write_text("c01_essai:\n  solution: [[lister]]\n  erreur: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="geste 1 : \\[outil, arguments\\] attendu"):
        temoins_caches(prive)


def test_un_complement_cache_se_trouve_apres_ceux_des_taches_publiques(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prive(tmp_path)
    monkeypatch.setattr(pme, "racine_depot", lambda: tmp_path)
    assert dossier_complement("c01_essai") == tmp_path / "07_taches" / "prive" / "complements" / "c01_essai"
    with pytest.raises(FileNotFoundError, match="complément d'état introuvable : c99_absent"):
        dossier_complement("c99_absent")


# --- les vraies tâches cachées, s'il y en a ------------------------------------------------------


@pas_de_cachees
def test_les_taches_cachees_sont_coherentes_sans_juge_et_d_un_seul_etat() -> None:
    ecarts = [t.identifiant for t in CACHEES if coherence_pme(t)]
    assert not ecarts, f"incohérentes avec la PME : {ecarts}"
    avec_juge = [
        t.identifiant for t in CACHEES if any(isinstance(v, JugeRequis) for c in t.controles for v in c.verification)
    ]
    assert not avec_juge, f"vérification juge_requis interdite : {avec_juge}"
    assert all(re.fullmatch(r"c\d{2}_[a-z0-9_]+", t.identifiant) for t in CACHEES)
    etat_des_taches(CACHEES)


@pas_de_cachees
def test_aucun_enonce_cache_ne_repete_un_autre_enonce() -> None:
    enonces = [t.enonce for t in lire_taches(PUBLIQUES)] + [t.enonce for t in CACHEES]
    assert len(enonces) == len(set(enonces)), "deux énoncés identiques : un témoin ne retrouverait pas sa tâche"


def _complements_non_fictifs(taches: list[Tache]) -> list[str]:
    """Les tâches dont un fichier de complément propre manque la mention FICTIF ou cite une adresse
    réelle ; leurs identifiants seuls."""
    adresse = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
    telephone = re.compile(r"\b0\d(?: \d\d){4}\b")
    fautifs: list[str] = []
    for t in taches:
        if t.complement is None:
            continue
        racine = dossier_complement(t.complement, societe_de(t))
        etat = dossier_version(t.etat_initial, societe_de(t))
        for fichier in (f for f in racine.rglob("*") if f.is_file()):
            relatif = fichier.relative_to(racine)
            if (etat / relatif).exists():
                continue  # copie d'un fichier de l'état, contrôlée avec lui
            contenu = fichier.read_bytes()
            texte = contenu.decode("utf-8", errors="ignore")
            if societe_de(t) in {"domivelle", "negovelle"}:
                # La règle des états de Domivelle et de Négovelle (test_domivelle_v1,
                # test_negovelle_v1) : la mention dans les PDF ; dans les textes, des numéros et des
                # IBAN fictifs. Leurs courriels ne portent pas la mention, pas plus que ceux des
                # compléments publics.
                fictif = (
                    b"FICTIF" in contenu
                    if fichier.suffix == ".pdf"
                    else all(n.startswith(("02 61 91", "06 39 98")) for n in telephone.findall(texte))
                    and all(i.startswith("FR76 9999 9") for i in re.findall(r"FR76 \d{4} \d", texte))
                )
            else:
                # Les fiches des logiciels (facturation, planning) suivent leur contrat, sans place
                # pour la mention : comme pour les compléments publics (test_complements).
                fictif = b"FICTIF" in contenu or relatif.parts[0] in {"facturation", "planning"}
            if not fictif or not all(d.endswith(".example") for d in adresse.findall(texte)):
                fautifs.append(t.identifiant)
    return sorted(set(fautifs))


@pas_de_cachees
def test_chaque_tache_cachee_a_ses_temoins_et_ses_complements_sont_fictifs() -> None:
    solutions, erreurs = temoins_caches()
    sans = [t.identifiant for t in CACHEES if t.identifiant not in solutions or t.identifiant not in erreurs]
    assert not sans, f"sans témoins : {sans}"
    fautifs = _complements_non_fictifs(CACHEES)
    assert not fautifs, f"complément sans mention FICTIF ou avec une adresse réelle : {fautifs}"


@pas_de_cachees
def test_chaque_budget_cache_suit_la_regle_du_temoin() -> None:
    solutions, _ = temoins_caches()
    ecarts = [
        t.identifiant
        for t in CACHEES
        if t.identifiant in solutions and t.budget.etapes_max != budget_etapes(len(solutions[t.identifiant]))
    ]
    assert not ecarts, f"budget hors de la règle (ease.taches.budget_etapes) : {ecarts}"


@pas_de_cachees
def test_chaque_temoin_cache_ne_se_sert_que_de_ce_qu_il_a_vu(tmp_path: Path) -> None:
    """La règle des témoins publics (test_temoins_lisent, JOURNAL, entrée 100). Le message ne cite
    que les identifiants des tâches en défaut."""
    solutions, _ = temoins_caches()
    ecarts = [
        t.identifiant
        for t in CACHEES
        if t.identifiant in solutions
        and ce_que_le_temoin_n_a_pas_vu(t, solutions[t.identifiant], tmp_path / t.identifiant)
    ]
    assert not ecarts, f"témoins qui se servent de ce qu'ils n'ont pas vu : {ecarts}"


@pas_de_cachees
def test_les_temoins_obtiennent_leurs_taux_sur_les_taches_cachees(tmp_path: Path) -> None:
    terrain = terrain_cachees(tmp_path / "pme", version=etat_des_taches(CACHEES))
    _, parfait = passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1)
    assert (parfait.reussites, parfait.erreurs_techniques) == (len(CACHEES), 0), "le parfait échoue sur une tâche"
    for temoin in (TemoinToujoursFaux(terrain), TemoinInerte(terrain)):
        _, resume = passer(temoin, tmp_path / "runs", repetitions=1)
        assert resume.reussites == 0, f"{temoin.identifiant} réussit une tâche cachée"


@pas_de_cachees
def test_le_marquage_des_controles_graves_caches_colle_et_l_inaction_le_tient() -> None:
    """prive/gravite.yaml, s'il existe (JOURNAL, entrée 102) : chaque étape marquée existe dans sa
    tâche et chaque contrôle grave tient sous l'inaction. Les messages ne citent que des identifiants."""
    gravite = lire_gravite()
    incoherentes = sorted({e.split(" ")[0].rstrip(":,") for e in ecarts(gravite, lire_taches(PUBLIQUES) + CACHEES)})
    assert not incoherentes, f"marquage de gravité incohérent : {incoherentes}"
    exposees = [t for t in CACHEES if numeros_graves(t, gravite)]
    notes = notes_de_l_inaction(exposees)
    non_tenues = [
        t.identifiant for t in exposees if any(notes[t.identifiant][n - 1][0] < 1 for n in numeros_graves(t, gravite))
    ]
    assert not non_tenues, f"contrôle grave que l'inaction ne tient pas : {non_tenues}"


@pytest.mark.skipif(bool(CACHEES), reason="il y a des tâches cachées")
def test_un_terrain_cache_vide_demande_par_son_nom_compte_comme_un_ecart(capsys: pytest.CaptureFixture[str]) -> None:
    from ease.temoins import main

    assert main(["pme_cachees"]) == 1
    assert "Terrain pme_cachees : aucune tâche." in capsys.readouterr().out


# --- la part cachée de la tranche dure (07_taches/prive/dure/, JOURNAL, entrée 171) ---------------


def _prive_dure(racine: Path) -> Path:
    """Un 07_taches/prive/dure/ d'exemple : la première tâche de la tranche, renommée, et ses témoins."""
    dure = racine / "07_taches" / "prive" / "dure"
    dure.mkdir(parents=True)
    source = sorted(dossier_dure().glob("h01_*.yaml"))[0]
    texte = source.read_text(encoding="utf-8").replace(f"identifiant: {source.stem}", "identifiant: hc01_essai")
    (dure / "hc01_essai.yaml").write_text(texte, encoding="utf-8")
    (dure / "temoins.yaml").write_text("hc01_essai:\n  solution: [[lister, {}]]\n  erreur: []\n", encoding="utf-8")
    return dure


def test_la_part_cachee_de_la_tranche_se_range_a_part_dans_prive_dure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ease.cachees as cachees

    monkeypatch.setattr(cachees, "racine_depot", lambda: tmp_path)
    _prive(tmp_path)
    dure = _prive_dure(tmp_path)
    assert dossier_prive_dure() == dossier_cachees_du_jeu("dure") == dure
    assert [t.identifiant for t in cachees_du_jeu("dure")] == ["hc01_essai"]
    assert [t.identifiant for t in cachees_du_jeu("public")] == ["c01_essai"]
    assert temoins_caches(dure) == ({"hc01_essai": [("lister", {})]}, {"hc01_essai": []})
    assert dossier_cachees_du_jeu("documents") is None and cachees_du_jeu("documents") == []


@pas_de_cachees_dure
def test_la_part_cachee_de_la_tranche_tient_a_la_pme_sans_juge_dans_l_etat_de_la_tranche() -> None:
    incoherentes = [t.identifiant for t in CACHEES_DURE if coherence_pme(t)]
    assert not incoherentes, f"incohérentes avec la PME : {incoherentes}"
    avec_juge = [
        t.identifiant
        for t in CACHEES_DURE
        if any(isinstance(v, JugeRequis) for c in t.controles for v in c.verification)
    ]
    assert not avec_juge, f"vérification juge_requis interdite : {avec_juge}"
    hors_motif = [t.identifiant for t in CACHEES_DURE if not re.fullmatch(r"hc\d{2}_[a-z0-9_]+", t.identifiant)]
    assert not hors_motif, f"identifiant hors du motif hcNN_nom : {hors_motif}"
    # Un run de la tranche ne mélange ni deux états ni deux sociétés : ses cachées partent du même.
    assert etat_des_taches(CACHEES_DURE) == etat_des_taches(taches_dure())
    assert societe_des_taches(CACHEES_DURE) == societe_des_taches(taches_dure())


@pas_de_cachees_dure
def test_aucun_enonce_cache_de_la_tranche_ne_repete_un_autre_enonce() -> None:
    enonces = [t.enonce for t in [*lire_taches(PUBLIQUES), *taches_dure(), *CACHEES, *CACHEES_DURE]]
    assert len(enonces) == len(set(enonces)), "deux énoncés identiques : un témoin ne retrouverait pas sa tâche"


@pas_de_cachees_dure
def test_chaque_tache_cachee_de_la_tranche_a_ses_temoins_son_budget_et_des_complements_fictifs(
    tmp_path: Path,
) -> None:
    solutions, erreurs = temoins_caches(dossier_prive_dure())
    sans = [t.identifiant for t in CACHEES_DURE if t.identifiant not in solutions or t.identifiant not in erreurs]
    assert not sans, f"sans témoins : {sans}"
    hors_budget = [
        t.identifiant for t in CACHEES_DURE if t.budget.etapes_max != budget_etapes(len(solutions[t.identifiant]))
    ]
    assert not hors_budget, f"budget hors de la règle (ease.taches.budget_etapes) : {hors_budget}"
    pas_vu = [
        t.identifiant
        for t in CACHEES_DURE
        if ce_que_le_temoin_n_a_pas_vu(t, solutions[t.identifiant], tmp_path / t.identifiant)
    ]
    assert not pas_vu, f"témoins qui se servent de ce qu'ils n'ont pas vu : {pas_vu}"
    fautifs = _complements_non_fictifs(CACHEES_DURE)
    assert not fautifs, f"complément sans mention FICTIF ou avec une adresse réelle : {fautifs}"


@pas_de_cachees_dure
def test_les_temoins_obtiennent_leurs_taux_sur_la_part_cachee_de_la_tranche(tmp_path: Path) -> None:
    terrain = terrain_dure_cachees(tmp_path / "pme", version=etat_des_taches(CACHEES_DURE))
    _, parfait = passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1)
    assert (parfait.reussites, parfait.erreurs_techniques) == (len(CACHEES_DURE), 0), "le parfait échoue sur une tâche"
    for temoin in (TemoinToujoursFaux(terrain), TemoinInerte(terrain)):
        _, resume = passer(temoin, tmp_path / "runs", repetitions=1)
        assert resume.reussites == 0, f"{temoin.identifiant} réussit une tâche cachée"


@pas_de_cachees_dure
def test_la_part_cachee_de_la_tranche_a_son_classement_avec_ses_durees_a_jour() -> None:
    """Le rapport de la tranche place ces tâches dans la courbe de l'horizon : chacune a sa fiche,
    à sa version, avec sa durée de la grille à jour (make classement JEU=dure CACHEES=1 ESTIMER=1)."""
    chemin = dossier_prive_dure() / "classement.yaml"
    assert chemin.is_file(), "07_taches/prive/dure/classement.yaml manque"
    classement = lire_classement(chemin)
    a_reprendre = sorted({e.split(" ")[0] for e in ecarts_classement(classement, CACHEES_DURE)})
    assert not a_reprendre, f"classement à reprendre : {a_reprendre}"
    sans_duree = [t.identifiant for t in CACHEES_DURE if classement.taches[t.identifiant].duree_estimee is None]
    assert not sans_duree, f"sans durée de la grille : {sans_duree}"


@pas_de_cachees_dure
def test_le_marquage_grave_de_la_tranche_cachee_colle_et_l_inaction_le_tient() -> None:
    """prive/dure/gravite.yaml, s'il existe : comme pour les cachées du socle."""
    gravite = lire_gravite(PUBLIQUES, dossier_dure(), dossier_prive_dure())
    publiques = {t.identifiant for t in [*lire_taches(PUBLIQUES), *taches_dure()]}
    part = Gravite(gravite.version, gravite.categories, {k: v for k, v in gravite.graves.items() if k not in publiques})
    incoherentes = sorted({e.split(" ")[0].rstrip(":,") for e in ecarts(part, CACHEES_DURE)})
    assert not incoherentes, f"marquage de gravité incohérent : {incoherentes}"
    exposees = [t for t in CACHEES_DURE if numeros_graves(t, part)]
    notes = notes_de_l_inaction(exposees)
    non_tenues = [
        t.identifiant for t in exposees if any(notes[t.identifiant][n - 1][0] < 1 for n in numeros_graves(t, part))
    ]
    assert not non_tenues, f"contrôle grave que l'inaction ne tient pas : {non_tenues}"


@pytest.mark.skipif(bool(CACHEES_DURE), reason="la tranche a des tâches cachées")
def test_une_part_cachee_vide_de_la_tranche_demandee_par_son_nom_compte_comme_un_ecart(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ease.temoins import main

    assert main(["dure_cachees"]) == 1
    assert "Terrain dure_cachees : aucune tâche." in capsys.readouterr().out


# --- les cachées derrière le gardien courant (v2, JOURNAL, entrée 176) ------------------------------

REFUS_CONNUS_CACHES: dict[str, Counter[str]] = {
    # Une tâche de la part cachée de la tranche écrit à un domaine inconnu de Calorelle, comme t33 :
    # destinataires_connus, règle de la v1, la bloque à tort.
    "tranche": Counter({"destinataires_connus": 1}),
}
"""Les blocages à tort du témoin parfait sur les cachées, comptés par règle sans nommer les tâches."""


@pytest.mark.parametrize("part", ["socle", "tranche"])
def test_le_temoin_parfait_passe_le_gardien_sur_les_cachees_sans_autre_refus_que_les_connus(
    part: str, tmp_path: Path
) -> None:
    """Le message ne donne que des règles et des nombres, jamais une tâche."""
    taches = CACHEES if part == "socle" else CACHEES_DURE
    if not taches:
        pytest.skip(f"aucune tâche cachée pour la part {part}")
    fabrique = terrain_cachees if part == "socle" else terrain_dure_cachees
    terrain = fabrique(tmp_path / "pme", version=etat_des_taches(taches), gardien=REGLES_GARDIEN)
    passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1)
    lignes = [json.loads(ligne) for ligne in (tmp_path / "pme_gardien.jsonl").read_text("utf-8").splitlines()]
    refus = Counter(str(ligne.get("regle")) for ligne in lignes if ligne["verdict"] == "bloque")
    assert refus == REFUS_CONNUS_CACHES.get(part, Counter()), f"refus du gardien par règle : {dict(refus)}"
    refusees = sum(1 for ligne in lignes if ligne["verdict"] == "validation" and ligne.get("reponse") != "accepter")
    assert refusees == 0, f"validations refusées : {refusees}"


# --- les parts cachées de Domivelle et de Négovelle (prive/domivelle/, prive/negovelle/) ---------
# JOURNAL, entrées 180 et 202.

PARTS_SOCIETES: dict[str, tuple[str, str, Callable[..., Terrain]]] = {
    "domivelle": ("domivelle", r"dvc\d{2}_[a-z0-9_]+", terrain_domivelle_cachees),
    "domivelle_dure": ("domivelle", r"dvhc\d{2}_[a-z0-9_]+", terrain_domivelle_dure_cachees),
    "negovelle": ("negovelle", r"ngc\d{2}_[a-z0-9_]+", terrain_negovelle_cachees),
    "negovelle_dure": ("negovelle", r"nghc\d{2}_[a-z0-9_]+", terrain_negovelle_dure_cachees),
}
"""Les parts cachées de Domivelle et de Négovelle : leur société, le motif de leurs identifiants et
la fabrique de leur terrain."""


def test_les_parts_cachees_de_domivelle_se_rangent_dans_prive_domivelle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ease.cachees as cachees

    monkeypatch.setattr(cachees, "racine_depot", lambda: tmp_path)
    _prive(tmp_path)
    prive = tmp_path / "07_taches" / "prive"
    for jeu, dossier, nom, motif in (
        ("domivelle", prive / "domivelle", "dvc01_essai", "dv01_*.yaml"),
        ("domivelle_dure", prive / "domivelle" / "dure", "dvhc01_essai", "dure/dvh01_*.yaml"),
    ):
        chemin = sorted(dossier_domivelle().glob(motif))[0]
        dossier.mkdir(parents=True, exist_ok=True)
        texte = chemin.read_text(encoding="utf-8").replace(f"identifiant: {chemin.stem}", f"identifiant: {nom}")
        (dossier / f"{nom}.yaml").write_text(texte, encoding="utf-8")
        assert dossier_cachees_du_jeu(jeu) == dossier
        assert [t.identifiant for t in cachees_du_jeu(jeu)] == [nom]
    # Les parts de Calorelle ne voient pas celles de Domivelle, ni l'inverse.
    assert [t.identifiant for t in cachees_du_jeu("public")] == ["c01_essai"]
    assert cachees_du_jeu("dure") == []


def test_les_parts_cachees_de_negovelle_se_rangent_dans_prive_negovelle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ease.cachees as cachees

    monkeypatch.setattr(cachees, "racine_depot", lambda: tmp_path)
    _prive(tmp_path)
    prive = tmp_path / "07_taches" / "prive"
    publiques = PUBLIQUES / "negovelle"
    for jeu, dossier, nom, motif in (
        ("negovelle", prive / "negovelle", "ngc01_essai", "ng01_*.yaml"),
        ("negovelle_dure", prive / "negovelle" / "dure", "nghc01_essai", "dure/ngh01_*.yaml"),
    ):
        chemin = sorted(publiques.glob(motif))[0]
        dossier.mkdir(parents=True, exist_ok=True)
        texte = chemin.read_text(encoding="utf-8").replace(f"identifiant: {chemin.stem}", f"identifiant: {nom}")
        (dossier / f"{nom}.yaml").write_text(texte, encoding="utf-8")
        assert dossier_cachees_du_jeu(jeu) == dossier
        assert [t.identifiant for t in cachees_du_jeu(jeu)] == [nom]
    # Le motif du socle ne prend pas la tranche, ni les parts des autres sociétés.
    assert [t.identifiant for t in cachees_du_jeu("public")] == ["c01_essai"]
    assert cachees_du_jeu("domivelle") == [] and cachees_du_jeu("dure") == []


def _part(jeu: str) -> list[Tache]:
    return cachees_du_jeu(jeu)


@pytest.mark.parametrize("jeu", list(PARTS_SOCIETES))
def test_chaque_part_cachee_tient_a_la_pme_sans_juge_dans_l_etat_de_ses_publiques(jeu: str) -> None:
    taches = _part(jeu)
    if not taches:
        pytest.skip(f"aucune tâche cachée pour {jeu}")
    societe, motif, _ = PARTS_SOCIETES[jeu]
    incoherentes = [t.identifiant for t in taches if coherence_pme(t)]
    assert not incoherentes, f"incohérentes avec la PME : {incoherentes}"
    avec_juge = [
        t.identifiant for t in taches if any(isinstance(v, JugeRequis) for c in t.controles for v in c.verification)
    ]
    assert not avec_juge, f"vérification juge_requis interdite : {avec_juge}"
    hors_motif = [t.identifiant for t in taches if not re.fullmatch(motif, t.identifiant)]
    assert not hors_motif, f"identifiant hors du motif de la part : {hors_motif}"
    assert etat_des_taches(taches) == etat_des_taches(taches_du_jeu(jeu))
    assert societe_des_taches(taches) == societe_des_taches(taches_du_jeu(jeu)) == societe


def test_aucun_enonce_cache_des_autres_societes_ne_repete_un_autre_enonce() -> None:
    cachees = [t for jeu in PARTS_SOCIETES for t in _part(jeu)]
    if not cachees:
        pytest.skip("aucune tâche cachée de Domivelle ni de Négovelle")
    autres = [
        *lire_taches(PUBLIQUES),
        *taches_dure(),
        *taches_domivelle(),
        *taches_domivelle_dure(),
        *taches_negovelle(),
        *taches_negovelle_dure(),
    ]
    # Chaque énoncé caché, unique parmi tous ; deux publiques de jeux différents peuvent se répéter,
    # un terrain ne les réunit pas (dv07 et dvh06, dv19 et dvh02).
    comptes = Counter(t.enonce for t in [*autres, *CACHEES, *CACHEES_DURE, *cachees])
    repetes = [t.identifiant for t in cachees if comptes[t.enonce] > 1]
    assert not repetes, f"énoncé répété ailleurs, un témoin ne retrouverait pas sa tâche : {repetes}"


@pytest.mark.parametrize("jeu", list(PARTS_SOCIETES))
def test_chaque_tache_cachee_a_ses_temoins_son_budget_et_des_complements_fictifs(jeu: str, tmp_path: Path) -> None:
    taches = _part(jeu)
    if not taches:
        pytest.skip(f"aucune tâche cachée pour {jeu}")
    solutions, erreurs = temoins_caches(dossier_cachees_du_jeu(jeu))
    sans = [t.identifiant for t in taches if t.identifiant not in solutions or t.identifiant not in erreurs]
    assert not sans, f"sans témoins : {sans}"
    hors_budget = [t.identifiant for t in taches if t.budget.etapes_max != budget_etapes(len(solutions[t.identifiant]))]
    assert not hors_budget, f"budget hors de la règle (ease.taches.budget_etapes) : {hors_budget}"
    pas_vu = [
        t.identifiant
        for t in taches
        if ce_que_le_temoin_n_a_pas_vu(t, solutions[t.identifiant], tmp_path / t.identifiant)
    ]
    assert not pas_vu, f"témoins qui se servent de ce qu'ils n'ont pas vu : {pas_vu}"
    fautifs = _complements_non_fictifs(taches)
    assert not fautifs, f"complément sans mention FICTIF ou avec une adresse réelle : {fautifs}"


@pytest.mark.parametrize("jeu", list(PARTS_SOCIETES))
def test_les_temoins_obtiennent_leurs_taux_sur_les_parts_cachees(jeu: str, tmp_path: Path) -> None:
    taches = _part(jeu)
    if not taches:
        pytest.skip(f"aucune tâche cachée pour {jeu}")
    terrain = PARTS_SOCIETES[jeu][2](tmp_path / "pme", version=etat_des_taches(taches))
    _, parfait = passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1)
    assert (parfait.reussites, parfait.erreurs_techniques) == (len(taches), 0), "le parfait échoue sur une tâche"
    for temoin in (TemoinToujoursFaux(terrain), TemoinInerte(terrain)):
        _, resume = passer(temoin, tmp_path / "runs", repetitions=1)
        assert resume.reussites == 0, f"{temoin.identifiant} réussit une tâche cachée"


@pytest.mark.parametrize("jeu", list(PARTS_SOCIETES))
def test_le_marquage_grave_des_parts_cachees_colle_et_l_inaction_le_tient(jeu: str) -> None:
    taches = _part(jeu)
    if not taches:
        pytest.skip(f"aucune tâche cachée pour {jeu}")
    cache = dossier_cachees_du_jeu(jeu)
    assert cache is not None
    gravite = lire_gravite(PUBLIQUES, dossier_du_jeu(jeu), cache)
    publiques = {t.identifiant for t in [*lire_taches(PUBLIQUES), *taches_du_jeu(jeu)]}
    part = Gravite(gravite.version, gravite.categories, {k: v for k, v in gravite.graves.items() if k not in publiques})
    incoherentes = sorted({e.split(" ")[0].rstrip(":,") for e in ecarts(part, taches)})
    assert not incoherentes, f"marquage de gravité incohérent : {incoherentes}"
    exposees = [t for t in taches if numeros_graves(t, part)]
    notes = notes_de_l_inaction(exposees)
    non_tenues = [
        t.identifiant for t in exposees if any(notes[t.identifiant][n - 1][0] < 1 for n in numeros_graves(t, part))
    ]
    assert not non_tenues, f"contrôle grave que l'inaction ne tient pas : {non_tenues}"


@pytest.mark.parametrize("jeu", [j for j in PARTS_SOCIETES if j.endswith("_dure")])
def test_la_part_cachee_d_une_tranche_longue_a_son_classement_avec_ses_durees_a_jour(jeu: str) -> None:
    """Le rapport de la tranche longue place ces tâches dans la courbe de l'horizon
    (make classement JEU=<jeu> CACHEES=1 ESTIMER=1)."""
    taches = _part(jeu)
    if not taches:
        pytest.skip(f"aucune tâche cachée pour {jeu}")
    cache = dossier_cachees_du_jeu(jeu)
    assert cache is not None
    chemin = cache / "classement.yaml"
    assert chemin.is_file(), f"le classement de la part cachée de {jeu} manque"
    classement = lire_classement(chemin)
    a_reprendre = sorted({e.split(" ")[0] for e in ecarts_classement(classement, taches)})
    assert not a_reprendre, f"classement à reprendre : {a_reprendre}"
    sans_duree = [t.identifiant for t in taches if classement.taches[t.identifiant].duree_estimee is None]
    assert not sans_duree, f"sans durée de la grille : {sans_duree}"


@pytest.mark.parametrize("jeu", list(PARTS_SOCIETES))
def test_le_temoin_parfait_passe_le_gardien_de_sa_societe_sur_ses_cachees_sans_refus(jeu: str, tmp_path: Path) -> None:
    """Le message ne donne que des règles et des nombres, jamais une tâche."""
    taches = _part(jeu)
    if not taches:
        pytest.skip(f"aucune tâche cachée pour {jeu}")
    societe, _, fabrique = PARTS_SOCIETES[jeu]
    terrain = fabrique(tmp_path / "pme", version=etat_des_taches(taches), gardien=regles_gardien(societe))
    passer(TemoinParfait(terrain), tmp_path / "runs", repetitions=1)
    lignes = [json.loads(ligne) for ligne in (tmp_path / "pme_gardien.jsonl").read_text("utf-8").splitlines()]
    refus = Counter(str(ligne.get("regle")) for ligne in lignes if ligne["verdict"] == "bloque")
    assert refus == Counter(), f"refus du gardien par règle : {dict(refus)}"
    refusees = sum(1 for ligne in lignes if ligne["verdict"] == "validation" and ligne.get("reponse") != "accepter")
    assert refusees == 0, f"validations refusées : {refusees}"
