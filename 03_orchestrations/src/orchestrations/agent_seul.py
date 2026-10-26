"""Agent seul : un modèle, les outils de la PME, et une boucle entre les deux.

EASE le lance dans son propre processus (règle 6) :

    python -m orchestrations.agent_seul --configuration <fichier.yaml> \\
        --mcp <adresse du relais> --enonce <fichier> --sortie <fichier>

L'agent ne reçoit que l'énoncé et les outils que le relais lui présente (règle 5), plus une
consigne courte et fixe (consignes/agent_seul.md), dont EASE note l'empreinte. À chaque tour, le
modèle répond : s'il appelle des outils, l'agent les appelle par le relais et lui rend les
résultats ; sinon, son message clôt l'exécution. Après chaque appel de modèle, l'agent réécrit
son fichier de sortie (contrat sortie_candidat), pour qu'un arrêt brutal laisse la consommation
déjà faite, et raconte le tour sur sa sortie standard : raisonnement, réponse et appels du
modèle, raison de fin et jetons écrits quand l'API les donne, qu'EASE range dans
journaux/<tâche>_r<k>_candidat.log. Un tour sans réponse ni appel y est signalé avec les champs
du message et leur longueur, sans leur contenu (JOURNAL, cent-vingtième entrée).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import anyio
from mcp import Client
from mcp.types import TextContent

from orchestrations.modele import (
    TOURS_VIDES,
    ConfigurationModele,
    ContexteDepasse,
    DelaiAppelDepasse,
    ErreurModele,
    Modele,
    Nombre,
    cle_api,
    lire_configuration,
    lire_usage,
    raisonnement,
)

CONSIGNE = Path(__file__).parent / "consignes" / "agent_seul.md"

type Fin = Literal["en_cours", "termine", "tours_max", "erreur", "contexte_depasse", "delai_depasse"]


class Outils(Protocol):
    """Les outils vus par l'agent : leur liste au format OpenAI, et l'appel de l'un d'eux."""

    async def lister(self) -> list[dict[str, Any]]: ...

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """(texte du résultat, vrai si l'outil a refusé)."""
        ...


class Repondeur(Protocol):
    async def repondre(self, messages: list[dict[str, Any]], outils: list[dict[str, Any]]) -> dict[str, Any]: ...


def _additionner(a: Nombre, b: Nombre) -> Nombre:
    return "?" if a == "?" or b == "?" else a + b


@dataclass
class Bilan:
    """Ce que l'agent a consommé, et comment il s'est arrêté."""

    role: str
    fin: Fin = "en_cours"
    detail: str | None = None
    appels_modele: int = 0
    entree: Nombre = 0
    entree_en_cache: Nombre = 0
    sortie: Nombre = 0
    modeles_renvoyes: set[str] = field(default_factory=lambda: set[str]())

    def compter(self, reponse: dict[str, Any]) -> None:
        """Un tour du modèle, et les tours vides rejoués avant lui, facturés eux aussi."""
        self.appels_modele += 1
        self.ajouter_usage(reponse.get("usage"))
        for usage in cast(list[object], reponse.get(TOURS_VIDES) or []):
            self.ajouter_usage(usage)
        modele = reponse.get("model")
        if isinstance(modele, str) and modele:
            self.modeles_renvoyes.add(modele)

    def ajouter_usage(self, usage: object) -> None:
        entree, cache, sortie = lire_usage(usage)
        self.entree = _additionner(self.entree, entree)
        self.entree_en_cache = _additionner(self.entree_en_cache, cache)
        self.sortie = _additionner(self.sortie, sortie)

    def en_json(self) -> dict[str, Any]:
        """La sortie de l'exécution, au contrat sortie_candidat."""
        consommation = (
            {self.role: {"entree": self.entree, "entree_en_cache": self.entree_en_cache, "sortie": self.sortie}}
            if self.appels_modele
            else {}
        )
        renvoyes = {self.role: ", ".join(sorted(self.modeles_renvoyes))} if self.modeles_renvoyes else {}
        return {
            "fin": self.fin,
            "detail": self.detail,
            "appels_modele": self.appels_modele,
            "consommation": consommation,
            "modeles_renvoyes": renvoyes,
        }


async def boucle(
    enonce: str,
    consigne: str,
    outils: Outils,
    modele: Repondeur,
    configuration: ConfigurationModele,
    noter: Callable[[Bilan], None],
    raconter: Callable[[str], None] = lambda texte: print(texte, flush=True),
) -> Bilan:
    """Fait travailler le modèle avec les outils jusqu'à sa réponse finale, ou jusqu'à la limite de tours."""
    bilan = Bilan(role=configuration.role)
    catalogue = await outils.lister()
    messages: list[dict[str, Any]] = [{"role": "system", "content": consigne}, {"role": "user", "content": enonce}]
    for _ in range(configuration.tours_max):
        try:
            reponse = await modele.repondre(messages, catalogue)
        except ErreurModele as panne:
            for usage in panne.usages_perdus:
                bilan.ajouter_usage(usage)
            # Un contexte ou un délai dépassé est un échec de l'agent, pas une panne (choix T3 du
            # 2026-10-14 ; choix S1 du cadrage du second Qwen local).
            bilan.fin = (
                "contexte_depasse"
                if isinstance(panne, ContexteDepasse)
                else "delai_depasse"
                if isinstance(panne, DelaiAppelDepasse)
                else "erreur"
            )
            bilan.detail = str(panne)
            noter(bilan)
            return bilan
        bilan.compter(reponse)
        message = cast(dict[str, Any], reponse["choices"][0]["message"])
        contenu: object = message.get("content")
        appels = cast(list[dict[str, Any]], message.get("tool_calls") or [])
        tour: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
        if appels:
            tour["tool_calls"] = appels
        pensee = raisonnement(message)
        if configuration.raisonnement_renvoye and pensee:
            tour[configuration.raisonnement_renvoye] = pensee
        messages.append(tour)
        raconter(recit(bilan.appels_modele, pensee, contenu, appels, fin=fin_du_tour(reponse)))
        if not appels and not (isinstance(contenu, str) and contenu.strip()):
            raconter(f"tour vide, champs du message : {champs(message)}")
        if not appels and tour_coupe_par_le_contexte(reponse, configuration):
            # Sans plafond de sortie demandé, vLLM laisse le tour écrire jusqu'à remplir le contexte,
            # puis le coupe : ce n'est pas une réponse finale (essai de Qwen du 2026-10-18).
            _, _, ecrits = lire_usage(reponse.get("usage"))
            bilan.fin = "contexte_depasse"
            bilan.detail = f"tour coupé par le serveur (fin length) après {ecrits} jetons écrits, sans appel d'outil"
            noter(bilan)
            return bilan
        if not appels:
            bilan.fin = "termine"
            noter(bilan)
            return bilan
        noter(bilan)
        for appel in appels:
            messages.append(
                {"role": "tool", "tool_call_id": appel.get("id", ""), "content": await executer_appel(appel, outils)}
            )
    bilan.fin, bilan.detail = "tours_max", f"{configuration.tours_max} tours sans réponse finale"
    noter(bilan)
    return bilan


def recit(
    numero: int,
    pensee: str | None,
    contenu: object,
    appels: list[dict[str, Any]],
    role: str | None = None,
    fin: str | None = None,
) -> str:
    """Un tour du modèle, en clair, pour le journal du candidat ; role nomme un second agent, fin
    dit pourquoi l'API a arrêté le tour."""
    tour = f"tour {numero}" if fin is None else f"tour {numero} ({fin})"
    lignes = [f"--- {tour} ---" if role is None else f"--- {role}, {tour} ---"]
    if pensee:
        lignes += ["raisonnement :", pensee.strip()]
    if isinstance(contenu, str) and contenu.strip():
        lignes += ["réponse :", contenu.strip()]
    for appel in appels:
        fonction = cast(dict[str, Any], appel.get("function") or {})
        lignes.append(f"appel : {fonction.get('name', '')}({fonction.get('arguments', '')})")
    return "\n".join(lignes)


def tour_coupe_par_le_contexte(reponse: dict[str, Any], configuration: ConfigurationModele) -> bool:
    """Vrai pour un tour coupé faute de place (fin length) quand la configuration ne plafonne pas
    la sortie : la conversation et le tour ont rempli le contexte du modèle."""
    choix = cast(list[dict[str, Any]], reponse.get("choices") or [{}])[0]
    plafond = {"max_tokens", "max_completion_tokens"} & set(configuration.parametres)
    return choix.get("finish_reason") == "length" and not plafond


def fin_du_tour(reponse: dict[str, Any]) -> str | None:
    """La raison de fin et les jetons écrits d'un tour, ce que l'API en dit ; None si elle ne dit rien."""
    choix = cast(list[dict[str, Any]], reponse.get("choices") or [{}])[0]
    raison: object = choix.get("finish_reason")
    _, _, ecrits = lire_usage(reponse.get("usage"))
    morceaux = [f"fin {raison}"] if isinstance(raison, str) else []
    if ecrits != "?":
        morceaux.append(f"{ecrits} jetons écrits")
    rejoues = len(cast(list[object], reponse.get(TOURS_VIDES) or []))
    if rejoues:
        morceaux.append(f"tours vides rejoués avant lui : {rejoues}")
    return ", ".join(morceaux) or None


def champs(message: dict[str, Any]) -> str:
    """Les champs d'un message et la longueur de leur texte, sans le texte : le raisonnement d'un
    candidat ne s'affiche pas."""
    morceaux = [
        f"{cle} {len(valeur)}" if isinstance(valeur, str) else f"{cle} {type(valeur).__name__}"
        for cle, valeur in message.items()
        if cle != "role"
    ]
    return ", ".join(morceaux) or "aucun"


async def executer_appel(appel: dict[str, Any], outils: Outils) -> str:
    """Le texte rendu au modèle pour un appel d'outil ; un refus commence par « Erreur : »."""
    fonction = cast(dict[str, Any], appel.get("function") or {})
    try:
        arguments: object = json.loads(fonction.get("arguments") or "{}")
    except json.JSONDecodeError:
        arguments = None
    if not isinstance(arguments, dict):
        return "Erreur : arguments illisibles, un objet JSON est attendu"
    texte, refus = await outils.appeler(str(fonction.get("name", "")), cast(dict[str, Any], arguments))
    return f"Erreur : {texte}" if refus else texte


def outil_openai(nom: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Un outil MCP au format des outils de l'API compatible OpenAI."""
    parametres = {cle: valeur for cle, valeur in schema.items() if cle != "$schema"}
    return {"type": "function", "function": {"name": nom, "description": description, "parameters": parametres}}


class OutilsMCP:
    """Les outils du relais d'EASE, par un client MCP ouvert."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def lister(self) -> list[dict[str, Any]]:
        outils: list[dict[str, Any]] = []
        curseur: str | None = None
        while True:
            page = await self._client.list_tools(cursor=curseur)
            outils += [outil_openai(o.name, o.description or "", dict(o.input_schema)) for o in page.tools]
            curseur = page.next_cursor
            if curseur is None:
                return outils

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        resultat = await self._client.call_tool(nom, arguments)
        texte = "\n".join(bloc.text for bloc in resultat.content if isinstance(bloc, TextContent))
        return texte, bool(resultat.is_error)


def ecrire_sortie(chemin: Path, bilan: Bilan) -> None:
    """Écrit la sortie d'un bloc : un fichier à moitié écrit n'est jamais lu."""
    ecrire_sortie_json(chemin, bilan.en_json())


def ecrire_sortie_json(chemin: Path, sortie: dict[str, Any]) -> None:
    """Écrit une sortie au contrat sortie_candidat, d'un bloc."""
    provisoire = chemin.with_name(chemin.name + ".tmp")
    provisoire.write_text(json.dumps(sortie, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provisoire.replace(chemin)


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m orchestrations.agent_seul")
    analyse.add_argument("--configuration", type=Path, required=True)
    analyse.add_argument("--mcp", required=True)
    analyse.add_argument("--enonce", type=Path, required=True)
    analyse.add_argument("--sortie", type=Path, required=True)
    options = analyse.parse_args(arguments)
    configuration = lire_configuration(options.configuration)
    bilan = Bilan(role=configuration.role)

    def noter(courant: Bilan) -> None:
        nonlocal bilan
        bilan = courant
        ecrire_sortie(options.sortie, courant)

    async def executer() -> None:
        cle = cle_api(configuration.cle_env, Path.cwd())
        async with Client(options.mcp, mode="legacy", cache=None) as client, Modele(configuration, cle) as modele:
            enonce = options.enonce.read_text(encoding="utf-8")
            await boucle(enonce, CONSIGNE.read_text(encoding="utf-8"), OutilsMCP(client), modele, configuration, noter)

    try:
        anyio.run(executer)
    except Exception as panne:  # rendue à EASE, qui la note en erreur technique
        bilan.fin, bilan.detail = "erreur", f"{type(panne).__name__} : {panne}"
        ecrire_sortie(options.sortie, bilan)
    if bilan.fin != "termine":
        print(f"agent seul, fin {bilan.fin} : {bilan.detail}", file=sys.stderr)
    return 1 if bilan.fin == "erreur" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
