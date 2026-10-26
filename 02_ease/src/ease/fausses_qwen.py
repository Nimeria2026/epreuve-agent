"""Réponses fausses du jeu de contrôle, écrites par Qwen en local : make fausses-qwen.

    python -m ease.fausses_qwen [--forcer] [--taches t06,t09]
    python -m ease.fausses_qwen --dure [--taches h07]   # make fausses-qwen JEU=dure

Le jeu de contrôle du juge manque de réponses fausses : les modèles réussissent presque tout. Ni
Claude, qui a écrit les premières et réglé les critères dessus, ni DeepSeek, qui sert de juge, ne
doivent les écrire. Qwen, servi par make qwen, en écrit quatre par tâche jugée, à partir de la
tâche et du contexte de l'agent seulement, sans voir les critères. Elles vont dans
controle/fausses_qwen.json, lues comme des textes « ecrit » du jeu ; l'erreur voulue y est notée
mais n'est jamais montrée à la personne qui étiquette. Avec --taches, seules ces tâches sont
écrites, ajoutées au fichier s'il existe (critères arrivés plus tard, t06 et t09 le 2026-10-07).

Avec --dure, le contrôle des consignes de la tranche dure (etalon/dure/controle/, JOURNAL,
cent-quatre-vingt-neuvième entrée). Une tâche de la tranche écrit à plusieurs destinataires, et
chaque consigne vise les siens : les quatre réponses d'une tâche se répartissent entre ses groupes
de destinataires, les plus visés d'abord, une demande par groupe, avec les faits des consignes qui
liraient ce courriel, jamais les consignes. Chaque réponse garde ses destinataires (« a »).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ease.etalon import CONTROLE, CONTROLE_DURE, PAR_TACHE_FAUSSES, Critere, enonces_des_taches, lire_criteres

ADRESSE = "http://127.0.0.1:30100/v1/chat/completions"
MODELE = "qwen3.8-27b-w4a16"
"""Ceux de 03_orchestrations/src/orchestrations/configurations/qwen_local.yaml."""

CONSIGNE = """Voici une tâche confiée à l'assistant d'une PME française, et ce qu'il avait sous les yeux.

Tâche : {enonce}

Ce que l'assistant avait sous les yeux : {contexte}

Destinataire du courriel : {destinataires}

Écris {nombre} courriels que cet assistant aurait pu envoyer, chacun avec au moins une erreur, \
différente d'un courriel à l'autre : des erreurs qu'un assistant pressé ou mal informé pourrait \
commettre, certaines visibles, d'autres discrètes. Chaque courriel reste crédible, avec une \
formule d'appel et une signature.

Réponds seulement en JSON, sans rien d'autre : {{"courriels": [{{"courriel": "le texte du \
courriel", "erreur": "l'erreur glissée, en une phrase"}}]}}"""

type Appel = Callable[[dict[str, Any]], dict[str, Any]]


def appel_local(adresse: str = ADRESSE, delai_secondes: float = 900.0) -> Appel:
    def appeler(corps: dict[str, Any]) -> dict[str, Any]:
        requete = urllib.request.Request(
            adresse, data=json.dumps(corps).encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(requete, timeout=delai_secondes) as reponse:
            return cast(dict[str, Any], json.loads(reponse.read().decode("utf-8")))

    return appeler


def lire_courriels(contenu: str) -> list[dict[str, str]]:
    """Les courriels de la réponse : le JSON entre la première et la dernière accolade."""
    debut, fin = contenu.find("{"), contenu.rfind("}")
    if debut < 0 or fin < debut:
        raise ValueError("aucun JSON dans la réponse de Qwen")
    donnees = cast(dict[str, Any], json.loads(contenu[debut : fin + 1]))
    courriels = cast(list[dict[str, Any]], donnees.get("courriels") or [])
    return [
        {"texte": str(c.get("courriel") or "").strip(), "erreur_voulue": str(c.get("erreur") or "").strip()}
        for c in courriels
        if str(c.get("courriel") or "").strip()
    ]


def groupes_de_destinataires(criteres: list[Critere]) -> list[tuple[list[str], str]]:
    """Tranche dure : les groupes de destinataires des consignes d'une tâche, les plus visés d'abord,
    chacun avec le contexte des consignes qui liraient son courriel (les faits, sans les consignes)."""
    groupes = sorted(
        {c.destinataires for c in criteres}, key=lambda g: (-sum(c.destinataires == g for c in criteres), sorted(g))
    )
    return [
        (sorted(g), "\n".join(dict.fromkeys(c.contexte for c in criteres if c.destinataires & g and c.contexte)))
        for g in groupes
    ]


def generer(
    appeler: Appel,
    dossier: Path = CONTROLE,
    par_tache: int = PAR_TACHE_FAUSSES,
    forcer: bool = False,
    taches: set[str] | None = None,
) -> list[dict[str, str]]:
    """Fait écrire par Qwen les réponses fausses de chaque tâche jugée (de taches seulement, si donné),
    et les garde. Renvoie les réponses écrites cette fois."""
    sortie = dossier / "fausses_qwen.json"
    deja: list[dict[str, Any]] = []
    if taches is not None and sortie.exists():
        deja = cast(list[dict[str, Any]], json.loads(sortie.read_text(encoding="utf-8")))
        if presentes := sorted(taches & {d["tache"] for d in deja}):
            raise FileExistsError(f"{sortie.name} a déjà des réponses pour {', '.join(presentes)}")
    elif sortie.exists() and not forcer:
        raise FileExistsError(f"{sortie.name} existe déjà : le refaire changerait des textes peut-être étiquetés")
    enonces = enonces_des_taches()
    gardees: list[dict[str, Any]] = []
    for tache, (destinataires, criteres) in lire_criteres(dossier).items():
        if taches is not None and tache not in taches:
            continue
        dure = any(c.destinataires for c in criteres)
        if dure:
            groupes = groupes_de_destinataires(criteres)
            demandes = [
                (a, contexte or "rien d'autre que la tâche", len(range(i, par_tache, len(groupes))))
                for i, (a, contexte) in enumerate(groupes)
                if i < par_tache
            ]
        else:
            demandes = [(sorted(destinataires), criteres[0].contexte, par_tache)]
        for a, contexte, nombre in demandes:
            message = CONSIGNE.format(
                enonce=enonces[tache], contexte=contexte, destinataires=", ".join(a), nombre=nombre
            )
            reponse = appeler({"model": MODELE, "messages": [{"role": "user", "content": message}]})
            choix = cast(list[dict[str, Any]], reponse.get("choices") or [{}])
            contenu = str(cast(dict[str, Any], choix[0].get("message") or {}).get("content") or "")
            courriels = lire_courriels(contenu)[:nombre]
            if len(courriels) < nombre:
                raise ValueError(f"{tache} : Qwen a rendu {len(courriels)} courriel(s) sur {nombre}")
            le = datetime.now(UTC).isoformat(timespec="seconds")
            vers: dict[str, Any] = {"a": a} if dure else {}
            gardees += [{"tache": tache, **vers, **c, "auteur": MODELE, "le": le} for c in courriels]
    dossier.mkdir(parents=True, exist_ok=True)
    provisoire = sortie.with_suffix(".tmp")
    provisoire.write_text(json.dumps(deja + gardees, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    provisoire.replace(sortie)
    return gardees


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m ease.fausses_qwen", description=__doc__)
    analyse.add_argument("--forcer", action="store_true", help="réécrit fausses_qwen.json")
    analyse.add_argument("--taches", help="ces tâches seulement, par préfixe : t06,t09")
    analyse.add_argument("--dure", action="store_true", help="le contrôle des consignes de la tranche dure")
    options = analyse.parse_args(arguments)
    controle = CONTROLE_DURE if options.dure else CONTROLE
    taches: set[str] | None = None
    if options.taches:
        prefixes = [p.strip() for p in str(options.taches).split(",") if p.strip()]
        taches = {t for t in lire_criteres(controle) if any(t.startswith(p) for p in prefixes)}
        if not taches:
            print(f"Aucune tâche jugée ne commence par {options.taches}.", file=sys.stderr)
            return 2
    try:
        gardees = generer(appel_local(), controle, forcer=options.forcer, taches=taches)
    except FileExistsError as erreur:
        print(f"Rien fait : {erreur}.", file=sys.stderr)
        return 2
    except (urllib.error.URLError, TimeoutError, ConnectionError) as erreur:
        print(f"Qwen ne répond pas ({erreur}) : lancer make qwen dans un autre terminal.", file=sys.stderr)
        return 3
    except ValueError as erreur:
        print(f"Réponse de Qwen inutilisable : {erreur}. Relancer make fausses-qwen.", file=sys.stderr)
        return 4
    ici = controle.relative_to(controle.parents[1])
    print(f"{len(gardees)} réponse(s) fausse(s) écrite(s) par Qwen dans {ici}/fausses_qwen.json.")
    print("Ne les lis pas avant de les étiqueter : make etiqueter CONTROLE=1" + (" JEU=dure." if options.dure else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
