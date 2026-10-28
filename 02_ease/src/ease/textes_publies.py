"""Les textes écrits d'une publication : ceux qui portent un résultat, que les pages placent tels
quels (cadrage de la page Épreuve d'agent du 2026-10-23, section 9, choix P2 ; cadrage du 2026-10-28,
figer la publication v1, section 3 ; JOURNAL, entrées 354 et 355).

Ils s'écrivent à la main dans ease/textes/<sujet>.yaml, sans aucun nombre écrit à la main, ni en
chiffres ni en lettres : chaque nombre est un renvoi à son endroit dans donnees.json, entre accolades,
que EASE remplace par la valeur. « {socle.par_candidat.QW.essais.pourcent} % » s'écrit « 92 % » ;
« {graves.taches_bloquees.nombre:lettres_f} tâche » s'écrit « une tâche ».

Un chemin passe par les clés des dictionnaires, par le rang d'un élément de liste, par sa clé (`cle`,
`identifiant`, `tache`) ou, pour une paire, par ses deux modèles (« QW-FN ») ; DS, QW et FN nomment
les trois modèles mesurés ; « nombre » compte les éléments d'une liste ou d'un dictionnaire. Après
deux-points, « lettres » écrit l'entier en lettres, « lettres_f » au féminin, « Lettres » et
« Lettres_f » avec une majuscule.

Un nombre de méthode, qui n'est pas un résultat, s'écrit dans <span class="hors-donnees">…</span>.
Ce que les textes affirment sans nombre, un écart établi ou non, un modèle devant l'autre, se déclare
sous « suppose », chemin et valeur attendue.

Un nombre écrit à la main, un renvoi qui ne mène à rien ou une supposition que les données démentent
arrête make publier : un nombre ne peut pas être le mauvais, une phrase ne peut pas contredire la
mesure.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import yaml

from ease.publication import nombres_affiches

DOSSIER = Path(__file__).resolve().parent / "textes"
"""Un fichier par publication : constat.yaml, premier_post.yaml."""

ALIAS = {
    "DS": "agent_seul_deepseek_flash_1017",
    "QW": "agent_seul_qwen_local_100k",
    "FN": "agent_seul_qwen_flash_next_strata",
}
"""Les noms courts des modèles mesurés dans un renvoi."""

SUPPOSE = "suppose"
"""La clé des suppositions : ce que les textes affirment sans nombre, contrôlé sur les données."""

COMPTE = "nombre"
"""Le dernier morceau d'un chemin qui compte les éléments d'une liste ou d'un dictionnaire."""

FORMES = ("lettres", "lettres_f", "Lettres", "Lettres_f")
RENVOI = re.compile(r"\{([A-Za-z0-9_.-]+)(?::(" + "|".join(FORMES) + r"))?\}")
HORS_DONNEES = re.compile(r'(?s)<span class="hors-donnees">.*?</span>')
MOTS_NOMBRES = re.compile(
    r"(?i)\b(?:zéro|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|quinze|seize"
    r"|vingts?|trente|quarante|cinquante|soixante|cents?|mille|moitié|tiers|double|triple)\b"
)
"""Les nombres écrits en lettres. « Un » et « une » n'y sont pas : ce sont d'abord des articles."""

LETTRES = (
    "zéro",
    "un",
    "deux",
    "trois",
    "quatre",
    "cinq",
    "six",
    "sept",
    "huit",
    "neuf",
    "dix",
    "onze",
    "douze",
    "treize",
    "quatorze",
    "quinze",
    "seize",
    "dix-sept",
    "dix-huit",
    "dix-neuf",
    "vingt",
)
MOINS = re.compile(r"^-(?=\d)")
DESIGNANTS = ("cle", "identifiant", "tache")


class TextesImpossibles(ValueError):
    """Les textes d'une publication manquent, ne se lisent pas, portent un nombre écrit à la main, un
    renvoi qui ne mène à rien ou une supposition que les données démentent."""


def lire_textes(sujet: str, dossier: Path = DOSSIER) -> dict[str, Any]:
    """Les textes d'une publication, tels qu'écrits, renvois et suppositions compris : un dictionnaire
    de textes, de listes et de dictionnaires, dont chaque feuille est une chaîne ; sous « suppose », un
    chemin par valeur attendue."""
    chemin = dossier / f"{sujet}.yaml"
    if not chemin.is_file():
        raise TextesImpossibles(f"aucun texte écrit pour {sujet} : {chemin} manque")
    textes = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    if not isinstance(textes, dict):
        raise TextesImpossibles(f"{chemin.name} : un dictionnaire de textes est attendu")
    textes = cast(dict[str, Any], textes)
    suppose = textes.get(SUPPOSE, {})
    if not isinstance(suppose, dict) or not all(
        isinstance(c, str) and (v is None or isinstance(v, str | int | bool))
        for c, v in cast(dict[Any, Any], suppose).items()
    ):
        raise TextesImpossibles(
            f"{chemin.name}, {SUPPOSE} : un chemin par valeur attendue, texte, entier, vrai, faux ou nul"
        )
    for endroit, valeur in _feuilles({c: v for c, v in textes.items() if c != SUPPOSE}):
        if not isinstance(valeur, str):
            raise TextesImpossibles(f"{chemin.name}, {endroit} : un texte est attendu, pas {type(valeur).__name__}")
    return textes


def _feuilles(valeur: object, endroit: str = "") -> Iterator[tuple[str, object]]:
    """Chaque feuille et son endroit : « constats[0].phrase »."""
    if isinstance(valeur, dict):
        for cle, sous in cast(dict[Any, Any], valeur).items():
            yield from _feuilles(sous, f"{endroit}.{cle}" if endroit else str(cle))
    elif isinstance(valeur, list):
        for rang, sous in enumerate(cast(list[Any], valeur)):
            yield from _feuilles(sous, f"{endroit}[{rang}]")
    else:
        yield endroit, valeur


def _designe(element: dict[str, Any], morceau: str) -> bool:
    """Un élément de liste désigné par sa clé, son identifiant, sa tâche, ou par les deux modèles d'une
    paire, dans un ordre ou dans l'autre."""
    if ALIAS.get(morceau, morceau) in (element.get(d) for d in DESIGNANTS):
        return True
    deux = [ALIAS.get(m, m) for m in morceau.split("-")]
    return len(deux) == 2 and deux[0] != deux[1] and {element.get("a"), element.get("b")} == set(deux)


def atteindre(donnees: dict[str, Any], chemin: str) -> object:
    """Ce qui se trouve au bout d'un chemin dans les données."""
    courant: object = donnees
    for morceau in chemin.split("."):
        courant = _un_pas(courant, morceau, chemin)
    return courant


def _un_pas(courant: object, morceau: str, chemin: str) -> object:
    """Un morceau de chemin : une clé, un rang, un élément désigné ou un compte."""
    cle = ALIAS.get(morceau, morceau)
    if isinstance(courant, dict):
        dictionnaire = cast(dict[str, Any], courant)
        if cle in dictionnaire:
            return dictionnaire[cle]
    if isinstance(courant, list):
        liste = cast(list[Any], courant)
        if cle.isdigit() and int(cle) < len(liste):
            return liste[int(cle)]
        elements = [cast(dict[str, Any], e) for e in liste if isinstance(e, dict)]
        trouves = [e for e in elements if _designe(e, morceau)]
        if len(trouves) == 1:
            return trouves[0]
    if morceau == COMPTE and isinstance(courant, dict | list):
        return len(cast(dict[Any, Any] | list[Any], courant))
    raise TextesImpossibles(f"{{{chemin}}} : « {morceau} » ne mène à rien")


def en_lettres(entier: int, forme: str) -> str:
    """Un entier de zéro à vingt écrit en lettres : « un », ou « une » au féminin, avec ou sans
    majuscule."""
    if not 0 <= entier < len(LETTRES):
        raise TextesImpossibles(
            f"{entier} ne s'écrit pas en lettres dans un texte publié : au-delà de vingt, en chiffres"
        )
    mot = "une" if entier == 1 and forme.endswith("_f") else LETTRES[entier]
    return mot[0].upper() + mot[1:] if forme[0].isupper() else mot


def valeur(donnees: dict[str, Any], chemin: str, forme: str | None = None) -> str:
    """La valeur d'un renvoi, écrite pour la page ; un texte ou un entier, jamais un nombre à virgule
    flottante, que la page écrirait à sa façon. Avec une forme, un entier écrit en lettres."""
    trouve = atteindre(donnees, chemin)
    if forme is not None:
        if isinstance(trouve, bool) or not isinstance(trouve, int):
            raise TextesImpossibles(f"{{{chemin}:{forme}}} : un entier est attendu, pas {type(trouve).__name__}")
        return en_lettres(trouve, forme)
    if isinstance(trouve, bool) or not isinstance(trouve, str | int):
        raise TextesImpossibles(f"{{{chemin}}} : un texte ou un entier est attendu, pas {type(trouve).__name__}")
    return MOINS.sub("−", str(trouve))


def ecrits_a_la_main(texte: str) -> list[str]:
    """Les nombres d'un texte qui ne viennent pas d'un renvoi ni d'un passage hors données : en
    chiffres, puis en lettres."""
    sans = HORS_DONNEES.sub(" ", RENVOI.sub(" ", texte))
    return nombres_affiches(sans) + MOTS_NOMBRES.findall(re.sub(r"<[^>]+>", " ", sans))


def rendre(texte: str, donnees: dict[str, Any]) -> str:
    """Un texte, ses renvois remplacés par leur valeur ; refusé s'il porte un nombre écrit à la main."""
    ecrits = ecrits_a_la_main(texte)
    if ecrits:
        raise TextesImpossibles(f"nombre écrit à la main : {', '.join(ecrits)}")
    return RENVOI.sub(lambda m: valeur(donnees, m.group(1), m.group(2)), texte)


def suppositions_dementies(suppose: dict[str, Any], donnees: dict[str, Any]) -> list[str]:
    """Les suppositions des textes que les données démentent, ou qui ne mènent à rien."""
    dementies: list[str] = []
    for chemin, attendu in suppose.items():
        try:
            trouve = atteindre(donnees, chemin)
        except TextesImpossibles as erreur:
            dementies.append(f"{SUPPOSE} {erreur}")
            continue
        voulu = ALIAS.get(attendu, attendu) if isinstance(attendu, str) else attendu
        if trouve != voulu or isinstance(trouve, bool) != isinstance(voulu, bool):
            dementies.append(f"{SUPPOSE} {chemin} = {attendu!r}, les données disent {trouve!r}")
    return dementies


def _rendre_tout(textes: object, donnees: dict[str, Any], endroit: str, erreurs: list[str]) -> object:
    if isinstance(textes, dict):
        return {
            cle: _rendre_tout(sous, donnees, f"{endroit}.{cle}" if endroit else str(cle), erreurs)
            for cle, sous in cast(dict[str, Any], textes).items()
        }
    if isinstance(textes, list):
        return [
            _rendre_tout(sous, donnees, f"{endroit}[{rang}]", erreurs)
            for rang, sous in enumerate(cast(list[Any], textes))
        ]
    try:
        return rendre(cast(str, textes), donnees)
    except TextesImpossibles as erreur:
        erreurs.append(f"{endroit} : {erreur}")
        return textes


def textes_controles(sujet: str, donnees: dict[str, Any], dossier: Path = DOSSIER) -> dict[str, Any]:
    """Les textes d'une publication, rendus sur ses données, sans les suppositions ; refusés au premier
    nombre écrit à la main, renvoi qui ne mène à rien ou supposition démentie, tous dits."""
    textes = lire_textes(sujet, dossier)
    erreurs = suppositions_dementies(textes.pop(SUPPOSE, {}), donnees)
    rendus = _rendre_tout(textes, donnees, "", erreurs)
    if erreurs:
        raise TextesImpossibles(f"textes de {sujet} : " + " ; ".join(erreurs))
    return cast(dict[str, Any], rendus)
