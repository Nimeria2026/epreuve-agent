"""Le poste de mesure : une seconde copie de travail du dépôt, figée sur un commit, d'où se lancent
les runs (décision d'Alexandre, JOURNAL, entrée 108). Deux postes, et nul autre : api et local, dans
<dépôt>_postes/ à côté du dossier de travail (cadrage du dépôt public et de l'organisation, section
10 ; JOURNAL, entrée 285) ; ease.poste tient la même liste et refuse un run lancé d'ailleurs.

    make poste-mesure POSTE=api|local [COMMIT=HEAD]

La copie est un worktree git du dépôt, à côté du dossier de travail. Elle a son propre `.venv` et
ses propres `node_modules`, et reprend par des liens le `.env`, le `99_local/` et les tâches
cachées du dossier de travail : les runs écrivent au même endroit, le rapport les trouve, et le
verrou de chaque candidat reste commun. Pendant un run lancé depuis la copie, on travaille,
commite, tire et installe dans le dossier de travail sans rien changer au run. La fiche du run
note le commit de la copie, sans modification.

La copie ne change de commit que si aucun run n'y tourne (processus `ease.mesure` dont le dossier
courant est la copie) et qu'elle n'a aucune modification. Bibliothèque standard seule ; Linux
(`/proc`) pour reconnaître un run en cours.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

POSTES = ("api", "local")
"""Les postes de mesure, ceux de ease.poste.POSTES."""

LIENS = (".env", "99_local", "07_taches/prive")
"""Ce que la copie reprend du dossier de travail, par un lien, quand il existe."""

EXCLUS = ("/99_local", "/07_taches/prive")
"""Les liens que git doit ignorer : le .gitignore ne vise que des dossiers (« 99_local/ »), et un
lien n'en est pas un pour lui."""


class PosteImpossible(Exception):
    """Le poste de mesure ne peut pas être préparé ; le message dit pourquoi."""


def environnement_git() -> dict[str, str]:
    """L'environnement sans les variables GIT_* : lancé depuis un crochet git (les tests du crochet
    avant commit), git y pose GIT_INDEX_FILE et d'autres, qui viseraient le mauvais dépôt."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"GIT_OPTIONAL_LOCKS": "0"}


def git(*arguments: str, dans: Path) -> str:
    resultat = subprocess.run(
        ["git", *arguments],
        cwd=dans,
        capture_output=True,
        text=True,
        env=environnement_git(),
        check=False,
    )
    if resultat.returncode != 0:
        raise PosteImpossible(f"git {' '.join(arguments)} : {resultat.stderr.strip()}")
    return resultat.stdout.strip()


def dossier_principal(depuis: Path) -> Path:
    """Le dossier de travail principal du dépôt, même appelé depuis la copie de mesure."""
    commun = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", dans=depuis))
    return commun.parent


def runs_en_cours(dossier: Path, proc: Path = Path("/proc")) -> list[int]:
    """Les processus de mesure (`python -m ease.mesure`) qui tournent dans le dossier donné."""
    trouves: list[int] = []
    for processus in proc.glob("[0-9]*"):
        try:
            commande = (processus / "cmdline").read_bytes().split(b"\0")
            courant = (processus / "cwd").readlink()
        except OSError:
            continue
        mesure = any(m in commande for m in (b"ease.mesure", b"ease.mesure_tau2", b"ease.publier"))
        if mesure and (courant == dossier or dossier in courant.parents):
            trouves.append(int(processus.name))
    return trouves


def _exclure(principal: Path) -> None:
    commun = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", dans=principal))
    fichier = commun / "info" / "exclude"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    lignes = fichier.read_text(encoding="utf-8").splitlines() if fichier.is_file() else []
    manquantes = [e for e in EXCLUS if e not in lignes]
    if manquantes:
        texte = "\n".join([*lignes, "# poste de mesure (09_outillage/scripts/poste_de_mesure.py)", *manquantes])
        fichier.write_text(texte + "\n", encoding="utf-8")


def preparer(principal: Path, dossier: Path, commit: str, installer: bool = True) -> str:
    """Crée la copie de mesure ou la place sur le commit, pose les liens, installe ; rend le commit."""
    # Chemin normalisé : « ../<dépôt>_confirmation », donné depuis le dossier de travail, est à côté de
    # lui, pas dedans, même si le chemin brut passe par le dossier de travail (JOURNAL, entrée 111).
    dossier = dossier.resolve()
    if dossier == principal or principal in dossier.parents:
        raise PosteImpossible(f"la copie de mesure doit être hors du dossier de travail : {dossier}")
    complet = git("rev-parse", "--verify", f"{commit}^{{commit}}", dans=principal)
    _exclure(principal)
    if not dossier.exists():
        dossier.parent.mkdir(parents=True, exist_ok=True)
        git("worktree", "add", "--detach", str(dossier), complet, dans=principal)
    else:
        if not (dossier / ".git").is_file():
            raise PosteImpossible(f"{dossier} existe et n'est pas une copie de travail de ce dépôt")
        en_cours = runs_en_cours(dossier)
        if en_cours:
            raise PosteImpossible(f"un run tourne dans {dossier} (processus {', '.join(map(str, en_cours))})")
        if git("status", "--porcelain", dans=dossier):
            raise PosteImpossible(f"{dossier} a des modifications ; la copie de mesure ne se modifie pas")
        git("checkout", "--quiet", "--detach", complet, dans=dossier)
    for lien in LIENS:
        cible, chemin = principal / lien, dossier / lien
        if cible.exists() and not chemin.is_symlink() and not chemin.exists():
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.symlink_to(cible)
    if installer:
        for commande in (["uv", "sync", "--all-packages", "--frozen"], ["pnpm", "install", "--frozen-lockfile"]):
            subprocess.run(commande, cwd=dossier, check=True)
    reste = git("status", "--short", dans=dossier)
    if reste:
        raise PosteImpossible(f"{dossier} n'est pas propre après préparation : {reste}")
    return complet


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="poste_de_mesure.py", description="Prépare le poste de mesure.")
    analyse.add_argument("--poste", choices=POSTES, required=True, help="api : modèles par API ; local : la carte")
    analyse.add_argument("--commit", default="HEAD", help="commit à mesurer (HEAD du dossier de travail par défaut)")
    options = analyse.parse_args(arguments)
    try:
        principal = dossier_principal(Path.cwd())
        dossier = principal.parent / f"{principal.name}_postes" / options.poste
        complet = preparer(principal, dossier, options.commit)
    except (PosteImpossible, subprocess.CalledProcessError) as erreur:
        print(f"Poste de mesure non préparé : {erreur}", file=sys.stderr)
        return 2
    print(f"Poste de mesure prêt : {dossier} au commit {complet[:8]}.")
    print(f"Lancer un run : cd {dossier} && make mesure CANDIDAT=<identifiant>")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
