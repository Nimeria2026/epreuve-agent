"""Le témoin rejoueur : les conversations airline que publie Sierra, rejouées et notées par EASE.

Second contrôle de la règle 4 du BRIEF, sans aucune dépense. Sierra publie, pour quatre agents,
200 conversations airline chacun (50 tâches, 4 essais), avec la récompense que τ²-bench leur a
donnée (`2026-10-08_faits_tau2_conversations_publiees.md`). Le témoin rejoueur refait chacune à
travers EASE : le serveur de 11_bancs_publics fait parler un utilisateur rejoué, qui redit les
messages publiés de l'utilisateur, et le témoin redonne, depuis son propre processus et par le
relais d'EASE, les gestes publiés de l'agent : chaque appel d'outil, chaque message au client.
EASE note la conversation comme d'habitude ; sa note doit être la note publiée. Le serveur dit
en plus, à la clôture, si la conversation rejouée a divergé de la publiée (messages de
l'utilisateur, réponses d'outil, fin) : la comparaison relève les deux, écarts de note et
divergences.

Deux formes d'un message publié de l'agent ne passent pas telles quelles par un outil MCP. Un
message qui porte plusieurs appels d'outil devient autant d'appels, dans le même ordre. Un message
qui porte du texte et des appels à la fois garde ses appels et perd son texte : τ²-bench ne le
montre pas à l'utilisateur, mais le compte pour les phrases à dire ; aucune phrase attendue des
800 conversations n'est dite seulement là (fichier de faits, section 3).

Le témoin joue les conversations dans l'ordre du run (chaque tâche, puis ses essais) et vérifie
que chaque énoncé finit par le premier message publié de la conversation qu'il va rejouer. Ce
message ne suffit pas à reconnaître la conversation : les quatre essais d'une tâche s'ouvrent
parfois sur le même (journal tau2, douzième entrée). Le rang la désigne ; la divergence relevée
à la clôture confirme l'essai.

Depuis la racine du dépôt, après `uv run --all-packages python -m bancs_publics.tau2_bench.donnees` :

    uv run --all-packages python -m ease.rejeu_tau2                       # les 4 agents, 800 conversations
    uv run --all-packages python -m ease.rejeu_tau2 --agents gpt_4_1 --taches 0,14
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import anyio
from mcp import Client

from ease.candidat_externe import CandidatExterne, Lancement
from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import Configuration, Machine
from ease.contrats.resultat_execution import ResultatExecution
from ease.executeur import Candidat, Consommation, ErreurOutil, Outils
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.statistiques import pass_k, resumer
from ease.temoins import fiche_temoin
from ease.terrain_tau2 import OUTIL_CLIENT, EnvironnementTau2, dossier_donnees, lancer_run, lire_taches

type Actions = list[tuple[str, dict[str, Any]]]

AGENTS: tuple[str, ...] = ("claude_3_7_sonnet", "gpt_4_1", "gpt_4_1_mini", "o4_mini")
"""Les agents dont Sierra publie les conversations airline, sous les noms du pont."""
ESSAIS = 4
CLASSEMENT: dict[str, tuple[float, float, float, float]] = {
    "claude_3_7_sonnet": (64.2, 58.9, 55.4, 52.1),
    "gpt_4_1": (56.0, 47.8, 42.4, 38.1),
    "gpt_4_1_mini": (48.7, 38.9, 32.1, 27.8),
    "o4_mini": (52.1, 44.2, 38.9, 34.7),
}
"""pass^1 à pass^4 airline du classement de τ²-bench, en pour cent (soumissions « legacy » du
2025-06-09, `web/leaderboard/public/submissions/`, lues le 2026-10-08). Leurs conversations ne
sont pas publiées : rapportés à côté, jamais comparés conversation par conversation."""


def fichier_publie(agent: str, donnees: Path | None = None) -> Path:
    chemin = (donnees or dossier_donnees()) / "publies" / f"{agent}.json"
    if not chemin.is_file():
        raise FileNotFoundError(
            f"conversations publiées introuvables : {chemin} ; lancer "
            "uv run --all-packages python -m bancs_publics.tau2_bench.donnees"
        )
    return chemin


def gestes(messages: Sequence[Mapping[str, Any]]) -> Actions:
    """Les gestes de l'agent d'une conversation publiée, après son message d'accueil fixe : chaque
    appel d'outil, dans l'ordre ; chaque message qui n'est que du texte, par l'outil du client."""
    joues: Actions = []
    for message in messages[1:]:
        if message.get("role") != "assistant":
            continue
        appels = cast(list[Mapping[str, Any]], message.get("tool_calls") or [])
        if appels:
            joues += [(str(a["name"]), dict(cast(Mapping[str, Any], a["arguments"]))) for a in appels]
        elif message.get("content"):
            joues.append((OUTIL_CLIENT, {"message": str(message["content"])}))
    return joues


@dataclass(frozen=True)
class ConversationPubliee:
    numero: str
    essai: int
    recompense: float
    premier: str
    """Le premier message publié de l'utilisateur, celui par lequel l'énoncé finit."""
    gestes: Actions


def conversations(agent: str, donnees: Path | None = None) -> dict[tuple[str, int], ConversationPubliee]:
    """Les conversations publiées d'un agent, par tâche et par essai."""
    publication: dict[str, Any] = json.loads(fichier_publie(agent, donnees).read_text(encoding="utf-8"))
    lues: dict[tuple[str, int], ConversationPubliee] = {}
    for simulation in cast(list[dict[str, Any]], publication["simulations"]):
        messages = cast(list[Mapping[str, Any]], simulation["messages"])
        premier = next(str(m["content"]) for m in messages if m.get("role") == "user")
        cle = (str(simulation["task_id"]), int(simulation["trial"]))
        recompense = float(cast(Mapping[str, Any], simulation["reward_info"])["reward"])
        lues[cle] = ConversationPubliee(cle[0], cle[1], recompense, premier, gestes(messages))
    return lues


class Rejeu:
    """Les conversations à rejouer d'un agent, dans l'ordre du run : chaque tâche, puis ses essais."""

    def __init__(self, agent: str, numeros: list[str] | None = None, donnees: Path | None = None) -> None:
        self.agent = agent
        self.taches = lire_taches("publie", donnees, numeros)
        self.publiees = conversations(agent, donnees)
        self.ordre = [self.publiees[(t.numero, e)] for t in self.taches for e in range(ESSAIS)]

    def conversation(self, rang: int, enonce: str) -> ConversationPubliee:
        """La conversation du rang donné dans le run, vérifiée sur l'énoncé reçu."""
        if rang >= len(self.ordre):
            raise ValueError(f"rang {rang} au-delà des {len(self.ordre)} conversations du rejeu")
        publiee = self.ordre[rang]
        if not enonce.endswith(f"user: {publiee.premier}"):
            raise ValueError(f"énoncé désaligné : tâche {publiee.numero}, essai {publiee.essai}")
        return publiee


class TemoinRejoueur:
    """Le témoin rejoueur dans le processus d'EASE : les mêmes gestes, par Outils. Aucun modèle."""

    def __init__(self, rejeu: Rejeu) -> None:
        self.rejeu = rejeu
        self._rang = 0

    @property
    def fiche(self) -> FicheCandidat:
        return fiche_temoin(f"temoin_rejoueur_{self.rejeu.agent}", f"Témoin rejoueur ({self.rejeu.agent})")

    @property
    def configuration(self) -> Configuration:
        return Configuration(modeles=[])

    @property
    def empreinte_prompts(self) -> str | None:
        return None

    @property
    def machine(self) -> Machine | None:
        return None

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        publiee = self.rejeu.conversation(self._rang, enonce)
        self._rang += 1
        for nom, arguments in publiee.gestes:
            try:
                outils.appeler_avec(nom, arguments)
            except ErreurOutil:
                continue  # l'agent publié a reçu la même erreur et a continué
        return Consommation()


async def _jouer_par_le_relais(adresse: str, actions: Actions) -> None:
    async with Client(adresse, mode="legacy", cache=None) as client:
        for nom, arguments in actions:
            await client.call_tool(nom, dict(arguments))  # une erreur d'outil revient au rejoueur, qui continue


def candidat_externe(rejeu: Rejeu, compteur: Path) -> CandidatExterne:
    """Le témoin rejoueur dans son propre processus, par le relais, comme un vrai candidat. Le
    compteur (un fichier remis à zéro ici) lui donne son rang dans le run d'une exécution à l'autre."""
    compteur.parent.mkdir(parents=True, exist_ok=True)
    compteur.write_text(json.dumps({"rang": 0}) + "\n", encoding="utf-8")
    commande = [sys.executable, "-m", "ease.rejeu_tau2", "jouer", "--agent", rejeu.agent, "--compteur", str(compteur)]
    commande += ["--taches", ",".join(t.numero for t in rejeu.taches)]
    return CandidatExterne(
        fiche=fiche_temoin(
            f"temoin_rejoueur_{rejeu.agent}_externe", f"Témoin rejoueur ({rejeu.agent}), processus séparé"
        ),
        configuration=Configuration(modeles=[]),
        lancement=Lancement(commande, delai_secondes=300),
    )


@dataclass(frozen=True)
class Comparaison:
    """Publié contre retrouvé, pour un agent."""

    agent: str
    conversations: list[tuple[str, int, float, float]]
    """(tâche, essai, récompense publiée, récompense retrouvée par EASE)."""
    publie: tuple[int, int, list[float]]
    """Réussites, conversations, pass^1 à pass^4, depuis les récompenses publiées."""
    retrouve: tuple[int, int, list[float]]
    """Les mêmes, depuis les résultats d'EASE."""
    erreurs_techniques: int
    divergences: list[tuple[str, int, str]]
    """(tâche, essai, première différence) des conversations rejouées qui ne sont pas la publiée."""

    @property
    def ecarts(self) -> list[tuple[str, int, float, float]]:
        return [c for c in self.conversations if abs(c[2] - c[3]) > 1e-6]


def _resume(par_tache: Mapping[str, list[bool]]) -> tuple[int, int, list[float]]:
    comptes = [(sum(v), len(v)) for v in par_tache.values()]
    k_max = min(n for _, n in comptes)
    return sum(c for c, _ in comptes), sum(n for _, n in comptes), [pass_k(comptes, k) for k in range(1, k_max + 1)]


def _divergence(chemin: Path) -> str | None:
    """La divergence que le serveur a notée à la clôture ; une note sans ce champ en est une."""
    note: object = json.loads(chemin.read_text(encoding="utf-8")) if chemin.is_file() else None
    if not isinstance(note, dict) or "divergence" not in note:
        return f"note du serveur sans divergence : {chemin}"
    divergence = cast(dict[str, Any], note)["divergence"]
    return None if divergence is None else str(divergence)


def comparer(rejeu: Rejeu, dossier_run: Path, travail: Path) -> Comparaison:
    """Récompense par conversation, puis réussites et pass^k, publiés contre retrouvés ; et les
    conversations rejouées qui ont divergé, d'après les notes du serveur dans son dossier de travail."""
    run = lire_fiche_de_run(dossier_run / "fiche_de_run.json").identifiant
    resultats: dict[tuple[str, int], ResultatExecution] = {}
    for chemin in sorted((dossier_run / "resultats").glob("*.json")):
        resultat = lire_resultat(chemin)
        numero = resultat.tache.identifiant.removeprefix("airline_")
        resultats[(numero, resultat.repetition - 1)] = resultat
    lignes: list[tuple[str, int, float, float]] = []
    divergences: list[tuple[str, int, str]] = []
    publies: dict[str, list[bool]] = {}
    retrouves: dict[str, list[bool]] = {}
    for publiee in rejeu.ordre:
        resultat = resultats[(publiee.numero, publiee.essai)]
        if resultat.arret == "erreur_technique":
            continue
        lignes.append((publiee.numero, publiee.essai, publiee.recompense, resultat.controles[0].score))
        execution = f"{run}_{resultat.tache.identifiant}_r{resultat.repetition}"
        divergence = _divergence(travail / execution / "evaluation.json")
        if divergence is not None:
            divergences.append((publiee.numero, publiee.essai, divergence))
        publies.setdefault(publiee.numero, []).append(abs(publiee.recompense - 1) <= 1e-6)
        retrouves.setdefault(publiee.numero, []).append(resultat.reussie)
    techniques = resumer(list(resultats.values())).erreurs_techniques
    return Comparaison(rejeu.agent, lignes, _resume(publies), _resume(retrouves), techniques, divergences)


def rejouer(
    agent: str,
    numeros: list[str] | None = None,
    externe: bool = True,
    dossier_runs: Path | None = None,
    travail: Path | None = None,
    donnees: Path | None = None,
) -> tuple[Path, Comparaison]:
    """Rejoue les conversations publiées d'un agent par EASE, puis compare les notes."""
    rejeu = Rejeu(agent, numeros, donnees)
    environnement = EnvironnementTau2("publie", donnees, travail, f"rejoue:{agent}")
    candidat: Candidat = (
        candidat_externe(rejeu, environnement.travail / f"compteur_{agent}.json") if externe else TemoinRejoueur(rejeu)
    )
    dossier = lancer_run(
        candidat=candidat,
        environnement=environnement,
        taches=rejeu.taches,
        repetitions=ESSAIS,
        dossier_runs=dossier_runs,
    )
    return dossier, comparer(rejeu, dossier, environnement.travail)


def _pc(valeur: float) -> str:
    return f"{100 * valeur:.1f}".replace(".", ",") + " %"


def tableau(comparaisons: list[Comparaison]) -> list[str]:
    """Le tableau « publié contre retrouvé » par agent, en Markdown."""
    lignes = [
        "| Agent | Publié (fichiers) | Retrouvé par EASE | Écarts | Divergences | pass^1 à pass^4 publiés | "
        "pass^1 à pass^4 retrouvés | Classement de τ²-bench |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in comparaisons:
        classement = " ; ".join(f"{v:.1f}".replace(".", ",") for v in CLASSEMENT[c.agent]) + " %"
        lignes.append(
            f"| {c.agent} | {c.publie[0]}/{c.publie[1]} | {c.retrouve[0]}/{c.retrouve[1]} | {len(c.ecarts)} | "
            f"{len(c.divergences)} | "
            f"{' ; '.join(_pc(p) for p in c.publie[2])} | {' ; '.join(_pc(p) for p in c.retrouve[2])} | {classement} |"
        )
    return lignes


def _jouer(arguments: list[str]) -> int:
    """Une exécution du témoin rejoueur dans son propre processus, lancée par CandidatExterne."""
    analyse = argparse.ArgumentParser(prog="python -m ease.rejeu_tau2 jouer")
    analyse.add_argument("--agent", choices=AGENTS, required=True)
    analyse.add_argument("--compteur", type=Path, required=True)
    analyse.add_argument("--taches", required=True)
    analyse.add_argument("--mcp", required=True)
    analyse.add_argument("--enonce", type=Path, required=True)
    analyse.add_argument("--sortie", type=Path, required=True)
    options = analyse.parse_args(arguments)
    rejeu = Rejeu(options.agent, options.taches.split(","))
    etat: dict[str, Any] = json.loads(options.compteur.read_text(encoding="utf-8"))
    rang = int(etat["rang"])
    options.compteur.write_text(json.dumps({"rang": rang + 1}) + "\n", encoding="utf-8")
    publiee = rejeu.conversation(rang, options.enonce.read_text(encoding="utf-8"))
    anyio.run(_jouer_par_le_relais, options.mcp, publiee.gestes)
    sortie: dict[str, Any] = {
        "fin": "termine",
        "detail": None,
        "appels_modele": 0,
        "consommation": {},
        "modeles_renvoyes": {},
    }
    options.sortie.write_text(json.dumps(sortie) + "\n", encoding="utf-8")
    return 0


def main(arguments: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if arguments[:1] == ["jouer"]:
        return _jouer(arguments[1:])
    analyse = argparse.ArgumentParser(prog="python -m ease.rejeu_tau2", description="Témoin rejoueur de τ²-bench.")
    analyse.add_argument("--agents", default=",".join(AGENTS), help=f"parmi {', '.join(AGENTS)}")
    analyse.add_argument("--taches", default=None, help="numéros de τ²-bench séparés par des virgules (toutes sinon)")
    analyse.add_argument("--dans-le-processus", action="store_true", help="sans processus séparé ni relais HTTP")
    options = analyse.parse_args(arguments)
    agents = [a.strip() for a in options.agents.split(",") if a.strip()]
    inconnus = [a for a in agents if a not in AGENTS]
    if inconnus:
        print(f"agents inconnus : {', '.join(inconnus)} (connus : {', '.join(AGENTS)})", file=sys.stderr)
        return 2
    numeros = None if options.taches is None else [n.strip() for n in options.taches.split(",") if n.strip()]
    print("Témoin rejoueur sur τ²-bench, runs dans 99_local/runs_tau2/\n")
    comparaisons: list[Comparaison] = []
    for agent in agents:
        dossier, comparaison = rejouer(agent, numeros, externe=not options.dans_le_processus)
        comparaisons.append(comparaison)
        print(f"{agent} : {len(comparaison.conversations)} conversations, run {dossier.name}")
        for numero, essai, publiee, retrouvee in comparaison.ecarts:
            print(f"  écart : tâche {numero}, essai {essai}, publiée {publiee:g}, retrouvée {retrouvee:g}")
        for numero, essai, divergence in comparaison.divergences:
            print(f"  divergence : tâche {numero}, essai {essai}, {divergence}")
    print()
    print("\n".join(tableau(comparaisons)))
    conforme = all(not c.ecarts and not c.divergences and c.erreurs_techniques == 0 for c in comparaisons)
    print(
        "\nChaque conversation rejouée est la publiée et retrouve sa note."
        if conforme
        else "\nÉCART : des notes diffèrent, des conversations divergent ou des exécutions ont échoué."
    )
    return 0 if conforme else 1


if __name__ == "__main__":
    sys.exit(main())
