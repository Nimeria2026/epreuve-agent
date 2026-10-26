"""Les données de τ²-bench, récupérées au commit figé, empreinte vérifiée, dans 99_local/tau2/.

Le paquet `tau2` ne contient pas ses données : il les lit dans `$TAU2_DATA_DIR`
(`tau2.utils.utils.DATA_DIR`). Ce module en télécharge les seuls fichiers dont le domaine airline
a besoin, depuis raw.githubusercontent.com, au commit de la version 1.0.1 de Sierra, celui que
fixe `pyproject.toml`, et le fichier de tâches de τ²-bench-Verified d'Amazon AGI à son commit.
S'y ajoutent les conversations airline de référence que Sierra publie dans
`data/tau2/results/final/` (4 agents, 50 tâches, 4 essais chacun, simulateur gpt-4.1), au même
commit de la version 1.0.1, où elles n'ont pas changé depuis leur entrée du 2025-06-10
(`2026-10-08_journal_tau2.md`, onzième entrée).
Chaque fichier est comparé à son empreinte sha256 relevée le 2026-10-08
(`00_docs/sources/2026-10-08_faits_tau2_bench.md`) ; un écart arrête tout. Licence des deux
dépôts : MIT, lue et datée le 2026-10-08.

Disposition locale, hors git :

    99_local/tau2/donnees/tau2/domains/airline/   base, politique, tâches de Sierra, découpage
    99_local/tau2/donnees/tau2/user_simulator/    consignes du simulateur d'utilisateur
    99_local/tau2/jeux/sierra.json                tâches de Sierra, version 1.0.1
    99_local/tau2/jeux/verified.json              tâches de τ²-bench-Verified
    99_local/tau2/jeux/publie.json                tâches embarquées dans les conversations publiées
    99_local/tau2/publies/<agent>.json            conversations publiées d'un agent, avec leur note

`donnees/` est le `TAU2_DATA_DIR` du serveur. Les jeux partagent la base et la politique,
identiques octet pour octet ; seul le fichier de tâches change. Le jeu `publie` n'est pas
téléchargé : il est tiré des tâches que chaque fichier de conversations publiées embarque, les
mêmes dans les quatre, celles qui ont servi à noter ces conversations ; `verifier` le refait.

Ce module n'importe pas τ²-bench : la bibliothèque standard suffit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

type Jeu = Literal["sierra", "verified", "publie"]
JEUX: tuple[Jeu, ...] = ("sierra", "verified", "publie")
JEU_PUBLIE: Jeu = "publie"

SIERRA = "sierra-research/tau2-bench"
COMMIT_SIERRA = "fc0055dc4e0a316c3f83133267fbd6faaa770992"
"""Version 1.0.1 de τ²-bench, du 2026-07-16 ; airline identique à la tête de main du 2026-10-06."""
VERIFIED = "amazon-agi/tau2-bench-verified"
COMMIT_VERIFIED = "864350a8971a8f8ee9e7b8472e2edc380a806b0c"
"""Tête de main de τ²-bench-Verified, du 2026-04-02."""

DELAI_SECONDES = 60


class DonneesInvalides(Exception):
    """Un fichier téléchargé n'a pas l'empreinte relevée : rien n'est gardé."""


@dataclass(frozen=True)
class Fichier:
    """Un fichier d'un dépôt à un commit, sa place dans le dossier local et son empreinte."""

    depot: str
    commit: str
    chemin: str
    destination: str
    sha256: str
    octets: int

    @property
    def url(self) -> str:
        return f"https://raw.githubusercontent.com/{self.depot}/{self.commit}/{self.chemin}"


def _sierra(chemin: str, sha256: str, octets: int) -> Fichier:
    return Fichier(SIERRA, COMMIT_SIERRA, f"data/{chemin}", f"donnees/{chemin}", sha256, octets)


DONNEES: tuple[Fichier, ...] = (
    _sierra(
        "tau2/domains/airline/db.json", "1af9fea6e03ca7ca15a22bb3fcaf3e351393e3fc9070b6777947da8996f7531b", 7042725
    ),
    _sierra("tau2/domains/airline/policy.md", "10dc0525421521208be39cee235bba84a16e2bcba9899eb93d92cd81d2f62fc4", 7676),
    _sierra(
        "tau2/domains/airline/tasks.json", "ccd8ba737b4cc371415af70151187788f728d6108d0916e73bb4317b40542052", 155528
    ),
    _sierra(
        "tau2/domains/airline/split_tasks.json",
        "b22ced4d9a9850ac9aea31c53bdcb6d6009058140bd9acc7db37c1d36222ba8b",
        1443,
    ),
    _sierra(
        "tau2/user_simulator/simulation_guidelines.md",
        "740a29dfa64d7bc08eea3bf7493575b914a63f744acbaf7f199ee07eddaf72d3",
        1449,
    ),
    _sierra(
        "tau2/user_simulator/simulation_guidelines_tools.md",
        "cbf3d8a4d8642fd04e559862f1afef55d7dd4e6a7e727ca49e239023c599de0c",
        2747,
    ),
)
"""Ce que τ²-bench lit dans TAU2_DATA_DIR pour airline."""

TACHES: dict[Jeu, Fichier] = {
    "sierra": Fichier(
        SIERRA,
        COMMIT_SIERRA,
        "data/tau2/domains/airline/tasks.json",
        "jeux/sierra.json",
        "ccd8ba737b4cc371415af70151187788f728d6108d0916e73bb4317b40542052",
        155528,
    ),
    "verified": Fichier(
        VERIFIED,
        COMMIT_VERIFIED,
        "data/tau2/domains/airline/tasks.json",
        "jeux/verified.json",
        "202f0cdb1cf4bc20b8a3284f00e212882a8dda8eaab81d1d69a5dd9676911ebe",
        150905,
    ),
}
"""Le fichier de tâches de chaque jeu téléchargé, rangé à part de TAU2_DATA_DIR."""


def _publie(fichier: str, nom: str, sha256: str, octets: int) -> Fichier:
    return Fichier(SIERRA, COMMIT_SIERRA, f"data/tau2/results/final/{fichier}", f"publies/{nom}.json", sha256, octets)


PUBLIES: dict[str, Fichier] = {
    "claude_3_7_sonnet": _publie(
        "claude-3-7-sonnet-20250219_airline_default_gpt-4.1-2025-04-14_4trials.json",
        "claude_3_7_sonnet",
        "40a2c6a246eab27db5cdefda895fbe7f44be78a23d300817248534aa606d66de",
        10551448,
    ),
    "gpt_4_1": _publie(
        "gpt-4.1-2025-04-14_airline_default_gpt-4.1-2025-04-14_4trials.json",
        "gpt_4_1",
        "31d19e79b8ddc5934a60701f913ff5fefb41dee5e68f7b813c26254ab2e2d5c8",
        8790399,
    ),
    "gpt_4_1_mini": _publie(
        "gpt-4.1-mini-2025-04-14_airline_base_gpt-4.1-2025-04-14_4trials.json",
        "gpt_4_1_mini",
        "41788956547a100fb8e34baf159f36dd1f07f0765798a5fdaf917576c5dba9d0",
        9781836,
    ),
    "o4_mini": _publie(
        "o4-mini-2025-04-16_airline_default_gpt-4.1-2025-04-14_4trials.json",
        "o4_mini",
        "6a3a354c9bce42b52905af096e9cea6f555548acbb17b567fd403c356df7b4ec",
        7599444,
    ),
}
"""Les conversations airline de référence de Sierra, par agent (licence MIT du dépôt, lue le 2026-10-08)."""


def racine_depot() -> Path:
    """La racine du dépôt POA : le premier dossier parent qui porte arborescence.toml."""
    for dossier in Path(__file__).resolve().parents:
        if (dossier / "arborescence.toml").is_file():
            return dossier
    raise FileNotFoundError("racine du dépôt introuvable (arborescence.toml)")


def dossier_local(racine: Path | None = None) -> Path:
    """99_local/tau2/ du dépôt."""
    return (racine or racine_depot()) / "99_local" / "tau2"


def dossier_donnees(dossier: Path) -> Path:
    """Le TAU2_DATA_DIR d'un dossier local."""
    return dossier / "donnees"


def fichier_taches(dossier: Path, jeu: Jeu) -> Path:
    """Le fichier de tâches d'un jeu dans un dossier local."""
    return dossier / ("jeux/publie.json" if jeu == JEU_PUBLIE else TACHES[jeu].destination)


def fichier_publie(dossier: Path, agent: str) -> Path:
    """Les conversations publiées d'un agent dans un dossier local."""
    return dossier / PUBLIES[agent].destination


def _taches_publiees(dossier: Path) -> bytes:
    """Le fichier du jeu publie : les tâches embarquées, identiques dans les quatre fichiers publiés."""
    embarquees = [json.loads(fichier_publie(dossier, agent).read_text(encoding="utf-8"))["tasks"] for agent in PUBLIES]
    if any(t != embarquees[0] for t in embarquees[1:]):
        raise DonneesInvalides("les conversations publiées n'embarquent pas toutes les mêmes tâches")
    return (json.dumps(embarquees[0], ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def empreinte_fichier(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _a_jour(fichier: Fichier, dossier: Path) -> bool:
    chemin = dossier / fichier.destination
    return chemin.is_file() and empreinte_fichier(chemin) == fichier.sha256


def _telecharger(fichier: Fichier, dossier: Path) -> None:
    destination = dossier / fichier.destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(fichier.url, timeout=DELAI_SECONDES) as reponse:
        contenu: bytes = reponse.read()
    obtenue = hashlib.sha256(contenu).hexdigest()
    if obtenue != fichier.sha256:
        raise DonneesInvalides(f"{fichier.url} : empreinte {obtenue}, attendue {fichier.sha256} ; rien n'est gardé")
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as provisoire:
        provisoire.write(contenu)
    Path(provisoire.name).replace(destination)


def recuperer(dossier: Path | None = None) -> Path:
    """Télécharge ce qui manque ou a changé, vérifie chaque empreinte, et rend le dossier local."""
    dossier = dossier or dossier_local()
    for fichier in (*DONNEES, *TACHES.values(), *PUBLIES.values()):
        if not _a_jour(fichier, dossier):
            _telecharger(fichier, dossier)
    jeu = fichier_taches(dossier, JEU_PUBLIE)
    contenu = _taches_publiees(dossier)
    if not jeu.is_file() or jeu.read_bytes() != contenu:
        jeu.parent.mkdir(parents=True, exist_ok=True)
        jeu.write_bytes(contenu)
    return dossier


def verifier(dossier: Path) -> list[str]:
    """Les fichiers absents ou modifiés d'un dossier local ; vide s'il est complet."""
    manquants = [f.destination for f in (*DONNEES, *TACHES.values(), *PUBLIES.values()) if not _a_jour(f, dossier)]
    jeu = fichier_taches(dossier, JEU_PUBLIE)
    publies_complets = not any(f.destination in manquants for f in PUBLIES.values())
    if not (publies_complets and jeu.is_file() and jeu.read_bytes() == _taches_publiees(dossier)):
        manquants.append("jeux/publie.json")
    return manquants


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(
        prog="python -m bancs_publics.tau2_bench.donnees",
        description="Récupère les données d'airline de τ²-bench, de Verified et les conversations publiées.",
    )
    analyse.add_argument("--dossier", type=Path, default=None, help="dossier local (99_local/tau2 par défaut)")
    options = analyse.parse_args(arguments)
    try:
        dossier = recuperer(options.dossier)
    except (OSError, DonneesInvalides) as erreur:
        print(f"Données de τ²-bench non récupérées : {erreur}", file=sys.stderr)
        return 1
    nombre = len(DONNEES) + len(TACHES) + len(PUBLIES)
    print(f"Données de τ²-bench à jour dans {dossier} ({nombre} fichiers, empreintes vérifiées ; jeu publie refait).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
