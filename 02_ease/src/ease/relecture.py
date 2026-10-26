"""Relecture des désaccords entre le juge et une personne, un par un, dans le terminal.

    python -m ease.relecture [--qui alexandre]    # make relire

Pour chaque désaccord du dernier étalonnage, la personne voit le texte, l'affirmation, sa propre
réponse, celle du juge et le passage qu'il cite, puis tranche : son étiquette était fausse, le
juge se trompe, ou l'affirmation est ambiguë et doit être réécrite. Les étiquettes d'origine ne
sont jamais retouchées : les décisions vont dans relecture_<qui>.json, à côté.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ease.chargement import racine_depot
from ease.etalon import DOSSIER, QUI, dossier_etalon, empreinte, enonces_des_taches

DECISIONS = {"1": "etiquette_fausse", "2": "juge_errone", "3": "affirmation_ambigue", "p": "indecis"}
LIBELLES = {
    "etiquette_fausse": "mon étiquette était fausse",
    "juge_errone": "le juge se trompe",
    "affirmation_ambigue": "l'affirmation est ambiguë",
    "indecis": "je ne sais pas",
}


def dernier_etalonnage(qui: str, dossier: Path | None = None, prefixe: str = "etalonnage") -> Path:
    candidats = sorted((dossier or racine_depot() / "99_local" / "juge").glob(f"{prefixe}_*_{qui}.json"))
    if not candidats:
        raise FileNotFoundError(f"aucun étalonnage pour {qui} : lancer make etalonner d'abord")
    return candidats[-1]


def desaccords(etalonnage: Path) -> list[dict[str, Any]]:
    comparaisons = cast(list[dict[str, Any]], json.loads(etalonnage.read_text(encoding="utf-8")))
    return [c for c in comparaisons if cast(dict[str, Any], c["verdict"])["vrai"] is not c["humain"]]


def cle_du_critere(comparaison: dict[str, Any]) -> str:
    """La clé gardée par l'étalonnage, ou, pour un étalonnage d'avant les contextes, l'empreinte de
    l'affirmation seule."""
    return str(comparaison.get("critere") or empreinte(str(comparaison["affirmation"])))


def _fichier(dossier: Path, qui: str) -> Path:
    return dossier / f"relecture_{qui}.json"


def lire_decisions(dossier: Path = DOSSIER, qui: str = QUI) -> list[dict[str, str]]:
    chemin = _fichier(dossier, qui)
    return cast(list[dict[str, str]], json.loads(chemin.read_text(encoding="utf-8"))) if chemin.exists() else []


def _oui_non(valeur: object) -> str:
    return "vrai" if valeur is True else "faux" if valeur is False else "illisible"


def relire(
    etalonnage: Path,
    dossier: Path = DOSSIER,
    qui: str = QUI,
    lire: Callable[[str], str] = input,
    ecrire: Callable[[str], None] = print,
) -> int:
    """Pose chaque désaccord pas encore tranché ; chaque décision est gardée aussitôt."""
    decisions = lire_decisions(dossier, qui)
    faites = {(d["texte"], d["critere"]) for d in decisions}
    tous = desaccords(etalonnage)
    a_faire = [c for c in tous if (c["texte"]["cle"], cle_du_critere(c)) not in faites]
    enonces = enonces_des_taches()
    tranches = 0
    for comparaison in a_faire:
        texte = cast(dict[str, str], comparaison["texte"])
        verdict = cast(dict[str, Any], comparaison["verdict"])
        ecrire(f"\n=== Désaccord {len(tous) - len(a_faire) + tranches + 1} sur {len(tous)} ===")
        ecrire(f"Ce qu'on demandait à l'agent : {enonces.get(texte['tache'], texte['tache'])}")
        if comparaison.get("contexte"):
            ecrire("\n--- Ce que l'agent avait sous les yeux ---\n" + str(comparaison["contexte"]))
        ecrire("\n--- Texte ---\n" + texte["texte"])
        ecrire("\n--- Affirmation ---\n" + str(comparaison["affirmation"]))
        ecrire(f"\nTa réponse : {_oui_non(comparaison['humain'])}. Le juge : {_oui_non(verdict['vrai'])}.")
        if verdict.get("preuve"):
            ecrire(f"Passage cité par le juge : « {verdict['preuve']} »".replace("« ", "« ").replace(" »", " »"))
        choix = ""
        while choix not in (*DECISIONS, "q"):
            choix = (
                lire(
                    "\n1 = mon étiquette était fausse, 2 = le juge se trompe, 3 = affirmation ambiguë, "
                    "p = je ne sais pas, q = quitter : "
                )
                .strip()
                .lower()
            )
        if choix == "q":
            break
        decisions.append(
            {
                "texte": texte["cle"],
                "critere": cle_du_critere(comparaison),
                "humain": _oui_non(comparaison["humain"]),
                "juge": _oui_non(verdict["vrai"]),
                "decision": DECISIONS[choix],
                "le": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        )
        provisoire = _fichier(dossier, qui).with_suffix(".tmp")
        provisoire.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        provisoire.replace(_fichier(dossier, qui))
        tranches += 1
    # Le fichier garde aussi les décisions des étalonnages passés : le bilan ne compte que celles-ci.
    ici = {(c["texte"]["cle"], cle_du_critere(c)) for c in tous}
    comptes = Counter(d["decision"] for d in decisions if (d["texte"], d["critere"]) in ici)
    detail = ", ".join(f"{n} {LIBELLES[d]}" for d, n in sorted(comptes.items()))
    ecrire(f"\n{sum(comptes.values())} désaccord(s) tranché(s) sur {len(tous)}" + (f" : {detail}." if detail else "."))
    return tranches


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m ease.relecture", description="Relecture des désaccords.")
    analyse.add_argument("--qui", default=QUI)
    analyse.add_argument("--controle", action="store_true", help="les désaccords du jeu de contrôle")
    analyse.add_argument("--dure", action="store_true", help="les désaccords du jeu de la tranche dure")
    options = analyse.parse_args(arguments)
    prefixe = ("dure_" if options.dure else "") + ("controle" if options.controle else "etalonnage")
    try:
        relire(
            dernier_etalonnage(options.qui, prefixe=prefixe),
            dossier_etalon(options.dure, options.controle),
            qui=options.qui,
        )
    except FileNotFoundError as erreur:
        print(f"Rien à relire : {erreur}.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
