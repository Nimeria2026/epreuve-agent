"""L'export public : ce qui sort de l'atelier vers le dépôt public « epreuve-agent » (ADR 0010 ;
cadrage du dépôt public et de l'organisation, sections 3 à 5 ; JOURNAL, entrée 293).

    make exporter-public [SORTIE=<dossier neuf>]

Prend le contenu d'un commit de l'atelier (HEAD par défaut), jamais la copie de travail : seul ce
qui est commité sort. Choisit les fichiers par une liste de ce qui sort (INCLUS) ; tout le reste
reste, dont le BRIEF, le PLAN, le journal de l'atelier, ATELIER.md, les notes de 00_docs/sources/ et
le coffre. JOURNAL_PUBLIC.md sort sous le nom JOURNAL.md, le README public remplace celui de
l'atelier, et CLAUDE.md n'importe plus qu'AGENTS.md.

Puis refuse d'écrire quoi que ce soit si un fichier choisi :
- est sous 99_local/, 12_coffre/ ou 07_taches/prive/, ou finit en .age ;
- cite l'identifiant d'une tâche cachée (07_taches/prive/, lus sur le disque) ;
- contient la valeur d'une variable du .env, ou un texte de export/interdits.md.
Le rapport nomme le fichier et la nature du problème, jamais la valeur ni la tâche en cause.

Enfin, écrit l'export dans SORTIE, un dossier qui ne doit pas exister (par défaut
/tmp/epreuve-agent_export_<horodatage>), et y passe la garde de l'arborescence. Rien ne part sur
GitHub : la poussée vers le dépôt public est un autre pas, avec l'accord d'Alexandre. Bibliothèque
standard seule.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]

INCLUS_DOSSIERS = (
    "00_docs/adr/",
    "00_docs/protocole/",
    "01_contrats/",
    "02_ease/",
    "03_orchestrations/",
    "04_eke/",
    "05_pme/",
    "06_gardien/",
    "07_taches/public/",
    "08_publications/",
    "09_outillage/",
    "10_deploiement/",
    "11_bancs_publics/",
    ".github/",
)
"""Les dossiers qui sortent, entiers (cadrage, section 4)."""

INCLUS_FICHIERS = frozenset(
    {
        "00_docs/README.md",
        "07_taches/README.md",
        "AGENTS.md",
        "LICENSE",
        "Makefile",
        "arborescence.toml",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".env.exemple",
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "package.json",
        "pnpm-workspace.yaml",
        "pnpm-lock.yaml",
        "tsconfig.base.json",
        "biome.json",
    }
)
"""Les fichiers qui sortent, un à un."""

EXCLUS = ("09_outillage/scripts/export/",)
"""Sous un dossier qui sort, ce qui reste : les modèles de l'export et la liste des interdits."""

RENOMMES = {"JOURNAL_PUBLIC.md": "JOURNAL.md"}
"""Le journal public sort sous le nom que le public attend (ADR 0009)."""

MODELE_README = "09_outillage/scripts/export/readme_public.md"
INTERDITS = "09_outillage/scripts/export/interdits.md"
CLAUDE_PUBLIC = "# CLAUDE.md\n\nCe fichier importe la porte d'entrée du dépôt, pour toute IA.\n\n@AGENTS.md\n"
"""Le CLAUDE.md public : celui de l'atelier importe aussi ATELIER.md, qui ne sort pas."""

JAMAIS = ("99_local/", "12_coffre/", "07_taches/prive/")
LONGUEUR_MIN_SECRET = 12
"""Une valeur du .env plus courte ne se cherche pas : elle n'est pas une clé (un port, un nom)."""


class ExportImpossible(Exception):
    """L'export ne se fait pas ; le message dit pourquoi."""


@dataclass(frozen=True)
class Fichier:
    chemin: str
    contenu: bytes
    mode: int


def _git(racine: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environnement = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"GIT_OPTIONAL_LOCKS": "0"}
    return subprocess.run(["git", *arguments], cwd=racine, capture_output=True, env=environnement, check=False)


def destination(chemin: str) -> str | None:
    """Le chemin public d'un fichier de l'atelier, ou None s'il ne sort pas."""
    if chemin in RENOMMES:
        return RENOMMES[chemin]
    if chemin.startswith(EXCLUS):
        return None
    if chemin in INCLUS_FICHIERS or chemin.startswith(INCLUS_DOSSIERS):
        return chemin
    return None


def fichiers_du_commit(racine: Path, commit: str) -> list[Fichier]:
    """Les fichiers d'un commit, par l'archive git : le contenu commité, avec ses droits d'exécution."""
    archive = _git(racine, "archive", "--format=tar", commit)
    if archive.returncode != 0:
        raise ExportImpossible(f"git archive {commit} : {archive.stderr.decode(errors='replace').strip()}")
    fichiers: list[Fichier] = []
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as lecture:
        for membre in lecture.getmembers():
            if membre.isfile():
                contenu = lecture.extractfile(membre)
                assert contenu is not None
                fichiers.append(Fichier(membre.name, contenu.read(), membre.mode))
    return fichiers


def choisir(fichiers: list[Fichier]) -> list[Fichier]:
    """Ce qui sort, sous son nom public, avec le README et le CLAUDE.md publics."""
    sortants = [Fichier(d, f.contenu, f.mode) for f in fichiers if (d := destination(f.chemin)) is not None]
    modele = next((f for f in fichiers if f.chemin == MODELE_README), None)
    if modele is None:
        raise ExportImpossible(f"le README public manque au commit : {MODELE_README}")
    sortants.append(Fichier("README.md", modele.contenu, 0o644))
    sortants.append(Fichier("CLAUDE.md", CLAUDE_PUBLIC.encode(), 0o644))
    return sorted(sortants, key=lambda f: f.chemin)


def identifiants_caches(racine: Path) -> set[str]:
    """Les identifiants des tâches cachées : la clé « identifiant: » de premier niveau de chaque fichier
    de 07_taches/prive/ qui est une tâche (il a un « enonce: »). Lus sur le disque, jamais affichés.
    Les autres fichiers de prive/ (compléments, gravité) ne nomment pas de tâche."""
    prive = racine / "07_taches" / "prive"
    trouves: set[str] = set()
    if prive.is_dir():
        for chemin in prive.rglob("*.y*ml"):
            texte = chemin.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^enonce:", texte, re.MULTILINE):
                trouves.update(re.findall(r"^identifiant:\s*['\"]?([A-Za-z0-9_\-]+)", texte, re.MULTILINE))
    return trouves


def secrets_du_env(racine: Path) -> list[bytes]:
    """Les valeurs du .env assez longues pour être des clés. Jamais affichées."""
    chemin = racine / ".env"
    if not chemin.is_file():
        return []
    valeurs: list[bytes] = []
    for ligne in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in ligne and not ligne.lstrip().startswith("#"):
            valeur = ligne.split("=", 1)[1].strip().strip("'\"")
            if len(valeur) >= LONGUEUR_MIN_SECRET:
                valeurs.append(valeur.encode())
    return valeurs


def interdits(fichiers: list[Fichier]) -> list[bytes]:
    """Les textes de export/interdits.md, lus dans le commit, en minuscules."""
    liste = next((f for f in fichiers if f.chemin == INTERDITS), None)
    if liste is None:
        raise ExportImpossible(f"la liste des interdits manque au commit : {INTERDITS}")
    lignes = liste.contenu.decode("utf-8").splitlines()
    return [ligne[2:].strip().lower().encode() for ligne in lignes if ligne.startswith("- ") and ligne[2:].strip()]


def _motif(textes: list[bytes]) -> re.Pattern[bytes] | None:
    return re.compile(b"|".join(re.escape(x) for x in sorted(set(textes), key=len, reverse=True))) if textes else None


def problemes(sortants: list[Fichier], caches: set[str], secrets: list[bytes], mots: list[bytes]) -> list[str]:
    """Ce qui empêche l'export, fichier par fichier, sans jamais citer la valeur en cause."""
    trouves: list[str] = []
    motif_caches = _motif([c.encode() for c in caches])
    motif_secrets = _motif(secrets)
    motif_mots = _motif(mots)
    for fichier in sortants:
        chemin = fichier.chemin.encode()
        if fichier.chemin.startswith(JAMAIS) or fichier.chemin.endswith(".age"):
            trouves.append(f"{fichier.chemin} : chemin qui ne sort jamais")
        if motif_caches and (motif_caches.search(fichier.contenu) or motif_caches.search(chemin)):
            trouves.append(f"{fichier.chemin} : cite une tâche cachée")
        if motif_secrets and motif_secrets.search(fichier.contenu):
            trouves.append(f"{fichier.chemin} : contient une valeur du .env")
        if motif_mots and (motif_mots.search(fichier.contenu.lower()) or motif_mots.search(chemin.lower())):
            trouves.append(f"{fichier.chemin} : contient un texte interdit (export/interdits.md)")
    return trouves


def ecrire(sortants: list[Fichier], sortie: Path) -> None:
    sortie.mkdir(parents=True)
    for fichier in sortants:
        chemin = sortie / fichier.chemin
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(fichier.contenu)
        chemin.chmod(0o755 if fichier.mode & 0o111 else 0o644)


def exporter(racine: Path, sortie: Path, commit: str = "HEAD") -> list[Fichier]:
    """Choisit, vérifie, puis écrit l'export ; rien n'est écrit au moindre problème."""
    if sortie.exists():
        raise ExportImpossible(f"{sortie} existe déjà ; un export s'écrit dans un dossier neuf")
    fichiers = fichiers_du_commit(racine, commit)
    sortants = choisir(fichiers)
    trouves = problemes(sortants, identifiants_caches(racine), secrets_du_env(racine), interdits(fichiers))
    if trouves:
        raise ExportImpossible(f"{len(trouves)} problème(s), rien n'est écrit :\n  " + "\n  ".join(trouves))
    ecrire(sortants, sortie)
    return sortants


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="exporter_public.py", description="L'export public de l'atelier.")
    horodatage = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    # Par défaut dans /tmp : un essai à relire, qui n'encombre pas le dossier des projets.
    analyse.add_argument("--sortie", type=Path, default=Path("/tmp") / f"epreuve-agent_export_{horodatage}")
    analyse.add_argument("--commit", default="HEAD")
    options = analyse.parse_args(arguments)
    try:
        sortants = exporter(RACINE, options.sortie, options.commit)
    except ExportImpossible as erreur:
        print(f"Export refusé : {erreur}", file=sys.stderr)
        return 2
    commit = _git(RACINE, "rev-parse", "--short", options.commit).stdout.decode().strip()
    etiquette = _git(RACINE, "describe", "--tags", "--abbrev=0", "--match", "protocole-*", options.commit)
    print(f"Export écrit : {options.sortie} ({len(sortants)} fichiers), du commit {commit}", end="")
    print(f", protocole {etiquette.stdout.decode().strip()}." if etiquette.returncode == 0 else ".")
    garde = subprocess.run(
        [sys.executable, str(options.sortie / "09_outillage" / "garde" / "verifier_arborescence.py")],
        cwd=options.sortie,
        check=False,
    )
    if garde.returncode != 0:
        print("La garde de l'arborescence refuse l'export : à corriger avant tout envoi.", file=sys.stderr)
        return 3
    print("À relire avant tout envoi vers le dépôt public.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
