"""Les témoins du banc sur τ²-bench (règle 4 du BRIEF), et leur commande.

Depuis la racine du dépôt, après `uv run --all-packages python -m bancs_publics.tau2_bench.donnees` :

    uv run --all-packages python -m ease.temoins_tau2                      # airline de Sierra, 50 tâches
    uv run --all-packages python -m ease.temoins_tau2 --jeu verified --taches 0,14 --repetitions 2

Comme sur la PME, chaque témoin a un comportement connu d'avance, donc un taux attendu, et
reconnaît la tâche à son énoncé, seule information qu'un candidat reçoit. Ils jouent contre
l'utilisateur écrit d'avance du serveur, qui ne coûte rien : son unique message clôt sur la
première réponse de l'agent, et l'énoncé finit par ce message.

- Parfait : les actions de référence de la tâche (`evaluation_criteria.actions`), puis un message
  au client qui contient chaque phrase à dire (`communicate_info`). Attendu : 100 %.
- Toujours faux : un avoir de 1 dollar envoyé à un client du jeu (`send_certificate`), écriture
  qu'aucune tâche ne demande, puis un message. Attendu : 0 %.
- Une fois sur deux : le parfait à un appel sur deux, le toujours faux à l'autre. Attendu : 50 %.
  Ne rien faire à l'autre appel ne donnerait pas 50 % : voir l'inerte.
- Inerte : ne fait rien. Sur la PME il obtient 0 % ; sur airline, une tâche dont les actions de
  référence ne font que lire et qui n'a rien à faire dire est réussie sans rien faire. Attendu :
  la part de ces tâches, le plancher d'inertie, calculé ici depuis le fichier de tâches et ce que
  chaque outil annonce (lecture seule ou non), sans regarder τ²-bench noter.
"""

from __future__ import annotations

import argparse
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import Configuration, Machine
from ease.executeur import Candidat, Consommation, DescriptionOutil, Outils
from ease.fiches import lire_resultat
from ease.statistiques import Resume, resumer
from ease.temoins import fiche_temoin
from ease.terrain_tau2 import (
    JEUX,
    OUTIL_CLIENT,
    EnvironnementTau2,
    Jeu,
    TacheTau2,
    lancer_run,
    lire_taches,
    taches_brutes,
)

type Actions = list[tuple[str, dict[str, Any]]]

REPETITIONS = 4
"""Nombre pair : le témoin une fois sur deux réussit alors exactement la moitié des exécutions."""
MESSAGE_SANS_PHRASE = "Your request has been handled. Thank you for contacting us."
MESSAGE_FAUX = "Done."


def premier_message(brute: Mapping[str, Any]) -> str:
    """Le message unique de l'utilisateur écrit d'avance du serveur (pont.premier_message_ecrit) :
    raison de l'appel, ce qu'il sait, ses consignes, séparés par une ligne vide."""
    consignes: object = cast(Mapping[str, Any], brute["user_scenario"])["instructions"]
    if not isinstance(consignes, dict):
        return str(consignes).strip()
    c = cast(dict[str, Any], consignes)
    parties: list[object] = [c.get("reason_for_call"), c.get("known_info"), c.get("task_instructions")]
    return "\n\n".join(p.strip() for p in parties if isinstance(p, str) and p.strip())


def _criteres(brute: Mapping[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], brute.get("evaluation_criteria") or {})


def actions_de_reference(brute: Mapping[str, Any]) -> Actions:
    actions = cast(list[dict[str, Any]], _criteres(brute).get("actions") or [])
    return [(str(a["name"]), dict(cast(dict[str, Any], a["arguments"]))) for a in actions]


def phrases_a_dire(brute: Mapping[str, Any]) -> list[str]:
    return [str(p) for p in cast(list[object], _criteres(brute).get("communicate_info") or [])]


def _clients(brutes: list[dict[str, Any]]) -> list[str]:
    """Les identifiants de client que citent les actions de référence, dans l'ordre du fichier."""
    vus: list[str] = []
    for brute in brutes:
        for _, arguments in actions_de_reference(brute):
            client = arguments.get("user_id")
            if isinstance(client, str) and client not in vus:
                vus.append(client)
    return vus


@dataclass(frozen=True)
class TerrainTau2:
    """Où passent les témoins sur τ²-bench : un jeu, ses tâches, et les gestes connus d'avance."""

    jeu: Jeu
    taches: list[TacheTau2]
    premiers: Mapping[str, str]
    solutions: Mapping[str, Actions]
    erreurs: Mapping[str, Actions]
    lectures_seules: Mapping[str, list[str]]
    """Pour chaque tâche, les outils de ses actions de référence, et si elle a une phrase à dire."""
    a_dire: Mapping[str, bool]
    donnees: Path | None = None

    @property
    def nom(self) -> str:
        return f"tau2_airline_{self.jeu}"

    def tache(self, enonce: str) -> str:
        """Identifiant de la tâche dont l'énoncé finit par le message de l'utilisateur écrit d'avance."""
        trouvees = [t.identifiant for t in self.taches if enonce.endswith(f"user: {self.premiers[t.identifiant]}")]
        if len(trouvees) != 1:
            raise ValueError(f"énoncé de τ²-bench reconnu {len(trouvees)} fois au lieu d'une")
        return trouvees[0]

    def plancher(self, outils: list[DescriptionOutil]) -> list[str]:
        """Les tâches qu'un agent inerte réussit : aucune action de référence par un outil qui se
        déclare en écriture (readOnlyHint faux), et rien à faire dire."""
        ecritures = {o.nom for o in outils if o.lecture_seule is False}
        return [
            t.identifiant
            for t in self.taches
            if not self.a_dire[t.identifiant] and not set(self.lectures_seules[t.identifiant]) & ecritures
        ]

    def environnement(self, travail: Path | None = None) -> EnvironnementTau2:
        return EnvironnementTau2(self.jeu, self.donnees, travail)


def terrain_tau2(jeu: Jeu = "sierra", numeros: list[str] | None = None, donnees: Path | None = None) -> TerrainTau2:
    """Le terrain d'un jeu de τ²-bench, sur toutes ses tâches ou sur celles de numeros."""
    brutes = taches_brutes(jeu, donnees)
    par_numero = {str(b["id"]): b for b in brutes}
    taches = lire_taches(jeu, donnees, numeros)
    clients = _clients(brutes)
    if not clients:
        raise ValueError(f"aucun client dans les actions de référence du jeu {jeu}")
    premiers: dict[str, str] = {}
    solutions: dict[str, Actions] = {}
    erreurs: dict[str, Actions] = {}
    outils: dict[str, list[str]] = {}
    a_dire: dict[str, bool] = {}
    for tache in taches:
        brute = par_numero[tache.numero]
        actions = actions_de_reference(brute)
        phrases = phrases_a_dire(brute)
        client = next((a["user_id"] for _, a in actions if isinstance(a.get("user_id"), str)), clients[0])
        premiers[tache.identifiant] = premier_message(brute)
        solutions[tache.identifiant] = [
            *actions,
            (OUTIL_CLIENT, {"message": " ".join(phrases) if phrases else MESSAGE_SANS_PHRASE}),
        ]
        erreurs[tache.identifiant] = [
            ("send_certificate", {"user_id": client, "amount": 1}),
            (OUTIL_CLIENT, {"message": MESSAGE_FAUX}),
        ]
        outils[tache.identifiant] = [nom for nom, _ in actions]
        a_dire[tache.identifiant] = bool(phrases)
    if len(set(premiers.values())) != len(premiers):
        raise ValueError(f"terrain {jeu} : deux tâches ont le même message d'utilisateur écrit d'avance")
    return TerrainTau2(jeu, taches, premiers, solutions, erreurs, outils, a_dire, donnees)


class TemoinTau2(ABC):
    """Socle des témoins sur τ²-bench : aucun modèle, aucun prompt, aucune machine."""

    identifiant = ""
    nom = ""

    def __init__(self, terrain: TerrainTau2) -> None:
        self.terrain = terrain

    def _jouer(self, table: Mapping[str, Actions], enonce: str, outils: Outils) -> Consommation:
        for nom, arguments in table[self.terrain.tache(enonce)]:
            outils.appeler_avec(nom, arguments)
        return Consommation()

    @property
    def fiche(self) -> FicheCandidat:
        return fiche_temoin(self.identifiant, self.nom)

    @property
    def configuration(self) -> Configuration:
        return Configuration(modeles=[])

    @property
    def empreinte_prompts(self) -> str | None:
        return None

    @property
    def machine(self) -> Machine | None:
        return None

    @abstractmethod
    def reussites_attendues(self, executions: int, plancher: int) -> int:
        """Réussites attendues sur un run : executions au total, plancher tâches réussies sans rien faire."""

    @abstractmethod
    def executer(self, enonce: str, outils: Outils) -> Consommation: ...


class TemoinParfaitTau2(TemoinTau2):
    identifiant, nom = "temoin_parfait", "Témoin parfait"

    def reussites_attendues(self, executions: int, plancher: int) -> int:
        return executions

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        return self._jouer(self.terrain.solutions, enonce, outils)


class TemoinToujoursFauxTau2(TemoinTau2):
    identifiant, nom = "temoin_toujours_faux", "Témoin toujours faux"

    def reussites_attendues(self, executions: int, plancher: int) -> int:
        return 0

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        return self._jouer(self.terrain.erreurs, enonce, outils)


class TemoinUneFoisSurDeuxTau2(TemoinTau2):
    identifiant, nom = "temoin_une_fois_sur_deux", "Témoin une fois sur deux"

    def __init__(self, terrain: TerrainTau2) -> None:
        super().__init__(terrain)
        self._appels = 0

    def reussites_attendues(self, executions: int, plancher: int) -> int:
        return executions // 2

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        self._appels += 1
        table = self.terrain.solutions if self._appels % 2 == 1 else self.terrain.erreurs
        return self._jouer(table, enonce, outils)


class TemoinInerteTau2(TemoinTau2):
    identifiant, nom = "temoin_inerte", "Témoin inerte"

    def reussites_attendues(self, executions: int, plancher: int) -> int:
        return executions * plancher // len(self.terrain.taches)

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        return Consommation()


def temoins(terrain: TerrainTau2) -> list[TemoinTau2]:
    return [
        TemoinParfaitTau2(terrain),
        TemoinToujoursFauxTau2(terrain),
        TemoinUneFoisSurDeuxTau2(terrain),
        TemoinInerteTau2(terrain),
    ]


def mesurer(
    candidat: Candidat,
    terrain: TerrainTau2,
    environnement: EnvironnementTau2,
    repetitions: int = REPETITIONS,
    dossier_runs: Path | None = None,
) -> tuple[Path, Resume]:
    """Lance un candidat sur les tâches d'un terrain, puis relit ses résultats depuis le disque."""
    dossier = lancer_run(
        candidat=candidat,
        environnement=environnement,
        taches=terrain.taches,
        repetitions=repetitions,
        dossier_runs=dossier_runs,
    )
    resultats = [lire_resultat(chemin) for chemin in sorted((dossier / "resultats").glob("*.json"))]
    return dossier, resumer(resultats)


def _pourcent(valeur: float) -> str:
    return f"{valeur * 100:.1f}".replace(".", ",").removesuffix(",0") + " %"


def passer(terrain: TerrainTau2, repetitions: int = REPETITIONS, dossier_runs: Path | None = None) -> bool:
    """Passe les quatre témoins sur un terrain, un seul serveur pour les quatre, et imprime le
    tableau. Vrai si chaque témoin obtient exactement ses réussites attendues."""
    lignes: list[list[str]] = []
    conforme = True
    with terrain.environnement() as environnement:
        plancher = terrain.plancher(environnement.outils())
        for temoin in temoins(terrain):
            dossier, resume = mesurer(temoin, terrain, environnement, repetitions, dossier_runs)
            attendues = temoin.reussites_attendues(resume.executions, len(plancher))
            ok = resume.reussites == attendues and resume.erreurs_techniques == 0
            conforme &= ok
            bas, haut = resume.intervalle
            lignes.append(
                [
                    temoin.identifiant,
                    f"{resume.reussites}/{resume.executions}",
                    _pourcent(resume.taux),
                    f"{_pourcent(bas)} à {_pourcent(haut)}",
                    _pourcent(resume.pass_k[repetitions]),
                    f"{attendues}/{resume.executions}",
                    "conforme" if ok else "ÉCART",
                    dossier.name,
                ]
            )
    entetes = ["témoin", "réussites", "taux", "IC 95 %", f"pass^{repetitions}", "attendu", "verdict", "dossier du run"]
    largeurs = [max(len(ligne[i]) for ligne in [entetes, *lignes]) for i in range(len(entetes))]
    print(
        f"Terrain {terrain.nom} : {len(terrain.taches)} tâches, {repetitions} répétitions ; "
        f"plancher d'inertie {len(plancher)} sur {len(terrain.taches)}\n"
    )
    for ligne in [entetes, *lignes]:
        print("  ".join(c.ljust(largeur) for c, largeur in zip(ligne, largeurs, strict=True)).rstrip())
    print()
    return conforme


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m ease.temoins_tau2", description="Témoins du banc sur τ²-bench.")
    analyse.add_argument("--jeu", choices=[*JEUX, "tous"], default="sierra")
    analyse.add_argument("--taches", default=None, help="numéros de τ²-bench séparés par des virgules (toutes sinon)")
    analyse.add_argument("--repetitions", type=int, default=REPETITIONS, help="nombre pair (4 par défaut)")
    options = analyse.parse_args(arguments)
    if options.repetitions < 2 or options.repetitions % 2:
        print("--repetitions doit être pair", file=sys.stderr)
        return 2
    jeux: list[Jeu] = list(JEUX) if options.jeu == "tous" else [cast(Jeu, options.jeu)]
    numeros = None if options.taches is None else [n.strip() for n in options.taches.split(",") if n.strip()]
    print("Témoins du banc sur τ²-bench, runs dans 99_local/runs_tau2/\n")
    # Chaque jeu passe, même après un écart sur le précédent.
    verdicts = [passer(terrain_tau2(jeu, numeros), options.repetitions) for jeu in jeux]
    conforme = all(verdicts)
    print("Le banc mesure ce qu'il doit." if conforme else "ÉCART : le banc ne retrouve pas les taux attendus.")
    return 0 if conforme else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
