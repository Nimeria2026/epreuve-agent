"""Appel d'un modèle par l'API HTTP compatible OpenAI : vLLM en local, ou un fournisseur.

Le corps envoyé reste minimal : le nom du modèle, les messages, les outils, et les paramètres de
la configuration, recopiés tels quels. Aucun réglage n'est ajouté en douce : sans paramètre, le
modèle tourne avec les réglages de son éditeur. La réponse est rendue brute, pour que rien ne se
perde entre ce que l'API dit et ce que l'agent en fait ; une seule clé s'y ajoute, TOURS_VIDES,
quand des tours vides ont été rejoués avant elle.

Un tour vide, fini par « stop » sans réponse ni appel d'outil, se rejoue comme une panne
passagère : le fournisseur a perdu ce que le modèle a écrit (gpt-oss-120b chez DeepInfra, JOURNAL,
cent-vingtième entrée). Après les nouveaux essais, l'exécution finit en erreur technique, pas en
échec du modèle. Les jetons des tours rejoués sont facturés : ils restent comptés.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, cast

import anyio
import httpx2
import yaml

type Inconnu = Literal["?"]
type Nombre = int | Inconnu

ATTENTES_SECONDES = (2.0, 10.0)
"""Attentes avant chaque nouvel essai, après un refus passager (429, 5xx) ou une coupure."""


class ErreurModele(Exception):
    """L'API du modèle n'a pas donné de réponse exploitable : une panne, pas une faute de l'agent.

    usages_perdus : l'usage des tours vides rejoués en vain, à compter quand même.
    """

    def __init__(self, message: str, usages_perdus: list[object] | None = None) -> None:
        super().__init__(message)
        self.usages_perdus: list[object] = usages_perdus or []


class ContexteDepasse(ErreurModele):
    """Le serveur refuse une conversation plus longue que le contexte du modèle : un échec de
    l'agent, sous un arrêt à part, et non une panne (cadrage du 2026-10-14, choix T3)."""


class DelaiAppelDepasse(ErreurModele):
    """Le modèle n'a pas fini de répondre dans le délai d'un appel : un échec de l'agent, sous un
    arrêt à part, sans nouvel essai (cadrage du second Qwen local, choix S1). Un tour qui s'emballe
    ne finit pas mieux à la deuxième fois, et chaque essai coûterait le délai entier."""


CONTEXTE_DEPASSE = re.compile(
    r"maximum context length|maximum model length|max_model_len|context_length_exceeded"
    r"|context length|too long and exceeds",
    re.IGNORECASE,
)
"""Ce que disent vLLM et les API compatibles OpenAI quand la conversation dépasse le contexte."""


def refus_de_contexte(statut: int, texte: str) -> bool:
    """Vrai pour un refus du serveur dû à une conversation trop longue pour le contexte."""
    return statut in (400, 413) and CONTEXTE_DEPASSE.search(texte) is not None


TOURS_VIDES = "tours_vides_rejoues"
"""Clé ajoutée à une réponse : l'usage de chaque tour vide rejoué avant elle."""


def tour_vide(donnees: Mapping[str, Any]) -> bool:
    """Vrai pour un tour fini par « stop » sans réponse ni appel d'outil."""
    choix = cast(list[dict[str, Any]], donnees.get("choices") or [{}])[0]
    message = cast(dict[str, Any], choix.get("message") or {})
    contenu: object = message.get("content")
    return (
        choix.get("finish_reason") == "stop"
        and not message.get("tool_calls")
        and not (isinstance(contenu, str) and contenu.strip())
    )


@dataclass(frozen=True)
class ConfigurationModele:
    """Comment joindre un modèle, et comment l'agent le traite (configurations/*.yaml)."""

    role: str
    modele: str
    adresse: str
    cle_env: str | None
    parametres: Mapping[str, Any]
    raisonnement_renvoye: str | None
    """Champ du message de l'assistant où renvoyer son raisonnement au tour suivant ; None sinon."""
    delai_appel_secondes: float
    tours_max: int


def lire_configuration(chemin: Path) -> ConfigurationModele:
    """Lit une configuration ; refuse une clé manquante ou inconnue."""
    donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    if not isinstance(donnees, dict):
        raise ValueError(f"{chemin.name} : un dictionnaire YAML est attendu")
    valeurs = cast(dict[str, Any], donnees)
    attendues = set(ConfigurationModele.__dataclass_fields__)
    if set(valeurs) != attendues:
        manquantes, inconnues = sorted(attendues - set(valeurs)), sorted(set(valeurs) - attendues)
        raise ValueError(f"{chemin.name} : clés manquantes {manquantes}, clés inconnues {inconnues}")
    return ConfigurationModele(**valeurs)


def cle_api(nom: str | None, dossier: Path) -> str | None:
    """La clé lue dans la variable d'environnement nom, ou dans le fichier .env du dossier."""
    if nom is None:
        return None
    if os.environ.get(nom):
        return os.environ[nom]
    fichier = dossier / ".env"
    if fichier.is_file():
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            cle, egal, valeur = ligne.strip().partition("=")
            if egal and cle.strip() == nom:
                return valeur.strip().strip("\"'")
    raise ValueError(f"clé d'API introuvable : ni la variable {nom} ni le fichier .env ne la donnent")


def _nombre(valeur: object) -> Nombre:
    return valeur if isinstance(valeur, int) and valeur >= 0 else "?"


def lire_usage(usage: object) -> tuple[Nombre, Nombre, Nombre]:
    """(entrée, entrée en cache, sortie) d'une réponse ; « ? » pour ce que l'API ne dit pas.

    La part lue en cache se trouve dans prompt_tokens_details.cached_tokens (format OpenAI) ou
    dans prompt_cache_hit_tokens (DeepSeek) ; vLLM 0.27.1 ne la donne pas.
    """
    if not isinstance(usage, dict):
        return "?", "?", "?"
    donnees = cast(dict[str, Any], usage)
    details = donnees.get("prompt_tokens_details")
    cache: object = cast(dict[str, Any], details).get("cached_tokens") if isinstance(details, dict) else None
    if cache is None:
        cache = donnees.get("prompt_cache_hit_tokens")
    return _nombre(donnees.get("prompt_tokens")), _nombre(cache), _nombre(donnees.get("completion_tokens"))


def raisonnement(message: Mapping[str, Any]) -> str | None:
    """Le raisonnement d'un message : reasoning_content chez DeepSeek, reasoning chez vLLM."""
    for champ in ("reasoning_content", "reasoning"):
        valeur = message.get(champ)
        if isinstance(valeur, str) and valeur:
            return valeur
    return None


class Modele:
    """Client d'un modèle, à ouvrir par `async with`."""

    def __init__(
        self, configuration: ConfigurationModele, cle: str | None, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self._configuration = configuration
        entetes = {"Authorization": f"Bearer {cle}"} if cle else {}
        self._client = httpx2.AsyncClient(
            base_url=configuration.adresse.rstrip("/"),
            headers=entetes,
            timeout=configuration.delai_appel_secondes,
            transport=transport,
        )

    async def __aenter__(self) -> Modele:
        return self

    async def __aexit__(
        self, type_: type[BaseException] | None, erreur: BaseException | None, trace: TracebackType | None
    ) -> None:
        await self._client.aclose()

    async def repondre(self, messages: list[dict[str, Any]], outils: list[dict[str, Any]]) -> dict[str, Any]:
        """Un appel au modèle ; quelques nouveaux essais après un refus passager, une coupure ou un tour vide."""
        corps: dict[str, Any] = {"model": self._configuration.modele, "messages": messages}
        if outils:
            corps["tools"] = outils
        corps |= dict(self._configuration.parametres)
        derniere = ""
        vides: list[object] = []
        for attente in (0.0, *ATTENTES_SECONDES):
            await anyio.sleep(attente)
            try:
                reponse = await self._client.post("/chat/completions", json=corps)
            except httpx2.ReadTimeout as lenteur:
                raise DelaiAppelDepasse(
                    f"pas de réponse en {self._configuration.delai_appel_secondes:.0f} s ({type(lenteur).__name__})",
                    vides,
                ) from lenteur
            except httpx2.TransportError as coupure:
                derniere = f"{type(coupure).__name__} : {coupure}"
                continue
            if reponse.status_code == 429 or reponse.status_code >= 500:
                derniere = f"HTTP {reponse.status_code} : {reponse.text[:300]}"
                continue
            if reponse.status_code != 200:
                if refus_de_contexte(reponse.status_code, reponse.text):
                    raise ContexteDepasse(f"HTTP {reponse.status_code} : {reponse.text[:300]}", vides)
                raise ErreurModele(f"HTTP {reponse.status_code} : {reponse.text[:300]}", vides)
            donnees: object = reponse.json()
            if not isinstance(donnees, dict) or not cast(dict[str, Any], donnees).get("choices"):
                raise ErreurModele(f"réponse sans choix : {reponse.text[:300]}", vides)
            rendue = cast(dict[str, Any], donnees)
            if tour_vide(rendue):
                vides.append(rendue.get("usage"))
                derniere = "tour vide : fin stop, ni réponse ni appel d'outil"
                continue
            if vides:
                rendue[TOURS_VIDES] = vides
            return rendue
        raise ErreurModele(
            f"pas de réponse après {len(ATTENTES_SECONDES) + 1} essais ; dernier échec : {derniere}", vides
        )
