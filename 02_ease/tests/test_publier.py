"""make publier : l'officiel d'une publication, écrit par le programme (cadrage du dépôt public et de
l'organisation, section 8)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from ease.chargement import racine_depot
from ease.publier import (
    PublicationImpossible,
    copier_reduit,
    identifiants_publics,
    publier,
    runs_retenus,
    temoins_repris,
    verifier_code,
)
from ease.taches import lire_taches

EXEMPLES = racine_depot() / "01_contrats" / "exemples"
PUBLIQUE = lire_taches(racine_depot() / "07_taches" / "public")[0]
AUTRE = "zz01_tache_non_publiee"


def _git(dossier: Path, *arguments: str) -> None:
    environnement = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", *arguments], cwd=dossier, check=True, capture_output=True, env=environnement)


def _depot(dossier: Path, etiquette: bool = True) -> Path:
    """Un atelier miniature : main, un commit, 99_local ignoré, l'étiquette du protocole."""
    dossier.mkdir(parents=True, exist_ok=True)
    _git(dossier, "init", "-q", "-b", "main")
    _git(dossier, "config", "user.email", "essai@exemple.fr")
    _git(dossier, "config", "user.name", "Essai")
    (dossier / ".gitignore").write_text("99_local/\n", encoding="utf-8")
    (dossier / "code.py").write_text("x = 1\n", encoding="utf-8")
    _git(dossier, "add", ".gitignore", "code.py")
    _git(dossier, "commit", "-q", "-m", "départ")
    if etiquette:
        _git(dossier, "tag", "protocole-v1")
    return dossier


def _run(dossier_runs: Path, nom: str, taches: list[tuple[str, int]], candidat: str = "candidat_fictif") -> Path:
    """Un run fictif : sa fiche, deux essais par tâche, leurs journaux et ceux du candidat."""
    run = dossier_runs / nom
    (run / "resultats").mkdir(parents=True)
    (run / "journaux").mkdir()
    fiche: dict[str, Any] = json.loads((EXEMPLES / "fiche_de_run_api.json").read_text(encoding="utf-8"))
    fiche.update(identifiant=nom, candidat={"identifiant": candidat, "version": "0.1.0"})
    fiche["jeu_taches"]["taches"] = [{"identifiant": t, "version": v} for t, v in taches]
    (run / "fiche_de_run.json").write_text(json.dumps(fiche), encoding="utf-8")
    for tache, version in taches:
        for repetition in (1, 2):
            journal = f"journaux/{tache}_r{repetition}.jsonl"
            resultat = {
                "tache": {"identifiant": tache, "version": version},
                "repetition": repetition,
                "reussie": repetition == 1,
                "journal": journal,
            }
            (run / "resultats" / f"{tache}_r{repetition}.json").write_text(json.dumps(resultat), encoding="utf-8")
            (run / journal).write_text("{}\n", encoding="utf-8")
            (run / "journaux" / f"{tache}_r{repetition}_candidat.log").write_text("bavard\n", encoding="utf-8")
    return run


def test_le_code_publie_est_commite_dans_main_et_porte_une_etiquette_du_protocole(tmp_path: Path) -> None:
    sans = _depot(tmp_path / "sans", etiquette=False)
    with pytest.raises(PublicationImpossible, match="aucune étiquette"):
        verifier_code(sans)
    depot = _depot(tmp_path / "depot")
    commit, etiquette = verifier_code(depot)
    assert (len(commit), etiquette) == (40, "protocole-v1")
    (depot / "code.py").write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(PublicationImpossible, match="non commitée"):
        verifier_code(depot)
    _git(depot, "checkout", "-q", "-b", "essai")
    _git(depot, "commit", "-q", "-am", "hors de main")
    with pytest.raises(PublicationImpossible, match="pas dans main"):
        verifier_code(depot)


def test_un_run_se_publie_reduit_a_ses_taches_publiques(tmp_path: Path) -> None:
    run = _run(tmp_path / "runs", "2026-10-21_120000_candidat_fictif", [(PUBLIQUE.identifiant, 1), (AUTRE, 1)])
    cible = tmp_path / "publie"
    comptes = copier_reduit(run, cible, identifiants_publics())
    assert comptes == {"taches": 1, "essais": 2, "reussis": 1}
    fiche = json.loads((cible / "fiche_de_run.json").read_text(encoding="utf-8"))
    assert [t["identifiant"] for t in fiche["jeu_taches"]["taches"]] == [PUBLIQUE.identifiant]
    publies = sorted(p.relative_to(cible).as_posix() for p in cible.rglob("*") if p.is_file())
    assert publies == [
        "fiche_de_run.json",
        f"journaux/{PUBLIQUE.identifiant}_r1.jsonl",
        f"journaux/{PUBLIQUE.identifiant}_r2.jsonl",
        f"resultats/{PUBLIQUE.identifiant}_r1.json",
        f"resultats/{PUBLIQUE.identifiant}_r2.json",
    ]
    assert not any(AUTRE in (cible / p).read_text(encoding="utf-8") for p in publies)


def test_les_runs_retenus_gardent_leur_role_et_leur_banc() -> None:
    donnees: dict[str, Any] = {
        "socle": {"runs": {"ref_a": ["r1", "r2"]}},
        "horizon": {"runs": {"ref_a": ["r3"]}},
        "graves": {"runs_avec_gardien": {"ref_a": ["r4"]}},
        "tau2": {"ref_a": {"runs": ["t1"]}},
    }
    retenus = runs_retenus(donnees)
    assert {n: (r.banc, sorted(r.roles)) for n, r in retenus.items()} == {
        "r1": ("runs", ["socle"]),
        "r2": ("runs", ["socle"]),
        "r3": ("runs", ["tranche"]),
        "r4": ("runs", ["gardien"]),
        "t1": ("runs_tau2", ["tau2"]),
    }
    with pytest.raises(PublicationImpossible, match="deux références"):
        runs_retenus({"socle": {"runs": {"ref_a": ["r1"], "ref_b": ["r1"]}}})


def test_une_publication_s_ecrit_une_fois_et_jamais_avec_un_temoin_en_ecart(tmp_path: Path) -> None:
    atelier = _depot(tmp_path / "atelier")
    runs = atelier / "99_local" / "runs"
    _run(runs, "2026-10-21_120000_ref_a", [(PUBLIQUE.identifiant, 1), (AUTRE, 1)], "ref_a")
    _run(runs, "2026-10-26_090000_temoin_parfait", [(PUBLIQUE.identifiant, 1)], "temoin_parfait")
    donnees: dict[str, Any] = {"socle": {"runs": {"ref_a": ["2026-10-21_120000_ref_a"]}}}

    def ecart() -> list[tuple[str, str, bool]]:
        return [("2026-10-26_090000_temoin_parfait", "temoin_parfait", False)]

    def conformes() -> list[tuple[str, str, bool]]:
        return [("2026-10-26_090000_temoin_parfait", "temoin_parfait", True)]

    with pytest.raises(PublicationImpossible, match="témoins en écart"):
        publier("constat", "2026-11-02", atelier, atelier, lambda: donnees, ecart)
    assert not (atelier / "08_publications").exists()
    dossier = publier("constat", "2026-11-02", atelier, atelier, lambda: donnees, conformes)
    assert dossier == atelier / "08_publications" / "2026-11-02_constat"
    manifeste = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    assert manifeste["protocole"] == "protocole-v1"
    assert [(r["run"], r["roles"], r["taches_non_publiees"]) for r in manifeste["runs"]] == [
        ("2026-10-21_120000_ref_a", ["socle"], 1),
        ("2026-10-26_090000_temoin_parfait", ["temoin"], 0),
    ]
    cachees = json.loads((dossier / "cachees.json").read_text(encoding="utf-8"))
    assert cachees == [{"run": "2026-10-21_120000_ref_a", "taches": 1, "essais": 2, "reussis": 1}]
    assert json.loads((dossier / "donnees.json").read_text(encoding="utf-8")) == donnees
    assert (dossier / "README.md").is_file()
    assert not (atelier / "99_local" / "publication" / "2026-11-02_constat.en_cours").exists()
    _git(atelier, "add", "08_publications")
    _git(atelier, "commit", "-q", "-m", "la publication")
    with pytest.raises(PublicationImpossible, match="existe déjà"):
        publier("constat", "2026-11-02", atelier, atelier, lambda: donnees, conformes)


def test_les_textes_ecrits_entrent_dans_le_paquet_et_un_texte_refuse_l_arrete(tmp_path: Path) -> None:
    # Cadrage du 2026-10-28, figer la publication v1, section 3 : make publier contrôle les textes
    # sur les données, les met dans le paquet, et le manifeste donne l'empreinte de chaque fichier.
    from ease.textes_publies import TextesImpossibles

    atelier = _depot(tmp_path / "atelier")
    runs = atelier / "99_local" / "runs"
    _run(runs, "2026-10-21_120000_ref_a", [(PUBLIQUE.identifiant, 1)], "ref_a")
    donnees: dict[str, Any] = {"socle": {"runs": {"ref_a": ["2026-10-21_120000_ref_a"]}, "texte": "77 sur 83"}}

    def conformes() -> list[tuple[str, str, bool]]:
        return []

    def faux(_: dict[str, Any]) -> dict[str, Any]:
        raise TextesImpossibles("textes de constat : titre : nombre écrit à la main : 78")

    with pytest.raises(PublicationImpossible, match="textes refusés"):
        publier("constat", "2026-11-03", atelier, atelier, lambda: donnees, conformes, faux)
    assert not (atelier / "08_publications").exists()
    assert not (atelier / "99_local" / "publication" / "2026-11-03_constat.en_cours").exists()
    dossier = publier(
        "constat", "2026-11-03", atelier, atelier, lambda: donnees, conformes, lambda _: {"titre": "77 sur 83"}
    )
    assert json.loads((dossier / "textes.json").read_text(encoding="utf-8")) == {"titre": "77 sur 83"}
    manifeste = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    assert sorted(manifeste["empreintes"]) == ["cachees.json", "donnees.json", "textes.json"]
    assert all(e.startswith("sha256:") for e in manifeste["empreintes"].values())


def test_les_temoins_d_une_publication_se_reprennent_sur_le_meme_code_seulement(tmp_path: Path) -> None:
    # Le jour de la sortie (JOURNAL, entrée 362) : le premier post reprend les témoins du constat,
    # écrit sur le même code ; un code changé entre les deux les fait repasser.
    atelier = _depot(tmp_path / "atelier")
    runs = atelier / "99_local" / "runs"
    _run(runs, "2026-10-21_120000_ref_a", [(PUBLIQUE.identifiant, 1)], "ref_a")
    _run(runs, "2026-10-26_090000_temoin_parfait", [(PUBLIQUE.identifiant, 1)], "temoin_parfait")
    donnees: dict[str, Any] = {"socle": {"runs": {"ref_a": ["2026-10-21_120000_ref_a"]}}}

    def conformes() -> list[tuple[str, str, bool]]:
        return [("2026-10-26_090000_temoin_parfait", "temoin_parfait", True)]

    with pytest.raises(PublicationImpossible, match="aucune publication"):
        temoins_repris(atelier, atelier, "2026-11-02_constat")
    publier("constat", "2026-11-02", atelier, atelier, lambda: donnees, conformes)
    _git(atelier, "add", "08_publications")
    _git(atelier, "commit", "-q", "-m", "le constat")
    (atelier / "JOURNAL_PUBLIC.md").write_text("entrée 3\n", encoding="utf-8")
    _git(atelier, "add", "JOURNAL_PUBLIC.md")
    _git(atelier, "commit", "-q", "-m", "le journal public")
    repris = temoins_repris(atelier, atelier, "2026-11-02_constat")
    assert repris == [("2026-10-26_090000_temoin_parfait", "temoin_parfait", True)]
    dossier = publier(
        "constat", "2026-11-03", atelier, atelier, lambda: donnees, lambda: repris, None, "2026-11-02_constat"
    )
    manifeste = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    assert manifeste["temoins_repris_de"] == "2026-11-02_constat"
    assert [r["roles"] for r in manifeste["runs"]] == [["socle"], ["temoin"]]
    _git(atelier, "add", "08_publications")
    _git(atelier, "commit", "-q", "-m", "la seconde publication")
    (atelier / "code.py").write_text("x = 2\n", encoding="utf-8")
    _git(atelier, "commit", "-q", "-am", "le code change")
    with pytest.raises(PublicationImpossible, match="le code a changé depuis 2026-11-02_constat"):
        temoins_repris(atelier, atelier, "2026-11-02_constat")
