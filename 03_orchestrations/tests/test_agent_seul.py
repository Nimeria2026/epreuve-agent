"""Agent seul : la boucle entre le modèle et les outils, avec un modèle et des outils simulés."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import anyio
import httpx2
import pytest
from jsonschema import Draft202012Validator
from orchestrations import modele as module_modele
from orchestrations.agent_seul import CONSIGNE, Bilan, boucle, ecrire_sortie, outil_openai
from orchestrations.modele import (
    ConfigurationModele,
    ContexteDepasse,
    DelaiAppelDepasse,
    ErreurModele,
    Modele,
    cle_api,
    lire_configuration,
    lire_usage,
    refus_de_contexte,
)

RACINE = Path(__file__).resolve().parents[2]
CONFIGURATIONS = RACINE / "03_orchestrations" / "src" / "orchestrations" / "configurations"
SCHEMA_SORTIE = json.loads((RACINE / "01_contrats" / "sortie_candidat.schema.json").read_text(encoding="utf-8"))


def _configuration(**changements: Any) -> ConfigurationModele:
    valeurs: dict[str, Any] = {
        "role": "agent",
        "modele": "modele-essai",
        "adresse": "http://modele.essai/v1",
        "cle_env": None,
        "parametres": {},
        "raisonnement_renvoye": None,
        "delai_appel_secondes": 5,
        "tours_max": 5,
    }
    return ConfigurationModele(**(valeurs | changements))


def _reponse(message: dict[str, Any], usage: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"model": "modele-annonce", "choices": [{"message": message}], "usage": usage or {}}


def _appel(nom: str, arguments: str, identifiant: str = "a1") -> dict[str, Any]:
    return {"id": identifiant, "type": "function", "function": {"name": nom, "arguments": arguments}}


class ModeleScripte:
    """Rend les réponses prévues, dans l'ordre, et garde une copie des messages reçus."""

    def __init__(self, reponses: Sequence[dict[str, Any] | Exception]) -> None:
        self._reponses = list(reponses)
        self.recus: list[list[dict[str, Any]]] = []

    async def repondre(self, messages: list[dict[str, Any]], outils: list[dict[str, Any]]) -> dict[str, Any]:
        self.recus.append([dict(m) for m in messages])
        reponse = self._reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse


class OutilsSimules:
    def __init__(self) -> None:
        self.appels: list[tuple[str, dict[str, Any]]] = []

    async def lister(self) -> list[dict[str, Any]]:
        return [outil_openai("lister_boites", "Liste les boîtes.", {"type": "object", "properties": {}})]

    async def appeler(self, nom: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        self.appels.append((nom, arguments))
        return ("outil inconnu", True) if nom != "lister_boites" else ("contact@calorelle.example", False)


RECITS: list[str] = []


def _tourner(modele: ModeleScripte, configuration: ConfigurationModele) -> tuple[Bilan, OutilsSimules, list[Bilan]]:
    outils, notes = OutilsSimules(), list[Bilan]()

    async def executer() -> Bilan:
        return await boucle("Énoncé.", "Consigne.", outils, modele, configuration, notes.append, RECITS.append)

    return anyio.run(executer), outils, notes


def test_l_agent_appelle_l_outil_puis_rend_la_main() -> None:
    modele = ModeleScripte(
        [
            _reponse(
                {"content": None, "tool_calls": [_appel("lister_boites", "{}")]},
                {"prompt_tokens": 300, "completion_tokens": 20},
            ),
            _reponse({"content": "Une boîte : contact@."}, {"prompt_tokens": 340, "completion_tokens": 12}),
        ]
    )
    bilan, outils, notes = _tourner(modele, _configuration())
    assert (bilan.fin, bilan.appels_modele, bilan.entree, bilan.sortie, bilan.entree_en_cache) == (
        "termine",
        2,
        640,
        32,
        "?",
    )
    assert outils.appels == [("lister_boites", {})]
    second = modele.recus[1]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "tool"]
    assert second[3] == {"role": "tool", "tool_call_id": "a1", "content": "contact@calorelle.example"}
    assert notes[-1].fin == "termine"


def test_un_refus_et_des_arguments_illisibles_reviennent_au_modele_comme_erreurs() -> None:
    appels = [_appel("supprimer", "{}", "a1"), _appel("lister_boites", "{pas du json", "a2")]
    modele = ModeleScripte([_reponse({"content": None, "tool_calls": appels}), _reponse({"content": "Fini."})])
    _, outils, _ = _tourner(modele, _configuration())
    retours = [m["content"] for m in modele.recus[1] if m["role"] == "tool"]
    assert retours == ["Erreur : outil inconnu", "Erreur : arguments illisibles, un objet JSON est attendu"]
    assert outils.appels == [("supprimer", {})]


@pytest.mark.parametrize(("renvoye", "attendu"), [(None, False), ("reasoning_content", True)])
def test_le_raisonnement_n_est_renvoye_que_si_la_configuration_le_demande(renvoye: str | None, attendu: bool) -> None:
    pense = {"content": None, "reasoning": "Je liste.", "tool_calls": [_appel("lister_boites", "{}")]}
    modele = ModeleScripte([_reponse(pense), _reponse({"content": "Fini."})])
    _tourner(modele, _configuration(raisonnement_renvoye=renvoye))
    tour = modele.recus[1][2]
    assert ("reasoning_content" in tour) is attendu
    assert "reasoning" not in tour


def test_la_limite_de_tours_arrete_la_boucle() -> None:
    boucle_sans_fin = [_reponse({"content": None, "tool_calls": [_appel("lister_boites", "{}")]}) for _ in range(3)]
    bilan, _, _ = _tourner(ModeleScripte(boucle_sans_fin), _configuration(tours_max=3))
    assert (bilan.fin, bilan.appels_modele) == ("tours_max", 3)


def test_une_panne_du_modele_finit_en_erreur_et_garde_la_consommation() -> None:
    premiere = _reponse(
        {"content": None, "tool_calls": [_appel("lister_boites", "{}")]}, {"prompt_tokens": 100, "completion_tokens": 5}
    )
    bilan, _, _ = _tourner(ModeleScripte([premiere, ErreurModele("HTTP 503")]), _configuration())
    assert (bilan.fin, bilan.detail, bilan.entree) == ("erreur", "HTTP 503", 100)


VLLM_TROP_LONG = (
    "This model's maximum context length is 40960 tokens. However, you requested 41234 tokens "
    "(41234 in the messages, 0 in the completion). Please reduce the length of the messages or completion."
)


def test_un_contexte_depasse_finit_sous_son_arret_et_garde_la_consommation() -> None:
    """Choix T3 du cadrage du 2026-10-14 : un échec de l'agent, sous un arrêt à part, pas une panne."""
    premiere = _reponse(
        {"content": None, "tool_calls": [_appel("lister_boites", "{}")]}, {"prompt_tokens": 100, "completion_tokens": 5}
    )
    trop_long = ContexteDepasse(f"HTTP 400 : {VLLM_TROP_LONG}")
    bilan, _, _ = _tourner(ModeleScripte([premiere, trop_long]), _configuration())
    assert (bilan.fin, bilan.entree) == ("contexte_depasse", 100)
    assert "maximum context length" in (bilan.detail or "")


@pytest.mark.parametrize(("parametres", "fin"), [({}, "contexte_depasse"), ({"max_tokens": 4096}, "termine")])
def test_un_tour_coupe_faute_de_place_est_un_contexte_depasse(parametres: dict[str, Any], fin: str) -> None:
    """Essai de Qwen du 2026-10-18 : sans plafond de sortie, vLLM laisse le tour écrire jusqu'à remplir
    le contexte, puis le coupe (fin length), sans appel d'outil ; ce n'est pas une réponse finale."""
    coupe = _reponse({"content": None}, {"prompt_tokens": 28609, "completion_tokens": 12351})
    coupe["choices"][0]["finish_reason"] = "length"
    bilan, _, _ = _tourner(ModeleScripte([coupe]), _configuration(parametres=parametres))
    assert bilan.fin == fin
    if fin == "contexte_depasse":
        assert "fin length" in (bilan.detail or "") and "12351 jetons écrits" in (bilan.detail or "")


@pytest.mark.parametrize(
    ("statut", "texte", "attendu"),
    [
        (400, json.dumps({"object": "error", "message": VLLM_TROP_LONG, "code": 400}), True),
        (400, "The decoder prompt (length 41234) is longer than the maximum model length of 40960.", True),
        (400, json.dumps({"error": {"code": "context_length_exceeded"}}), True),
        (400, json.dumps({"erreur": "outil mal décrit"}), False),
        (500, VLLM_TROP_LONG, False),
    ],
)
def test_le_refus_d_une_conversation_trop_longue_se_reconnait(statut: int, texte: str, attendu: bool) -> None:
    assert refus_de_contexte(statut, texte) is attendu


def test_le_client_leve_un_contexte_depasse_sans_reessayer() -> None:
    recues: list[httpx2.Request] = []

    def refuser(requete: httpx2.Request) -> httpx2.Response:
        recues.append(requete)
        return httpx2.Response(400, json={"object": "error", "message": VLLM_TROP_LONG, "code": 400})

    async def appeler() -> None:
        async with Modele(_configuration(), None, transport=httpx2.MockTransport(refuser)) as modele:
            await modele.repondre([{"role": "user", "content": "Bonjour"}], [])

    with pytest.raises(ContexteDepasse, match="maximum context length"):
        anyio.run(appeler)
    assert len(recues) == 1


def test_un_appel_trop_lent_finit_en_delai_depasse_sans_reessayer() -> None:
    """Choix S1 du cadrage du second Qwen local : un appel qui dépasse son délai est un échec de
    l'agent, sous son arrêt, et ne se rejoue pas."""
    recues: list[httpx2.Request] = []

    def trop_lent(requete: httpx2.Request) -> httpx2.Response:
        recues.append(requete)
        raise httpx2.ReadTimeout("lecture trop longue", request=requete)

    async def appeler() -> None:
        async with Modele(_configuration(), None, transport=httpx2.MockTransport(trop_lent)) as modele:
            await modele.repondre([{"role": "user", "content": "Bonjour"}], [])

    with pytest.raises(DelaiAppelDepasse, match="pas de réponse en"):
        anyio.run(appeler)
    assert len(recues) == 1
    premiere = _reponse(
        {"content": None, "tool_calls": [_appel("lister_boites", "{}")]}, {"prompt_tokens": 100, "completion_tokens": 5}
    )
    bilan, _, _ = _tourner(ModeleScripte([premiere, DelaiAppelDepasse("pas de réponse en 900 s")]), _configuration())
    assert (bilan.fin, bilan.entree) == ("delai_depasse", 100)


def test_la_sortie_respecte_son_contrat(tmp_path: Path) -> None:
    bilan = Bilan(role="agent", fin="termine", appels_modele=2, entree=640, entree_en_cache="?", sortie=32)
    bilan.modeles_renvoyes.add("modele-annonce")
    chemin = tmp_path / "sortie.json"
    ecrire_sortie(chemin, bilan)
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    # Les annotations de jsonschema laissent is_valid partiellement inconnu, comme dans ease.chargement.
    valide: Callable[[Any], bool] = Draft202012Validator(SCHEMA_SORTIE).is_valid  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert valide(donnees)
    assert donnees["modeles_renvoyes"] == {"agent": "modele-annonce"}
    assert not (tmp_path / "sortie.json.tmp").exists()


@pytest.mark.parametrize(
    ("usage", "attendu"),
    [
        ({"prompt_tokens": 50, "completion_tokens": 7, "prompt_tokens_details": {"cached_tokens": 30}}, (50, 30, 7)),
        ({"prompt_tokens": 50, "completion_tokens": 7, "prompt_cache_hit_tokens": 40}, (50, 40, 7)),
        ({"prompt_tokens": 50, "completion_tokens": 7, "prompt_tokens_details": None}, (50, "?", 7)),
        (None, ("?", "?", "?")),
    ],
    ids=["openai", "deepseek", "vllm", "absent"],
)
def test_l_usage_se_lit_dans_les_formats_des_fournisseurs(usage: Any, attendu: tuple[Any, Any, Any]) -> None:
    assert lire_usage(usage) == attendu


def test_le_client_reessaie_apres_une_panne_passagere_et_envoie_les_parametres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_modele, "ATTENTES_SECONDES", (0.0, 0.0))
    recues: list[httpx2.Request] = []
    statuts = [503, 200]

    def repondre(requete: httpx2.Request) -> httpx2.Response:
        recues.append(requete)
        statut = statuts.pop(0)
        return httpx2.Response(statut, json=_reponse({"content": "ok"}) if statut == 200 else {"erreur": "occupé"})

    configuration = _configuration(parametres={"temperature": 0.2})

    async def appeler() -> dict[str, Any]:
        async with Modele(configuration, "cle-secrete", transport=httpx2.MockTransport(repondre)) as modele:
            return await modele.repondre([{"role": "user", "content": "Bonjour"}], [])

    assert anyio.run(appeler)["choices"][0]["message"]["content"] == "ok"
    corps = json.loads(recues[-1].content)
    assert (len(recues), corps["temperature"], "tools" in corps) == (2, 0.2, False)
    assert str(recues[-1].url) == "http://modele.essai/v1/chat/completions"
    assert recues[-1].headers["Authorization"] == "Bearer cle-secrete"


def _vide(ecrits: int) -> dict[str, Any]:
    """Un tour vide comme chez DeepInfra : fin stop, ni réponse ni appel, des jetons écrits."""
    return {
        "choices": [{"message": {"content": "", "reasoning_content": "x", "tool_calls": []}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": ecrits},
    }


def _client(reponses: list[dict[str, Any]]) -> Callable[[httpx2.Request], httpx2.Response]:
    return lambda requete: httpx2.Response(200, json=reponses.pop(0))


def test_un_tour_vide_se_rejoue_et_ses_jetons_restent_comptes(monkeypatch: pytest.MonkeyPatch) -> None:
    """JOURNAL, entrée 120 : gpt-oss-120b chez DeepInfra perdait l'appel d'outil d'un tour sur deux."""
    monkeypatch.setattr(module_modele, "ATTENTES_SECONDES", (0.0, 0.0))
    bon = _reponse({"content": "Fait."}, usage={"prompt_tokens": 100, "completion_tokens": 20})
    bon["choices"][0]["finish_reason"] = "stop"
    reponses = [_vide(60), bon]

    async def appeler() -> dict[str, Any]:
        async with Modele(_configuration(), None, transport=httpx2.MockTransport(_client(reponses))) as modele:
            return await modele.repondre([{"role": "user", "content": "Bonjour"}], [])

    rendue = anyio.run(appeler)
    assert rendue[module_modele.TOURS_VIDES] == [{"prompt_tokens": 100, "completion_tokens": 60}]
    bilan = Bilan(role="agent")
    bilan.compter(rendue)
    assert (bilan.appels_modele, bilan.entree, bilan.sortie) == (1, 200, 80)


def test_trois_tours_vides_font_une_erreur_technique_comptee(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_modele, "ATTENTES_SECONDES", (0.0, 0.0))
    reponses = [_vide(60), _vide(70), _vide(80)]

    class ClientVide:
        async def repondre(self, messages: list[dict[str, Any]], outils: list[dict[str, Any]]) -> dict[str, Any]:
            async with Modele(_configuration(), None, transport=httpx2.MockTransport(_client(reponses))) as modele:
                return await modele.repondre(messages, outils)

    outils, notes = OutilsSimules(), list[Bilan]()

    async def executer() -> Bilan:
        return await boucle("Énoncé.", "Consigne.", outils, ClientVide(), _configuration(), notes.append, RECITS.append)

    bilan = anyio.run(executer)
    assert bilan.fin == "erreur" and "tour vide" in (bilan.detail or "")
    assert (bilan.entree, bilan.sortie) == (300, 210)


def test_une_requete_refusee_par_l_api_n_est_pas_reessayee() -> None:
    recues: list[httpx2.Request] = []

    def refuser(requete: httpx2.Request) -> httpx2.Response:
        recues.append(requete)
        return httpx2.Response(400, json={"erreur": "outil mal décrit"})

    async def appeler() -> None:
        async with Modele(_configuration(), None, transport=httpx2.MockTransport(refuser)) as modele:
            await modele.repondre([{"role": "user", "content": "Bonjour"}], [])

    with pytest.raises(ErreurModele, match="HTTP 400"):
        anyio.run(appeler)
    assert len(recues) == 1
    assert "Authorization" not in recues[0].headers


def test_la_cle_se_lit_dans_l_environnement_ou_dans_le_fichier_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLE_ESSAI", raising=False)
    (tmp_path / ".env").write_text("AUTRE=x\nCLE_ESSAI='depuis-le-fichier'\n", encoding="utf-8")
    assert cle_api("CLE_ESSAI", tmp_path) == "depuis-le-fichier"
    monkeypatch.setenv("CLE_ESSAI", "depuis-l-environnement")
    assert cle_api("CLE_ESSAI", tmp_path) == "depuis-l-environnement"
    with pytest.raises(ValueError, match="CLE_ABSENTE"):
        cle_api("CLE_ABSENTE", tmp_path)


def test_les_configurations_livrees_se_lisent_et_la_consigne_existe() -> None:
    noms = {chemin.stem: lire_configuration(chemin) for chemin in sorted(CONFIGURATIONS.glob("*.yaml"))}
    assert noms["qwen_local"].adresse == "http://127.0.0.1:30100/v1"
    assert noms["deepseek_flash"].raisonnement_renvoye == "reasoning_content"
    # Réglages des éditeurs (choix validé le 2026-10-05). gpt-oss-120b porte le sien, medium, écrit
    # parce que DeepInfra ne dit pas ce qu'il applique sans lui (JOURNAL, entrée 120).
    assert noms.pop("gpt_oss_deepinfra").parametres == {"reasoning_effort": "medium"}
    # Réglages de l'éditeur de MiMo (JOURNAL, entrée 233).
    assert noms.pop("mimo_v26_flash_deepinfra").parametres == {"temperature": 1.0, "top_p": 0.95}
    # Réglages de l'éditeur de Qwen3.8-Flash-Next, écrits faute de connaître ceux de Strata (entrée 295).
    assert noms.pop("qwen_flash_next_strata").parametres == {"temperature": 1.0, "top_p": 0.95, "top_k": 20}
    # Le diagnostic des appels perdus par Strata : la même, plus tool_choice (JOURNAL, entrée 333).
    assert noms.pop("qwen_flash_next_strata_choix_outil").parametres == {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "tool_choice": "auto",
    }
    assert all(c.parametres == {} for c in noms.values())
    assert CONSIGNE.read_text(encoding="utf-8").strip()


def test_une_configuration_incomplete_est_refusee(tmp_path: Path) -> None:
    chemin = tmp_path / "bancale.yaml"
    chemin.write_text("role: agent\nmodele: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clés manquantes"):
        lire_configuration(chemin)


def test_les_orchestrations_n_importent_jamais_ease() -> None:
    """Règle 5 : EASE contient les contrôles et les solutions ; une orchestration n'y touche pas."""
    interdit = re.compile(r"^\s*(from|import)\s+ease\b", re.MULTILINE)
    sources = (RACINE / "03_orchestrations").rglob("*.py")
    assert [str(s) for s in sources if interdit.search(s.read_text(encoding="utf-8"))] == []


def test_la_raison_de_fin_et_un_tour_vide_sont_racontes_sans_le_raisonnement() -> None:
    """gpt-oss-120b chez DeepInfra finissait sur des tours sans réponse ni appel (JOURNAL, entrée 120)."""
    RECITS.clear()
    vide: dict[str, Any] = {
        "choices": [{"message": {"content": "", "reasoning_content": "ab"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 97},
    }
    bilan, _, _ = _tourner(ModeleScripte([vide]), _configuration())
    assert bilan.fin == "termine"
    assert RECITS == [
        "--- tour 1 (fin stop, 97 jetons écrits) ---\nraisonnement :\nab",
        "tour vide, champs du message : content 0, reasoning_content 2",
    ]


def test_chaque_tour_est_raconte_en_clair() -> None:
    RECITS.clear()
    pense = {"content": None, "reasoning": "Je liste les boîtes.", "tool_calls": [_appel("lister_boites", "{}")]}
    _tourner(ModeleScripte([_reponse(pense), _reponse({"content": "Une boîte."})]), _configuration())
    assert RECITS == [
        "--- tour 1 ---\nraisonnement :\nJe liste les boîtes.\nappel : lister_boites({})",
        "--- tour 2 ---\nréponse :\nUne boîte.",
    ]
