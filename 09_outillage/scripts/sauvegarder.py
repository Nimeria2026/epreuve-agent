"""La sauvegarde de l'atelier sur la clé USB d'Alexandre, dans un dossier chiffré par gocryptfs, en
archives compressées (ADR 0008 ; cadrage du dépôt public et de l'organisation, section 9 ; JOURNAL,
entrées 289 et 290).

    make sauvegarder CLE=/media/<utilisateur>/<clé> [INITIALISER=1 : la première fois]

La clé sert aussi aux sauvegardes d'autres projets : elle reste en clair, et seul le dossier
<clé>/Nimeria_poa_chiffre/ est chiffré, fichiers et noms compris. La commande l'ouvre (gocryptfs
demande son mot de passe), y écrit ce qui a changé, puis le referme. Elle refuse un chemin qui n'est
pas un point de montage, pour ne pas écrire sur le disque du PC par erreur, et dit la date de la
copie précédente. La première fois, INITIALISER=1 crée le dossier chiffré : gocryptfs demande un mot
de passe et affiche une clé maîtresse, à garder toutes deux.

L'atelier compte des dizaines de milliers de petits fichiers, et une clé formatée en exFAT donne à
chacun un bloc entier : copiés un par un, 1,5 Go en occupaient plus de 4,7 (entrée 290). Ils partent
donc en archives tar.gz, une par morceau :
- chaque run de 99_local/runs/, 99_local/runs_tau2/ et de chaque dossier de 99_local/importes/ ;
- chaque autre entrée de premier niveau de 99_local/ et de 07_taches/prive/ ;
- la clé age du coffre, copiée telle quelle.
99_local/travail/, des états que chaque run recrée, ne se sauvegarde pas. Un morceau n'est réécrit que
si un de ses fichiers a changé de taille ou de date ; un morceau disparu de l'atelier reste sur la
clé ; un morceau qui change y est remplacé par sa nouvelle version (le coffre, dans git, garde les
anciennes des tâches cachées et des verdicts du juge).

Bibliothèque standard seule, et gocryptfs (sudo apt install gocryptfs).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import termios
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

CHIFFRE = "Nimeria_poa_chiffre"
"""Le dossier chiffré, sur la clé."""

EN_CLAIR = "Nimeria_poa_sauvegarde"
"""La copie en clair du 2026-10-26, d'avant le dossier chiffré : à effacer de la clé."""

TRACE = ".derniere_sauvegarde"
INDEX = "index.json"
DOSSIERS_DE_RUNS = ("99_local/runs", "99_local/runs_tau2")
NON_SAUVEGARDES = ("99_local/travail",)
"""Les états de travail des runs, que chaque run recrée (cadrage, section 8)."""

CLE_AGE = Path.home() / ".config" / "age" / "poa.txt"
"""La clé privée du coffre (12_coffre/README.md) : une copie de plus, dans le dossier chiffré."""


class SauvegardeImpossible(Exception):
    """La sauvegarde ne se fait pas ; le message dit pourquoi."""


@dataclass
class Sauvegarde:
    chiffre: Path
    precedente: str | None
    ecrits: int
    inchanges: int
    en_clair: Path | None


def creer_gocryptfs(chiffre: Path) -> None:
    chiffre.mkdir(exist_ok=True)
    subprocess.run(["gocryptfs", "-init", str(chiffre)], check=True)


def ouvrir_gocryptfs(chiffre: Path, ouvert: Path) -> None:
    """Ouvre le dossier chiffré ; gocryptfs demande son mot de passe. Une touche Entrée tapée en trop
    pendant la création ne doit pas lui répondre à vide (entrée 291) : l'entrée en attente du
    terminal est vidée avant."""
    if sys.stdin.isatty():
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    print("Ouverture du dossier chiffré : gocryptfs demande son mot de passe.", flush=True)
    subprocess.run(["gocryptfs", str(chiffre), str(ouvert)], check=True)


def fermer_gocryptfs(ouvert: Path) -> None:
    programme = shutil.which("fusermount3") or shutil.which("fusermount") or "fusermount"
    subprocess.run([programme, "-u", str(ouvert)], check=True)


def morceaux(racine: Path) -> Iterator[Path]:
    """Les morceaux de la sauvegarde, chemins relatifs à l'atelier, dans l'ordre des chemins."""
    runs = {racine / d for d in DOSSIERS_DE_RUNS}
    importes = racine / "99_local" / "importes"
    exclus = {racine / d for d in NON_SAUVEGARDES}
    for base in (racine / "99_local", racine / "07_taches" / "prive"):
        if not base.is_dir():
            continue
        for entree in sorted(base.iterdir()):
            if entree in exclus:
                continue
            if entree in runs:
                yield from (r.relative_to(racine) for r in sorted(entree.iterdir()))
            elif entree == importes:
                for origine in sorted(p for p in entree.iterdir() if p.is_dir()):
                    yield from (r.relative_to(racine) for r in sorted(origine.iterdir()))
                yield from (p.relative_to(racine) for p in sorted(entree.iterdir()) if not p.is_dir())
            else:
                yield entree.relative_to(racine)


def signature(chemin: Path) -> str:
    """Ce qui dit qu'un morceau a changé sans le relire : chemin, taille et date de chacun de ses fichiers."""
    fichiers = [chemin] if chemin.is_file() else sorted(p for p in chemin.rglob("*") if p.is_file())
    somme = hashlib.sha256()
    for fichier in fichiers:
        etat = fichier.stat()
        somme.update(f"{fichier.relative_to(chemin.parent).as_posix()}\0{etat.st_size}\0{etat.st_mtime_ns}\n".encode())
    return somme.hexdigest()


def _ecrire(source: Path, cible: Path) -> None:
    """Un dossier en tar.gz, un fichier tel quel ; écrit à côté puis renommé, jamais à moitié."""
    cible.parent.mkdir(parents=True, exist_ok=True)
    provisoire = cible.with_name(cible.name + ".en_cours")
    if source.is_dir():
        with tarfile.open(provisoire, "w:gz") as archive:
            archive.add(source, arcname=source.name)
    else:
        shutil.copy2(source, provisoire)
    provisoire.replace(cible)


def sauvegarder(
    racine: Path,
    cle: Path,
    initialiser: bool = False,
    est_monte: Callable[[Path], bool] = os.path.ismount,
    creer: Callable[[Path], None] = creer_gocryptfs,
    ouvrir: Callable[[Path, Path], None] = ouvrir_gocryptfs,
    fermer: Callable[[Path], None] = fermer_gocryptfs,
    cle_age: Path = CLE_AGE,
    maintenant: str | None = None,
) -> Sauvegarde:
    """Ouvre le dossier chiffré de la clé, y écrit les morceaux qui ont changé, le referme."""
    if not est_monte(cle):
        raise SauvegardeImpossible(f"{cle} n'est pas un point de montage ; brancher la clé, puis CLE=<son chemin>")
    if ouvrir is ouvrir_gocryptfs and shutil.which("gocryptfs") is None:
        raise SauvegardeImpossible("gocryptfs manque : sudo apt install gocryptfs")
    chiffre = cle / CHIFFRE
    if not (chiffre / "gocryptfs.conf").is_file():
        if not initialiser:
            raise SauvegardeImpossible(
                f"{chiffre} n'existe pas encore ; la première fois : make sauvegarder CLE={cle} INITIALISER=1"
            )
        if chiffre.exists() and any(chiffre.iterdir()):
            raise SauvegardeImpossible(f"{chiffre} existe, n'est pas vide et n'est pas un dossier gocryptfs")
        creer(chiffre)
    ouvert = Path(tempfile.mkdtemp(prefix="poa_sauvegarde_"))
    try:
        ouvrir(chiffre, ouvert)
    except BaseException:
        ouvert.rmdir()
        raise
    try:
        if not est_monte(ouvert):
            raise SauvegardeImpossible("le dossier chiffré ne s'est pas ouvert ; rien n'a été écrit")
        trace, chemin_index = ouvert / TRACE, ouvert / INDEX
        precedente = trace.read_text(encoding="utf-8").strip() if trace.is_file() else None
        index: dict[str, str] = json.loads(chemin_index.read_text(encoding="utf-8")) if chemin_index.is_file() else {}
        ecrits = inchanges = 0
        for relatif in morceaux(racine):
            source, cle_index = racine / relatif, relatif.as_posix()
            cible = ouvert / (cle_index + (".tar.gz" if source.is_dir() else ""))
            empreinte = signature(source)
            if index.get(cle_index) == empreinte and cible.is_file():
                inchanges += 1
                continue
            _ecrire(source, cible)
            index[cle_index] = empreinte
            ecrits += 1
            chemin_index.write_text(
                json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
            )
        if cle_age.is_file():
            shutil.copy2(cle_age, ouvert / "cle_age_poa.txt")
        trace.write_text((maintenant or datetime.now(UTC).isoformat(timespec="seconds")) + "\n", encoding="utf-8")
    finally:
        fermer(ouvert)
        ouvert.rmdir()
    en_clair = cle / EN_CLAIR
    return Sauvegarde(chiffre, precedente, ecrits, inchanges, en_clair if en_clair.exists() else None)


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="sauvegarder.py", description="Sauvegarde chiffrée de l'atelier.")
    analyse.add_argument("cle", nargs="?", type=Path, help="le point de montage de la clé USB")
    analyse.add_argument("--initialiser", action="store_true", help="crée le dossier chiffré, la première fois")
    options = analyse.parse_args(arguments)
    if options.cle is None:
        print("Sauvegarde non faite : CLE=<chemin de la clé montée> manque.", file=sys.stderr)
        return 2
    racine = Path(__file__).resolve().parents[2]
    try:
        resultat = sauvegarder(racine, options.cle, options.initialiser)
    except (SauvegardeImpossible, subprocess.CalledProcessError, OSError) as erreur:
        print(f"Sauvegarde non faite : {erreur}", file=sys.stderr)
        return 2
    print(
        f"Sauvegarde chiffrée faite dans {resultat.chiffre} : {resultat.ecrits} morceau(x) écrit(s), "
        f"{resultat.inchanges} inchangé(s) ; la précédente : {resultat.precedente or 'aucune'}."
    )
    if resultat.en_clair is not None:
        print(f"La copie en clair du 2026-10-26 est encore sur la clé : {resultat.en_clair}. À effacer, par toi.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
