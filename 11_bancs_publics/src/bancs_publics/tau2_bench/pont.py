"""Le seul module du pont qui parle au paquet tau2 : une conversation d'airline, jouée pas à pas
par un agent du dehors, et notée par l'évaluateur de τ²-bench.

τ²-bench (Sierra, licence MIT, version 1.0.1) fait jouer un agent contre un simulateur
d'utilisateur, sous son propre orchestrateur. Son gymnase (`tau2.gym.gym_agent.AgentGymEnv`) le
fait tourner dans un fil à part et laisse un agent extérieur donner chaque geste : un message au
client, ou un appel d'outil. Ce module s'en sert tel quel, pour que les tours, les limites de 200
messages et de 10 erreurs d'outil, les fins de conversation et la note soient ceux de τ²-bench.
Il remplace trois méthodes du gymnase, internes à la version figée : la tâche vient du jeu chargé
(Sierra ou Verified), la base d'un cache en mémoire, et l'utilisateur, au besoin, d'un texte écrit
d'avance. Les tests du pont repèrent une version de τ²-bench qui les changerait.

Une course dans le gymnase, trouvée le 2026-10-08 (1 exécution sur 400 du témoin parfait) : l'agent
du gymnase annonce son tour (`is_agent_turn`) dès qu'il efface son drapeau, puis met à jour son
observation sous son verrou ; `AgentGymEnv.step` la lit sans ce verrou, et peut lire celle du tour
d'avant, sans la réponse de l'outil. Le pont lit l'observation sous le verrou de l'agent, et une
réponse qui manque encore devient une panne du pont, jamais une erreur montrée à l'agent.

τ²-bench n'a pas d'annotations complètes pour pyright strict : ses appels restent ici, et le reste
du pont ne voit que des textes, des dictionnaires et des booléens. `TAU2_DATA_DIR` doit être posé
avant le premier import de ce module (`bancs_publics.tau2_bench.__main__`).

L'utilisateur écrit d'avance ne coûte rien et sert aux témoins et aux tests : il donne en un seul
message la raison de l'appel, ce qu'il sait et ses consignes, puis clôt la conversation
(`###STOP###`) à la première réponse de l'agent. Il ne mesure aucun agent.

L'utilisateur rejoué ne coûte rien non plus : il redit, dans l'ordre, les messages de l'utilisateur
d'une conversation publiée par Sierra, un à chaque message de l'agent, `###STOP###` compris. Face
aux gestes de l'agent de cette conversation rejoués à l'identique, τ²-bench doit refaire la même
conversation et la noter comme ses auteurs (témoin rejoueur, `ease.rejeu_tau2`). À la clôture, la
note dit en plus si la conversation rejouée a divergé de la publiée, et où : une note égale ne
suffit pas à prouver la même conversation.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false
# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportIncompatibleMethodOverride=false
# pyright: reportMissingTypeArgument=false, reportAttributeAccessIssue=false

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import litellm
from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT
from tau2.config import DEFAULT_LLM_ARGS_USER, DEFAULT_MAX_STEPS
from tau2.data_model.message import AssistantMessage, Message, ToolCall, ToolMessage, UserMessage
from tau2.data_model.simulation import SimulationRun
from tau2.data_model.tasks import StructuredUserInstructions, Task
from tau2.domains.airline.data_model import FlightDB
from tau2.domains.airline.environment import get_environment
from tau2.domains.airline.utils import AIRLINE_DB_PATH
from tau2.environment.environment import Environment
from tau2.environment.toolkit import ToolType
from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau2.gym.gym_agent import AgentGymEnv
from tau2.user.user_simulator import UserSimulator
from tau2.user.user_simulator_base import STOP, UserState

litellm.suppress_debug_info = True
"""litellm imprime une liste des fournisseurs quand il ne sait pas chiffrer une réponse (celles
d'OpenRouter, nommées google/gemini-2.5-flash) ; τ²-bench n'en garde qu'un coût nul, et EASE
chiffre le simulateur lui-même (ease.terrain_tau2.consommation_simulateur)."""

DOMAINE = "airline"
ECRIT_D_AVANCE = "ecrit_d_avance"
"""Nom de l'utilisateur écrit d'avance, à la place d'un modèle de simulateur."""
REJOUE = "rejoue"
"""Préfixe de l'utilisateur rejoué : `rejoue:<agent>`, les conversations publiées de cet agent."""
OUTIL_CLIENT = "send_message_to_user"
"""L'outil par lequel l'agent parle au client ; son résultat est la réponse du client."""

type TypeOutil = Literal["lecture", "ecriture", "generique"]


class ConversationTerminee(Exception):
    """L'utilisateur, l'agent ou une limite de τ²-bench a clos la conversation : plus aucun geste."""


class PanneDuPont(Exception):
    """Le pont n'a pas su lire la réponse d'un geste : une erreur technique, pas une faute de l'agent."""


@dataclass(frozen=True)
class Outil:
    """Un outil d'airline tel que τ²-bench le présente à son agent : nom, description, schéma."""

    nom: str
    description: str
    schema: dict[str, Any]
    type: TypeOutil


_TYPES: dict[ToolType, TypeOutil] = {
    ToolType.READ: "lecture",
    ToolType.WRITE: "ecriture",
    ToolType.GENERIC: "generique",
}

_verrou_base = threading.Lock()
_base_brute: dict[str, Any] | None = None


def _base_neuve() -> FlightDB:
    """Une base d'airline neuve, validée depuis une lecture unique de db.json."""
    global _base_brute
    with _verrou_base:
        if _base_brute is None:
            _base_brute = json.loads(Path(AIRLINE_DB_PATH).read_text(encoding="utf-8"))
        brute = _base_brute
    return FlightDB.model_validate(brute)


def environnement_neuf() -> Environment:
    return get_environment(db=_base_neuve())


def outils_airline() -> list[Outil]:
    """Les 14 outils d'airline, dans l'ordre de τ²-bench, avec leur type (lecture, écriture, générique)."""
    environnement = environnement_neuf()
    boite = environnement.tools
    if boite is None:
        raise RuntimeError("τ²-bench ne donne aucun outil pour airline")
    outils: list[Outil] = []
    for outil in environnement.get_tools():
        fonction = outil.openai_schema["function"]
        type_outil = _TYPES[boite.tool_type(outil.name)]
        outils.append(Outil(fonction["name"], fonction["description"], dict(fonction["parameters"]), type_outil))
    return outils


def consigne_systeme() -> str:
    """La consigne de l'agent de τ²-bench : ses instructions, puis la politique du domaine."""
    return SYSTEM_PROMPT.format(agent_instruction=AGENT_INSTRUCTION, domain_policy=environnement_neuf().get_policy())


def lire_taches(chemin: Path) -> dict[str, Task]:
    """Les tâches d'un fichier tasks.json de τ²-bench, par identifiant."""
    brutes: list[dict[str, Any]] = json.loads(chemin.read_text(encoding="utf-8"))
    taches = [Task.model_validate(brute) for brute in brutes]
    return {tache.id: tache for tache in taches}


def premier_message_ecrit(tache: Task) -> str:
    """Le message unique de l'utilisateur écrit d'avance : raison de l'appel, ce qu'il sait, ses
    consignes, séparés par une ligne vide."""
    consignes = tache.user_scenario.instructions
    if not isinstance(consignes, StructuredUserInstructions):
        return str(consignes).strip()
    parties = [consignes.reason_for_call, consignes.known_info, consignes.task_instructions]
    return "\n\n".join(p.strip() for p in parties if p and p.strip())


class UtilisateurEcritDAvance(UserSimulator):
    """Un utilisateur sans modèle : son premier message est écrit d'avance, puis il clôt."""

    def __init__(self, premier: str) -> None:
        super().__init__(llm=ECRIT_D_AVANCE)
        self._premier = premier

    def get_init_state(self, message_history: list[Message] | None = None) -> UserState:
        historique: list[Any] = list(message_history or [])
        return UserState(messages=historique, system_messages=[])

    def set_seed(self, seed: int) -> None:
        del seed

    def generate_next_message(self, message: Any, state: UserState) -> tuple[UserMessage, UserState]:
        del message
        deja = any(isinstance(m, UserMessage) for m in state.messages)
        reponse = UserMessage(role="user", content=STOP if deja else self._premier)
        state.messages.append(reponse)
        return reponse, state


@dataclass(frozen=True)
class Publiee:
    """Une conversation publiée par Sierra, vue du pont : les messages de l'utilisateur, que redit
    l'utilisateur rejoué, puis ce qui montre que la conversation rejouée est la même."""

    utilisateur: list[str]
    reponses: list[tuple[str | None, bool]]
    """Chaque réponse d'outil, dans l'ordre : son contenu et si c'est une erreur."""
    terminaison: str


def lire_publiees(chemin: Path) -> dict[tuple[str, int], Publiee]:
    """Les conversations d'un fichier publié par Sierra, par tâche et par essai."""
    publication: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
    publiees: dict[tuple[str, int], Publiee] = {}
    for simulation in publication["simulations"]:
        cle = (str(simulation["task_id"]), int(simulation["trial"]))
        if cle in publiees:
            raise ValueError(f"{chemin.name} : deux conversations pour la tâche {cle[0]}, essai {cle[1]}")
        messages: list[dict[str, Any]] = simulation["messages"]
        publiees[cle] = Publiee(
            utilisateur=[str(m["content"]) for m in messages if m["role"] == "user"],
            reponses=[(m["content"], bool(m.get("error"))) for m in messages if m["role"] == "tool"],
            terminaison=str(simulation["termination_reason"]),
        )
    return publiees


def _contenu(texte: str | None) -> Any:
    """Un contenu de réponse d'outil, comparé comme τ²-bench le fait en rejeu strict : lu comme
    JSON s'il en est, tel quel sinon (Environment.set_state)."""
    if texte is None:
        return None
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        return texte


def divergence(simulation: SimulationRun, publiee: Publiee) -> str | None:
    """La première différence entre une conversation rejouée et la publiée, None s'il n'y en a pas :
    mêmes messages de l'utilisateur, mêmes réponses d'outil (contenu et erreur), même fin."""
    messages: list[Any] = list(simulation.messages or [])
    dits = [str(m.content) for m in messages if isinstance(m, UserMessage)]
    for rang, (dit, publie) in enumerate(zip(dits, publiee.utilisateur, strict=False), 1):
        if dit != publie:
            return f"message {rang} de l'utilisateur différent du publié"
    if len(dits) != len(publiee.utilisateur):
        return f"{len(dits)} messages de l'utilisateur pour {len(publiee.utilisateur)} publiés"
    reponses = [(m.content, bool(m.error)) for m in messages if isinstance(m, ToolMessage)]
    for rang, ((texte, erreur), (attendu, erreur_attendue)) in enumerate(
        zip(reponses, publiee.reponses, strict=False), 1
    ):
        if erreur != erreur_attendue or _contenu(texte) != _contenu(attendu):
            return f"réponse d'outil {rang} différente de la publiée"
    if len(reponses) != len(publiee.reponses):
        return f"{len(reponses)} réponses d'outil pour {len(publiee.reponses)} publiées"
    terminaison = str(simulation.termination_reason.value)
    if terminaison != publiee.terminaison:
        return f"fin {terminaison} pour {publiee.terminaison} publiée"
    return None


class UtilisateurRejoue(UserSimulator):
    """Un utilisateur sans modèle qui redit les messages d'une conversation publiée, dans l'ordre.

    S'il n'a plus rien à dire, la conversation rejouée a divergé de la publiée : il clôt, et
    divergence() le relève à la clôture."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__(llm=REJOUE)
        self._messages = list(messages)

    def get_init_state(self, message_history: list[Message] | None = None) -> UserState:
        historique: list[Any] = list(message_history or [])
        return UserState(messages=historique, system_messages=[])

    def set_seed(self, seed: int) -> None:
        del seed

    def generate_next_message(self, message: Any, state: UserState) -> tuple[UserMessage, UserState]:
        del message
        rang = sum(1 for m in state.messages if isinstance(m, UserMessage))
        texte = self._messages[rang] if rang < len(self._messages) else STOP
        reponse = UserMessage(role="user", content=texte)
        state.messages.append(reponse)
        return reponse, state


class _Gymnase(AgentGymEnv):
    """Le gymnase de τ²-bench sur une tâche donnée, une base en cache et l'utilisateur choisi."""

    def __init__(self, tache: Task, utilisateur: str, rejoues: list[str] | None = None) -> None:
        sans_modele = utilisateur == ECRIT_D_AVANCE or utilisateur.startswith(REJOUE)
        modele = None if sans_modele else utilisateur
        super().__init__(
            domain=DOMAINE,
            task_id=tache.id,
            max_steps=DEFAULT_MAX_STEPS,
            user_llm=modele,
            user_llm_args=dict(DEFAULT_LLM_ARGS_USER),
        )
        self._tache = tache
        self._utilisateur = utilisateur
        self._rejoues = rejoues

    def _get_task(self) -> Task:
        return self._tache

    def _get_environment(self) -> Environment:
        return environnement_neuf()

    def _get_user(self) -> UserSimulator:
        if self._rejoues is not None:
            return UtilisateurRejoue(self._rejoues)
        if self._utilisateur == ECRIT_D_AVANCE:
            return UtilisateurEcritDAvance(premier_message_ecrit(self._tache))
        if self._utilisateur.startswith(REJOUE):
            raise ValueError("utilisateur rejoué sans conversation publiée")
        return super()._get_user()

    @property
    def termine(self) -> bool:
        return self._simulation_done.is_set()

    def observation(self) -> list[Message]:
        """L'observation de l'agent du gymnase, lue sous son verrou : l'orchestrateur la met à jour
        sous ce même verrou, après avoir annoncé le tour de l'agent."""
        agent = self._agent
        if agent is None:
            return []
        with agent._lock:
            return list(agent.observation)

    def simulation(self) -> SimulationRun | None:
        return self._simulation_run

    def jouer(self, geste: AssistantMessage) -> list[Message]:
        """Le pas de AgentGymEnv.step, sans relire le geste depuis un texte : un message au client
        ne peut pas passer pour un appel d'outil, ni l'inverse."""
        if self._orchestrator is None or self._agent is None:
            raise RuntimeError("conversation non ouverte")
        with self._lock:
            if self._simulation_done.is_set():
                raise ConversationTerminee("The conversation has ended.")
            self._agent.set_action(geste)
            while not self._simulation_done.is_set() and not self._agent.is_agent_turn:
                self._simulation_done.wait(timeout=0.01)
        if self._orchestrator_thread is not None and self._simulation_done.is_set():
            self._orchestrator_thread.join(timeout=10)
        return self.observation()


def _texte(message: Message) -> str:
    contenu = message.content
    return "" if contenu is None else str(contenu)


def _ligne(message: Message) -> str:
    return f"{message.role}: {_texte(message)}"


@dataclass(frozen=True)
class Reponse:
    """Ce que rend un geste : le texte pour l'agent, s'il est en erreur, et si la conversation est close."""

    texte: str
    erreur: bool
    terminee: bool


class Conversation:
    """Une exécution d'une tâche d'airline : ouverture, gestes de l'agent, clôture et note."""

    def __init__(self, tache: Task, jeu: str, utilisateur: str, publiee: Publiee | None = None) -> None:
        """publiee : la conversation publiée que redit l'utilisateur rejoué, avec utilisateur
        `rejoue:<agent>`."""
        self.tache = tache
        self.jeu = jeu
        self.utilisateur = utilisateur
        self._publiee = publiee
        self._gymnase = _Gymnase(tache, utilisateur, None if publiee is None else publiee.utilisateur)
        self._appels = 0
        self._ouverte = False

    def ouvrir(self) -> str:
        """Lance l'orchestrateur de τ²-bench jusqu'au premier tour de l'agent ; rend l'énoncé :
        la consigne de l'agent de τ²-bench, puis le début de la conversation."""
        self._gymnase.reset()
        self._ouverte = True
        debut = "\n".join(
            _ligne(m) for m in self._gymnase.observation() if isinstance(m, AssistantMessage | UserMessage)
        )
        return f"{consigne_systeme()}\n\nConversation so far:\n{debut}"

    @property
    def terminee(self) -> bool:
        return self._gymnase.termine

    def outil(self, nom: str, arguments: dict[str, Any]) -> Reponse:
        """Un appel d'outil d'airline, exécuté par l'orchestrateur de τ²-bench."""
        self._appels += 1
        appel = ToolCall(id=f"appel_{self._appels}", name=nom, arguments=arguments, requestor="assistant")
        observation = self._gymnase.jouer(AssistantMessage(role="assistant", content=None, tool_calls=[appel]))
        reponse = next((m for m in reversed(observation) if isinstance(m, ToolMessage)), None)
        if reponse is None or reponse.id != appel.id:
            if self.terminee:
                return Reponse("The conversation has ended.", True, True)
            raise PanneDuPont(f"aucune réponse de τ²-bench à l'appel {appel.id} ({nom})")
        return Reponse(_texte(reponse), bool(reponse.error), self.terminee)

    def message(self, texte: str) -> Reponse:
        """Un message de l'agent au client ; rend la réponse du client."""
        observation = self._gymnase.jouer(AssistantMessage(role="assistant", content=texte))
        reponse = next((m for m in reversed(observation) if isinstance(m, UserMessage)), None)
        return Reponse("" if reponse is None else _texte(reponse), False, self.terminee)

    def cloturer(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Clôt la conversation et la note avec l'évaluateur de τ²-bench.

        Un agent qui rend la main avant que le client ait clos appelle l'outil d'arrêt du gymnase,
        comme le prévoit τ²-bench pour un agent extérieur : la fin est alors agent_stop, notée
        normalement. Rend la simulation (format de τ²-bench, réévaluable) et la note ; sous
        l'utilisateur rejoué, la note porte aussi `divergence`, None si la conversation rejouée est
        la publiée."""
        if not self._ouverte:
            raise RuntimeError("conversation non ouverte")
        if not self.terminee:
            arret = ToolCall(id="arret", name="done", arguments={}, requestor="assistant")
            self._gymnase.jouer(AssistantMessage(role="assistant", content=None, tool_calls=[arret]))
        simulation = self._gymnase.simulation()
        if simulation is None:
            raise RuntimeError("τ²-bench n'a pas rendu de simulation")
        note = evaluer(simulation, self.tache, self.jeu)
        if self._publiee is not None:
            note["divergence"] = divergence(simulation, self._publiee)
        return simulation.model_dump(mode="json"), note


def evaluer(simulation: SimulationRun, tache: Task, jeu: str) -> dict[str, Any]:
    """La note de τ²-bench (evaluate_simulation, type ALL : sans juge) mise à plat pour EASE."""
    note = evaluate_simulation(
        simulation=simulation,
        task=tache,
        evaluation_type=EvaluationType.ALL,
        solo_mode=False,
        domain=DOMAINE,
    )
    base = None if note.db_check is None else bool(note.db_check.db_match)
    phrases = [{"phrase": c.info, "dite": bool(c.met)} for c in note.communicate_checks or []]
    composantes = {str(getattr(k, "value", k)): float(v) for k, v in (note.reward_breakdown or {}).items()}
    remarque = (note.info or {}).get("note")
    return {
        "jeu": jeu,
        "tache": tache.id,
        "terminaison": str(simulation.termination_reason.value),
        "recompense": float(note.reward),
        "base_egale": base,
        "phrases": phrases,
        "composantes": composantes,
        "note": None if remarque is None else str(remarque),
    }


def evaluer_fichier(chemin_simulation: Path, tache: Task, jeu: str) -> dict[str, Any]:
    """Réévalue une simulation écrite sur le disque, dans un processus neuf si besoin."""
    simulation = SimulationRun.model_validate_json(chemin_simulation.read_text(encoding="utf-8"))
    return evaluer(simulation, tache, jeu)
