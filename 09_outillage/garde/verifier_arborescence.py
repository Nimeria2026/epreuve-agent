#!/usr/bin/env python3
"""Garde de l'arborescence du dépôt POA.

Compare le dépôt au plan déclaré dans arborescence.toml et signale tout écart.

Modes :
  (sans option)     parcourt tout le dépôt ;
  --chemin C [...]  contrôle un ou plusieurs chemins, existants ou à créer
                    (un « / » final désigne un dossier) ;
  --indexe          contrôle les fichiers ajoutés à l'index git (crochet pre-commit) ;
  --hook-claude     lit sur l'entrée standard l'appel d'outil envoyé par Claude Code
                    et bloque l'écriture si le chemin sort du plan.

Codes de sortie :
  0  conforme ;
  1  écarts trouvés (ou, en mode --hook-claude, erreur sans blocage) ;
  2  plan illisible, ou écriture bloquée en mode --hook-claude (code attendu par Claude Code).

N'utilise que la bibliothèque standard. Python 3.11 ou plus (tomllib), ou le paquet tomli.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

RACINE = Path(__file__).resolve().parents[2]
FICHIER_PLAN = "arborescence.toml"
DOSSIER_ADR = PurePosixPath("00_docs/adr")
MOTIF_ADR = re.compile(r"^\d{4}-\d{2}-\d{2}_(\d{4})_[a-z0-9_]+\.md$")
FICHIERS_ADR_LIBRES = {"README.md", "modele_adr.md"}
MOTIF_PAR_DEFAUT = r"^[a-z0-9_][a-z0-9_.-]*$"

RAPPEL = (
    "Si c'est un vrai problème rencontré : écrire un ADR dans 00_docs/adr/, mettre à jour "
    "arborescence.toml (version et numéro d'ADR), noter la décision dans JOURNAL.md. "
    "Sinon : ranger le fichier à un emplacement prévu par le plan."
)


class PlanIllisible(Exception):
    """Le plan arborescence.toml ne peut pas être lu."""


def charger_plan(racine: Path = RACINE) -> dict[str, Any]:
    """Lit arborescence.toml à la racine du dépôt."""
    if sys.version_info >= (3, 11):  # noqa: UP036 (la garde tourne aussi avec le python3 du système)
        import tomllib
    else:  # Python 3.10 : le paquet tomli, s'il est installé
        try:
            import tomli as tomllib
        except ModuleNotFoundError as erreur:
            raise PlanIllisible("Python 3.11 ou plus est requis pour lire le plan (ou le paquet tomli).") from erreur
    chemin = racine / FICHIER_PLAN
    try:
        with chemin.open("rb") as flux:
            plan: dict[str, Any] = tomllib.load(flux)
            return plan
    except FileNotFoundError as erreur:
        raise PlanIllisible(f"{FICHIER_PLAN} est introuvable à la racine du dépôt.") from erreur
    except tomllib.TOMLDecodeError as erreur:
        raise PlanIllisible(f"{FICHIER_PLAN} est mal formé : {erreur}") from erreur


class Garde:
    """Applique le plan à des chemins relatifs à la racine du dépôt."""

    def __init__(self, plan: dict[str, Any], racine: Path) -> None:
        self.plan = plan
        self.racine = racine
        nommage: dict[str, Any] = plan.get("nommage", {})
        self.motif = re.compile(nommage.get("motif", MOTIF_PAR_DEFAUT))
        self.exceptions = set(nommage.get("exceptions", []))
        self.libres = [PurePosixPath(c) for c in nommage.get("libre", [])]
        ignorer: dict[str, Any] = plan.get("ignorer", {})
        self.ignores_chemins = [PurePosixPath(c) for c in ignorer.get("chemins", [])]
        self.ignores_noms = set(ignorer.get("noms", []))
        self.ignores_suffixes = tuple(ignorer.get("suffixes", []))
        racine_plan: dict[str, Any] = plan.get("racine", {})
        self.fichiers_racine = set(racine_plan.get("fichiers", []))
        self.dossiers_racine = set(racine_plan.get("dossiers", []))
        self.zones: dict[str, dict[str, Any]] = plan.get("zones", {})
        # Les noms déclarés explicitement sont acceptés même s'ils ne suivent pas le motif.
        declares = self.fichiers_racine | self.dossiers_racine
        for zone in self.zones.values():
            for entree in zone.get("entrees", []):
                if not any(joker in entree for joker in "*?["):
                    declares.add(entree.rstrip("/"))
            declares.update(zone.get("sans_extension", []))
        self.declares = declares

    # --- règles élémentaires -------------------------------------------------------------

    def est_ignore(self, rel: PurePosixPath) -> bool:
        for chemin in self.ignores_chemins:
            if rel == chemin or chemin in rel.parents:
                return True
        return any(
            partie in self.ignores_noms or (self.ignores_suffixes and partie.endswith(self.ignores_suffixes))
            for partie in rel.parts
        )

    def nom_valide(self, nom: str) -> bool:
        return nom in self.exceptions or nom in self.declares or bool(self.motif.fullmatch(nom))

    def nom_libre(self, chemin: PurePosixPath) -> bool:
        """Vrai si le chemin est strictement sous un chemin à nommage libre (ADR 0003)."""
        return any(libre in chemin.parents for libre in self.libres)

    def controler(self, rel: PurePosixPath, est_fichier: bool) -> list[str]:
        """Contrôle un chemin relatif à la racine, qu'il existe ou qu'il soit à créer."""
        if not rel.parts or self.est_ignore(rel):
            return []
        ecarts: list[str] = []
        parties = rel.parts

        for rang, nom in enumerate(parties, start=1):
            if self.nom_libre(PurePosixPath(*parties[:rang])):
                break
            if not self.nom_valide(nom):
                ecarts.append(
                    f"{rel} : le nom « {nom} » ne respecte pas le nommage "
                    "(minuscules, chiffres, _ - ., sans accent ni espace)."
                )
                break

        premier = parties[0]
        if len(parties) == 1:
            if est_fichier and premier not in self.fichiers_racine:
                ecarts.append(f"{rel} : fichier non prévu à la racine.")
            elif not est_fichier and premier not in self.dossiers_racine:
                ecarts.append(f"{rel}/ : dossier non prévu à la racine.")
            return ecarts

        if premier not in self.dossiers_racine:
            ecarts.append(f"{rel} : le dossier « {premier}/ » n'est pas prévu à la racine.")
            return ecarts

        zone = self.zones.get(premier)
        if zone is None:
            return ecarts

        entrees = zone.get("entrees", [])
        second = parties[1]
        etiquette = second if (est_fichier and len(parties) == 2) else f"{second}/"
        if not any(fnmatch.fnmatchcase(etiquette, entree) for entree in entrees):
            ecarts.append(
                f"{rel} : « {etiquette} » n'est pas une entrée prévue dans {premier}/ "
                f"(permises : {', '.join(entrees)})."
            )

        if est_fichier:
            nom = parties[-1]
            suffixe = PurePosixPath(nom).suffix.lower()
            permises = [e.lower() for e in zone.get("extensions", [])]
            if nom not in zone.get("sans_extension", []) and suffixe not in permises:
                ecarts.append(
                    f"{rel} : extension « {suffixe or 'aucune'} » non permise dans {premier}/ "
                    f"(permises : {', '.join(permises)})."
                )
        return ecarts

    # --- contrôles d'ensemble ------------------------------------------------------------

    def controler_obligatoires(self) -> list[str]:
        ecarts: list[str] = []
        for nom_zone, zone in self.zones.items():
            dossier = self.racine / nom_zone
            if not dossier.is_dir():
                continue
            for obligatoire in zone.get("obligatoires", []):
                if not (dossier / obligatoire.rstrip("/")).exists():
                    ecarts.append(f"{nom_zone}/{obligatoire} : obligatoire et absent.")
        return ecarts

    def controler_adr(self) -> list[str]:
        ecarts: list[str] = []
        version = self.plan.get("version")
        if not isinstance(version, int) or version < 1:
            ecarts.append(f"{FICHIER_PLAN} : « version » doit être un entier à partir de 1.")
        numero = str(self.plan.get("adr", ""))
        dossier = self.racine / DOSSIER_ADR
        if not dossier.is_dir():
            return [*ecarts, f"{DOSSIER_ADR}/ est introuvable : le plan doit s'appuyer sur un ADR."]
        numeros: set[str] = set()
        for fichier in sorted(dossier.iterdir()):
            if fichier.is_dir():
                ecarts.append(f"{DOSSIER_ADR / fichier.name}/ : pas de sous-dossier dans adr/.")
                continue
            if fichier.name in FICHIERS_ADR_LIBRES:
                continue
            correspondance = MOTIF_ADR.match(fichier.name)
            if correspondance is None:
                ecarts.append(f"{DOSSIER_ADR / fichier.name} : un ADR se nomme AAAA-MM-JJ_NNNN_titre.md.")
            else:
                numeros.add(correspondance.group(1))
        if numero not in numeros:
            ecarts.append(f"{FICHIER_PLAN} cite l'ADR « {numero} », introuvable dans {DOSSIER_ADR}/.")
        return ecarts

    def parcourir(self) -> list[str]:
        """Parcourt tout le dépôt. Un dossier en écart n'est pas exploré plus loin."""
        ecarts: list[str] = []

        def visiter(dossier: Path) -> None:
            for entree in sorted(dossier.iterdir(), key=lambda p: p.name):
                rel = PurePosixPath(entree.relative_to(self.racine).as_posix())
                if self.est_ignore(rel):
                    continue
                est_fichier = not entree.is_dir() or entree.is_symlink()
                ecarts_entree = self.controler(rel, est_fichier)
                ecarts.extend(ecarts_entree)
                if not est_fichier and not ecarts_entree:
                    visiter(entree)

        visiter(self.racine)
        ecarts.extend(self.controler_obligatoires())
        ecarts.extend(self.controler_adr())
        return ecarts


# --- modes d'appel -----------------------------------------------------------------------


def chemins_indexes(racine: Path) -> list[str]:
    """Fichiers ajoutés, copiés ou renommés dans l'index git."""
    sortie = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACR", "-z"],
        cwd=racine,
        capture_output=True,
        check=True,
    )
    return [chemin for chemin in sortie.stdout.decode("utf-8").split("\0") if chemin]


def rapporter(ecarts: list[str], plan: dict[str, Any]) -> int:
    if not ecarts:
        print(f"Arborescence conforme au plan (version {plan.get('version')}, ADR {plan.get('adr')}).")
        return 0
    print(f"{len(ecarts)} écart(s) par rapport au plan {FICHIER_PLAN} :")
    for ecart in ecarts:
        print(f"  - {ecart}")
    print(RAPPEL)
    return 1


def mode_hook_claude(racine: Path) -> int:
    """Crochet PreToolUse de Claude Code : code 2 pour bloquer, avec le motif sur stderr."""
    try:
        donnees = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("Garde : appel illisible, écriture laissée passer.", file=sys.stderr)
        return 1
    entree: dict[str, Any] = donnees.get("tool_input") or {}
    cible = entree.get("file_path") or entree.get("notebook_path")
    if not cible:
        return 0
    chemin = Path(cible)
    if not chemin.is_absolute():
        chemin = Path(donnees.get("cwd") or ".") / chemin
    try:
        rel = chemin.resolve().relative_to(racine)
    except ValueError:
        return 0  # écriture hors du dépôt : pas l'affaire de la garde
    try:
        garde = Garde(charger_plan(racine), racine)
    except PlanIllisible as erreur:
        print(f"Garde : {erreur} Écriture laissée passer.", file=sys.stderr)
        return 1
    ecarts = garde.controler(PurePosixPath(rel.as_posix()), est_fichier=True)
    if not ecarts:
        return 0
    print("Écriture bloquée par la garde de l'arborescence :", file=sys.stderr)
    for ecart in ecarts:
        print(f"  - {ecart}", file=sys.stderr)
    print(RAPPEL, file=sys.stderr)
    return 2


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    racine = RACINE
    if args[:1] == ["--hook-claude"]:
        return mode_hook_claude(racine)
    try:
        plan = charger_plan(racine)
    except PlanIllisible as erreur:
        print(f"Garde : {erreur}", file=sys.stderr)
        return 2
    garde = Garde(plan, racine)
    ecarts: list[str]
    if not args:
        ecarts = garde.parcourir()
    elif args[0] == "--chemin" and len(args) > 1:
        ecarts = []
        for chemin in args[1:]:
            ecarts.extend(garde.controler(PurePosixPath(chemin), est_fichier=not chemin.endswith("/")))
    elif args == ["--indexe"]:
        ecarts = []
        for chemin in chemins_indexes(racine):
            ecarts.extend(garde.controler(PurePosixPath(chemin), est_fichier=True))
        ecarts.extend(garde.controler_adr())
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return rapporter(ecarts, plan)


if __name__ == "__main__":
    sys.exit(main())
