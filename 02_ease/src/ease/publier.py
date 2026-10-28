"""L'officiel d'une publication, dans 08_publications/<date>_<sujet>/ (cadrage du dépôt public et de
l'organisation, section 8 ; JOURNAL, entrée 284).

    make publier SUJET=constat [DATE=AAAA-MM-JJ]

Seul ce qu'un manifeste liste fonde un chiffre public. Le manifeste s'écrit ici, jamais à la main :

1. le code doit être commité, son commit dans main, et porter une étiquette du protocole ; le dossier
   de la publication ne doit pas exister, une publication ne se modifie jamais ;
2. les témoins passent sur tous les terrains, sur ce commit ; un seul écart, et rien ne se publie ;
3. les données se calculent (ease.donnees_publication), et la liste des runs retenus en sort, avec
   leur rôle : socle, tranche, gardien, τ²-bench ; les runs des témoins s'y ajoutent ;
4. chaque run est copié réduit à ses tâches publiques, sans les journaux du candidat ; la part des
   autres tâches n'est donnée qu'en comptes, sans nom (cachees.json) ;
5. le manifeste donne, pour chaque run, son rôle, sa référence, son candidat, le contexte servi, son
   commit, sa signature et les empreintes du run entier et de sa copie.

La publication se construit dans 99_local/publication/, puis prend sa place d'un seul coup : une
publication interrompue reste un brouillon et n'entre jamais dans 08_publications.

    make publier SUJET=premier_post TEMOINS_DE=AAAA-MM-JJ_constat

reprend le passage des témoins d'une publication écrite sur le même code (règle 2) : entre son
commit et celui-ci, rien n'a changé de ce que les témoins mettent à l'épreuve (HORS_DES_TEMOINS),
sinon refus ; le manifeste dit d'où viennent ses témoins (JOURNAL, entrée 362).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from ease.candidats import DOSSIER as DOSSIER_CANDIDATS
from ease.chargement import racine_depot
from ease.donnees_publication import DOSSIER_TAU2, donnees_constat, donnees_premier_post, donnees_video
from ease.jouet import TACHES_JOUET
from ease.taches import JEUX, taches_du_jeu
from ease.textes_publies import TextesImpossibles, textes_controles

SUJETS = ("constat", "premier_post")

ROLES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("socle", "runs"), "socle"),
    (("runs",), "socle"),
    (("horizon", "runs"), "tranche"),
    (("graves", "runs_avec_gardien"), "gardien"),
)
"""Où les données nomment leurs runs, référence par référence, et le rôle de ces runs. Le premier post
nomme les siens à la racine ; τ²-bench se lit à part (runs_retenus)."""

ETIQUETTES = "protocole-*"
"""Les étiquettes git d'une version du protocole ; la plus proche du commit publié est citée."""

CHAMPS_SIGNATURE = ("configuration", "empreinte_prompts", "machine", "etat_pme", "repetitions", "regles_gardien")
"""Les champs d'une fiche de run que compare le rapport avant d'assembler des runs (rapport._signature) :
leur empreinte est la signature du run, sans la version renvoyée par le modèle, qui varie d'un appel
à l'autre."""

JOURNAL_DU_CANDIDAT = "_candidat.log"
"""Le suffixe des journaux du candidat : ce qu'il écrit lui-même, gardé dans l'atelier."""


class PublicationImpossible(Exception):
    """La publication ne se fait pas ; le message dit pourquoi."""


@dataclass
class Retenu:
    """Un run retenu par le calcul : son banc (runs ou runs_tau2), sa référence et ses rôles."""

    banc: str
    reference: str
    roles: set[str] = field(default_factory=set[str])


def _environnement_git() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"GIT_OPTIONAL_LOCKS": "0"}


def _git(*arguments: str, dans: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments], cwd=dans, capture_output=True, text=True, env=_environnement_git(), check=False
    )


def verifier_code(racine: Path) -> tuple[str, str]:
    """Le commit du code et l'étiquette du protocole qu'il porte ; refuse un code modifié, un commit
    hors de main, un commit sans étiquette du protocole (règle 4 de la section 8)."""
    modifications = _git("status", "--porcelain", dans=racine)
    if modifications.returncode != 0:
        raise PublicationImpossible(f"git status : {modifications.stderr.strip()}")
    if modifications.stdout.strip():
        nombre = len(modifications.stdout.strip().splitlines())
        raise PublicationImpossible(f"le code a {nombre} modification(s) non commitée(s) ; commiter d'abord")
    commit = _git("rev-parse", "HEAD", dans=racine).stdout.strip()
    if _git("merge-base", "--is-ancestor", "HEAD", "main", dans=racine).returncode != 0:
        raise PublicationImpossible(f"le commit {commit[:7]} n'est pas dans main")
    etiquette = _git("describe", "--tags", "--abbrev=0", "--match", ETIQUETTES, "HEAD", dans=racine)
    if etiquette.returncode != 0:
        raise PublicationImpossible(f"aucune étiquette {ETIQUETTES} avant le commit {commit[:7]}")
    return commit, etiquette.stdout.strip()


def dossier_principal(racine: Path) -> Path:
    """Le dossier de travail principal de l'atelier, même appelé depuis un poste de mesure : c'est là
    que la publication s'écrit, pour être commitée."""
    commun = _git("rev-parse", "--path-format=absolute", "--git-common-dir", dans=racine)
    if commun.returncode != 0:
        raise PublicationImpossible(f"git rev-parse : {commun.stderr.strip()}")
    return Path(commun.stdout.strip()).parent


def runs_retenus(donnees: dict[str, Any]) -> dict[str, Retenu]:
    """Les runs que nomment les données d'une publication, avec leur banc, leur référence et leurs rôles."""
    retenus: dict[str, Retenu] = {}

    def retenir(nom: str, banc: str, reference: str, role: str) -> None:
        retenu = retenus.setdefault(nom, Retenu(banc, reference))
        if (retenu.banc, retenu.reference) != (banc, reference):
            raise PublicationImpossible(f"le run {nom} est retenu pour deux références")
        retenu.roles.add(role)

    for chemin, role in ROLES:
        valeur: object = donnees
        for cle in chemin:
            valeur = cast(dict[str, object], valeur).get(cle) if isinstance(valeur, dict) else None
        if not isinstance(valeur, dict):
            continue
        for reference, noms in cast(dict[str, list[str]], valeur).items():
            for nom in noms:
                retenir(nom, "runs", reference, role)
    for reference, tau2 in cast(dict[str, dict[str, Any]], donnees.get("tau2", {})).items():
        for nom in cast(list[str], tau2["runs"]):
            retenir(nom, "runs_tau2", reference, "tau2")
    return retenus


def identifiants_publics() -> frozenset[str]:
    """Les tâches que tout le monde peut lire : celles des jeux publics et du jouet. Toute autre tâche
    d'un run de la PME est tenue pour cachée : la liste nomme ce qui peut sortir."""
    return frozenset(t.identifiant for jeu in JEUX for t in taches_du_jeu(jeu)) | {t.identifiant for t in TACHES_JOUET}


def empreinte_dossier(dossier: Path) -> str:
    """L'empreinte SHA-256 d'un dossier : chemin et contenu de chaque fichier, dans l'ordre des chemins."""
    somme = hashlib.sha256()
    for chemin in sorted(p for p in dossier.rglob("*") if p.is_file()):
        relatif = chemin.relative_to(dossier).as_posix()
        somme.update(f"{relatif}\0{hashlib.sha256(chemin.read_bytes()).hexdigest()}\n".encode())
    return f"sha256:{somme.hexdigest()}"


def empreinte_fichier(chemin: Path) -> str:
    """L'empreinte d'un fichier de la publication, pour que la page qui le lit sache qu'il n'a pas changé."""
    return f"sha256:{hashlib.sha256(chemin.read_bytes()).hexdigest()}"


def signature(fiche: dict[str, Any]) -> str:
    """L'empreinte de ce que le rapport compare entre deux runs avant de les assembler (CHAMPS_SIGNATURE)."""
    champs = {c: fiche.get(c) for c in CHAMPS_SIGNATURE}
    configuration = champs.get("configuration")
    if isinstance(configuration, dict):
        modeles = cast(list[dict[str, Any]], cast(dict[str, Any], configuration).get("modeles", []))
        champs["configuration"] = {
            **cast(dict[str, Any], configuration),
            "modeles": [{k: v for k, v in m.items() if k != "version_renvoyee"} for m in modeles],
        }
    texte = json.dumps(champs, sort_keys=True, ensure_ascii=False)
    return f"sha256:{hashlib.sha256(texte.encode()).hexdigest()}"


def contexte_servi(candidat: str) -> int | None:
    """Le contexte que la déclaration d'un candidat demande à son serveur : 102 400 ou 40 960 jetons
    pour les parts de Qwen ; aucun pour un candidat par API ou un témoin."""
    for dossier in (DOSSIER_CANDIDATS, DOSSIER_TAU2):
        chemin = dossier / f"{candidat}.yaml"
        if chemin.is_file():
            lancement = cast(dict[str, Any], yaml.safe_load(chemin.read_text(encoding="utf-8")))["lancement"]
            return cast(int | None, lancement.get("contexte_serveur"))
    return None


def copier_reduit(source: Path, cible: Path, publics: frozenset[str] | None) -> dict[str, int]:
    """Copie un run réduit à ses tâches publiques (toutes si publics vaut None, pour τ²-bench) : sa
    fiche, leurs résultats et leurs journaux, sans les journaux du candidat. Rend les comptes des autres
    tâches : leur nombre, leurs essais, leurs réussites. Les fichiers qu'aucun résultat gardé ne nomme
    ne sont pas copiés."""
    fiche = cast(dict[str, Any], json.loads((source / "fiche_de_run.json").read_text(encoding="utf-8")))
    jeu = cast(list[dict[str, Any]], fiche["jeu_taches"]["taches"])
    gardees = {t["identifiant"] for t in jeu if publics is None or t["identifiant"] in publics}
    fiche["jeu_taches"]["taches"] = [t for t in jeu if t["identifiant"] in gardees]
    (cible / "resultats").mkdir(parents=True)
    (cible / "journaux").mkdir()
    (cible / "fiche_de_run.json").write_text(json.dumps(fiche, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    essais = reussis = 0
    for chemin in sorted((source / "resultats").glob("*.json")):
        resultat = cast(dict[str, Any], json.loads(chemin.read_text(encoding="utf-8")))
        if resultat["tache"]["identifiant"] not in gardees:
            essais += 1
            reussis += bool(resultat.get("reussie"))
            continue
        shutil.copy2(chemin, cible / "resultats" / chemin.name)
        journal = source / cast(str, resultat["journal"])
        if journal.is_file() and not journal.name.endswith(JOURNAL_DU_CANDIDAT):
            shutil.copy2(journal, cible / "journaux" / journal.name)
    return {"taches": len(jeu) - len(gardees), "essais": essais, "reussis": reussis}


def _ecrire(chemin: Path, contenu: object) -> None:
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")


def _calculer(sujet: str, racine: Path) -> dict[str, Any]:
    runs, runs_tau2 = racine / "99_local" / "runs", racine / "99_local" / "runs_tau2"
    if sujet == "constat":
        return donnees_constat(runs, dossier_runs_tau2=runs_tau2)
    return donnees_premier_post(runs, dossier_runs_tau2=runs_tau2)


def _temoins(racine: Path) -> list[tuple[str, str, bool]]:
    from ease.temoins import conforme, passage_complet

    return [(d.name, t.identifiant, conforme(t, r)) for t, d, r in passage_complet(racine / "99_local" / "runs")]


HORS_DES_TEMOINS = (
    "08_publications/",
    "JOURNAL_PUBLIC.md",
    "JOURNAL.md",
    "00_docs/sources/",
    "Makefile",
    "02_ease/src/ease/publier.py",
    "02_ease/tests/test_publier.py",
)
"""Ce que les témoins ne mettent pas à l'épreuve, et qui peut donc changer entre deux publications
sans qu'ils se repassent : les publications, les journaux, les sources, et l'écriture d'une
publication elle-même (le passage des témoins n'appelle ni make ni ce module)."""


def temoins_repris(atelier: Path, racine: Path, publication: str) -> list[tuple[str, str, bool]]:
    """Le passage des témoins d'une publication déjà écrite, repris pour une autre sur le même code :
    les témoins vérifient le code, et entre son commit et HEAD n'a changé que ce qu'ils ne mettent pas
    à l'épreuve (HORS_DES_TEMOINS), sinon refus. Ce passage était conforme, puisque la publication
    s'est écrite (publier refuse un témoin en écart)."""
    chemin = atelier / "08_publications" / publication / "manifeste.json"
    if not chemin.is_file():
        raise PublicationImpossible(f"aucune publication {publication} dont reprendre les témoins")
    manifeste = cast(dict[str, Any], json.loads(chemin.read_text(encoding="utf-8")))
    difference = _git("diff", "--name-only", str(manifeste["commit"]), "HEAD", dans=racine)
    if difference.returncode != 0:
        raise PublicationImpossible(f"git diff depuis {publication} : {difference.stderr.strip()}")
    changes = [f for f in difference.stdout.splitlines() if f and not f.startswith(HORS_DES_TEMOINS)]
    if changes:
        raise PublicationImpossible(
            f"le code a changé depuis {publication} ({len(changes)} fichier(s), dont {changes[0]}) : "
            "les témoins se repassent"
        )
    lignes = cast(list[dict[str, Any]], manifeste["runs"])
    passages = [(str(r["run"]), str(r["reference"]), True) for r in lignes if "temoin" in r["roles"]]
    if not passages:
        raise PublicationImpossible(f"{publication} ne liste aucun témoin")
    return passages


def publier(
    sujet: str,
    date: str,
    racine: Path,
    atelier: Path,
    calculer: Callable[[], dict[str, Any]],
    temoins: Callable[[], Iterable[tuple[str, str, bool]]],
    textes: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    temoins_repris_de: str | None = None,
) -> Path:
    """Écrit la publication dans atelier/08_publications/<date>_<sujet>/ ; racine est le code qui la
    calcule, l'atelier ou un poste de mesure, dont 99_local est celui de l'atelier."""
    if sujet not in SUJETS:
        raise PublicationImpossible(f"sujet inconnu : {sujet} (connus : {', '.join(SUJETS)})")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise PublicationImpossible(f"date illisible : {date} (AAAA-MM-JJ)")
    commit, etiquette = verifier_code(racine)
    dossier = atelier / "08_publications" / f"{date}_{sujet}"
    if dossier.exists():
        raise PublicationImpossible(f"{dossier.name} existe déjà : une publication ne se modifie jamais")
    passages = list(temoins())
    ecarts = [f"{temoin} ({run})" for run, temoin, ok in passages if not ok]
    if ecarts:
        raise PublicationImpossible(f"témoins en écart, le banc se trompe : {', '.join(ecarts)}")
    donnees = calculer()
    ecrits: dict[str, Any] | None = None
    if textes is not None:
        try:
            ecrits = textes(donnees)
        except TextesImpossibles as erreur:
            raise PublicationImpossible(f"textes refusés : {erreur}") from erreur
    retenus = runs_retenus(donnees)
    for run, temoin, _ in passages:
        retenus[run] = Retenu("runs", temoin, {"temoin"})
    publics = identifiants_publics()
    brouillon = atelier / "99_local" / "publication" / f"{dossier.name}.en_cours"
    if brouillon.exists():
        raise PublicationImpossible(f"un brouillon interrompu attend : {brouillon} ; le mettre de côté")
    (brouillon / "runs").mkdir(parents=True)
    lignes: list[dict[str, Any]] = []
    cachees: list[dict[str, Any]] = []
    for nom in sorted(retenus):
        retenu = retenus[nom]
        source = racine / "99_local" / retenu.banc / nom
        if not (source / "fiche_de_run.json").is_file():
            raise PublicationImpossible(f"run retenu introuvable : {retenu.banc}/{nom}")
        fiche = cast(dict[str, Any], json.loads((source / "fiche_de_run.json").read_text(encoding="utf-8")))
        cible = brouillon / "runs" / nom
        comptes = copier_reduit(source, cible, None if retenu.banc == "runs_tau2" else publics)
        candidat = cast(str, fiche["candidat"]["identifiant"])
        code = cast(dict[str, Any], fiche.get("code") or {})
        lignes.append(
            {
                "run": nom,
                "banc": "τ²-bench" if retenu.banc == "runs_tau2" else "PME",
                "roles": sorted(retenu.roles),
                "reference": retenu.reference,
                "candidat": candidat,
                "contexte_servi": contexte_servi(candidat),
                "commit": code.get("commit"),
                "modifications_non_commitees": code.get("modifications_non_commitees"),
                "signature": signature(fiche),
                "taches_publiees": len(fiche["jeu_taches"]["taches"]) - comptes["taches"],
                "taches_non_publiees": comptes["taches"],
                "empreinte_du_run": empreinte_dossier(source),
                "empreinte_publiee": empreinte_dossier(cible),
            }
        )
        if comptes["taches"]:
            cachees.append({"run": nom, **comptes})
    _ecrire(brouillon / "donnees.json", donnees)
    if sujet == "premier_post":
        _ecrire(brouillon / "donnees_video.json", donnees_video(donnees))
    _ecrire(brouillon / "cachees.json", cachees)
    if ecrits is not None:
        _ecrire(brouillon / "textes.json", ecrits)
    empreintes = {f.name: empreinte_fichier(f) for f in sorted(brouillon.glob("*.json"))}
    _ecrire(
        brouillon / "manifeste.json",
        {
            "sujet": sujet,
            "date": date,
            "produit_le": datetime.now(UTC).isoformat(timespec="seconds"),
            "commit": commit,
            "protocole": etiquette,
            "empreintes": empreintes,
            **({"temoins_repris_de": temoins_repris_de} if temoins_repris_de else {}),
            "runs": lignes,
        },
    )
    (brouillon / "README.md").write_text(_lisezmoi(sujet, date, commit, etiquette, lignes), encoding="utf-8")
    dossier.parent.mkdir(parents=True, exist_ok=True)
    brouillon.rename(dossier)
    return dossier


def _lisezmoi(sujet: str, date: str, commit: str, etiquette: str, lignes: list[dict[str, Any]]) -> str:
    roles: dict[str, int] = {}
    for ligne in lignes:
        for role in ligne["roles"]:
            roles[role] = roles.get(role, 0) + 1
    detail = ", ".join(f"{role} {nombre}" for role, nombre in sorted(roles.items()))
    return (
        f"# Publication {date}, {sujet}\n\n"
        f"Écrite par `make publier` au commit `{commit[:7]}`, protocole `{etiquette}`. Elle ne se modifie\n"
        "jamais : une erreur donne une nouvelle publication, qui cite celle-ci.\n\n"
        f"- `manifeste.json` : les {len(lignes)} runs qui fondent ses chiffres ({detail}), leur rôle et\n"
        "  leurs empreintes ;\n"
        "- `donnees.json` : les chiffres, calculés sur ces runs ;\n"
        "- `runs/` : chaque run réduit à ses tâches publiques, sans les journaux du candidat ; sa fiche\n"
        "  ne liste que ces tâches, l'empreinte du jeu restant celle du jeu entier ;\n"
        "- `cachees.json` : la part des tâches non publiées, en comptes par run, sans nom de tâche.\n"
    )


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m ease.publier", description="L'officiel d'une publication.")
    analyse.add_argument("sujet", choices=SUJETS, help="la publication")
    analyse.add_argument("--date", default=datetime.now(UTC).date().isoformat(), help="AAAA-MM-JJ, aujourd'hui sinon")
    analyse.add_argument(
        "--temoins-de", default=None, help="AAAA-MM-JJ_sujet : reprendre les témoins de cette publication, même code"
    )
    options = analyse.parse_args(arguments)
    racine = racine_depot()
    try:
        atelier = dossier_principal(racine)
        dossier = publier(
            options.sujet,
            options.date,
            racine,
            atelier,
            lambda: _calculer(options.sujet, racine),
            (lambda: temoins_repris(atelier, racine, options.temoins_de))
            if options.temoins_de
            else (lambda: _temoins(racine)),
            lambda donnees: textes_controles(options.sujet, donnees),
            options.temoins_de,
        )
    except PublicationImpossible as erreur:
        print(f"Publication refusée : {erreur}", file=sys.stderr)
        return 1
    manifeste = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    print(f"Publication écrite : {dossier} ({len(manifeste['runs'])} runs). À relire, puis commiter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
