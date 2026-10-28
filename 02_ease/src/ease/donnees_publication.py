"""Les données d'une publication, calculées par EASE sur les runs que retient le rapport (cadrage du
générateur des images, 2026-10-19, §3) : chaque chiffre y est déjà arrondi et écrit comme il
s'affichera, avec sa fourchette, et l'écart de chaque paire de candidats. Le générateur des images ne
lit que ce fichier et ne calcule rien ; la vidéo du premier post, dans le dépôt Nimeria, lit sa part
(cadrage du générateur, §6).

Le premier post (cadrage de la publication, §4) : les 63 tâches publiques du socle de Calorelle,
métier par métier puis ensemble, agent seul, cinq essais par tâche. Pour chaque candidat : les
essais réussis et leur fourchette (bootstrap à deux niveaux, celui du rapport), les tâches réussies
cinq fois sur cinq et leur fourchette (bootstrap sur les tâches) ; pour chaque chiffre, l'écart
de chaque paire de candidats (`paires`), établi quand sa fourchette exclut zéro ; avec deux candidats,
le même écart aussi sous `ecarts`, le format d'avant les trois modèles. Une tâche sans run complet rend
les données impossibles : une publication ne se fait pas sur un rapport provisoire.

Le constat (cadrage de la publication, §5 à §7, choix C1 à C4 et du 2026-10-20) : la réussite et
les tâches réussies 5 fois sur 5 sur tout le socle de Calorelle, cachées comprises et jamais
nommées ; l'horizon à 50 % de la tranche dure, et sa courbe ; la durée médiane d'une exécution au
socle ; les fautes graves des tâches à contrôle grave du socle, sans gardien puis avec ; τ²-bench.
Chaque écart, paire par paire, dit s'il est établi : par la fourchette de la différence (bootstrap
sur les tâches), et pour l'horizon, quand les deux fourchettes ne se touchent pas.

Les nombres s'écrivent comme dans le rapport : virgule décimale, espace insécable, pourcentages et
points à une décimale, sans « ,0 ».

Depuis la racine du dépôt :

    python -m ease.donnees_publication premier_post --sortie <données.json> [--video <donnees.json>]
    python -m ease.donnees_publication constat --sortie <données.json>
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from ease.cachees import cachees_du_jeu, dossier_cachees_du_jeu
from ease.candidats import DOSSIER as DOSSIER_CANDIDATS
from ease.candidats import lire_candidat
from ease.chargement import racine_depot
from ease.classement import durees_a_jour, lire_classement
from ease.contrats.resultat_execution import ResultatExecution
from ease.contrats.tache import JugeRequis, Tache
from ease.fiches import lire_resultat
from ease.gravite import Gravite, exposee, fautes_graves, lire_gravite
from ease.horizon import ajuster
from ease.rapport import (
    REPETITIONS,
    Mesures,
    RapportImpossible,
    bilan_horizon,
    bootstrap,
    bootstrap_ecart,
    bootstrap_plusieurs,
    durees_cachees,
    rassembler,
    sans_noms,
    taux,
)
from ease.statistiques import intervalle_wilson
from ease.taches import dossier_du_jeu, taches_du_jeu

NB = " "
VERSION = 1
"""Version du format des données ; elle change quand un champ change de sens."""

PUBLIQUES_PUBLIEES = tuple(f"t{n:02d}" for n in range(1, 64))
"""Les tâches publiques du socle que le premier post et le constat publient, t01 à t63, par leur
numéro : le socle de Calorelle complet, lot de t46 à t63 compris (choix du 2026-10-21, JOURNAL,
deux-cent-trente-cinquième entrée). Si le jeu public grandit encore, les publications gardent leurs
tâches (deux-cent-vingt-sixième entrée)."""

CACHEES_PUBLIEES = 20
"""Le nombre de tâches cachées du socle que le constat publie. Elles se comptent sans se nommer : une
cachée de plus ou de moins arrête le constat, qui ne change pas de tâches en silence."""


def publiques_publiees() -> list[Tache]:
    """Les tâches publiques du socle publiées, t01 à t63, dans l'ordre du jeu."""
    retenues = [t for t in taches_du_jeu("public") if t.identifiant.split("_")[0] in PUBLIQUES_PUBLIEES]
    if len(retenues) != len(PUBLIQUES_PUBLIEES):
        raise RapportImpossible(
            f"{len(retenues)} tâches publiques du socle numérotées de {PUBLIQUES_PUBLIEES[0]} "
            f"à {PUBLIQUES_PUBLIEES[-1]}, {len(PUBLIQUES_PUBLIEES)} attendues"
        )
    return retenues


def cachees_publiees() -> list[Tache]:
    """Les tâches cachées du socle publiées, refusées si leur nombre a changé."""
    cachees = cachees_du_jeu("public")
    if len(cachees) != CACHEES_PUBLIEES:
        raise RapportImpossible(f"{len(cachees)} tâches cachées dans le socle, {CACHEES_PUBLIEES} publiées")
    return cachees


CANDIDATS = (
    ("agent_seul_deepseek_flash_1017", "DeepSeek V4.1 Flash"),
    ("agent_seul_qwen_local_100k", "Qwen 3.8 27B"),
    ("agent_seul_qwen_flash_next_strata", "Qwen3.8-Flash-Next"),
)
"""Les trois modèles du premier post et du constat (cadrage de la publication, §2 ; JOURNAL, entrée
322), dans l'ordre des images : DeepSeek dans sa version du 17 octobre, mesurée en entier (entrée
231) ; Qwen à 102 400 jetons de contexte (entrée 226), assemblé de ses deux candidats (PARTS) ;
Qwen3.8-Flash-Next sous Strata, sur la même carte (entrées 295 à 343)."""

PARTS = {"agent_seul_qwen_local_100k": ("agent_seul_qwen_local_100k", "agent_seul_qwen_local")}
"""Les références qui s'assemblent de plusieurs candidats, tâche par tâche, le premier d'abord (JOURNAL,
entrées 226 et 273) : une tâche prend les runs du premier candidat qui l'a mesurée en entier à sa
version courante. Qwen à 40 960 jetons ne garde que des tâches qu'il n'a jamais vues coupées par le
contexte ; les deux candidats ne diffèrent que par le contexte et les délais qui vont avec
(_verifier_parts)."""

DIFFERENCES_PERMISES = frozenset(
    {"identifiant", "nom", "service_modele", "arguments", "delai_secondes", "contexte_serveur", "empreinte_de"}
)
"""Ce en quoi les déclarations des parts d'une référence peuvent différer : leur nom, le contexte servi,
le fichier de configuration et les délais ; leurs configurations, par le seul délai d'un appel."""

DETAILS = {
    "agent_seul_deepseek_flash_1017": "par API",
    "agent_seul_qwen_local_100k": "en local, une carte RTX 3090",
    "agent_seul_qwen_flash_next_strata": "en local, la même carte",
}
"""Comment chaque référence est servie, dit sous son nom."""

COURTS = {
    "agent_seul_deepseek_flash_1017": "DeepSeek",
    "agent_seul_qwen_local_100k": "Qwen 27B",
    "agent_seul_qwen_flash_next_strata": "Flash-Next",
}
"""Le nom court de chaque référence, celui des écarts et des légendes serrées (maquette à trois
modèles, JOURNAL, entrée 339)."""

DETAILS_CONSTAT = {
    "agent_seul_deepseek_flash_1017": "par API, en heures creuses",
    "agent_seul_qwen_local_100k": "en local, une carte RTX 3090, contexte de 102 400 jetons",
    "agent_seul_qwen_flash_next_strata": "en local, la même carte et environ 50 Go de mémoire vive, compressé à 3 bits",
}
"""Comment chaque référence est servie, dit sur le tableau du constat (cadrage de la publication, §5) :
le contexte de Qwen y est, c'est lui qui l'arrête sur les tâches longues. Il est déclaré au contexte de
sa première part, les autres parts entre parenthèses avec leurs tâches (detail_avec_parts)."""

GRADUATIONS_MINUTES = (30.0, 60.0)
"""Les graduations intérieures de l'axe des durées de la courbe d'horizon, entre ses deux bornes."""

POINTS_DE_COURBE = 48
"""Le nombre de durées où la courbe d'horizon et sa bande sont calculées, à intervalles égaux en
logarithme sur la plage des tâches."""

METIERS = (
    ("administration", "Administration et RH"),
    ("commercial", "Commercial"),
    ("comptabilite", "Comptabilité"),
    ("planning", "Planning"),
    ("relation_client", "Relation client"),
)
"""Les métiers du socle, par la famille de chaque tâche, dans l'ordre des images."""

LIBELLES_FAUTES = {
    "fuite": "une donnée qui sort",
    "argent": "de l'argent engagé",
    "consigne_piegee": "une consigne piégée suivie",
    "envoi_a_un_inconnu": "un envoi à un inconnu",
    "securite": "une règle de sécurité non tenue",
    "infraction": "une infraction à la loi",
}
"""Le nom court de chaque sorte de faute grave sur les pages ; la définition reste celle de
gravite.yaml (cadrage du 2026-10-28, figer la publication v1, section 2)."""

ENSEMBLE = {2: "Les deux", 3: "Les trois", 4: "Les quatre", 5: "Les cinq", 6: "Les six"}
"""Le libellé de la ligne qui réunit les métiers, selon leur nombre."""

VIDEO = {
    "agent_seul_deepseek_flash_1017": "deepseek",
    "agent_seul_qwen_local_100k": "qwen",
    "agent_seul_qwen_flash_next_strata": "flashnext",
}
"""Les clés de donnees.json, le fichier que lit la vidéo du premier post."""

EXEMPLE = ("t10_rib_par_un_collegue", "agent_seul_qwen_local_100k", 1, 1)
"""L'essai raconté par l'image 3 (cadrage de la publication, §4) : la tâche, le candidat, l'essai, et
le contrôle qu'il manque ; les données comptent, pour chaque candidat, les essais qui manquent ce
même contrôle."""

TAU2: tuple[tuple[str, str, float | None, float | None, str], ...] = (
    ("agent_seul_deepseek_flash_1017", "reproduction_tau2_deepseek_flash_1017", 0.733, None, "2026-10-26"),
    ("agent_seul_qwen_local_100k", "reproduction_tau2_qwen_local", 0.780, 0.024, "2026-10-26"),
    ("agent_seul_qwen_flash_next_strata", "reproduction_tau2_qwen_flash_next_strata", None, None, "2026-10-27"),
)
"""τ²-bench, compagnie aérienne : pour chaque référence, son candidat de reproduction, le score
publié sur OpenRouter et son écart type quand il en a un, et le jour du relevé (protocole de mesure,
partie 6 ; JOURNAL, entrées 114, 117, 273, 277 et 329), à relire le jour de la publication. Le
contrôle du banc repose sur les scores qui portent un écart type ; un score sans écart type vient de
peu de runs et bouge (DeepSeek 1017 : 77,3 % le 21 octobre, 73,3 % le 26) ; Flash-Next n'a pas de
score publié. Qwen garde son run à 40 960 jetons, aucune de ses tâches n'y étant coupée (entrée
228). Le score publié vient de dehors : il est daté et sourcé, et n'est pas calculé ici."""

SOURCE_TAU2 = "OpenRouter, relevé le {}"

DOSSIER_TAU2 = DOSSIER_CANDIDATS.parent / "candidats_tau2"
"""Les déclarations des candidats de τ²-bench, celles de mesure_tau2.DOSSIER, sans charger le banc."""

GRADUATIONS = (0.0, 0.5, 1.0)
"""Les graduations des axes de réussite, de 0 à 100 %."""

ECHELLE_TAUX = (0.6, 1.0, (0.6, 0.8, 1.0))
"""L'échelle des réussites sur la page Épreuve d'agent, de 60 à 100 %, et ses graduations : chaque
chiffre y porte sa position, de 0 à 100, parce que la page ne calcule rien (maquette de la page,
refonte 11)."""

GRADUATIONS_TAU2 = (0.5, 0.75, 1.0)
"""Les graduations de l'axe de τ²-bench, de 50 à 100 % : les scores y sont tous au-dessus de 50 %."""

MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

Groupes = list[list[ResultatExecution]]


def nombre(valeur: float, decimales: int) -> str:
    """Un nombre écrit comme dans le rapport : séparateur de milliers insécable, virgule décimale."""
    return f"{valeur:,.{decimales}f}".replace(",", NB).replace(".", ",")


def pourcent(valeur: float) -> str:
    """Une proportion en pourcentage, sans le signe : « 96,4 », « 100 »."""
    return nombre(100 * valeur, 1).removesuffix(",0")


def points(valeur: float) -> str:
    """Un écart de proportions en points : « 7,1 », « -13,3 »."""
    return nombre(100 * valeur, 1).removesuffix(",0")


def _proche(valeur: float) -> int:
    """L'entier le plus proche, une moitié allant au-dessus (round() de Python va au pair)."""
    return math.floor(valeur + 0.5)


def _position(valeur: float, bas: float, haut: float) -> float:
    """La place d'une valeur sur une échelle, de 0 à 100, bornée aux deux bouts, au centième."""
    return round(max(0.0, min(100.0, (valeur - bas) / (haut - bas) * 100)), 2)


def _place(c: dict[str, Any]) -> dict[str, Any]:
    """Un chiffre de réussite avec sa position sur l'échelle de la page, et celle de sa fourchette."""
    bas, haut, _ = ECHELLE_TAUX
    return c | {
        "position": _position(c["valeur"], bas, haut),
        "fourchette_position": [_position(b, bas, haut) for b in c["fourchette"]],
    }


def _minutes_de_grille(minutes: float, arrondi: Callable[[float], int] = _proche) -> str:
    """Une durée de la grille, écrite pour la page : à la minute sous une heure, aux cinq minutes
    au-delà (« 16 min », « 1 h 30 ») ; une décimale serait de trop pour une durée estimée (maquette
    de la page, refonte 11). Une borne « moins de » s'arrondit au-dessus (math.ceil), une borne
    « plus de » au-dessous (math.floor) : l'arrondi ne rend jamais la phrase fausse."""
    total = arrondi(minutes) if minutes < 60 else 5 * arrondi(minutes / 5)
    if total < 60:
        return f"{total}{NB}min"
    heures, reste = divmod(total, 60)
    return f"{heures}{NB}h{NB}{reste:02d}" if reste else f"{heures}{NB}h"


def _lecture_de_grille(valeur: float, plage: tuple[float, float]) -> str:
    """Un horizon écrit pour la page, comme lecture_horizon du rapport, arrondi."""
    if math.isinf(valeur):
        return f"au-delà de {_minutes_de_grille(plage[1], math.floor)}"
    if valeur == 0:
        return f"en deçà de {_minutes_de_grille(plage[0], math.ceil)}"
    return _minutes_de_grille(valeur)


def _fourchette_de_grille(fourchette: tuple[float, float], plage: tuple[float, float]) -> tuple[list[str], str]:
    """Les deux bornes d'une fourchette d'horizon, et la phrase qui la dit : « de moins de 16 min à
    38 min », ou « au-delà de 1 h 30 » quand elle est tout entière au-delà de la plus longue tâche."""
    bas, haut = fourchette
    debut = f"moins de {_minutes_de_grille(plage[0], math.ceil)}" if bas == 0 else _lecture_de_grille(bas, plage)
    fin = f"plus de {_minutes_de_grille(plage[1], math.floor)}" if math.isinf(haut) else _lecture_de_grille(haut, plage)
    if math.isinf(bas) or haut == 0:
        return [debut, fin], _lecture_de_grille(bas if math.isinf(bas) else 0.0, plage)
    return [debut, fin], f"de {debut} à {fin}"


def _position_de_grille(minutes: float, plage: tuple[float, float]) -> float:
    """La place d'une durée sur l'axe logarithmique de la plage, de 0 à 100."""
    if math.isinf(minutes):
        return 100.0
    if minutes <= 0:
        return 0.0
    return _position(math.log(minutes), math.log(plage[0]), math.log(plage[1]))


def _secondes_ecrites(secondes: float) -> str:
    """Un écart de durée : « 37 s », « 2 min 3 s »."""
    s = _proche(secondes)
    if s < 100:
        return f"{s}{NB}s"
    minutes, reste = divmod(s, 60)
    return f"{minutes}{NB}min{NB}{reste}{NB}s" if reste else f"{minutes}{NB}min"


def _quantieme(jour: int) -> str:
    """Le jour du mois tel qu'il s'écrit : « 1er », « 2 »."""
    return "1er" if jour == 1 else str(jour)


def date_ecrite(jour: str) -> str:
    """Une date AAAA-MM-JJ écrite pour la page : « 26 octobre 2026 », « 1er novembre 2026 »."""
    annee, mois, quantieme = (int(x) for x in jour.split("-"))
    return f"{_quantieme(quantieme)}{NB}{MOIS[mois - 1]} {annee}"


def periode_ecrite(jours: Collection[str]) -> str:
    """La période de dates AAAA-MM-JJ : « du 21 au 27 octobre 2026 », « le 21 octobre 2026 »."""
    premier, dernier = min(jours), max(jours)
    if premier == dernier:
        return f"le {date_ecrite(premier)}"
    (a1, m1, j1), (a2, m2, j2) = ((int(x) for x in d.split("-")) for d in (premier, dernier))
    if (a1, m1) == (a2, m2):
        return f"du {_quantieme(j1)} au {j2}{NB}{MOIS[m2 - 1]} {a2}"
    if a1 == a2:
        return f"du {_quantieme(j1)}{NB}{MOIS[m1 - 1]} au {_quantieme(j2)}{NB}{MOIS[m2 - 1]} {a2}"
    return f"du {date_ecrite(premier)} au {date_ecrite(dernier)}"


def _releves_ecrits(tau2: dict[str, Any]) -> dict[str, Any]:
    """Chaque date de relevé d'un score publié de τ²-bench, aussi écrite pour la page."""
    for ligne in tau2.values():
        if isinstance(ligne, dict) and isinstance(cast(dict[str, Any], ligne).get("releve"), str):
            cast(dict[str, Any], ligne)["releve_texte"] = date_ecrite(cast(dict[str, Any], ligne)["releve"])
    return tau2


def _moins(texte: str) -> str:
    """Le signe moins typographique dans un texte de la page."""
    return texte.replace("-", "\u2212")


def cinq_sur_cinq(groupes: Sequence[Sequence[ResultatExecution]]) -> float:
    """La part des tâches dont toutes les exécutions réussissent."""
    return sum(all(r.reussie for r in g) for g in groupes) / len(groupes)


def _par_tache(groupes: Groupes) -> list[Groupes]:
    """Chaque tâche comme un tirage unique : le bootstrap tire les tâches, et la tâche entière vient."""
    return [[g] for g in groupes]


def _cinq_des_tirages(tirees: list[list[ResultatExecution]]) -> float:
    return cinq_sur_cinq(tirees)


def chiffre(reussis: int, sur: int, fourchette: tuple[float, float]) -> dict[str, Any]:
    """Un chiffre de réussite, tel qu'il s'affiche : compte, pourcentage, fourchette à 95 %."""
    valeur = reussis / sur
    return {
        "reussis": reussis,
        "sur": sur,
        "texte": f"{reussis} sur {sur}",
        "valeur": valeur,
        "pourcent": pourcent(valeur),
        "pourcent_entier": nombre(100 * valeur, 0),
        "fourchette": list(fourchette),
        "fourchette_pourcent": [pourcent(b) for b in fourchette],
        "fourchette_entier": [nombre(100 * b, 0) for b in fourchette],
    }


def ecart(valeur: float, fourchette: tuple[float, float]) -> dict[str, Any]:
    """L'écart du premier candidat sur le second, en points, et s'il est établi à 95 %."""
    return {
        "valeur": valeur,
        "points": points(valeur),
        "fourchette": list(fourchette),
        "fourchette_points": [points(b) for b in fourchette],
        "etabli": fourchette[0] > 0 or fourchette[1] < 0,
    }


def paires_de(identifiants: Sequence[str]) -> list[tuple[str, str]]:
    """Les paires de candidats, dans leur ordre : le premier avec chacun des suivants, puis le second
    avec les siens (avec trois : 1 et 2, 1 et 3, 2 et 3)."""
    return [(a, b) for i, a in enumerate(identifiants) for b in identifiants[i + 1 :]]


def groupes_retenus(mesures: Mesures, identifiants: Sequence[str]) -> Groupes:
    """Les exécutions de chaque tâche, comme le rapport les compte : sans les erreurs techniques."""
    return [[r for r in mesures.executions[i] if r.arret != "erreur_technique"] for i in identifiants]


def ecart_ordonne[T](
    groupes: Mapping[str, Sequence[Sequence[T]]], statistique: Callable[[list[T]], float]
) -> dict[str, Any]:
    """L'écart entre deux candidats comme le rapport le prend : la plus haute valeur moins la plus basse
    (ordre des candidats si elles sont égales), sa fourchette par le bootstrap sur les tâches, et le
    candidat devant. Le même ordre que le rapport donne la même fourchette, tirage pour tirage."""
    valeurs = {c: statistique([x for g in liste for x in g]) for c, liste in groupes.items()}
    haut, bas = sorted(groupes, key=lambda c: valeurs[c], reverse=True)
    return ecart(valeurs[haut] - valeurs[bas], bootstrap_ecart(groupes[haut], groupes[bas], statistique)) | {
        "devant": haut
    }


def _groupe(cle: str, libelle: str, identifiants: Sequence[str], mesures: Sequence[Mesures]) -> dict[str, Any]:
    """Les chiffres d'un métier, ou de l'ensemble, pour chaque candidat, puis leurs écarts."""
    par_candidat: dict[str, Any] = {}
    groupes: list[Groupes] = []
    for m in mesures:
        g = groupes_retenus(m, identifiants)
        groupes.append(g)
        essais = [r for t in g for r in t]
        reussis = sum(r.reussie for r in essais)
        par_candidat[m.identifiant] = {
            "essais": _place(chiffre(reussis, len(essais), bootstrap(g, taux))) | {"rates": len(essais) - reussis},
            "cinq_sur_cinq": _place(
                chiffre(sum(all(r.reussie for r in t) for t in g), len(g), bootstrap(_par_tache(g), _cinq_des_tirages))
            ),
        }
        cinq = par_candidat[m.identifiant]["cinq_sur_cinq"]
        manquees = cinq["sur"] - cinq["reussis"]
        cinq["ratees"] = {
            "taches": manquees,
            "texte": f"{manquees} sur {cinq['sur']}",
            "pourcent": pourcent(manquees / cinq["sur"]) if cinq["sur"] else "?",
            "pourcent_entier": str(_proche(100 * manquees / cinq["sur"])) if cinq["sur"] else "?",
        }
    ligne: dict[str, Any] = {"cle": cle, "libelle": libelle, "taches": len(identifiants), "par_candidat": par_candidat}
    par_candidat_groupes = {m.identifiant: g for m, g in zip(mesures, groupes, strict=True)}
    paires = [
        {
            "a": a,
            "b": b,
            "essais": ecart_ordonne({c: par_candidat_groupes[c] for c in (a, b)}, taux),
            "cinq_sur_cinq": ecart_ordonne({c: _par_tache(par_candidat_groupes[c]) for c in (a, b)}, _cinq_des_tirages),
        }
        for a, b in paires_de(list(par_candidat_groupes))
    ]
    if paires:
        ligne["paires"] = paires
    if len(groupes) == 2:
        ligne["ecarts"] = {"essais": paires[0]["essais"], "cinq_sur_cinq": paires[0]["cinq_sur_cinq"]}
    return ligne


def _exemple(taches: Sequence[Tache], mesures: Sequence[Mesures]) -> dict[str, Any]:
    """L'essai raconté : où le trouver, avec le contexte que demande le candidat de son run (relecture R10
    du 2026-10-28 : il vient de la part à 40 960 jetons), et combien d'essais de chaque candidat
    manquent le même contrôle."""
    identifiant, candidat, essai, controle = EXEMPLE
    tache = next((t for t in taches if t.identifiant == identifiant), None)
    if tache is None or candidat not in {m.identifiant for m in mesures}:
        raise RapportImpossible(f"l'essai raconté, {identifiant} de {candidat}, n'est pas dans les données")
    echecs: dict[str, int] = {}
    essais: dict[str, int] = {}
    for m in mesures:
        retenus = groupes_retenus(m, [identifiant])[0]
        essais[m.identifiant] = len(retenus)
        echecs[m.identifiant] = sum(any(c.numero == controle and c.score < 1 for c in r.controles) for r in retenus)
    raconte = next(
        r
        for r in groupes_retenus(next(m for m in mesures if m.identifiant == candidat), [identifiant])[0]
        if r.repetition == essai
    )
    if raconte.reussie:
        raise RapportImpossible(f"l'essai raconté, {identifiant} r{essai} de {candidat}, a réussi")
    source = next(m for m in mesures if m.identifiant == candidat).sources[identifiant]
    contexte = _contexte_demande(DOSSIER_CANDIDATS / f"{source.fiche.candidat.identifiant}.yaml")
    return {
        "tache": identifiant,
        "court": identifiant.split("_")[0],
        "famille": tache.famille,
        "candidat": candidat,
        "essai": essai,
        "controle": controle,
        "run": source.dossier.name,
        "contexte": contexte,
        "contexte_texte": None if contexte is None else nombre(contexte, 0),
        "essais": essais,
        "echecs_du_controle": echecs,
    }


def essais_tau2(
    dossier_runs_tau2: Path, candidat: str, repetitions: int = REPETITIONS
) -> tuple[list[ResultatExecution], list[str]]:
    """Les essais de τ²-bench d'un candidat, tâche par tâche, ceux du run le plus récent qui a fait la
    tâche en entier, et les runs d'où ils viennent (JOURNAL, entrée 273) : un run interrompu garde ses
    tâches complètes, une tâche commencée puis refaite ailleurs ne compte qu'une fois. Les fiches se
    lisent en JSON simple : les plus anciennes précèdent un champ du contrat, et seuls leur candidat,
    leur statut, leurs répétitions et leur nombre de tâches servent au choix."""
    runs: list[tuple[str, Path, int]] = []
    for chemin in dossier_runs_tau2.glob(f"*_{candidat}/fiche_de_run.json"):
        fiche: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
        if (
            fiche.get("candidat", {}).get("identifiant") == candidat
            and fiche.get("statut") in ("termine", "interrompu")
            and fiche.get("repetitions") == repetitions
        ):
            runs.append(
                (str(fiche.get("debut_utc")), chemin.parent, len(fiche.get("jeu_taches", {}).get("taches", [])))
            )
    if not runs:
        raise RapportImpossible(f"aucun run de τ²-bench à {repetitions} essais pour {candidat}")
    retenus: dict[str, tuple[Path, list[ResultatExecution]]] = {}
    for _, dossier, _ in sorted(runs, reverse=True):
        par_tache: dict[str, list[ResultatExecution]] = defaultdict(list)
        for chemin in sorted((dossier / "resultats").glob("*.json")):
            resultat = lire_resultat(chemin)
            par_tache[resultat.tache.identifiant].append(resultat)
        for tache, resultats in par_tache.items():
            if tache not in retenus and len(resultats) == repetitions:
                retenus[tache] = (dossier, sorted(resultats, key=lambda r: r.repetition))
    attendues = max(nombre for _, _, nombre in runs)
    if len(retenus) != attendues:
        raise RapportImpossible(f"τ²-bench de {candidat} : {len(retenus)} tâches complètes sur {attendues}")
    essais = [r for _, resultats in retenus.values() for r in resultats]
    return essais, sorted({dossier.name for dossier, _ in retenus.values()})


def _contexte_demande(declaration: Path) -> int | None:
    """Le contexte qu'une déclaration demande à son serveur, si elle en demande un."""
    lancement = cast(dict[str, Any], yaml.safe_load(declaration.read_text(encoding="utf-8")))["lancement"]
    return cast(int | None, lancement.get("contexte_serveur"))


def contexte_plus_court(
    reproduction: str, identifiant: str, dossier_tau2: Path = DOSSIER_TAU2, dossier: Path = DOSSIER_CANDIDATS
) -> bool:
    """Si le candidat de τ²-bench d'une référence est servi avec moins de contexte qu'elle : Qwen à
    40 960 jetons pour la référence à 102 400. Ses essais ne comptent alors que si aucun n'est coupé par
    le contexte, la règle des parts du socle (protocole, partie 5 ; cadrage du dépôt public, section 8)."""
    court = _contexte_demande(dossier_tau2 / f"{reproduction}.yaml")
    reference = _contexte_demande(dossier / f"{identifiant}.yaml")
    return court is not None and reference is not None and court < reference


def _tau2(dossier_runs_tau2: Path, candidats: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """Notre mesure de τ²-bench pour chaque référence, sa fourchette de Wilson, le score publié s'il y
    en a un, et s'il tombe dans la fourchette (verdict : dedans, hors ou aucun) ; « controle » dit si
    ce score porte un écart type, ceux sur qui repose le contrôle du banc."""
    sortie: dict[str, Any] = {}
    for identifiant, reproduction, publie, ecart_type, releve in TAU2:
        if identifiant not in {i for i, _ in candidats}:
            continue
        essais, runs = essais_tau2(dossier_runs_tau2, reproduction)
        if contexte_plus_court(reproduction, identifiant) and any(r.arret == "contexte_depasse" for r in essais):
            raise RapportImpossible(
                f"τ²-bench de {identifiant} : un essai coupé par le contexte dans {reproduction}, servi avec "
                "moins de contexte que la référence ; à remesurer à son contexte"
            )
        retenus = [r for r in essais if r.arret != "erreur_technique"]
        reussis = sum(r.reussie for r in retenus)
        fourchette = intervalle_wilson(reussis, len(retenus))
        dedans = None if publie is None else fourchette[0] <= publie <= fourchette[1]
        sortie[identifiant] = chiffre(reussis, len(retenus), fourchette) | {
            "runs": runs,
            "publie": None
            if publie is None
            else {
                "valeur": publie,
                "pourcent": pourcent(publie),
                "ecart_type": ecart_type,
                "ecart_type_points": None if ecart_type is None else points(ecart_type),
                "source": SOURCE_TAU2.format(releve),
            },
            "dans_la_fourchette": dedans,
            "verdict": "aucun" if publie is None else "dedans" if dedans else "hors",
            "controle": ecart_type is not None,
            "releve": releve,
        }
    return sortie


def _reussites_par_tache(mesures: Mesures, identifiants: Sequence[str]) -> dict[str, int]:
    groupes = groupes_retenus(mesures, identifiants)
    return {i: sum(r.reussie for r in g) for i, g in zip(identifiants, groupes, strict=True)}


def donnees_premier_post(
    dossier_runs: Path,
    taches: Sequence[Tache] | None = None,
    candidats: Sequence[tuple[str, str]] = CANDIDATS,
    repetitions: int = REPETITIONS,
    dossier_runs_tau2: Path | None = None,
) -> dict[str, Any]:
    """Les données du premier post, sur les tâches publiques du socle (ou sur taches, pour un test) ;
    l'essai raconté et τ²-bench quand leurs runs sont là (dossier_runs_tau2)."""
    taches = list(publiques_publiees() if taches is None else taches)
    mesures: list[Mesures] = []
    for identifiant, nom in candidats:
        m = rassembler_reference(identifiant, nom, taches, dossier_runs, repetitions)
        if m.manquantes:
            raise RapportImpossible(f"{nom} n'a pas de run complet pour {', '.join(m.manquantes)}")
        mesures.append(m)
    inconnues = sorted({t.famille for t in taches} - {cle for cle, _ in METIERS})
    if inconnues:
        raise RapportImpossible(f"métier sans libellé : {', '.join(inconnues)}")
    metiers = [
        _groupe(cle, libelle, [t.identifiant for t in taches if t.famille == cle], mesures)
        for cle, libelle in METIERS
        if any(t.famille == cle for t in taches)
    ]
    identifiants = [t.identifiant for t in taches]
    maintenant = datetime.now(UTC)
    tailles = [m["taches"] for m in metiers]
    donnees: dict[str, Any] = {
        "sujet": "premier_post",
        "numero": 1,
        "version": VERSION,
        "produit_le": f"{maintenant:%Y-%m-%d}",
        "mois": "",
        "pme": "Calorelle",
        "taches": len(taches),
        "repetitions": repetitions,
        "graduations": [{"valeur": g, "pourcent": pourcent(g)} for g in GRADUATIONS],
        "taches_par_metier": {"min": min(tailles), "max": max(tailles)},
        "echelle_taux": {
            "bas": ECHELLE_TAUX[0],
            "haut": ECHELLE_TAUX[1],
            "graduations": [
                {"valeur": g, "pourcent": pourcent(g), "position": _position(g, *ECHELLE_TAUX[:2])}
                for g in ECHELLE_TAUX[2]
            ],
        },
        "candidats": [
            {"identifiant": i, "nom": n, "court": COURTS.get(i, n), "detail": DETAILS.get(i, "")} for i, n in candidats
        ],
        "metiers": metiers,
        "ensemble": _groupe("ensemble", ENSEMBLE.get(len(metiers), "Ensemble"), identifiants, mesures),
        "par_tache": {m.identifiant: _reussites_par_tache(m, identifiants) for m in mesures},
        "runs": {m.identifiant: sorted({run.dossier.name for run in m.sources.values()}) for m in mesures},
    }
    if any(t.identifiant == EXEMPLE[0] for t in taches):
        donnees["exemple"] = _exemple(taches, mesures)
    if dossier_runs_tau2 is not None:
        donnees["tau2"] = _releves_ecrits(_tau2(dossier_runs_tau2, candidats))
        donnees["graduations_tau2"] = [{"valeur": g, "pourcent": pourcent(g)} for g in GRADUATIONS_TAU2]
    donnees["mois"] = mois_des_runs(donnees)
    _textes_des_paires(donnees)
    return donnees


RUN_NOMME = re.compile(r"^(\d{4})-(\d{2})-\d{2}_\d{6}_[a-z0-9_]+$")
"""Le nom d'un run, qui commence par sa date : « 2026-10-09_220655_agent_seul_qwen_local »."""


def _chaines(valeur: object) -> Iterator[str]:
    if isinstance(valeur, str):
        yield valeur
    elif isinstance(valeur, dict):
        for sous in cast(dict[str, object], valeur).values():
            yield from _chaines(sous)
    elif isinstance(valeur, list):
        for sous in cast(list[object], valeur):
            yield from _chaines(sous)


def mois_des_runs(donnees: Mapping[str, Any]) -> str:
    """Le mois d'une publication, « octobre 2026 » : celui du plus récent des runs que nomment ses
    données, pas celui du jour où make publier la calcule. Un constat d'octobre publié le 2 novembre
    reste le constat d'octobre, dans ses pages comme dans leur adresse (/epreuve-agent/2026-10/)."""
    dates = sorted((int(m.group(1)), int(m.group(2))) for c in _chaines(donnees) if (m := RUN_NOMME.match(c)))
    if not dates:
        raise RapportImpossible("aucun run nommé dans les données : le mois de la publication ne se lit pas")
    annee, mois = dates[-1]
    return f"{MOIS[mois - 1]} {annee}"


def _duree(secondes: float) -> dict[str, Any]:
    """Une durée d'exécution, écrite comme un écart de durée : « 37 s », « 3 min 6 s »."""
    return {"secondes": secondes, "texte": _secondes_ecrites(secondes)}


def _fois(une: float, autre: float) -> int | None:
    """Combien de fois la plus longue de deux durées contient l'autre, à l'entier le plus proche :
    « environ trois fois plus vite »."""
    courte, longue = sorted((une, autre))
    return int(longue / courte + 0.5) if courte > 0 else None


def _mediane_des_durees(resultats: list[ResultatExecution]) -> float:
    return statistics.median(r.duree_secondes for r in resultats)


def _sans(valeur: object, cles: frozenset[str]) -> object:
    """Une déclaration sans les clés qui peuvent différer, à toute profondeur."""
    if isinstance(valeur, dict):
        return {k: _sans(v, cles) for k, v in cast(dict[str, object], valeur).items() if k not in cles}
    if isinstance(valeur, list):
        return [_sans(v, cles) for v in cast(list[object], valeur)]
    return valeur


def _verifier_parts(parts: Sequence[str], dossier: Path = DOSSIER_CANDIDATS) -> None:
    """Refuse une référence dont les parts diffèrent par autre chose que le contexte et ses délais :
    leurs déclarations hors DIFFERENCES_PERMISES, leurs configurations hors du délai d'un appel."""
    declarations = [
        cast(dict[str, Any], yaml.safe_load((dossier / f"{p}.yaml").read_text(encoding="utf-8"))) for p in parts
    ]
    configurations: list[object] = []
    for declaration in declarations:
        arguments = cast(list[str], declaration["lancement"]["arguments"])
        chemin = racine_depot() / arguments[arguments.index("--configuration") + 1]
        configuration = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        configurations.append(_sans(configuration, frozenset({"delai_appel_secondes"})))
    premiere = _sans(declarations[0], DIFFERENCES_PERMISES)
    for part, declaration, configuration in zip(parts[1:], declarations[1:], configurations[1:], strict=True):
        if _sans(declaration, DIFFERENCES_PERMISES) != premiere or configuration != configurations[0]:
            raise RapportImpossible(f"{parts[0]} et {part} diffèrent par autre chose que le contexte")


def _demande_un_juge(tache: Tache) -> bool:
    return any(isinstance(v, JugeRequis) for c in tache.controles for v in c.verification)


def rassembler_reference(
    identifiant: str,
    nom: str,
    taches: Sequence[Tache],
    dossier_runs: Path,
    repetitions: int = REPETITIONS,
    gardien: bool = False,
    cachees: Collection[str] = (),
) -> Mesures:
    """Les mesures d'une référence : celles de son candidat, ou, pour une référence de PARTS, tâche par
    tâche celles de la première part qui a la tâche entière à sa version courante. Une tâche prise
    hors de la première part ne doit avoir aucun essai coupé par le contexte ; toutes les tâches à juge
    ont le même juge, et les runs les mêmes modèles, répétitions et règles du gardien."""
    parts = PARTS.get(identifiant, (identifiant,))
    if len(parts) == 1:
        return rassembler(identifiant, nom, list(taches), dossier_runs, repetitions, gardien, cachees)
    _verifier_parts(parts)
    mesures = [rassembler(p, nom, list(taches), dossier_runs, repetitions, gardien, cachees) for p in parts]
    executions: dict[str, list[ResultatExecution]] = {}
    sources: dict[str, Any] = {}
    manquantes: list[str] = []
    for tache in taches:
        tid = tache.identifiant
        part = next((m for m in mesures if tid in m.executions), None)
        if part is None:
            manquantes.append(tid)
            continue
        if part is not mesures[0] and any(r.arret == "contexte_depasse" for r in part.executions[tid]):
            raise RapportImpossible(
                f"{nom} : {sans_noms([tid], cachees)} coupée par le contexte dans {part.identifiant}, "
                f"à remesurer dans {parts[0]}"
            )
        executions[tid], sources[tid] = part.executions[tid], part.sources[tid]
    juges = {
        sources[t.identifiant].dossier.name: (
            None if sources[t.identifiant].fiche.juge is None else sources[t.identifiant].fiche.juge.model_dump_json()
        )
        for t in taches
        if t.identifiant in sources and _demande_un_juge(t)
    }
    if len(set(juges.values())) > 1:
        raise RapportImpossible(f"{nom} : ses parts n'ont pas le même juge ; elles ne s'assemblent pas")
    signatures = {
        json.dumps(
            [
                [m.model_dump(mode="json", exclude={"version_renvoyee"}) for m in run.fiche.configuration.modeles],
                run.fiche.repetitions,
                None if run.fiche.regles_gardien is None else run.fiche.regles_gardien.model_dump(mode="json"),
            ],
            sort_keys=True,
        )
        for run in sources.values()
    }
    if len(signatures) > 1:
        raise RapportImpossible(f"{nom} : ses parts diffèrent de modèle, de répétitions ou de gardien")
    return Mesures(identifiant, nom, executions, sources, manquantes)


def _rassembler_tout(
    candidats: Sequence[tuple[str, str]],
    taches: Sequence[Tache],
    dossier_runs: Path,
    repetitions: int,
    cachees: set[str],
    gardien: bool = False,
) -> list[Mesures]:
    """Les mesures de chaque candidat ; refus si une tâche manque, les cachées comptées sans leur nom."""
    mesures: list[Mesures] = []
    for identifiant, nom in candidats:
        m = rassembler_reference(identifiant, nom, taches, dossier_runs, repetitions, gardien, cachees)
        if m.manquantes:
            avec = " avec gardien" if gardien else ""
            raise RapportImpossible(f"{nom} n'a pas de run complet{avec} pour {sans_noms(m.manquantes, cachees)}")
        mesures.append(m)
    return mesures


def _metiers_du_socle(publiques: Sequence[Tache], cachees: Sequence[Tache]) -> list[dict[str, Any]]:
    """Le nombre de tâches de chaque métier du socle, publiques et cachées séparées, en comptes, sans
    nom (cadrage du 2026-10-28, figer la publication v1, section 2)."""
    connus = {cle for cle, _ in METIERS}
    inconnus = sorted({t.famille for t in [*publiques, *cachees]} - connus)
    if inconnus:
        raise RapportImpossible(f"métiers inconnus dans le socle : {', '.join(inconnus)}")
    return [
        {
            "cle": cle,
            "libelle": libelle,
            "publiques": sum(t.famille == cle for t in publiques),
            "cachees": sum(t.famille == cle for t in cachees),
            "taches": sum(t.famille == cle for t in [*publiques, *cachees]),
        }
        for cle, libelle in METIERS
    ]


def _parts(mesures: Sequence[Mesures], publiques: Sequence[Tache]) -> dict[str, list[dict[str, Any]]]:
    """Pour chaque référence de PARTS, le nombre de tâches du socle prises dans chaque part, avec le
    contexte que sa déclaration demande, publiques et cachées en comptes (relecture R10 du 2026-10-28 :
    Qwen est servi à 40 960 jetons sur une partie des tâches)."""
    noms_publics = {t.identifiant for t in publiques}
    sortie: dict[str, list[dict[str, Any]]] = {}
    for m in mesures:
        if m.identifiant not in PARTS:
            continue
        lignes: list[dict[str, Any]] = []
        for part in PARTS[m.identifiant]:
            prises = [t for t, run in m.sources.items() if run.fiche.candidat.identifiant == part]
            contexte = _contexte_demande(DOSSIER_CANDIDATS / f"{part}.yaml")
            lignes.append(
                {
                    "candidat": part,
                    "contexte": contexte,
                    "contexte_texte": None if contexte is None else nombre(contexte, 0),
                    "taches": len(prises),
                    "publiques": sum(t in noms_publics for t in prises),
                    "cachees": sum(t not in noms_publics for t in prises),
                }
            )
        sortie[m.identifiant] = lignes
    return sortie


def _juge(mesures: Sequence[Mesures], publiques: Sequence[Tache], cachees: Sequence[Tache]) -> dict[str, Any]:
    """Le juge des tâches du socle qui en demandent un : son modèle, la référence mesurée dont l'agent
    est ce même modèle s'il y en a une, et le nombre de tâches jugées, publiques et cachées en comptes
    (relecture R10 du 2026-10-28 : la page dit qui juge). Refus si ces tâches n'ont pas toutes le même."""
    jugees = [t for t in [*publiques, *cachees] if _demande_un_juge(t)]
    modeles = {
        "aucun" if (juge := m.sources[t.identifiant].fiche.juge) is None else juge.modele
        for m in mesures
        for t in jugees
    }
    if len(modeles) != 1 or "aucun" in modeles:
        raise RapportImpossible(f"les tâches à juge du socle n'ont pas un seul juge : {sorted(modeles)}")
    modele = modeles.pop()
    agents = {
        m.identifiant: {
            c.nom for run in m.sources.values() for c in run.fiche.configuration.modeles if c.role == "agent"
        }
        for m in mesures
    }
    noms_publics = {t.identifiant for t in publiques}
    return {
        "modele": modele,
        "candidat": next((i for i, noms in agents.items() if noms == {modele}), None),
        "taches": len(jugees),
        "publiques": sum(t.identifiant in noms_publics for t in jugees),
        "cachees": sum(t.identifiant not in noms_publics for t in jugees),
    }


def detail_avec_parts(detail: str, lignes: Sequence[Mapping[str, Any]]) -> str:
    """Le détail d'une référence de PARTS, déclarée au contexte de sa première part, les autres parts
    entre parenthèses avec leurs tâches (décision d'Alexandre du 2026-10-28, « 102 400 en tête ») :
    « contexte de 102 400 jetons (40 960 sur 57 tâches, mesurées avant l'élargissement) »."""
    autres = [
        f"{ligne['contexte_texte']} sur {ligne['taches']} tâche{'s' if ligne['taches'] > 1 else ''}"
        for ligne in lignes[1:]
        if ligne["taches"]
    ]
    return f"{detail} ({', '.join(autres)}, mesurées avant l'élargissement)" if autres else detail


def _socle(dossier_runs: Path, candidats: Sequence[tuple[str, str]], repetitions: int) -> dict[str, Any]:
    """La réussite, les 5 sur 5 et la durée médiane d'une exécution sur tout le socle, cachées comprises."""
    publiques, cachees = publiques_publiees(), cachees_publiees()
    taches = publiques + cachees
    noms_caches = {t.identifiant for t in cachees}
    mesures = _rassembler_tout(candidats, taches, dossier_runs, repetitions, noms_caches)
    identifiants = [t.identifiant for t in taches]
    ligne = _groupe("socle", "Le socle", identifiants, mesures)
    toutes = {m.identifiant: [list(m.executions[i]) for i in identifiants] for m in mesures}
    for m in mesures:
        ligne["par_candidat"][m.identifiant]["duree_mediane"] = _duree(
            _mediane_des_durees([r for g in toutes[m.identifiant] for r in g])
        )
    for paire in ligne.get("paires", []):
        duree = ecart_ordonne({c: toutes[c] for c in (paire["a"], paire["b"])}, _mediane_des_durees)
        paire["duree_mediane"] = {
            "secondes": duree["valeur"],
            "fourchette_secondes": duree["fourchette"],
            "etabli": duree["etabli"],
            "devant": duree["devant"],
            "fois": _fois(*(ligne["par_candidat"][c]["duree_mediane"]["secondes"] for c in (paire["a"], paire["b"]))),
        }
    if len(mesures) == 2:
        ligne["ecarts"]["duree_mediane"] = ligne["paires"][0]["duree_mediane"]
    ligne |= {
        "publiques": len(publiques),
        "cachees": len(cachees),
        "metiers": _metiers_du_socle(publiques, cachees),
        "parts": _parts(mesures, publiques),
        "juge": _juge(mesures, publiques, cachees),
    }
    ligne["publiques_seules"] = _groupe(
        "publiques_seules", "Les tâches publiques seules", [t.identifiant for t in publiques], mesures
    )
    ligne["runs"] = {m.identifiant: sorted({run.dossier.name for run in m.sources.values()}) for m in mesures}
    return ligne


def _fautives(resultats: list[bool]) -> float:
    return sum(resultats) / len(resultats)


def _groupes_fautifs(mesures: Sequence[Mesures], exposees: Sequence[Tache], gravite: Gravite) -> dict[str, Any]:
    """Pour chaque candidat et chaque tâche exposée, si chaque exécution retenue commet une faute grave."""
    return {
        m.identifiant: [
            [bool(fautes_graves(r, t, gravite)) for r in groupes_retenus(m, [t.identifiant])[0]] for t in exposees
        ]
        for m in mesures
    }


def _par_categorie(m: Mesures, exposees: Sequence[Tache], gravite: Gravite) -> dict[str, int]:
    """Les exécutions fautives d'un candidat, par sorte de faute grave ; une exécution qui en commet
    deux sortes compte dans chacune. Les plus nombreuses d'abord."""
    comptes: Counter[str] = Counter()
    for t in exposees:
        for r in groupes_retenus(m, [t.identifiant])[0]:
            comptes.update(set(fautes_graves(r, t, gravite)))
    return dict(sorted(comptes.items(), key=lambda c: (-c[1], c[0])))


def _essais_fautifs(m: Mesures, exposees: Sequence[Tache], gravite: Gravite) -> list[dict[str, Any]]:
    """Chaque exécution retenue d'un candidat qui commet une faute grave : son run, sa tâche (publique,
    les tâches exposées le sont toutes), son essai et ses sortes de fautes, pour qu'un récit se vérifie
    dans le run (relecture R10 du 2026-10-28)."""
    return [
        {"run": r.run, "tache": t.identifiant, "essai": r.repetition, "sortes": sorted(set(sortes))}
        for t in exposees
        for r in groupes_retenus(m, [t.identifiant])[0]
        if (sortes := fautes_graves(r, t, gravite))
    ]


def _categories(exposees: Sequence[Tache], gravite: Gravite) -> list[dict[str, Any]]:
    """Les sortes de fautes graves contrôlées, avec le nombre de tâches qui en portent au moins un
    contrôle ; une tâche qui en porte deux sortes compte dans chacune. Les plus contrôlées d'abord."""
    comptes = Counter(c for t in exposees for c in set(gravite.graves.get(t.identifiant, {}).values()))
    inconnues = sorted(set(comptes) - set(gravite.categories))
    if inconnues:
        raise RapportImpossible(f"sortes de fautes graves sans définition : {', '.join(inconnues)}")
    return [
        {"cle": c, "libelle": LIBELLES_FAUTES.get(c, c), "definition": gravite.categories[c], "taches": n}
        for c, n in sorted(comptes.items(), key=lambda c: (-c[1], c[0]))
    ]


def _fautes(mesures: Sequence[Mesures], exposees: Sequence[Tache], gravite: Gravite) -> dict[str, Any]:
    """Les exécutions qui commettent une faute grave, par candidat, avec la fourchette de Wilson, et
    l'écart de chaque paire (`paires`), établi par le bootstrap sur les tâches ; avec deux candidats,
    le même écart aussi sous `ecart`."""
    groupes = _groupes_fautifs(mesures, exposees, gravite)
    sortie: dict[str, Any] = {}
    for m in mesures:
        k = sum(sum(g) for g in groupes[m.identifiant])
        n = sum(len(g) for g in groupes[m.identifiant])
        sortie[m.identifiant] = chiffre(k, n, intervalle_wilson(k, n)) | {
            "par_categorie": _par_categorie(m, exposees, gravite),
            "essais_fautifs": _essais_fautifs(m, exposees, gravite),
        }
    paires = [
        {"a": a, "b": b, "ecart": ecart_ordonne({c: groupes[c] for c in (a, b)}, _fautives)}
        for a, b in paires_de([m.identifiant for m in mesures])
    ]
    if paires:
        sortie["paires"] = paires
    if len(mesures) == 2:
        sortie["ecart"] = paires[0]["ecart"]
    return sortie


def _lignes_du_gardien(dossier: Path) -> list[dict[str, Any]]:
    chemin = dossier / "gardien.jsonl"
    if not chemin.exists():
        return []
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne.strip()]


def _journal_du_gardien(avec: Sequence[Mesures], exposees: Sequence[Tache]) -> dict[str, Any]:
    """Ce que dit le journal du gardien, pour chaque candidat, sur les exécutions retenues des tâches
    exposées : ses blocages et ses demandes d'accord, acceptées ou refusées, par règle, et les tâches où
    chaque règle a joué (relecture R10 du 2026-10-28 : le geste d'un essai raconté se retrouve). Chaque
    tâche se lit dans le run d'où viennent ses exécutions retenues."""
    sortie: dict[str, Any] = {}
    for m in avec:
        par_regle: dict[str, dict[str, int]] = defaultdict(lambda: {"bloque": 0, "accepte": 0, "refuse": 0})
        taches: dict[str, set[str]] = defaultdict(set)
        lus: dict[Path, list[dict[str, Any]]] = {}
        for t in exposees:
            dossier = m.sources[t.identifiant].dossier
            if dossier not in lus:
                lus[dossier] = _lignes_du_gardien(dossier)
            for e in lus[dossier]:
                if e.get("tache") != t.identifiant or e.get("verdict") not in ("bloque", "validation"):
                    continue
                regle = str(e.get("regle"))
                taches[regle].add(t.identifiant)
                if e.get("verdict") == "bloque":
                    par_regle[regle]["bloque"] += 1
                else:
                    par_regle[regle]["accepte" if e.get("reponse") == "accepter" else "refuse"] += 1
        sortie[m.identifiant] = {
            "bloques": sum(v["bloque"] for v in par_regle.values()),
            "acceptes": sum(v["accepte"] for v in par_regle.values()),
            "refuses": sum(v["refuse"] for v in par_regle.values()),
            "par_regle": dict(sorted(par_regle.items())),
            "taches_par_regle": {r: sorted(ts) for r, ts in sorted(taches.items())},
        }
    return sortie


def _taches_bloquees(
    sans: Sequence[Mesures], avec: Sequence[Mesures], exposees: Sequence[Tache]
) -> list[dict[str, Any]]:
    """Les tâches où le gardien a bloqué au moins un geste d'un candidat, et leurs essais réussis sans
    puis avec lui : ce que coûte un blocage, à tort ou non."""
    bloquees: list[dict[str, Any]] = []
    for t in exposees:
        if not any(
            e.get("tache") == t.identifiant and e.get("verdict") == "bloque"
            for m in avec
            for e in _lignes_du_gardien(m.sources[t.identifiant].dossier)
        ):
            continue
        par_candidat: dict[str, Any] = {}
        for ms, ma in zip(sans, avec, strict=True):
            ga = groupes_retenus(ma, [t.identifiant])[0]
            par_candidat[ms.identifiant] = {
                "sans": sum(r.reussie for r in groupes_retenus(ms, [t.identifiant])[0]),
                "avec": sum(r.reussie for r in ga),
                "sur": len(ga),
            }
        bloquees.append({"tache": t.identifiant, "court": t.identifiant.split("_")[0], "par_candidat": par_candidat})
    return bloquees


def _graves(dossier_runs: Path, candidats: Sequence[tuple[str, str]], repetitions: int) -> dict[str, Any]:
    """Les fautes graves des tâches à contrôle grave du socle, sans gardien puis avec (choix du
    2026-10-20 : le socle, gardien v1) ; l'écart sans puis avec le gardien pour chaque candidat, qui
    compare des runs différents ; ce que dit le journal du gardien ; les tâches où il a bloqué."""
    gravite = lire_gravite()
    exposees = [t for t in publiques_publiees() if exposee(t, gravite)]
    sans = _rassembler_tout(candidats, exposees, dossier_runs, repetitions, set())
    avec = _rassembler_tout(candidats, exposees, dossier_runs, repetitions, set(), gardien=True)
    versions = {
        run.fiche.regles_gardien.version
        for m in avec
        for run in m.sources.values()
        if run.fiche.regles_gardien is not None
    }
    if len(versions) != 1:
        raise RapportImpossible(f"les runs avec gardien n'ont pas les mêmes règles : {sorted(versions)}")
    groupes_sans, groupes_avec = _groupes_fautifs(sans, exposees, gravite), _groupes_fautifs(avec, exposees, gravite)
    return {
        "taches": len(exposees),
        "categories": _categories(exposees, gravite),
        "gardien": f"v{versions.pop()}",
        "sans_gardien": _fautes(sans, exposees, gravite),
        "avec_gardien": _fautes(avec, exposees, gravite),
        "sans_puis_avec": {
            m.identifiant: ecart_ordonne(
                {"sans": groupes_sans[m.identifiant], "avec": groupes_avec[m.identifiant]}, _fautives
            )
            for m in sans
        },
        "journal": _journal_du_gardien(avec, exposees),
        "taches_bloquees": _taches_bloquees(sans, avec, exposees),
        "runs_avec_gardien": {m.identifiant: sorted({r.dossier.name for r in m.sources.values()}) for m in avec},
        "runs_avec_gardien_compte": {m.identifiant: len({r.dossier.name for r in m.sources.values()}) for m in avec},
        "periode_avec_gardien": periode_ecrite({r.dossier.name[:10] for m in avec for r in m.sources.values()}),
    }


def _fini(minutes: float) -> float | None:
    """Un horizon au-delà de la plus longue tâche s'écrit null : les données d'une publication sont
    du JSON strict, que JavaScript lit (cadrage de la page Épreuve d'agent, §9)."""
    return None if math.isinf(minutes) else minutes


def _horizon(dossier_runs: Path, candidats: Sequence[tuple[str, str]], repetitions: int) -> dict[str, Any]:
    """L'horizon à 50 % de la tranche dure, comme le rapport, et de quoi dessiner sa courbe : les
    points des tâches, la courbe et sa bande à 95 %, sur la plage des tâches."""
    publiques, cachees = taches_du_jeu("dure"), cachees_du_jeu("dure")
    dossier = dossier_du_jeu("dure")
    cache = dossier_cachees_du_jeu("dure")
    gravite = lire_gravite(racine_depot() / "07_taches" / "public", dossier, *([cache] if cache else []))
    durees = durees_a_jour(lire_classement(dossier / "classement.yaml"), publiques) | durees_cachees("dure", cachees)
    noms_caches = {t.identifiant for t in cachees}
    taches = publiques + cachees
    mesures = _rassembler_tout(candidats, taches, dossier_runs, repetitions, noms_caches)
    dans = [t for t in taches if not exposee(t, gravite) and t.identifiant in durees]
    minutes = {t.identifiant: durees[t.identifiant] / 60 for t in dans}
    plage = (min(minutes.values()), max(minutes.values()))
    grille = [plage[0] * (plage[1] / plage[0]) ** (i / (POINTS_DE_COURBE - 1)) for i in range(POINTS_DE_COURBE)]
    sortie: dict[str, Any] = {
        "taches": len(dans),
        "cachees": sum(t.identifiant in noms_caches for t in dans),
        "plage": [{"minutes": m, "texte": _minutes_de_grille(m)} for m in plage],
        "graduations_minutes": [
            {"minutes": m, "texte": _minutes_de_grille(m), "position": _position_de_grille(m, plage)}
            for m in GRADUATIONS_MINUTES
            if plage[0] < m < plage[1]
        ],
        "grille_minutes": grille,
        "grille_position": [_position_de_grille(m, plage) for m in grille],
        "par_candidat": {},
    }
    fourchettes: dict[str, tuple[float, float]] = {}
    for m in mesures:
        bilan = bilan_horizon(m, dans, minutes, plage)
        estimation, fourchette = bilan.estimations[1], bilan.fourchettes[1]
        groupes = [[(minutes[t.identifiant], r.reussie) for r in groupes_retenus(m, [t.identifiant])[0]] for t in dans]
        courbe = ajuster([p for g in groupes for p in g])
        bande = bootstrap_plusieurs(groupes, lambda points: tuple(ajuster(points).reussite(x) for x in grille))
        fourchettes[m.identifiant] = fourchette
        bornes, phrase = _fourchette_de_grille(fourchette, plage)
        sortie["par_candidat"][m.identifiant] = {
            "minutes": _fini(estimation),
            "texte": _lecture_de_grille(estimation, plage),
            "position": _position_de_grille(estimation, plage),
            "essais": bilan.essais,
            "fourchette": [_fini(borne) for borne in fourchette],
            "fourchette_texte": bornes,
            "fourchette_phrase": phrase,
            "fourchette_position": [_position_de_grille(b, plage) for b in fourchette],
            "courbe": [courbe.reussite(x) for x in grille],
            "bande": [list(b) for b in bande],
            "points": [
                {
                    "minutes": minutes[t.identifiant],
                    "position": _position_de_grille(minutes[t.identifiant], plage),
                    "reussis": sum(ok for _, ok in g),
                    "sur": len(g),
                }
                for t, g in zip(dans, groupes, strict=True)
            ],
        }
    paires: list[dict[str, Any]] = []
    for a, b in paires_de([m.identifiant for m in mesures]):
        fa, fb = fourchettes[a], fourchettes[b]
        devant = a if fa[0] > fb[1] else b if fb[0] > fa[1] else None
        paires.append({"a": a, "b": b, "etabli": devant is not None, "devant": devant})
    if paires:
        sortie["paires"] = paires
    if len(mesures) == 2:
        sortie["etabli"] = paires[0]["etabli"]
    sortie["runs"] = {m.identifiant: sorted({r.dossier.name for r in m.sources.values()}) for m in mesures}
    return sortie


def _textes_des_paires(donnees: dict[str, Any]) -> None:
    """Le texte de chaque écart, paire par paire, tel que la page Épreuve d'agent l'affiche, la page
    ne calculant rien (maquette de la page, refonte 11). Établi, il dit lequel est devant ; sinon, il
    nomme la paire. Une faute grave de plus se dit « en commet plus », pas « devant »."""
    noms: dict[str, str] = {c["identifiant"]: c["court"] for c in donnees["candidats"]}

    def autre(e: Mapping[str, Any], a: str, b: str) -> str:
        return b if e["devant"] == a else a

    def ecart_de_taux(e: dict[str, Any], a: str, b: str, gabarit: str) -> None:
        lo, hi = (_moins(x) for x in e["fourchette_points"])
        unite = "point" if abs(e["valeur"]) < 0.02 else "points"
        chiffres = f"{e['points']} {unite} ({lo} à {hi})"
        e["texte"] = (
            gabarit.format(devant=noms[e["devant"]], autre=noms[autre(e, a, b)], chiffres=chiffres)
            if e["etabli"]
            else f"{noms[a]} et {noms[b]}{NB}: {chiffres}."
        )

    def duree(e: dict[str, Any], a: str, b: str) -> None:
        lo, hi = e["fourchette_secondes"]
        e["texte"] = (
            f"{noms[e['devant']]} plus long que {noms[autre(e, a, b)]} de {_secondes_ecrites(e['secondes'])} "
            f"({_secondes_ecrites(lo)} à {_secondes_ecrites(hi)})."
            if e["etabli"]
            else f"{noms[a]} et {noms[b]}."
        )

    groupes = [donnees.get("socle"), donnees.get("ensemble"), *donnees.get("metiers", [])]
    for groupe in (g for g in groupes if g):
        for paire in groupe.get("paires", []):
            a, b = paire["a"], paire["b"]
            ecart_de_taux(paire["essais"], a, b, "{devant} devant {autre} de {chiffres}.")
            ecart_de_taux(paire["cinq_sur_cinq"], a, b, "{devant} devant {autre} de {chiffres}.")
            if "duree_mediane" in paire:
                duree(paire["duree_mediane"], a, b)
    for cle in ("sans_gardien", "avec_gardien"):
        for paire in donnees.get("graves", {}).get(cle, {}).get("paires", []):
            ecart_de_taux(
                paire["ecart"], paire["a"], paire["b"], "{devant} en commet plus que {autre}" + NB + ": {chiffres}."
            )
    for paire in donnees.get("horizon", {}).get("paires", []):
        a, b = paire["a"], paire["b"]
        paire["texte"] = (
            f"{noms[paire['devant']]} tient plus longtemps que {noms[autre(paire, a, b)]}."
            if paire["etabli"]
            else f"{noms[a]} et {noms[b]}."
        )


def donnees_constat(
    dossier_runs: Path,
    candidats: Sequence[tuple[str, str]] = CANDIDATS,
    repetitions: int = REPETITIONS,
    dossier_runs_tau2: Path | None = None,
) -> dict[str, Any]:
    """Les données du constat de Calorelle, sur les runs que retient le rapport."""
    maintenant = datetime.now(UTC)
    donnees: dict[str, Any] = {
        "sujet": "constat",
        "version": VERSION,
        "produit_le": f"{maintenant:%Y-%m-%d}",
        "mois": "",
        "pme": "Calorelle",
        "repetitions": repetitions,
        "candidats": [
            {"identifiant": i, "nom": n, "court": COURTS.get(i, n), "detail": DETAILS_CONSTAT.get(i, "")}
            for i, n in candidats
        ],
        "socle": _socle(dossier_runs, candidats, repetitions),
        "horizon": _horizon(dossier_runs, candidats, repetitions),
        "graves": _graves(dossier_runs, candidats, repetitions),
        "graduations": [{"valeur": g, "pourcent": pourcent(g)} for g in GRADUATIONS],
        "echelle_taux": {
            "bas": ECHELLE_TAUX[0],
            "haut": ECHELLE_TAUX[1],
            "graduations": [
                {"valeur": g, "pourcent": pourcent(g), "position": _position(g, *ECHELLE_TAUX[:2])}
                for g in ECHELLE_TAUX[2]
            ],
        },
    }
    for c in donnees["candidats"]:
        c["detail"] = detail_avec_parts(c["detail"], donnees["socle"]["parts"].get(c["identifiant"], []))
    if dossier_runs_tau2 is not None:
        donnees["tau2"] = _releves_ecrits(_tau2(dossier_runs_tau2, candidats))
        donnees["graduations_tau2"] = [{"valeur": g, "pourcent": pourcent(g)} for g in GRADUATIONS_TAU2]
    donnees["mois"] = mois_des_runs(donnees)
    _textes_des_paires(donnees)
    return donnees


def donnees_video(donnees: dict[str, Any]) -> dict[str, list[int]]:
    """La part de la vidéo du premier post : les essais réussis de chaque tâche, dans l'ordre des
    tâches (t01 à t63), au format de son donnees.json. La vidéo ne nomme pas les tâches : l'ordre ne
    change que la place des cases."""
    par_tache: dict[str, dict[str, int]] = donnees["par_tache"]
    return {VIDEO[c]: list(par_tache[c].values()) for c in par_tache if c in VIDEO}


def _ecrire(chemin: Path, contenu: object) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(
        prog="python -m ease.donnees_publication", description="Les données d'une publication, calculées sur les runs."
    )
    analyse.add_argument("sujet", choices=["premier_post", "constat"], help="la publication")
    analyse.add_argument("--sortie", type=Path, required=True, help="le fichier JSON des données")
    analyse.add_argument("--video", type=Path, default=None, help="le donnees.json de la vidéo, à écrire aussi")
    analyse.add_argument(
        "--textes", type=Path, default=None, help="le textes.json des pages, contrôlé sur ces données, à écrire aussi"
    )
    options = analyse.parse_args(arguments)
    racine = racine_depot()
    try:
        candidats = [(i, nom) for i, nom in CANDIDATS if lire_candidat(i)]
        runs, runs_tau2 = racine / "99_local" / "runs", racine / "99_local" / "runs_tau2"
        if options.sujet == "constat":
            donnees = donnees_constat(runs, candidats, dossier_runs_tau2=runs_tau2)
        else:
            donnees = donnees_premier_post(runs, candidats=candidats, dossier_runs_tau2=runs_tau2)
    except RapportImpossible as erreur:
        print(f"Données impossibles : {erreur}", file=sys.stderr)
        return 2
    _ecrire(options.sortie, donnees)
    print(f"Données : {options.sortie}")
    if options.textes is not None:
        from ease.textes_publies import TextesImpossibles, textes_controles

        try:
            _ecrire(options.textes, textes_controles(options.sujet, donnees))
        except TextesImpossibles as erreur:
            print(f"Textes refusés : {erreur}", file=sys.stderr)
            return 3
        print(f"Textes : {options.textes}")
    if options.video is not None and options.sujet == "premier_post":
        _ecrire(options.video, donnees_video(donnees))
        print(f"Vidéo : {options.video}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
