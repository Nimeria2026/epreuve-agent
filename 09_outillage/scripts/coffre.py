"""Le coffre : la copie en ligne, chiffrée avec age, de ce qui n'existe qu'une fois et ne se refait
pas (ADR 0008 ; cadrage du dépôt public et de l'organisation, section 9 ; JOURNAL, entrée 286).

    make coffre

Les morceaux, un par entrée :
- chaque entrée de premier niveau de 07_taches/prive/, les tâches cachées ;
- chaque entrée de 99_local/juge/, les verdicts du juge ;
- chaque run entier d'une publication qui a des tâches non publiées (08_publications/*/manifeste.json).
Un dossier devient une archive tar.gz reproductible : mêmes fichiers, mêmes octets.

Chaque morceau nouveau ou changé est chiffré pour la clé publique de 12_coffre/destinataire.txt, dans
12_coffre/<numéro>.age ; les autres ne sont pas touchés, age donnant un fichier neuf à chaque
chiffrement. L'index (numéro, chemin, empreinte de chaque morceau) reste en clair dans
99_local/coffre/index.json, hors git, et chiffré dans 12_coffre/index.age. Rien ne s'efface : un morceau
disparu de l'atelier garde son fichier, l'index le dit absent. La sortie ne donne que des nombres,
jamais un chemin : ceux des tâches cachées les nomment.

Bibliothèque standard seule, et le programme age (sudo apt install age).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

COFFRE = "12_coffre"
INDEX_LOCAL = Path("99_local") / "coffre" / "index.json"

Chiffreur = Callable[[bytes], bytes]


class CoffreImpossible(Exception):
    """Le coffre ne se met pas à jour ; le message dit pourquoi."""


@dataclass
class Bilan:
    nouveaux: int = 0
    changes: int = 0
    inchanges: int = 0
    absents: int = 0


def archive_reproductible(dossier: Path) -> bytes:
    """Un dossier en tar.gz dont les octets ne dépendent que des chemins et des contenus : ordre des
    chemins, dates, propriétaires et droits fixés."""
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for chemin in sorted(dossier.rglob("*")):
            info = tarfile.TarInfo(chemin.relative_to(dossier).as_posix())
            info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
            if chemin.is_dir():
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                archive.addfile(info)
            elif chemin.is_file():
                donnees = chemin.read_bytes()
                info.size, info.mode = len(donnees), 0o644
                archive.addfile(info, io.BytesIO(donnees))
    return gzip.compress(tampon.getvalue(), mtime=0)


def _contenu(chemin: Path) -> Callable[[], bytes]:
    return (lambda: archive_reproductible(chemin)) if chemin.is_dir() else chemin.read_bytes


def morceaux(racine: Path) -> dict[str, Callable[[], bytes]]:
    """Les morceaux du coffre, par chemin dans l'atelier, chacun avec de quoi lire son contenu."""
    trouves: dict[str, Callable[[], bytes]] = {}
    for dossier in (racine / "07_taches" / "prive", racine / "99_local" / "juge"):
        if dossier.is_dir():
            for chemin in sorted(dossier.iterdir()):
                trouves[chemin.relative_to(racine).as_posix()] = _contenu(chemin)
    for manifeste in sorted((racine / "08_publications").glob("*/manifeste.json")):
        for run in json.loads(manifeste.read_text(encoding="utf-8"))["runs"]:
            if run["taches_non_publiees"]:
                banc = "runs_tau2" if run["banc"] == "τ²-bench" else "runs"
                chemin = racine / "99_local" / banc / run["run"]
                if not chemin.is_dir():
                    raise CoffreImpossible(
                        f"un run publié manque à 99_local/{banc}/ (manifeste {manifeste.parent.name})"
                    )
                trouves[chemin.relative_to(racine).as_posix()] = _contenu(chemin)
    return trouves


def destinataire(racine: Path) -> str:
    """La clé publique age du coffre, la première ligne age1… de 12_coffre/destinataire.txt."""
    chemin = racine / COFFRE / "destinataire.txt"
    lignes = chemin.read_text(encoding="utf-8").splitlines() if chemin.is_file() else []
    cle = next((ligne.strip() for ligne in lignes if ligne.strip().startswith("age1")), None)
    if cle is None:
        raise CoffreImpossible(
            f"aucune clé publique dans {COFFRE}/destinataire.txt ; la créer : age-keygen -o ~/.config/age/poa.txt, "
            "puis copier sa ligne « Public key: age1… » (la partie age1…) dans ce fichier"
        )
    return cle


def chiffreur_age(cle: str) -> Chiffreur:
    """Chiffre pour une clé publique, par le programme age."""
    if shutil.which("age") is None:
        raise CoffreImpossible("le programme age manque : sudo apt install age")

    def chiffrer(donnees: bytes) -> bytes:
        return subprocess.run(["age", "-r", cle], input=donnees, capture_output=True, check=True).stdout

    return chiffrer


def mettre_a_jour(racine: Path, chiffrer: Chiffreur, maintenant: str | None = None) -> Bilan:
    """Chiffre les morceaux nouveaux ou changés, marque les absents, réécrit l'index s'il a changé."""
    date = maintenant or datetime.now(UTC).isoformat(timespec="seconds")
    coffre, local = racine / COFFRE, racine / INDEX_LOCAL
    if not local.is_file() and (coffre / "index.age").is_file():
        raise CoffreImpossible(
            f"l'index en clair manque ({INDEX_LOCAL}) ; le déchiffrer d'abord : "
            f"age -d -i <clé privée> {COFFRE}/index.age > {INDEX_LOCAL}"
        )
    index: dict[str, dict[str, object]] = json.loads(local.read_text(encoding="utf-8")) if local.is_file() else {}
    suivant = max((int(str(e["numero"])) for e in index.values()), default=0) + 1
    bilan = Bilan()
    presents = morceaux(racine)
    for chemin, lire in presents.items():
        donnees = lire()
        empreinte = f"sha256:{hashlib.sha256(donnees).hexdigest()}"
        entree = index.get(chemin)
        if entree is not None:
            fichier = coffre / f"{int(str(entree['numero'])):05d}.age"
            if entree["empreinte"] == empreinte and fichier.is_file() and "absent_depuis" not in entree:
                bilan.inchanges += 1
                continue
            numero = int(str(entree["numero"]))
            bilan.changes += 1
        else:
            numero, suivant = suivant, suivant + 1
            bilan.nouveaux += 1
        coffre.mkdir(exist_ok=True)
        (coffre / f"{numero:05d}.age").write_bytes(chiffrer(donnees))
        index[chemin] = {"numero": numero, "empreinte": empreinte, "octets": len(donnees), "chiffre_le": date}
    for chemin, entree in index.items():
        if chemin not in presents and "absent_depuis" not in entree:
            entree["absent_depuis"] = date
            bilan.absents += 1
    if bilan.nouveaux or bilan.changes or bilan.absents or not (coffre / "index.age").is_file():
        texte = json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(texte, encoding="utf-8")
        coffre.mkdir(exist_ok=True)
        (coffre / "index.age").write_bytes(chiffrer(texte.encode("utf-8")))
    return bilan


def main(arguments: list[str] | None = None) -> int:
    racine = Path(__file__).resolve().parents[2]
    try:
        bilan = mettre_a_jour(racine, chiffreur_age(destinataire(racine)))
    except (CoffreImpossible, subprocess.CalledProcessError) as erreur:
        print(f"Coffre non mis à jour : {erreur}", file=sys.stderr)
        return 2
    print(
        f"Coffre : {bilan.nouveaux} morceau(x) nouveau(x), {bilan.changes} changé(s), {bilan.inchanges} inchangé(s), "
        f"{bilan.absents} disparu(s) de l'atelier."
    )
    if bilan.nouveaux or bilan.changes or bilan.absents:
        print(f"À commiter : {COFFRE}/ ; la copie en ligne attend la poussée.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
