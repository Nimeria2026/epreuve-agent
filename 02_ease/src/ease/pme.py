"""La PME fictive vue par EASE : état initial, remise à zéro, empreinte, et l'environnement où
agit le candidat.

L'état de travail d'une exécution est une copie de 05_pme/societes/<société>/<version>/ : les
serveurs MCP y lisent et y écrivent, puis EASE le capture pour ses contrôles sans passer par eux
(règle 3). EASE parle aux serveurs en MCP, par stdio, comme n'importe quel client : il ne les
importe jamais (règle 6).

Avec le gardien (06_gardien, étape 4), EASE ne lance qu'un processus : le gardien, qui lance
lui-même les services de la tâche et juge chaque appel avec ses règles avant de le transmettre.
EASE ne lit des règles que leur version et leur empreinte, pour la fiche de run.

Les services sont des serveurs TypeScript lancés par Node, sauf EKE (étape 6), l'outil
documentaire écrit en Python : il se lance par le Python de l'environnement du dépôt, celui
d'EASE, `python -m eke --etat … --pour …`, seulement pour les tâches qui le déclarent (décision
d'Alexandre du 2026-10-10, journal d'EKE, vingt-quatrième entrée). Avec le gardien, EASE lui passe
ce Python (`--python`), et le gardien lance EKE derrière lui comme les autres services.

Une tâche dit de quel état initial elle part (v1, v2) ; un run ne mélange jamais deux états
(JOURNAL, quatre-vingt-unième entrée). Depuis l'entrée 90, tout le banc part de v2, l'état par
défaut ; v1 reste lisible pour relire les runs qui en sont partis.
"""

from __future__ import annotations

import functools
import hashlib
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TextIO, cast

import yaml
from anyio.from_thread import BlockingPortal, start_blocking_portal
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation, RequestParamsMeta, TextContent

from ease.chargement import SOCIETE, dossier_complements_caches, dossier_societe, racine_depot
from ease.contrats.fiche_de_run import ReglesGardien
from ease.contrats.tache import Tache
from ease.empreintes import empreinte_texte
from ease.etat_pme import Instantane, capturer
from ease.executeur import MARQUE_LECTURE_SEULE, DescriptionOutil, ErreurOutil
from ease.taches import SERVICES_PYTHON, societe_de

PARTIES = ("entreprise", "dossiers", "messagerie", "facturation", "planning", "ventes")
"""Les parties d'un état copiées à la remise à zéro ; planning/ n'existe qu'à partir de v2 de
Calorelle, ventes/ que chez Négovelle, la PME de négoce (cadrage du 2026-10-17, section 5)."""


def dossier_version(version: str, societe: str = SOCIETE) -> Path:
    """Dossier de l'état initial d'une version d'une société, par exemple v1 de Calorelle."""
    dossier = dossier_societe(societe) / version
    if not (dossier / "entreprise").is_dir():
        raise FileNotFoundError(f"état initial introuvable : {dossier}")
    return dossier


def etat_des_taches(taches: Sequence[Tache]) -> str:
    """L'état initial commun aux tâches d'un run ; des tâches parties de deux états sont refusées
    ensemble."""
    versions = sorted({t.etat_initial for t in taches})
    if not versions:
        raise ValueError("aucune tâche")
    if len(versions) > 1:
        raise ValueError(
            f"les tâches partent de {len(versions)} états ({', '.join(versions)}) ; un run n'en mélange jamais deux"
        )
    return versions[0]


def dossier_complement(nom: str, societe: str = SOCIETE) -> Path:
    """Dossier d'un complément d'état propre à une tâche (étape 4, JOURNAL, soixantième entrée) :
    celui des tâches publiques, dans le dossier de la société, sinon celui d'une tâche cachée,
    hors git (dossier_complements_caches, ADR 0006). La racine se lit ici, par racine_depot de ce
    module, que test_taches_cachees remplace."""
    racine = racine_depot()
    dossier = dossier_societe(societe, racine) / "complements" / nom
    if not dossier.is_dir():
        dossier = dossier_complements_caches(societe, racine) / nom
    if not dossier.is_dir():
        raise FileNotFoundError(f"complément d'état introuvable : {nom}")
    inconnus = sorted(p.name for p in dossier.iterdir() if p.name not in {*PARTIES, "README.md"})
    if inconnus:
        raise ValueError(f"complément {nom} : entrées inconnues {', '.join(inconnus)} (permis : {', '.join(PARTIES)})")
    return dossier


def remettre_a_zero(
    destination: Path, version: str = "v3", complement: str | None = None, societe: str = SOCIETE
) -> None:
    """Remplace l'état de travail par une copie fraîche de l'état initial, puis pose le complément
    de la tâche s'il y en a un : ses fichiers s'ajoutent, ou remplacent ceux de même chemin."""
    source = dossier_version(version, societe)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for partie in PARTIES:
        if (source / partie).is_dir():
            shutil.copytree(source / partie, destination / partie)
    if complement is not None:
        ajout = dossier_complement(complement, societe)
        for partie in PARTIES:
            if (ajout / partie).is_dir():
                shutil.copytree(ajout / partie, destination / partie, dirs_exist_ok=True)


def _empreinte_dossier(source: Path) -> str:
    lignes = [
        f"{chemin.relative_to(source).as_posix()} {hashlib.sha256(chemin.read_bytes()).hexdigest()}"
        for partie in PARTIES
        if (source / partie).is_dir()
        for chemin in sorted((source / partie).rglob("*"))
        if chemin.is_file()
    ]
    return empreinte_texte("\n".join(lignes))


def empreinte_version(version: str = "v3", societe: str = SOCIETE) -> str:
    """Empreinte de l'état initial : chaque fichier, son chemin et son contenu."""
    return _empreinte_dossier(dossier_version(version, societe))


def empreinte_complement(nom: str, societe: str = SOCIETE) -> str:
    """Empreinte d'un complément d'état, calculée comme celle d'une version."""
    return _empreinte_dossier(dossier_complement(nom, societe))


DELAI_SECONDES = 30.0
"""Attente maximale d'une réponse de serveur ; au-delà, l'exécution finit en erreur technique."""


def serveur_du_service(service: str) -> Path:
    """Point d'entrée du serveur MCP d'un service TypeScript de la PME, par exemple messagerie."""
    principal = racine_depot() / "05_pme" / service / "src" / "principal.ts"
    if not principal.is_file():
        raise ValueError(f"service inconnu de la PME : {service}")
    return principal


def commande_du_service(service: str) -> list[str]:
    """La commande qui lance le serveur MCP d'un service, avant --etat et --pour."""
    if service in SERVICES_PYTHON:
        return [sys.executable, "-m", SERVICES_PYTHON[service]]
    return ["node", str(serveur_du_service(service))]


REGLES_COURANTES = {"domivelle": "v2.yaml"}
"""Version courante des règles du gardien d'une autre société que Calorelle, quand ce n'est plus la
première : Domivelle en version 2 depuis la tâche dvh08 (JOURNAL, entrée 160)."""

REGLES_CALORELLE = "v2.yaml"
"""Version courante des règles du gardien de Calorelle : la version 2, écrite depuis le manuel pour
les pièges de la tranche dure (JOURNAL, entrées 175 et 176). La version 1 reste pour rejouer les runs
passés."""


def regles_gardien(societe: str = SOCIETE) -> Path:
    """Règles courantes du gardien pour une société, celles de make mesure GARDIEN=1 : celles de
    Calorelle à la racine de 06_gardien/regles/, celles d'une autre société dans un sous-dossier à
    son nom (ADR 0006). Seul endroit où s'écrit ce chemin."""
    dossier = racine_depot() / "06_gardien" / "regles"
    if societe == SOCIETE:
        return dossier / REGLES_CALORELLE
    return dossier / societe / REGLES_COURANTES.get(societe, "v1.yaml")


REGLES_GARDIEN = regles_gardien()
"""Règles courantes du gardien de Calorelle."""

PREFIXE_REFUS_GARDIEN = "Bloqué par le gardien"
"""Début du texte d'un refus du gardien (06_gardien/src/passerelle.ts), qui le distingue d'un refus de la PME."""

Validation = Literal["refuser", "accepter"]
"""Réponse simulée de la personne dont le gardien attend l'accord, pendant les essais."""


def principal_du_gardien() -> Path:
    """Point d'entrée du gardien, un programme TypeScript lancé par Node."""
    return racine_depot() / "06_gardien" / "src" / "principal.ts"


def lire_regles_gardien(chemin: Path) -> ReglesGardien:
    """Version et empreinte d'un fichier de règles du gardien. Le gardien les applique ; EASE les note."""
    texte = chemin.read_text(encoding="utf-8")
    donnees: object = yaml.safe_load(texte)
    version = cast(dict[str, object], donnees).get("version") if isinstance(donnees, dict) else None
    if not isinstance(version, str) or not version:
        raise ValueError(f"{chemin} : version des règles absente")
    return ReglesGardien(version=version, empreinte=empreinte_texte(texte))


def blocages_du_gardien(journal: Path) -> list[str]:
    """Les refus du gardien dans le journal d'une exécution, dans l'ordre des étapes."""
    if not journal.is_file():
        return []
    erreurs = [json.loads(ligne).get("erreur") for ligne in journal.read_text(encoding="utf-8").splitlines() if ligne]
    return [e for e in erreurs if isinstance(e, str) and e.startswith(PREFIXE_REFUS_GARDIEN)]


async def _lister_outils(client: Client) -> list[DescriptionOutil]:
    outils: list[DescriptionOutil] = []
    curseur: str | None = None
    while True:
        page = await client.list_tools(cursor=curseur)
        outils += [
            DescriptionOutil(
                o.name,
                o.description or "",
                o.input_schema,
                None if o.annotations is None else o.annotations.read_only_hint,
            )
            for o in page.tools
        ]
        curseur = page.next_cursor
        if curseur is None:
            return outils


JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
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


def lire_horloge(etat: Path) -> datetime:
    """L'heure simulée d'un état (entreprise/horloge.yaml), celle que lisent les serveurs."""
    donnees: object = yaml.safe_load((etat / "entreprise" / "horloge.yaml").read_text(encoding="utf-8"))
    debut = cast("dict[str, object]", donnees).get("debut") if isinstance(donnees, dict) else None
    if isinstance(debut, datetime):
        instant = debut
    elif isinstance(debut, str):
        instant = datetime.fromisoformat(debut)
    else:
        raise ValueError(f"horloge simulée illisible dans {etat}")
    if instant.tzinfo is None:
        raise ValueError(f"horloge simulée sans fuseau dans {etat}")
    return instant


def phrase_horloge(instant: datetime) -> str:
    """« Nous sommes le lundi 2 novembre 2026, il est 9 h. », à l'heure locale de l'horloge."""
    jour = "1er" if instant.day == 1 else str(instant.day)
    heure = f"{instant.hour} h" if instant.minute == 0 else f"{instant.hour} h {instant.minute:02d}"
    return f"Nous sommes le {JOURS[instant.weekday()]} {jour} {MOIS[instant.month - 1]} {instant.year}, il est {heure}."


class EnvironnementPME:
    """La PME pour une tâche : l'état remis à zéro, et ses services lancés pour la personne servie.

    Chaque service de la tâche est un serveur MCP en TypeScript, lancé par Node en stdio le temps
    d'une exécution, avec les droits de la personne de agent_pour. L'agent voit les outils sous
    le nom que leur donnent les serveurs ; deux services qui annonceraient le même nom sont
    refusés. Ce que les serveurs écrivent sur leur sortie d'erreur va dans un journal placé à
    côté de l'état de travail, remis à neuf à la première ouverture.
    """

    def __init__(
        self,
        version: str = "v3",
        dossier: Path | None = None,
        gardien: Path | None = None,
        validation: Validation = "refuser",
        societe: str = SOCIETE,
    ) -> None:
        """gardien : fichier de règles ; le gardien se place alors entre l'agent et les services.
        societe : la société fictive de l'état, Calorelle par défaut (ADR 0006)."""
        self._version = version
        self._societe = societe
        self._dossier = dossier or racine_depot() / "99_local" / "pme"
        self.journal_serveurs = self._dossier.with_name(f"{self._dossier.name}_serveurs.log")
        self.journal_gardien = self._dossier.with_name(f"{self._dossier.name}_gardien.jsonl")
        """Une ligne par appel jugé par le gardien, toutes exécutions confondues, remis à neuf à la
        première ouverture."""
        self._gardien = gardien
        self._validation: Validation = validation
        self._regles = None if gardien is None else lire_regles_gardien(gardien)
        self._complements: dict[str, str] = {}
        """Empreinte de chaque complément à sa première lecture : un complément modifié pendant
        le run l'arrête, comme des règles du gardien modifiées."""
        self._deja_ouvert = False
        self._pile: ExitStack | None = None
        self._portail: BlockingPortal | None = None
        self._outils: dict[str, tuple[Client, DescriptionOutil]] = {}

    @property
    def version(self) -> str:
        return self._version

    @property
    def societe(self) -> str:
        return self._societe

    def empreinte(self) -> str:
        return empreinte_version(self._version, self._societe)

    @property
    def regles_gardien(self) -> ReglesGardien | None:
        return self._regles

    def empreinte_complement(self, tache: Tache) -> str | None:
        if tache.complement is None:
            return None
        return self._complements.setdefault(tache.complement, empreinte_complement(tache.complement, self._societe))

    def ouvrir(self, tache: Tache) -> None:
        self.fermer()
        if societe_de(tache) != self._societe:
            raise ValueError(
                f"{tache.identifiant} est une tâche de {societe_de(tache)}, la PME est {self._societe} : "
                "un run ne mélange jamais deux sociétés"
            )
        if tache.etat_initial != self._version:
            raise ValueError(
                f"{tache.identifiant} part de l'état {tache.etat_initial}, la PME est en {self._version} : "
                "un run ne mélange jamais deux états"
            )
        if tache.complement is not None and self.empreinte_complement(tache) != empreinte_complement(
            tache.complement, self._societe
        ):
            raise ValueError(f"complément {tache.complement} modifié pendant le run")
        remettre_a_zero(self._dossier, self._version, tache.complement, self._societe)
        pile = ExitStack()
        try:
            self._dossier.parent.mkdir(parents=True, exist_ok=True)
            premiere = not self._deja_ouvert
            journal = pile.enter_context(self.journal_serveurs.open("w" if premiere else "a", encoding="utf-8"))
            self._deja_ouvert = True
            journal.write(f"--- {tache.identifiant}, pour {tache.agent_pour}\n")
            journal.flush()
            portail = pile.enter_context(start_blocking_portal())
            outils: dict[str, tuple[Client, DescriptionOutil]] = {}
            for client in self._clients(tache, journal, premiere):
                pile.enter_context(portail.wrap_async_context_manager(client))
                for outil in portail.call(_lister_outils, client):
                    if outil.nom in outils:
                        raise ValueError(f"deux services de la PME annoncent l'outil {outil.nom}")
                    outils[outil.nom] = (client, outil)
        except BaseException:
            pile.close()
            raise
        self._pile, self._portail, self._outils = pile, portail, outils

    def _clients(self, tache: Tache, journal: TextIO, premiere: bool) -> list[Client]:
        """Un client par service de la tâche, ou un seul vers le gardien qui les lance tous."""
        etat_et_personne = ["--etat", str(self._dossier), "--pour", tache.agent_pour]
        if self._gardien is None:
            return [self._client(commande_du_service(s), etat_et_personne, journal) for s in tache.services]
        if lire_regles_gardien(self._gardien) != self._regles:
            raise ValueError(f"règles du gardien modifiées pendant le run : {self._gardien}")
        for service in tache.services:
            commande_du_service(service)  # un service inconnu est refusé ici, avant de lancer le gardien
        if premiere:
            self.journal_gardien.write_text("", encoding="utf-8")
        arguments = [
            *etat_et_personne,
            *("--services", ",".join(tache.services), "--regles", str(self._gardien)),
            *("--journal", str(self.journal_gardien), "--tache", tache.identifiant),
            *("--validation", tache.validation_simulee or self._validation),
        ]
        if any(s in SERVICES_PYTHON for s in tache.services):
            arguments += ["--python", sys.executable]
        return [self._client(["node", str(principal_du_gardien())], arguments, journal)]

    def _client(self, commande: list[str], arguments: list[str], journal: TextIO) -> Client:
        parametres = StdioServerParameters(command=commande[0], args=[*commande[1:], *arguments])
        return Client(
            stdio_client(parametres, errlog=journal),
            mode="legacy",  # poignée de main MCP classique, celle que parlent les serveurs de la PME
            cache=None,  # chaque appel atteint le serveur
            read_timeout_seconds=DELAI_SECONDES,
            client_info=Implementation(name="ease", version="0.1.0"),
        )

    def fermer(self) -> None:
        pile, self._pile, self._portail, self._outils = self._pile, None, None, {}
        if pile is not None:
            pile.close()

    def outils(self) -> list[DescriptionOutil]:
        return [description for _, description in self._outils.values()]

    def preambule(self) -> str:
        """La date et l'heure de l'horloge de l'état ouvert, complément compris (t16 et t26 ont
        la leur), celles dont les serveurs datent les courriels envoyés."""
        return phrase_horloge(lire_horloge(self._dossier))

    def appeler(self, nom: str, arguments: Mapping[str, Any], lecture_seule: bool = False) -> str:
        """Appelle un outil ; un refus du serveur revient à l'agent comme une ErreurOutil. Un appel de
        l'accès en lecture seule porte la marque MARQUE_LECTURE_SEULE dans son _meta MCP."""
        if self._portail is None:
            raise RuntimeError("PME fermée : ouvrir(tache) d'abord")
        if nom not in self._outils:
            raise ErreurOutil(f"outil inconnu : {nom}")
        client, _ = self._outils[nom]
        meta = cast(RequestParamsMeta, {MARQUE_LECTURE_SEULE: True}) if lecture_seule else None
        resultat = self._portail.call(functools.partial(client.call_tool, meta=meta), nom, dict(arguments))
        texte = "\n".join(bloc.text for bloc in resultat.content if isinstance(bloc, TextContent))
        if resultat.is_error:
            raise ErreurOutil(texte)
        return texte

    def etat(self) -> Instantane:
        return capturer(self._dossier)
