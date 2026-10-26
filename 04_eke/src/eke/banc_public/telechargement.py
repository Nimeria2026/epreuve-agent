"""Le jeu fr-bench-pdf2md dans `99_local/`, fichier par fichier, sous manifeste.

Le jeu vit sur Hugging Face ; une version s'y désigne par son commit. Tout passe par l'API
publique, en bibliothèque standard :

1. la liste des fichiers de la version, avec la taille de chacun et l'empreinte que le dépôt en
   donne (sha256 pour un fichier stocké en LFS, identifiant de blob git sinon) ;
2. chaque fichier, vérifié contre cette empreinte avant d'être rangé ;
3. le manifeste, écrit une fois tout rangé : pour chaque fichier, sa source, la version, sa
   taille et son sha256.

À chaque lancement, les fichiers rangés sont comparés au manifeste : un fichier manquant, en
trop, d'une autre taille ou d'un autre sha256 arrête tout (`EcartJeu`). Un téléchargement
interrompu reprend : un fichier déjà rangé n'est gardé que s'il correspond à l'annonce du dépôt.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from eke.contrat import racine_depot

DEPOT = "pulsia/fr-bench-pdf2md"
REVISION = "6ee20957e8dadf8523a4b9033498dee03c0b0368"
"""Version des scores publiés, décision d'Alexandre (journal de l'étape 6, neuvième entrée)."""
API = "https://huggingface.co/api/datasets/{depot}/revision/{revision}?blobs=true"
SOURCE = "https://huggingface.co/datasets/{depot}/resolve/{revision}/{chemin}"
DOSSIER = racine_depot() / "99_local" / "bancs_documents" / "fr_bench_pdf2md"
AGENT = "eke-banc-public (projet Epreuve d'agent)"
ESSAIS = 8
"""Tentatives par fichier ; le dépôt répond 429 quand on le presse, avec un délai à respecter."""
FILS = 4

LireUrl = Callable[[str], bytes]


class EcartJeu(Exception):
    """Le jeu sur disque, le manifeste et l'annonce du dépôt ne disent pas la même chose."""


@dataclass(frozen=True)
class Annonce:
    """Un fichier tel que l'API du dépôt l'annonce pour la version."""

    chemin: str
    taille: int
    sha256: str | None
    """Empreinte LFS, donnée pour les fichiers stockés en LFS (les PDF)."""
    blob_git: str
    """Identifiant git du contenu : sha1 de « blob <taille>\\0 » suivi du contenu."""


@dataclass(frozen=True)
class Entree:
    """Une ligne du manifeste."""

    chemin: str
    source: str
    revision: str
    taille: int
    sha256: str


@dataclass(frozen=True)
class Manifeste:
    jeu: str
    revision: str
    api: str
    ecrit_le: str
    fichiers: tuple[Entree, ...]

    def en_json(self) -> str:
        donnees = asdict(self)
        donnees["fichiers"] = [asdict(e) for e in self.fichiers]
        return json.dumps(donnees, ensure_ascii=False, indent=1) + "\n"


def dossier_donnees(dossier: Path, revision: str = REVISION) -> Path:
    return dossier / revision[:7]


def chemin_manifeste(dossier: Path, revision: str = REVISION) -> Path:
    return dossier / f"manifeste_{revision[:7]}.json"


def empreinte_fichier(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def blob_git(donnees: bytes) -> str:
    entete = f"blob {len(donnees)}\0".encode()
    return hashlib.sha1(entete + donnees, usedforsecurity=False).hexdigest()


def _lire_url(url: str) -> bytes:
    """GET avec reprise : 429 et 5xx attendent le délai demandé (Retry-After), 10 s au plus."""
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT})
    for essai in range(ESSAIS):
        try:
            with urllib.request.urlopen(requete, timeout=120) as reponse:
                contenu: bytes = reponse.read()
                return contenu
        except urllib.error.HTTPError as erreur:
            if (erreur.code != 429 and erreur.code < 500) or essai == ESSAIS - 1:
                raise
            attente = erreur.headers.get("Retry-After", "10")
            time.sleep(min(float(attente) if attente.isdigit() else 10.0, 10.0))
        except (urllib.error.URLError, TimeoutError):
            if essai == ESSAIS - 1:
                raise
            time.sleep(2.0 * (essai + 1))
    raise AssertionError("inatteignable")


def _chemin_sur(chemin: str) -> PurePosixPath:
    """Un chemin relatif du dépôt, sans « .. » ni racine : il reste sous le dossier des données."""
    pur = PurePosixPath(chemin)
    if pur.is_absolute() or ".." in pur.parts or not pur.parts:
        raise EcartJeu(f"chemin refusé dans l'annonce du dépôt : {chemin!r}")
    return pur


def retenu(chemin: str) -> bool:
    """Les fichiers du jeu qu'EKE garde : la carte (licence) et tout `pdfs/`."""
    return chemin == "README.md" or chemin.startswith("pdfs/")


def annonces(
    lire_url: LireUrl = _lire_url,
    revision: str = REVISION,
    depot: str = DEPOT,
    garder: Callable[[str], bool] = retenu,
) -> list[Annonce]:
    """Les fichiers retenus de la version, tels que l'API les annonce."""
    url = API.format(depot=depot, revision=revision)
    reponse: dict[str, Any] = json.loads(lire_url(url))
    if reponse.get("sha") != revision:
        raise EcartJeu(f"l'API rend la version {reponse.get('sha')!r}, pas {revision}")
    resultat: list[Annonce] = []
    for fichier in reponse["siblings"]:
        chemin = str(fichier["rfilename"])
        if not garder(chemin):
            continue
        _chemin_sur(chemin)
        lfs: dict[str, Any] | None = fichier.get("lfs")
        sha256 = str(lfs["sha256"]) if lfs is not None else None
        resultat.append(Annonce(chemin, int(fichier["size"]), sha256, str(fichier["blobId"])))
    return sorted(resultat, key=lambda a: a.chemin)


def verifier_annonce(annonce: Annonce, donnees: bytes) -> None:
    """EcartJeu si le contenu n'est pas celui que le dépôt annonce."""
    if len(donnees) != annonce.taille:
        raise EcartJeu(f"{annonce.chemin} : {len(donnees)} octets, le dépôt en annonce {annonce.taille}")
    if annonce.sha256 is not None:
        trouve = hashlib.sha256(donnees).hexdigest()
        if trouve != annonce.sha256:
            raise EcartJeu(f"{annonce.chemin} : sha256 {trouve}, le dépôt annonce {annonce.sha256}")
    elif blob_git(donnees) != annonce.blob_git:
        raise EcartJeu(f"{annonce.chemin} : blob git {blob_git(donnees)}, le dépôt annonce {annonce.blob_git}")


def source(chemin: str, revision: str = REVISION, depot: str = DEPOT) -> str:
    return SOURCE.format(depot=depot, revision=revision, chemin=urllib.parse.quote(chemin))


def _ranger(annonce: Annonce, donnees_dir: Path, lire_url: LireUrl, revision: str, depot: str) -> Entree:
    cible = donnees_dir / _chemin_sur(annonce.chemin)
    if cible.exists():
        verifier_annonce(annonce, cible.read_bytes())
    else:
        contenu = lire_url(source(annonce.chemin, revision, depot))
        verifier_annonce(annonce, contenu)
        cible.parent.mkdir(parents=True, exist_ok=True)
        partiel = cible.with_name(cible.name + ".partiel")
        partiel.write_bytes(contenu)
        partiel.replace(cible)
    return Entree(
        annonce.chemin, source(annonce.chemin, revision, depot), revision, annonce.taille, empreinte_fichier(cible)
    )


def telecharger(
    dossier: Path = DOSSIER,
    lire_url: LireUrl = _lire_url,
    revision: str = REVISION,
    dire: Callable[[str], None] = print,
    fils: int = FILS,
    depot: str = DEPOT,
    garder: Callable[[str], bool] = retenu,
) -> Manifeste:
    """Range la version dans `dossier/<revision[:7]>/` et écrit son manifeste.

    Si le manifeste existe déjà, rien n'est téléchargé : le jeu est vérifié contre lui.
    `depot` et `garder` servent à un autre jeu de Hugging Face (OmniExtractBench).
    """
    if chemin_manifeste(dossier, revision).exists():
        return verifier(dossier, revision)
    liste = annonces(lire_url, revision, depot, garder)
    donnees_dir = dossier_donnees(dossier, revision)
    total = sum(a.taille for a in liste)
    dire(f"{len(liste)} fichiers, {total} octets, version {revision}")
    entrees: list[Entree] = []

    def ranger(annonce: Annonce) -> Entree:
        return _ranger(annonce, donnees_dir, lire_url, revision, depot)

    with ThreadPoolExecutor(max_workers=fils) as executeur:
        for rang, entree in enumerate(executeur.map(ranger, liste), 1):
            entrees.append(entree)
            if rang % 100 == 0 or rang == len(liste):
                dire(f"{rang}/{len(liste)} fichiers rangés")
    manifeste = Manifeste(
        jeu=depot,
        revision=revision,
        api=API.format(depot=depot, revision=revision),
        ecrit_le=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        fichiers=tuple(sorted(entrees, key=lambda e: e.chemin)),
    )
    _fichiers_en_trop(donnees_dir, {e.chemin for e in manifeste.fichiers})
    chemin_manifeste(dossier, revision).write_text(manifeste.en_json(), encoding="utf-8")
    return verifier(dossier, revision)


def lire_manifeste(dossier: Path, revision: str = REVISION) -> Manifeste:
    chemin = chemin_manifeste(dossier, revision)
    if not chemin.exists():
        raise EcartJeu(f"pas de manifeste : {chemin} ; lancer d'abord le téléchargement")
    brut: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
    fichiers = tuple(Entree(**e) for e in brut["fichiers"])
    return Manifeste(brut["jeu"], brut["revision"], brut["api"], brut["ecrit_le"], fichiers)


def _fichiers_sur_disque(donnees_dir: Path) -> set[str]:
    return {p.relative_to(donnees_dir).as_posix() for p in donnees_dir.rglob("*") if p.is_file()}


def _fichiers_en_trop(donnees_dir: Path, attendus: Iterable[str]) -> None:
    en_trop = sorted(_fichiers_sur_disque(donnees_dir) - set(attendus))
    if en_trop:
        raise EcartJeu(f"{len(en_trop)} fichiers hors manifeste, dont {en_trop[:3]}")


def verifier(dossier: Path = DOSSIER, revision: str = REVISION) -> Manifeste:
    """Compare chaque fichier rangé à son manifeste ; EcartJeu au premier désaccord constaté."""
    manifeste = lire_manifeste(dossier, revision)
    if manifeste.revision != revision or any(e.revision != revision for e in manifeste.fichiers):
        raise EcartJeu(f"le manifeste ne porte pas sur la version {revision}")
    donnees_dir = dossier_donnees(dossier, revision)
    attendus = {e.chemin for e in manifeste.fichiers}
    manquants = sorted(attendus - _fichiers_sur_disque(donnees_dir))
    if manquants:
        raise EcartJeu(f"{len(manquants)} fichiers du manifeste manquent, dont {manquants[:3]}")
    _fichiers_en_trop(donnees_dir, attendus)
    for entree in manifeste.fichiers:
        chemin = donnees_dir / _chemin_sur(entree.chemin)
        taille = chemin.stat().st_size
        if taille != entree.taille:
            raise EcartJeu(f"{entree.chemin} : {taille} octets, le manifeste en note {entree.taille}")
        if empreinte_fichier(chemin) != entree.sha256:
            raise EcartJeu(f"{entree.chemin} : sha256 différent de celui du manifeste")
    return manifeste
