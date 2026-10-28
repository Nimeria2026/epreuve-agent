"""τ²-bench vu par EASE : un terrain de mesure, comme la PME, servi par MCP (étape 7).

Le serveur de `11_bancs_publics` (ADR 0004) fait tourner τ²-bench de Sierra, version 1.0.1, sur le
domaine airline : ses 14 outils, son simulateur d'utilisateur, son orchestrateur et son
évaluateur. EASE le lance une fois par run, par stdio, et lui parle comme à un serveur de la PME :
il ne l'importe jamais (règle 6). Il présente à l'agent les outils d'airline et l'outil qui parle
au client, jamais les deux outils qui lui sont réservés, `poa_ouvrir` et `poa_cloturer`.

Une exécution : `poa_ouvrir` remet une base neuve, lance la conversation jusqu'au premier tour de
l'agent et rend l'énoncé (la consigne de l'agent de τ²-bench, sa politique, le début de la
conversation) ; le candidat agit par Outils, qui compte les étapes, tient le journal et applique
le budget ; `poa_cloturer` clôt la conversation et écrit la note de τ²-bench sur le disque, où EASE
la lit, comme l'état final de la PME (règle 3). La note ne se partage pas : c'est celle des
auteurs du banc, base finale comparée à la base cible et phrases à dire, 0 ou 1.

Les tâches de τ²-bench ne suivent pas le contrat de tâche de la PME : leur contrôle est celui de
τ²-bench. Ce module a donc son propre exécuteur, qui reprend celui d'EASE (Outils, budget, arrêts,
coût) et écrit la même fiche de run et les mêmes résultats, aux mêmes contrats. L'état initial
s'y note en v1, avec l'empreinte des données de τ²-bench ; le champ banc_public de la fiche
(journal de l'étape 7, quatrième et seizième entrées) nomme le banc, sa version installée par
uv.lock, le domaine, le jeu et le simulateur d'utilisateur, avec ses jetons et son coût, lus à la
fin du run dans les conversations que le serveur écrit. Une tâche s'y nomme airline_<numéro>, en
version 1, dans le jeu tau2_airline_sierra ou tau2_airline_verified.

Le simulateur, quand c'est un modèle, appelle son API depuis le serveur : sa clé passe au serveur
par `variables`, jamais au candidat ni dans un fichier du run.

Ce module lit aussi le fichier de tâches de τ²-bench (des données, pas du code) : la liste des
tâches pour EASE, et leurs actions de référence pour les témoins (ease.temoins_tau2).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from anyio.from_thread import BlockingPortal, start_blocking_portal
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation, TextContent
from pydantic import BaseModel

from ease.chargement import ecarts_schema, racine_depot
from ease.contrats.fiche_de_run import (
    BancPublic,
    EtatPME,
    FicheDeRun,
    JetonsSimulateur,
    JeuDeTaches,
    ReferenceCandidat,
    SimulateurDuRun,
    TacheDuJeu,
    Tarif,
)
from ease.contrats.resultat_execution import Jetons, ReferenceTache, ResultatControle, ResultatExecution
from ease.empreintes import empreinte_json
from ease.executeur import (
    Arret,
    ArretDuRun,
    BudgetEtapesDepasse,
    Candidat,
    Consommation,
    DescriptionOutil,
    ErreurOutil,
    Outils,
    cout_dollars,
    maintenant,
    nouveau_dossier_de_run,
    version_code,
)
from ease.fiches import regles_fiche_de_run, regles_resultat

type Jeu = Literal["sierra", "verified", "publie"]
JEUX: tuple[Jeu, ...] = ("sierra", "verified")
"""Les jeux des témoins ; s'y ajoute « publie », les tâches embarquées dans les conversations que
publie Sierra, celles du témoin rejoueur (ease.rejeu_tau2)."""

OUVRIR = "poa_ouvrir"
CLOTURER = "poa_cloturer"
RESERVES = frozenset({OUVRIR, CLOTURER})
"""Les outils du serveur réservés à EASE, jamais présentés à l'agent."""
OUTIL_CLIENT = "send_message_to_user"

ETAPES_MAX = 100
"""Budget d'étapes d'une tâche de τ²-bench. Chaque geste de l'agent y prend deux messages (le
geste et sa réponse) sur les 200 que τ²-bench permet : sa propre limite tombe la première."""
COUT_MAX_DOLLARS = 1.0
"""τ²-bench n'a pas de plafond de coût ; celui-ci ne doit jamais tomber (une conversation airline
coûte de l'ordre du centime : 2026-10-08_faits_tau2_bench.md, section 5)."""
DELAI_SECONDES = 600.0
VERSION_ETAT = "v1"
"""La fiche de run veut une version d'état en v<n> : pour τ²-bench, la seule base d'airline."""
BANC = "tau2_bench"
PAQUET = "tau2"
DOMAINE = "airline"
ECRIT_D_AVANCE = "ecrit_d_avance"
REJOUE = "rejoue:"


def dossier_donnees(racine: Path | None = None) -> Path:
    """99_local/tau2/ : données de τ²-bench, récupérées par
    `uv run --all-packages python -m bancs_publics.tau2_bench.donnees`."""
    return (racine or racine_depot()) / "99_local" / "tau2"


def fichier_taches(jeu: Jeu, donnees: Path | None = None) -> Path:
    chemin = (donnees or dossier_donnees()) / "jeux" / f"{jeu}.json"
    if not chemin.is_file():
        raise FileNotFoundError(
            f"tâches de τ²-bench introuvables : {chemin} ; lancer "
            "uv run --all-packages python -m bancs_publics.tau2_bench.donnees"
        )
    return chemin


def nom_jeu(jeu: Jeu) -> str:
    return f"tau2_airline_{jeu}"


@dataclass(frozen=True)
class Simulateur:
    """Celui qui joue le client : un modèle au format de litellm, ou un utilisateur sans modèle
    (ecrit_d_avance, rejoue:<agent>), que le serveur reçoit par --utilisateur."""

    modele: str = ECRIT_D_AVANCE
    fournisseur: str | None = None
    parametres: Mapping[str, Any] = field(default_factory=lambda: {})
    """Réglages que le serveur envoie au modèle à chaque appel, notés tels quels dans la fiche."""
    tarif: Tarif | None = None
    cle_env: str | None = None
    """Variable de sa clé d'API, passée au seul serveur ; None sans modèle."""

    @property
    def sans_modele(self) -> bool:
        return sans_modele(self.modele)


def sans_modele(utilisateur: str) -> bool:
    return utilisateur == ECRIT_D_AVANCE or utilisateur.startswith(REJOUE)


@dataclass(frozen=True)
class BudgetTau2:
    etapes_max: int = ETAPES_MAX
    cout_max_dollars: float = COUT_MAX_DOLLARS


@dataclass(frozen=True)
class TacheTau2:
    """Une tâche d'airline de τ²-bench, telle qu'EASE la lance et la note."""

    numero: str
    """Son identifiant chez τ²-bench, par exemple « 14 »."""
    version: int = 1
    budget: BudgetTau2 = field(default_factory=BudgetTau2)

    @property
    def identifiant(self) -> str:
        return f"airline_{self.numero}"


def taches_brutes(jeu: Jeu, donnees: Path | None = None) -> list[dict[str, Any]]:
    """Le fichier de tâches de τ²-bench, tel quel."""
    brutes: object = json.loads(fichier_taches(jeu, donnees).read_text(encoding="utf-8"))
    if not isinstance(brutes, list):
        raise ValueError(f"tâches de τ²-bench illisibles pour le jeu {jeu}")
    return cast(list[dict[str, Any]], brutes)


def lire_taches(jeu: Jeu, donnees: Path | None = None, numeros: list[str] | None = None) -> list[TacheTau2]:
    """Les tâches d'un jeu, dans l'ordre de τ²-bench ; numeros en garde certaines, dans cet ordre."""
    connues = [str(brute["id"]) for brute in taches_brutes(jeu, donnees)]
    if numeros is None:
        return [TacheTau2(n) for n in connues]
    inconnus = [n for n in numeros if n not in connues]
    if inconnus:
        raise ValueError(f"tâches inconnues dans le jeu {jeu} : {', '.join(inconnus)}")
    return [TacheTau2(n) for n in numeros]


def empreinte_donnees(jeu: Jeu, donnees: Path | None = None) -> str:
    """Empreinte des fichiers que lit τ²-bench (base, politique, consignes du simulateur) et des
    tâches du jeu, chacun par son empreinte sha256, lue sur le disque."""
    racine = donnees or dossier_donnees()
    fichiers = sorted(p for p in (racine / "donnees").rglob("*") if p.is_file())
    fichiers.append(fichier_taches(jeu, donnees))
    return empreinte_json(
        {p.relative_to(racine).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in fichiers}
    )


@dataclass(frozen=True)
class Phrase:
    phrase: str
    dite: bool


@dataclass(frozen=True)
class Evaluation:
    """La note de τ²-bench pour une exécution, lue dans evaluation.json."""

    recompense: float
    terminaison: str
    base_egale: bool | None
    phrases: tuple[Phrase, ...]
    note: str | None

    @property
    def detail(self) -> str:
        base = {True: "base égale à la cible", False: "base différente de la cible", None: "base non comparée"}
        dites = sum(1 for p in self.phrases if p.dite)
        morceaux = [
            f"τ²-bench : récompense {self.recompense:g}",
            f"fin {self.terminaison}",
            base[self.base_egale],
            f"phrases dites {dites} sur {len(self.phrases)}",
        ]
        if self.note:
            morceaux.append(self.note)
        return " ; ".join(morceaux)


def lire_evaluation(chemin: Path) -> Evaluation:
    donnees: object = json.loads(chemin.read_text(encoding="utf-8"))
    if not isinstance(donnees, dict):
        raise ValueError(f"note de τ²-bench illisible : {chemin}")
    d = cast(dict[str, Any], donnees)
    recompense, terminaison, base, note = d.get("recompense"), d.get("terminaison"), d.get("base_egale"), d.get("note")
    phrases: object = d.get("phrases")
    if (
        not isinstance(recompense, int | float)
        or not 0 <= recompense <= 1
        or not isinstance(terminaison, str)
        or not (base is None or isinstance(base, bool))
        or not (note is None or isinstance(note, str))
        or not isinstance(phrases, list)
    ):
        raise ValueError(f"note de τ²-bench hors de sa forme : {chemin}")
    lues: list[Phrase] = []
    for brute in cast(list[object], phrases):
        if not isinstance(brute, dict):
            raise ValueError(f"phrase illisible dans {chemin}")
        p = cast(dict[str, Any], brute)
        if not isinstance(p.get("phrase"), str) or not isinstance(p.get("dite"), bool):
            raise ValueError(f"phrase illisible dans {chemin}")
        lues.append(Phrase(p["phrase"], p["dite"]))
    return Evaluation(float(recompense), terminaison, base, tuple(lues), note)


def _description(outil: Any) -> DescriptionOutil:
    annotations = outil.annotations
    return DescriptionOutil(
        outil.name,
        outil.description or "",
        outil.input_schema,
        None if annotations is None else annotations.read_only_hint,
    )


class EnvironnementTau2:
    """Le serveur de τ²-bench pour un run : démarré une fois, une exécution ouverte à la fois.

    Utilisable par `with EnvironnementTau2(...) as environnement:` ; demarrer() et arreter() à la
    main sinon. Ce que le serveur écrit sur sa sortie d'erreur va dans un journal à côté du
    dossier de travail, remis à neuf au démarrage."""

    def __init__(
        self,
        jeu: Jeu = "sierra",
        donnees: Path | None = None,
        travail: Path | None = None,
        utilisateur: str = ECRIT_D_AVANCE,
        variables: Mapping[str, str] | None = None,
    ) -> None:
        """variables : ajoutées à l'environnement minimal du serveur (clé du simulateur) ; le
        serveur n'hérite pas de celui d'EASE (mcp.client.stdio)."""
        self.jeu: Jeu = jeu
        self.donnees = donnees or dossier_donnees()
        self.travail = travail or self.donnees.with_name("tau2_travail")
        self.utilisateur = utilisateur
        self._variables = dict(variables) if variables else None
        self.journal_serveur = self.travail.with_name(f"{self.travail.name}_serveur.log")
        self._pile: ExitStack | None = None
        self._portail: BlockingPortal | None = None
        self._client: Client | None = None
        self._outils: dict[str, DescriptionOutil] = {}
        self._execution: str | None = None
        self._enonce: str | None = None

    def __enter__(self) -> EnvironnementTau2:
        self.demarrer()
        return self

    def __exit__(self, *details: object) -> None:
        self.arreter()

    @property
    def demarre(self) -> bool:
        return self._client is not None

    def demarrer(self) -> None:
        """Lance le serveur s'il ne tourne pas ; sans effet sinon."""
        if self._client is not None:
            return
        fichier_taches(self.jeu, self.donnees)
        pile = ExitStack()
        try:
            self.travail.mkdir(parents=True, exist_ok=True)
            journal = pile.enter_context(self.journal_serveur.open("w", encoding="utf-8"))
            portail = pile.enter_context(start_blocking_portal())
            arguments = ["-m", "bancs_publics.tau2_bench", "--jeu", self.jeu, "--donnees", str(self.donnees)]
            arguments += ["--travail", str(self.travail), "--utilisateur", self.utilisateur]
            client = Client(
                stdio_client(
                    StdioServerParameters(command=sys.executable, args=arguments, env=self._variables), errlog=journal
                ),
                mode="legacy",
                cache=None,
                read_timeout_seconds=DELAI_SECONDES,
                client_info=Implementation(name="ease", version="0.1.0"),
            )
            pile.enter_context(portail.wrap_async_context_manager(client))
            liste = portail.call(client.list_tools)
            outils = {o.name: _description(o) for o in liste.tools}
            if not set(outils) >= RESERVES:
                raise RuntimeError(f"le serveur de τ²-bench n'annonce pas {', '.join(sorted(RESERVES))}")
        except BaseException:
            pile.close()
            raise
        self._pile, self._portail, self._client = pile, portail, client
        self._outils = {nom: o for nom, o in outils.items() if nom not in RESERVES}

    def arreter(self) -> None:
        pile, self._pile, self._portail, self._client = self._pile, None, None, None
        self._outils, self._execution, self._enonce = {}, None, None
        if pile is not None:
            pile.close()

    def _reserve(self, nom: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._portail is None or self._client is None:
            raise RuntimeError("serveur de τ²-bench arrêté : demarrer() d'abord")
        resultat = self._portail.call(self._client.call_tool, nom, arguments)
        texte = "\n".join(b.text for b in resultat.content if isinstance(b, TextContent))
        if resultat.is_error:
            raise RuntimeError(f"{nom} refusé par le serveur de τ²-bench : {texte}")
        donnees: object = json.loads(texte)
        if not isinstance(donnees, dict):
            raise RuntimeError(f"{nom} : réponse illisible")
        return cast(dict[str, Any], donnees)

    @property
    def version(self) -> str:
        return VERSION_ETAT

    def empreinte(self) -> str:
        return empreinte_donnees(self.jeu, self.donnees)

    def ouvrir(self, tache: TacheTau2, execution: str, essai: int = 0) -> None:
        """Ouvre une exécution : base neuve, conversation lancée jusqu'au premier tour de l'agent.
        Sa simulation et sa note iront dans <travail>/<execution>/ ; le nom porte celui du run,
        pour que deux runs n'écrivent jamais au même endroit. essai : la répétition, à partir de 0 ;
        seul l'utilisateur rejoué s'en sert, pour redire la conversation publiée de cet essai."""
        self.demarrer()
        reponse = self._reserve(OUVRIR, {"tache": tache.numero, "execution": execution, "essai": essai})
        enonce = reponse.get("enonce")
        if not isinstance(enonce, str) or not enonce:
            raise RuntimeError(f"{OUVRIR} : énoncé absent")
        self._execution, self._enonce = execution, enonce

    def enonce(self) -> str:
        """L'énoncé de l'exécution ouverte : consigne de l'agent de τ²-bench, politique, début de
        la conversation. Il change d'une exécution à l'autre avec un simulateur qui est un modèle."""
        if self._enonce is None:
            raise RuntimeError("aucune exécution ouverte")
        return self._enonce

    def outils(self) -> list[DescriptionOutil]:
        return list(self._outils.values())

    def appeler(self, nom: str, arguments: Mapping[str, Any], lecture_seule: bool = False) -> str:
        """Un geste de l'agent ; un outil réservé ou inconnu lui est refusé comme une ErreurOutil.
        Une panne du serveur lève RuntimeError : l'exécution finit en erreur technique."""
        del lecture_seule  # aucun outil d'airline n'a d'effet de bord en lisant
        if self._portail is None or self._client is None or self._execution is None:
            raise RuntimeError("aucune exécution ouverte")
        if nom not in self._outils:
            raise ErreurOutil(f"Unknown tool: {nom}")
        resultat = self._portail.call(self._client.call_tool, nom, dict(arguments))
        texte = "\n".join(b.text for b in resultat.content if isinstance(b, TextContent))
        structure: dict[str, Any] = resultat.structured_content or {}
        if resultat.is_error and structure.get("panne") is True:
            raise RuntimeError(f"panne du serveur de τ²-bench : {texte}")
        if resultat.is_error:
            raise ErreurOutil(texte)
        return texte

    def fermer(self) -> Evaluation:
        """Clôt l'exécution ouverte et lit la note de τ²-bench sur le disque."""
        if self._execution is None:
            raise RuntimeError("aucune exécution ouverte")
        execution, self._execution, self._enonce = self._execution, None, None
        self._reserve(CLOTURER, {})
        return lire_evaluation(self.travail / execution / "evaluation.json")


def controles(evaluation: Evaluation) -> list[ResultatControle]:
    """Un seul contrôle, celui de τ²-bench : sa récompense, 0 ou 1, de poids 1."""
    return [
        ResultatControle(numero=1, famille="resultat", poids=1.0, score=evaluation.recompense, detail=evaluation.detail)
    ]


def sans_note(raison: str) -> list[ResultatControle]:
    """Le contrôle d'une conversation que τ²-bench n'a pas notée : score nul, la raison dite.
    L'exécution est alors une erreur technique, hors des chiffres."""
    return [ResultatControle(numero=1, famille="resultat", poids=1.0, score=0.0, detail=raison)]


def _jetons_totaux(consommation: Consommation) -> Jetons:
    """Comme executeur._jetons_totaux : un rôle sans compte rend tout le total inconnu."""

    def somme(valeurs: list[int | Literal["?"]]) -> int | Literal["?"]:
        entiers = [v for v in valeurs if isinstance(v, int)]
        return "?" if len(entiers) != len(valeurs) else sum(entiers)

    jetons = list(consommation.par_role.values())
    return Jetons(
        entree=somme([j.entree for j in jetons]),
        entree_en_cache=somme([j.entree_en_cache for j in jetons]),
        sortie=somme([j.sortie for j in jetons]),
    )


def _ecrire_contrat[M: BaseModel](chemin: Path, contrat: str, objet: M, regles: Callable[[M], list[str]]) -> None:
    """Comme executeur._ecrire_contrat : rien n'est écrit hors de son contrat."""
    donnees = objet.model_dump(mode="json")
    erreurs = ecarts_schema(contrat, donnees) + regles(objet)
    if erreurs:
        raise ValueError(f"EASE allait écrire {chemin.name} hors de son contrat : {erreurs}")
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


type Compte = int | Literal["?"]


def _ajouter(total: Compte, valeur: object) -> Compte:
    if total == "?" or not isinstance(valeur, int) or isinstance(valeur, bool) or valeur < 0:
        return "?"
    return total + valeur


def consommation_simulateur(simulations: Iterable[Path]) -> tuple[JetonsSimulateur, float | Literal["?"]]:
    """Jetons du simulateur, dont ceux de réflexion, et coût annoncé par son fournisseur, sommés sur
    des conversations écrites par le serveur (simulation.json) : l'usage brut de chaque réponse de
    son API, que τ²-bench garde dans raw_data. Un compte qui manque à une réponse rend le total
    « ? » ; une conversation absente aussi (exécution en panne avant sa clôture)."""
    entree: Compte = 0
    cache: Compte = 0
    sortie: Compte = 0
    reflexion: Compte = 0
    annonce: float | Literal["?"] = 0.0
    for chemin in simulations:
        if not chemin.is_file():
            return JetonsSimulateur(entree="?", entree_en_cache="?", sortie="?", dont_reflexion="?"), "?"
        donnees: object = json.loads(chemin.read_text(encoding="utf-8"))
        messages: object = cast(dict[str, Any], donnees).get("messages") if isinstance(donnees, dict) else None
        for message in cast(list[object], messages) if isinstance(messages, list) else []:
            if not isinstance(message, dict) or cast(dict[str, Any], message).get("role") != "user":
                continue
            brut: object = cast(dict[str, Any], message).get("raw_data")
            usage: object = cast(dict[str, Any], brut).get("usage") if isinstance(brut, dict) else None
            u = cast(dict[str, Any], usage) if isinstance(usage, dict) else {}
            details: object = u.get("prompt_tokens_details")
            en_cache: object = cast(dict[str, Any], details).get("cached_tokens") if isinstance(details, dict) else None
            ecrits: object = u.get("completion_tokens_details")
            pensee: object = cast(dict[str, Any], ecrits).get("reasoning_tokens") if isinstance(ecrits, dict) else None
            entree = _ajouter(entree, u.get("prompt_tokens"))
            cache = _ajouter(cache, en_cache)
            sortie = _ajouter(sortie, u.get("completion_tokens"))
            reflexion = _ajouter(reflexion, pensee)
            cout: object = u.get("cost")
            connu = isinstance(cout, int | float) and not isinstance(cout, bool) and cout >= 0
            annonce = annonce + float(cast(float, cout)) if annonce != "?" and connu else "?"
    return JetonsSimulateur(entree=entree, entree_en_cache=cache, sortie=sortie, dont_reflexion=reflexion), annonce


def cout_simulateur(jetons: JetonsSimulateur, tarif: Tarif) -> float | Literal["?"]:
    """Coût du simulateur au tarif de la fiche, comme executeur.cout_dollars pour un rôle."""
    entree, cache, sortie = jetons.entree, jetons.entree_en_cache, jetons.sortie
    prix_cache = tarif.entree_en_cache_dollars_par_million
    if entree == "?" or cache == "?" or sortie == "?" or (cache > 0 and prix_cache == "?"):
        return "?"
    prix_cache_connu = 0.0 if prix_cache == "?" else prix_cache
    return (
        (entree - cache) * tarif.entree_dollars_par_million
        + cache * prix_cache_connu
        + sortie * tarif.sortie_dollars_par_million
    ) / 1e6


def banc_public(environnement: EnvironnementTau2, simulateur: Simulateur, executions: list[str] | None) -> BancPublic:
    """Le champ banc_public de la fiche ; executions : celles du run, à sa fin, dont la consommation
    du simulateur est lue sur le disque ; None tant que le run tourne."""
    jetons: JetonsSimulateur | None = None
    cout: float | Literal["?"] | None = None
    annonce: float | Literal["?"] | None = None
    if not simulateur.sans_modele and executions is not None:
        jetons, annonce = consommation_simulateur(environnement.travail / e / "simulation.json" for e in executions)
        cout = "?" if simulateur.tarif is None else cout_simulateur(jetons, simulateur.tarif)
    return BancPublic(
        nom=BANC,
        version=importlib.metadata.version(PAQUET),
        domaine=DOMAINE,
        jeu=environnement.jeu,
        simulateur=SimulateurDuRun(
            modele=simulateur.modele,
            fournisseur=simulateur.fournisseur,
            parametres=dict(simulateur.parametres),
            tarif=simulateur.tarif,
            jetons=jetons,
            cout_dollars=cout,
            cout_annonce_dollars=annonce,
        ),
    )


def nom_execution(run: str, tache: TacheTau2, repetition: int) -> str:
    """Le dossier d'une exécution dans le dossier de travail du serveur : le run, la tâche, l'essai."""
    return f"{run}_{tache.identifiant}_r{repetition}"


def executer_une_fois(
    candidat: Candidat,
    environnement: EnvironnementTau2,
    tache: TacheTau2,
    run: str,
    repetition: int,
    dossier_run: Path,
) -> ResultatExecution:
    """Une exécution, comme executeur.executer_une_fois : ouverture, passage du candidat, note.

    La conversation est close avant la lecture de la note : plus rien ne peut la changer. Une
    clôture sans note, quand le client simulé n'a pas répondu (un appel refusé chez son fournisseur,
    JOURNAL, entrées 232 et 325), finit l'exécution en erreur technique, et le run continue."""
    nom = f"{tache.identifiant}_r{repetition}"
    journal = dossier_run / "journaux" / f"{nom}.jsonl"
    journal.touch()
    environnement.ouvrir(tache, nom_execution(run, tache, repetition), repetition - 1)
    outils = Outils(environnement, tache.budget.etapes_max, journal)
    debut, chrono = maintenant(), time.monotonic()
    consommation = Consommation()
    arret: Arret = "termine"
    detail: str | None = None
    evaluation: Evaluation | None = None
    panne_cloture: str | None = None
    try:
        try:
            consommation = candidat.executer(environnement.enonce(), outils)
        except ArretDuRun:
            raise
        except BudgetEtapesDepasse as erreur:
            arret, detail = "budget_etapes", str(erreur)
        except ErreurOutil as erreur:
            detail = f"l'agent s'est arrêté sur une erreur d'outil : {erreur}"
        except Exception as erreur:  # une panne, pas un échec de l'agent
            arret, detail = "erreur_technique", f"{type(erreur).__name__} : {erreur}"
        if arret == "termine" and outils.budget_atteint:
            arret, detail = "budget_etapes", f"budget de {tache.budget.etapes_max} étapes atteint"
        duree, fin = time.monotonic() - chrono, maintenant()
    finally:
        try:
            evaluation = environnement.fermer()
        except Exception as erreur:  # τ²-bench n'a pas noté la conversation : une panne, pas l'agent
            panne_cloture = f"clôture sans note de τ²-bench, {type(erreur).__name__} : {erreur}"

    if evaluation is None:
        arret = "erreur_technique"
        detail = panne_cloture if detail is None else f"{detail} ; {panne_cloture}"
    cout = cout_dollars(consommation, candidat.configuration)
    if arret == "termine" and cout != "?" and cout > tache.budget.cout_max_dollars:
        arret, detail = "budget_cout", f"{cout:.6f} $ pour un budget de {tache.budget.cout_max_dollars} $"
    resultats = controles(evaluation) if evaluation is not None else sans_note(detail or "?")
    return ResultatExecution(
        run=run,
        tache=ReferenceTache(identifiant=tache.identifiant, version=tache.version),
        repetition=repetition,
        debut_utc=debut,
        fin_utc=fin,
        arret=arret,
        detail_arret=detail,
        controles=resultats,
        score=math.fsum(c.poids * c.score for c in resultats),
        reussie=arret == "termine" and all(c.score == 1 for c in resultats),
        etapes=outils.etapes,
        jetons=_jetons_totaux(consommation),
        cout_dollars=cout,
        energie_wh=consommation.energie_wh,
        duree_secondes=duree,
        journal=f"journaux/{nom}.jsonl",
    )


def lancer_run(
    *,
    candidat: Candidat,
    environnement: EnvironnementTau2,
    taches: list[TacheTau2],
    repetitions: int,
    dossier_runs: Path | None = None,
    simulateur: Simulateur | None = None,
) -> Path:
    """Lance le candidat sur chaque tâche, repetitions fois, comme executeur.lancer_run, et rend le
    dossier du run. Démarre le serveur s'il ne tourne pas, et l'arrête alors à la fin.

    simulateur : sa description pour la fiche, qui doit nommer l'utilisateur du serveur ; par
    défaut, l'utilisateur sans modèle de l'environnement.

    Les runs vont dans 99_local/runs_tau2/ par défaut, à part de ceux de la PME : le rapport et le
    rejeu du gardien lisent 99_local/runs/ et prendraient la version d'état v1 de la fiche pour
    celle de Calorelle."""
    simulateur = simulateur or Simulateur(environnement.utilisateur)
    if simulateur.modele != environnement.utilisateur:
        raise ValueError(f"simulateur {simulateur.modele} décrit, {environnement.utilisateur} lancé par le serveur")
    if simulateur.sans_modele != sans_modele(environnement.utilisateur):
        raise ValueError("simulateur mal décrit")
    racine = racine_depot()
    debut, identifiant, dossier = nouveau_dossier_de_run(
        dossier_runs or racine / "99_local" / "runs_tau2", candidat.fiche.identifiant
    )
    (dossier / "resultats").mkdir()
    (dossier / "journaux").mkdir()
    fiche = FicheDeRun(
        identifiant=identifiant,
        debut_utc=debut,
        fin_utc=None,
        statut="en_cours",
        raison_interruption=None,
        code=version_code(racine),
        candidat=ReferenceCandidat(identifiant=candidat.fiche.identifiant, version=candidat.fiche.version),
        configuration=candidat.configuration,
        empreinte_prompts=candidat.empreinte_prompts,
        jeu_taches=JeuDeTaches(
            nom=nom_jeu(environnement.jeu),
            taches=[
                TacheDuJeu(identifiant=t.identifiant, version=t.version, empreinte_complement=None) for t in taches
            ],
            empreinte=empreinte_json(
                {
                    "taches": [t.identifiant for t in taches],
                    "fichier": "sha256:"
                    + hashlib.sha256(fichier_taches(environnement.jeu, environnement.donnees).read_bytes()).hexdigest(),
                }
            ),
        ),
        etat_pme=EtatPME(version=environnement.version, empreinte=environnement.empreinte()),
        regles_gardien=None,
        repetitions=repetitions,
        machine=candidat.machine,
        juge=None,
        banc_public=banc_public(environnement, simulateur, None),
    )
    chemin_fiche = dossier / "fiche_de_run.json"
    _ecrire_contrat(chemin_fiche, "fiche_de_run", fiche, regles_fiche_de_run)
    demarre_ici = not environnement.demarre
    ouvertes: list[str] = []
    """Les exécutions tentées : le simulateur a pu parler dès l'ouverture, même si la suite échoue."""
    try:
        environnement.demarrer()
        for tache in taches:
            for repetition in range(1, repetitions + 1):
                ouvertes.append(nom_execution(identifiant, tache, repetition))
                resultat = executer_une_fois(candidat, environnement, tache, identifiant, repetition, dossier)
                chemin = dossier / "resultats" / f"{tache.identifiant}_r{repetition}.json"
                _ecrire_contrat(chemin, "resultat_execution", resultat, regles_resultat)
    except BaseException as interruption:
        raison = f"{type(interruption).__name__} : {interruption}".rstrip(" :")
        fiche = fiche.model_copy(
            update={
                "statut": "interrompu",
                "fin_utc": maintenant(),
                "raison_interruption": raison,
                "banc_public": banc_public(environnement, simulateur, ouvertes),
            }
        )
        _ecrire_contrat(chemin_fiche, "fiche_de_run", fiche, regles_fiche_de_run)
        raise
    finally:
        if demarre_ici:
            environnement.arreter()
    fiche = fiche.model_copy(
        update={
            "statut": "termine",
            "fin_utc": maintenant(),
            "configuration": candidat.configuration,
            "banc_public": banc_public(environnement, simulateur, ouvertes),
        }
    )
    _ecrire_contrat(chemin_fiche, "fiche_de_run", fiche, regles_fiche_de_run)
    return dossier
