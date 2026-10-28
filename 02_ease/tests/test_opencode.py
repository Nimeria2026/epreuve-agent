"""Les règles de l'atelier pour opencode, opencode.json à la racine (ADR 0011 ; JOURNAL, entrée 304).

opencode lit ses règles dans l'ordre, la dernière qui correspond l'emporte ; « * » couvre tout
caractère, « / » compris. Ces tests rejouent cette lecture sur le fichier du dépôt.
"""

from __future__ import annotations

import json
from fnmatch import fnmatchcase
from typing import Any

import pytest
from ease.chargement import racine_depot

FICHIER = racine_depot() / "opencode.json"
if not FICHIER.is_file():
    pytest.skip("opencode.json reste dans l'atelier, hors de l'export public (ADR 0011)", allow_module_level=True)
CONFIGURATION: dict[str, Any] = json.loads(FICHIER.read_text(encoding="utf-8"))
ATELIER = "/maison/Projets/Nimeria_poa"


def decision(cle: str, sujet: str, agent: str | None = None) -> str | None:
    """Les règles du fichier, puis celles de l'agent, qui passent après : la dernière l'emporte.
    C'est l'ordre que montre `opencode debug agents` sous opencode 2.0.16 (JOURNAL, entrée 307)."""
    regles: list[tuple[str, str]] = list(CONFIGURATION["permission"][cle].items())
    if agent is not None:
        propres: dict[str, str] | str = CONFIGURATION["agent"][agent].get("permission", {}).get(cle, {})
        regles += [("*", propres)] if isinstance(propres, str) else list(propres.items())
    trouvees = [action for motif, action in regles if fnmatchcase(sujet, motif)]
    return trouvees[-1] if trouvees else None


def test_atelier_et_la_methode_sont_charges() -> None:
    instructions: list[str] = CONFIGURATION["instructions"]
    assert instructions[0] == "ATELIER.md"
    assert (racine_depot() / "ATELIER.md").is_file()
    assert [chemin.rsplit("/", 1)[-1] for chemin in instructions[1:]] == [
        "METHODE.md",
        "ANTI_AI_STYLE.md",
        "AUTONOMIE.md",
    ]


@pytest.mark.parametrize(
    ("chemin", "attendue"),
    [
        ("AGENTS.md", "allow"),
        (".env.exemple", "allow"),
        (".env", "deny"),
        ("07_taches/prive/t99_essai.yaml", "deny"),
        ("99_local/seance_cachees/notes.md", "deny"),
        ("99_local/runs/2026-10-26_120411_agent_seul_x/fiche_de_run.json", "ask"),
        ("99_local/runs/2026-10-26_120411_agent_seul_x/journaux/t01_r1_candidat.log", "deny"),
        ("99_local/importes/2026-10-25_strata/run/fiche_de_run.json", "ask"),
    ],
)
def test_ce_qui_se_lit(chemin: str, attendue: str) -> None:
    assert decision("read", f"{ATELIER}/{chemin}") == attendue


@pytest.mark.parametrize(
    ("chemin", "attendue"),
    [
        ("02_ease/src/ease/mesure.py", "allow"),
        ("08_publications/README.md", "allow"),
        ("08_publications/2026-11-02_constat/donnees.json", "deny"),
        ("99_local/runs/2026-10-26_120411_agent_seul_x/fiche_de_run.json", "deny"),
        ("07_taches/prive/t99_essai.yaml", "deny"),
        (".env", "deny"),
    ],
)
def test_ce_qui_s_ecrit(chemin: str, attendue: str) -> None:
    assert decision("edit", f"{ATELIER}/{chemin}") == attendue


@pytest.mark.parametrize(
    ("commande", "attendue"),
    [
        ("make mesure CANDIDAT=agent_seul_x", None),
        ("git status --porcelain", None),
        ("git push origin main", "ask"),
        ("rm -r 99_local/chantier/essai", "ask"),
        ("git add -A", "deny"),
        ("git commit --no-verify -m essai", "deny"),
        ("git worktree prune", "deny"),
        ("cat .env", "deny"),
        ("cat 07_taches/prive/t99_essai.yaml", "deny"),
        ("tail 99_local/runs/r/journaux/t01_r1_candidat.log", "deny"),
    ],
)
def test_ce_qui_se_lance(commande: str, attendue: str | None) -> None:
    assert decision("bash", commande) == attendue


def test_l_agent_des_cachees_ne_parle_qu_au_poste() -> None:
    agent = CONFIGURATION["agent"]["cachees"]
    fournisseur, modele = agent["model"].split("/", 1)
    local = CONFIGURATION["provider"][fournisseur]
    assert local["options"]["baseURL"].startswith("http://127.0.0.1:")
    assert modele in local["models"]
    assert agent["permission"]["webfetch"] == "deny" and agent["permission"]["websearch"] == "deny"
    consigne = agent["prompt"].removeprefix("{file:./").removesuffix("}")
    assert (racine_depot() / consigne).is_file()


@pytest.mark.parametrize(
    ("cle", "sujet", "attendue"),
    [
        ("read", f"{ATELIER}/07_taches/prive/t99_essai.yaml", "allow"),
        ("read", f"{ATELIER}/99_local/seance_cachees/notes.md", "allow"),
        ("read", f"{ATELIER}/03_orchestrations/src/orchestrations/agent_seul.py", "deny"),
        ("read", f"{ATELIER}/.env", "deny"),
        ("read", f"{ATELIER}/99_local/runs/r/journaux/t01_r1_candidat.log", "deny"),
        ("read", f"{ATELIER}/99_local/runs/r/fiche_de_run.json", "ask"),
        ("edit", f"{ATELIER}/07_taches/prive/t99_essai.yaml", "allow"),
        ("edit", f"{ATELIER}/JOURNAL.md", "deny"),
        ("edit", f"{ATELIER}/07_taches/public/t01_ranger_facture_fournisseur.yaml", "deny"),
        ("bash", "make temoins TERRAIN=pme_cachees", None),
        ("bash", "ls 07_taches/prive/domivelle", "allow"),
        ("bash", "rm 07_taches/prive/t99_essai.yaml", "ask"),
        ("bash", "git status", "deny"),
        ("bash", "cat .env", "deny"),
    ],
)
def test_ce_que_peut_l_agent_des_cachees(cle: str, sujet: str, attendue: str | None) -> None:
    assert decision(cle, sujet, "cachees") == attendue


def test_l_agent_par_defaut_n_ouvre_toujours_pas_les_cachees() -> None:
    assert decision("read", f"{ATELIER}/07_taches/prive/t99_essai.yaml") == "deny"
    assert decision("bash", "ls 07_taches/prive/domivelle") == "deny"


RELEVE = racine_depot() / "00_docs" / "sources" / "2026-10-26_politiques_de_donnees_opencode.md"
ADMIS = (
    # Les modèles qui ne gardent ni n'entraînent sur les requêtes, d'après le relevé ci-dessus
    # (JOURNAL, entrée 307). Un modèle n'entre ici qu'avec sa politique relue et notée.
    "poa-local/qwen3.8-flash-next-iq3_s",
    "opencode-go/glm-5.3-flash",
    "opencode-go/glm-5.3",
    "opencode-go/glm-5.2",
    "opencode-go/qwen3.8-max",
    "opencode-go/qwen3.8-flash",
    "opencode-go/qwen3.7-plus",
    "opencode-go/kimi-k3.1-pro",
    "opencode-go/kimi-k3",
    "opencode-go/kimi-k2.7-code",
    "opencode-go/mimo-v2.6-pro",
    "opencode-go/mimo-v2.6-flash",
    "opencode-go/mimo-v2.5-pro",
    "opencode-go/mimo-v2.5",
    "opencode-go/minimax-m3",
    "opencode-go/minimax-m3.1-flash",
    "opencode-go/longcat-2.0",
    "opencode-go/gemini-4-argon",
    "opencode-go/hy4-preview",
    "opencode-go/hy3",
    "opencode-go/step-5-preview",
)


def test_chaque_modele_admis_a_sa_politique_relue() -> None:
    releve = RELEVE.read_text(encoding="utf-8")
    for modele in ADMIS:
        assert modele.split("/", 1)[1] in releve, modele
    ecartes = ("deepseek", "muse-spark", "grok", "gpt-", "claude", "beam", "iceman")
    assert not [m for m in ADMIS if any(e in m for e in ecartes)]


def test_un_agent_qui_ouvre_les_cachees_n_a_qu_un_modele_admis() -> None:
    cachee = f"{ATELIER}/07_taches/prive/t99_essai.yaml"
    ouvrants = [nom for nom in CONFIGURATION["agent"] if decision("read", cachee, nom) == "allow"]
    assert ouvrants == [nom for nom in CONFIGURATION["agent"] if nom.startswith("cachees")]
    assert "cachees" in ouvrants
    reference = CONFIGURATION["agent"]["cachees"]["permission"]
    for nom in ouvrants:
        agent = CONFIGURATION["agent"][nom]
        assert agent["model"] in ADMIS, nom
        assert agent["permission"] == reference, nom


def test_le_titre_des_seances_n_entraine_rien() -> None:
    # L'agent qui titre chaque séance lit son premier message, dans la séance des cachées aussi.
    assert CONFIGURATION["agent"]["title"]["model"] in ADMIS
