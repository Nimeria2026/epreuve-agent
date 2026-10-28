"""Mesure d'un candidat sur τ²-bench (étape 7, règle 4) : agent de reproduction, simulateur, fiche.

Le serveur de 11_bancs_publics tourne avec l'utilisateur écrit d'avance et l'agent de
reproduction parle à un modèle simulé : aucun modèle réel n'est appelé, aucune clé n'est lue.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from ease.candidat_externe import CandidatExterne, Lancement
from ease.candidats import declarations
from ease.chargement import ContratInvalide
from ease.contrats.fiche_de_run import JetonsSimulateur, Tarif
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.mesure_tau2 import SIMULATEURS, cle_du_simulateur, declarations_tau2, lire_candidat_tau2, main, resume_tau2
from ease.temoins_tau2 import TerrainTau2, terrain_tau2
from ease.terrain_tau2 import (
    OUTIL_CLIENT,
    EnvironnementTau2,
    Simulateur,
    consommation_simulateur,
    cout_simulateur,
    lancer_run,
)

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def donnees() -> None:
    subprocess.run([sys.executable, "-m", "bancs_publics.tau2_bench.donnees"], check=True, capture_output=True)


def _repondre(terrain: TerrainTau2, corps: dict[str, Any], recus: list[dict[str, Any]]) -> dict[str, Any]:
    """Le modèle simulé reconnaît la tâche au premier message du client et rejoue la solution du
    témoin parfait : ses appels d'outils, puis le message au client en texte, comme l'agent de
    τ²-bench."""
    recus.append(corps)
    messages: list[dict[str, Any]] = corps["messages"]
    actions = terrain.solutions[terrain.tache(f"user: {messages[2]['content']}")]
    faits = sum(1 for m in messages if m["role"] == "assistant") - 1  # le salut est de τ²-bench
    if faits < len(actions) and actions[faits][0] != OUTIL_CLIENT:
        nom, arguments = actions[faits]
        appel = {
            "id": f"appel-{faits}",
            "type": "function",
            "function": {"name": nom, "arguments": json.dumps(arguments)},
        }
        message: dict[str, Any] = {"role": "assistant", "content": None, "tool_calls": [appel]}
    elif faits < len(actions):
        message = {"role": "assistant", "content": actions[faits][1]["message"]}
    else:
        message = {"role": "assistant", "content": "Anything else?"}
    usage = {"prompt_tokens": len(json.dumps(messages)) // 4, "completion_tokens": 10}
    return {"model": "modele-simule", "choices": [{"index": 0, "message": message}], "usage": usage}


@pytest.fixture
def modele_simule(tmp_path: Path, donnees: None) -> Iterator[tuple[Path, TerrainTau2, list[dict[str, Any]]]]:
    del donnees
    terrain = terrain_tau2("sierra", ["0", "14"])
    recus: list[dict[str, Any]] = []

    class Gestionnaire(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            reponse = json.dumps(_repondre(terrain, corps, recus)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reponse)))
            self.end_headers()
            self.wfile.write(reponse)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    configuration = tmp_path / "modele_simule.yaml"
    configuration.write_text(
        f"role: agent\nmodele: modele-demande\nadresse: http://127.0.0.1:{serveur.server_address[1]}/v1\n"
        "cle_env: null\nparametres: {temperature: 0.0, tool_choice: auto}\nraisonnement_renvoye: null\n"
        "delai_appel_secondes: 30\ntours_max: 40\n",
        encoding="utf-8",
    )
    yield configuration, terrain, recus
    serveur.shutdown()
    fil.join(5)


def _reproduction(configuration: Path) -> CandidatExterne:
    """Le candidat déclaré pour DeepSeek, relancé sur le modèle simulé, hors créneau."""
    declare = lire_candidat_tau2("reproduction_tau2_deepseek_flash")
    commande = [sys.executable, "-m", "orchestrations.reproduction_tau2", "--configuration", str(configuration)]
    return CandidatExterne(
        declare.fiche, declare.configuration, Lancement(commande, delai_secondes=120), declare.empreinte_prompts
    )


def test_l_agent_de_reproduction_joue_tau2_par_le_relais_et_la_fiche_nomme_le_banc(
    modele_simule: tuple[Path, TerrainTau2, list[dict[str, Any]]], tmp_path: Path
) -> None:
    configuration, terrain, recus = modele_simule
    with EnvironnementTau2("sierra", travail=tmp_path / "travail") as environnement:
        dossier = lancer_run(
            candidat=_reproduction(configuration),
            environnement=environnement,
            taches=terrain.taches,
            repetitions=1,
            dossier_runs=tmp_path / "runs",
        )
    resultats = [lire_resultat(c) for c in sorted((dossier / "resultats").glob("*.json"))]
    assert [(r.tache.identifiant, r.reussie, r.arret) for r in resultats] == [
        ("airline_0", True, "termine"),
        ("airline_14", True, "termine"),
    ]
    # Ce que voit le modèle : la consigne de τ²-bench en message système, la conversation en
    # messages, les 14 outils d'airline sans celui du client, les réglages de τ²-bench.
    premier = recus[0]
    assert [m["role"] for m in premier["messages"]] == ["system", "assistant", "user"]
    assert premier["messages"][0]["content"].startswith("<instructions>")
    assert premier["messages"][1]["content"] == "Hi! How can I help you today?"
    assert len(premier["tools"]) == 14 and OUTIL_CLIENT not in {o["function"]["name"] for o in premier["tools"]}
    assert (premier["temperature"], premier["tool_choice"]) == (0.0, "auto")
    gestes = [json.loads(ligne)["outil"] for ligne in (dossier / "journaux" / "airline_14_r1.jsonl").open()]
    assert gestes == ["cancel_reservation", "book_reservation", OUTIL_CLIENT]
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    assert fiche.banc_public is not None
    banc = fiche.banc_public
    assert (banc.nom, banc.version, banc.domaine, banc.jeu) == ("tau2_bench", "1.0.1", "airline", "sierra")
    assert banc.simulateur.modele == "ecrit_d_avance" and banc.simulateur.jetons is None
    assert fiche.candidat.identifiant == "reproduction_tau2_deepseek_flash"
    lignes = resume_tau2(dossier)
    assert lignes[0].startswith("Réussite : 2/2") and any(ligne.startswith("pass^k : pass^1 100 %") for ligne in lignes)


def test_la_fiche_refuse_un_simulateur_qui_ne_dit_pas_vrai(
    modele_simule: tuple[Path, TerrainTau2, list[dict[str, Any]]], tmp_path: Path
) -> None:
    configuration, terrain, _ = modele_simule
    environnement = EnvironnementTau2("sierra", travail=tmp_path / "travail")
    with pytest.raises(ValueError, match="simulateur"):
        lancer_run(
            candidat=_reproduction(configuration),
            environnement=environnement,
            taches=terrain.taches,
            repetitions=1,
            dossier_runs=tmp_path / "runs",
            simulateur=SIMULATEURS["gemini_2_5_flash"],
        )


def _simulation(chemin: Path, usages: list[dict[str, Any] | None]) -> Path:
    messages: list[dict[str, Any]] = [{"role": "assistant", "content": "Hi! How can I help you today?"}]
    for usage in usages:
        messages.append({"role": "user", "content": "...", "raw_data": None if usage is None else {"usage": usage}})
        messages.append({"role": "assistant", "content": "ok", "raw_data": {"usage": {"prompt_tokens": 9}}})
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps({"messages": messages}), encoding="utf-8")
    return chemin


SIMULE = "google/gemini-2.5-flash"
"""Le nom que litellm envoie à OpenRouter pour openrouter/google/gemini-2.5-flash."""
REQUETE = {"model": SIMULE, "temperature": 0.0, "usage": {"include": True}}

TARIF = Tarif(
    entree_dollars_par_million=0.30,
    entree_en_cache_dollars_par_million=0.03,
    sortie_dollars_par_million=2.50,
    source="essai",
    releve_le=date(2026, 10, 10),
)


def test_les_jetons_du_simulateur_se_lisent_dans_les_conversations(tmp_path: Path) -> None:
    detail = {"cached_tokens": 600}
    a = _simulation(
        tmp_path / "a" / "simulation.json",
        [
            {
                "prompt_tokens": 1000,
                "completion_tokens": 50,
                "prompt_tokens_details": detail,
                "completion_tokens_details": {"reasoning_tokens": 30},
                "cost": 0.0002,
            },
            {
                "prompt_tokens": 2000,
                "completion_tokens": 70,
                "prompt_tokens_details": {"cached_tokens": 0},
                "completion_tokens_details": {"reasoning_tokens": 0},
                "cost": 0.0008,
            },
        ],
    )
    jetons, annonce = consommation_simulateur([a])
    assert jetons == JetonsSimulateur(entree=3000, entree_en_cache=600, sortie=120, dont_reflexion=30)
    assert annonce == pytest.approx(0.001)
    attendu = (2400 * 0.30 + 600 * 0.03 + 120 * 2.50) / 1e6
    assert cout_simulateur(jetons, TARIF) == pytest.approx(attendu)
    # Ce qui manque devient « ? » : le cache, le coût annoncé, une conversation entière.
    b = _simulation(tmp_path / "b" / "simulation.json", [{"prompt_tokens": 10, "completion_tokens": 1}])
    jetons, annonce = consommation_simulateur([a, b])
    assert (jetons.entree, jetons.entree_en_cache, jetons.sortie, jetons.dont_reflexion, annonce) == (
        3010,
        "?",
        121,
        "?",
        "?",
    )
    assert cout_simulateur(jetons, TARIF) == "?"
    jetons, annonce = consommation_simulateur([a, tmp_path / "absente" / "simulation.json"])
    assert (jetons.entree, annonce) == ("?", "?")


Modification = Callable[[dict[str, Any]], None]


def _banc(simulateur: dict[str, Any]) -> Modification:
    def modifier(fiche: dict[str, Any]) -> None:
        fiche["banc_public"] = {
            "nom": "tau2_bench",
            "version": "1.0.1",
            "domaine": "airline",
            "jeu": "verified",
            "simulateur": {
                "modele": "openrouter/google/gemini-2.5-flash",
                "fournisseur": "OpenRouter",
                "parametres": {"temperature": 0.0},
                "tarif": None,
                "jetons": {"entree": 1, "entree_en_cache": 0, "sortie": 1, "dont_reflexion": 0},
                "cout_dollars": "?",
                "cout_annonce_dollars": 0.0,
            }
            | simulateur,
        }

    return modifier


@pytest.mark.parametrize(
    ("modification", "message"),
    [
        (_banc({}), None),
        (_banc({"modele": "ecrit_d_avance"}), "sans modèle"),
        (_banc({"modele": "rejoue:gpt_4_1", "fournisseur": None, "jetons": None}), "sans modèle"),
        (_banc({"fournisseur": None}), "requis pour un modèle"),
        (_banc({"cout_dollars": None}), "à la fin du run"),
    ],
)
def test_la_fiche_garde_un_simulateur_coherent(tmp_path: Path, modification: Modification, message: str | None) -> None:
    fiche: dict[str, Any] = json.loads((RACINE / "01_contrats/exemples/fiche_de_run_api.json").read_text("utf-8"))
    modification(fiche)
    chemin = tmp_path / "fiche_de_run.json"
    chemin.write_text(json.dumps(fiche), encoding="utf-8")
    if message is None:
        assert lire_fiche_de_run(chemin).banc_public is not None
        return
    with pytest.raises(ContratInvalide, match=message):
        lire_fiche_de_run(chemin)


def test_les_candidats_de_tau2_vivent_a_part_de_ceux_de_la_pme() -> None:
    reproduction = ["reproduction_tau2_deepseek_flash", "reproduction_tau2_qwen_local"]
    declares = [
        "auteur_relecteur_tau2_deepseek_flash",
        "reproduction_tau2_deepseek_flash",
        "reproduction_tau2_deepseek_flash_1017",
        "reproduction_tau2_mimo_v26_flash_deepinfra",
        "reproduction_tau2_qwen_flash_next_strata",
        "reproduction_tau2_qwen_local",
        "reproduction_tau2_qwen_local_100k",
    ]
    # A/B du 2026-10-11 ; contexte élargi et MiMo, 21 et 22 octobre ; Flash-Next sous Strata, 26 octobre.
    assert declarations_tau2() == declares
    assert not set(declarations_tau2()) & set(declarations())
    deepseek, qwen = (lire_candidat_tau2(nom) for nom in reproduction)
    assert deepseek.lancement.creneau == "heures_creuses_deepseek" and qwen.lancement.sonde is not None
    assert deepseek.empreinte_prompts != qwen.empreinte_prompts
    assert main(["agent_seul_deepseek_flash"]) == 2  # un candidat de la PME est refusé ici


def test_les_reglages_du_simulateur_sont_ceux_que_tau2_lui_envoie() -> None:
    """La fiche note ce que le serveur envoie au simulateur : DEFAULT_LLM_ARGS_USER de τ²-bench, lu
    dans un processus à part (EASE n'importe jamais τ²-bench)."""
    code = "import json; from tau2.config import DEFAULT_LLM_ARGS_USER as A; print(json.dumps(A))"
    lus = json.loads(subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout)
    assert dict(SIMULATEURS["gemini_2_5_flash"].parametres) == lus
    assert SIMULATEURS["ecrit_d_avance"] == Simulateur()


def test_la_cle_du_simulateur_se_lit_sans_s_afficher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POA_CLE_ESSAI", raising=False)
    assert cle_du_simulateur("POA_CLE_ESSAI", tmp_path) is None
    (tmp_path / ".env").write_text("AUTRE=1\nPOA_CLE_ESSAI=\n", encoding="utf-8")
    assert cle_du_simulateur("POA_CLE_ESSAI", tmp_path) is None  # une ligne vide n'est pas une clé
    (tmp_path / ".env").write_text('POA_CLE_ESSAI="abc"\n', encoding="utf-8")
    assert cle_du_simulateur("POA_CLE_ESSAI", tmp_path) == "abc"
    monkeypatch.setenv("POA_CLE_ESSAI", "xyz")
    assert cle_du_simulateur("POA_CLE_ESSAI", tmp_path) == "xyz"


def _complet(modele: str, contenu: str, usage: dict[str, Any]) -> dict[str, Any]:
    """Une réponse au format complet de l'API compatible OpenAI, que litellm relit."""
    return {
        "id": "essai",
        "object": "chat.completion",
        "created": 1760000000,
        "model": modele,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": contenu}, "finish_reason": "stop"}],
        "usage": usage,
    }


@pytest.fixture
def deux_modeles(tmp_path: Path, donnees: None) -> Iterator[tuple[Path, str, list[dict[str, Any]]]]:
    """Un serveur qui joue l'agent (modele-demande) et le simulateur, sous le nom que litellm donne
    à OpenRouter pour gemini-2.5-flash : le simulateur demande de l'aide, puis clôt dès la première
    réponse de l'agent."""
    del donnees
    recus: list[dict[str, Any]] = []

    class Gestionnaire(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            recus.append(corps | {"autorisation": self.headers.get("Authorization")})
            if corps["model"] == SIMULE:
                tours = sum(1 for m in corps["messages"] if m["role"] == "assistant")
                texte = "I need help with my reservation." if tours == 0 else "Thanks. ###STOP###"
                usage = {
                    "prompt_tokens": 1000,
                    "completion_tokens": 40,
                    "total_tokens": 1040,
                    "prompt_tokens_details": {"cached_tokens": 400},
                    "completion_tokens_details": {"reasoning_tokens": 25},
                    "cost": 0.000222,
                }
                reponse = _complet(SIMULE, texte, usage)
            else:
                reponse = _complet(
                    "modele-simule", "Sure, what is your user id?", {"prompt_tokens": 50, "completion_tokens": 5}
                )
            donnees = json.dumps(reponse).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    adresse = f"http://127.0.0.1:{serveur.server_address[1]}/v1"
    configuration = tmp_path / "modele_simule.yaml"
    configuration.write_text(
        f"role: agent\nmodele: modele-demande\nadresse: {adresse}\ncle_env: null\nparametres: {{}}\n"
        "raisonnement_renvoye: null\ndelai_appel_secondes: 30\ntours_max: 10\n",
        encoding="utf-8",
    )
    yield configuration, adresse, recus
    serveur.shutdown()
    fil.join(5)


def test_le_simulateur_d_openrouter_recoit_sa_cle_par_le_seul_serveur_et_se_compte(
    deux_modeles: tuple[Path, str, list[dict[str, Any]]], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Le chemin du vrai simulateur, sans dépense : le simulateur déclaré, gemini-2.5-flash par
    OpenRouter, joué par un faux OpenRouter local (OPENROUTER_API_BASE, lu par litellm). La clé ne
    passe qu'au serveur de τ²-bench ; la requête ne porte aucun réglage de réflexion (décision
    d'Alexandre du 2026-10-10) ; la fiche somme les jetons, dont la réflexion, et les coûts."""
    configuration, adresse, recus = deux_modeles
    simulateur = SIMULATEURS["gemini_2_5_flash"]
    assert simulateur.cle_env is not None
    variables = {simulateur.cle_env: "cle-d-essai", "OPENROUTER_API_BASE": adresse}
    environnement = EnvironnementTau2(
        "sierra", travail=tmp_path / "travail", utilisateur=simulateur.modele, variables=variables
    )
    with environnement:
        dossier = lancer_run(
            candidat=_reproduction(configuration),
            environnement=environnement,
            taches=terrain_tau2("sierra", ["0"]).taches,
            repetitions=1,
            dossier_runs=tmp_path / "runs",
            simulateur=simulateur,
        )
    resultat = lire_resultat(dossier / "resultats" / "airline_0_r1.json")
    assert resultat.arret == "termine" and resultat.detail_arret is None
    # La sortie standard du serveur ne porte que MCP, jusqu'à son arrêt : litellm, qui ne sait pas
    # chiffrer une réponse nommée google/gemini-2.5-flash, n'y imprime rien (essai du 2026-10-10).
    assert not [r for r in caplog.records if "Failed to parse JSONRPC" in r.getMessage()]
    simules = [r for r in recus if r["model"] == SIMULE]
    assert len(simules) == 2 and {r["autorisation"] for r in simules} == {"Bearer cle-d-essai"}
    # La requête entière, hors messages : la température de τ²-bench, et le décompte d'usage que
    # litellm 1.82.6 demande à OpenRouter ; rien sur la réflexion.
    assert all({k: v for k, v in r.items() if k not in ("messages", "autorisation")} == REQUETE for r in simules)
    agent = [r for r in recus if r["model"] == "modele-demande"]
    assert agent[0]["messages"][2] == {"role": "user", "content": "I need help with my reservation."}
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    assert fiche.banc_public is not None
    du_simulateur = fiche.banc_public.simulateur
    assert du_simulateur.jetons == JetonsSimulateur(entree=2000, entree_en_cache=800, sortie=80, dont_reflexion=50)
    assert du_simulateur.cout_dollars == pytest.approx((1200 * 0.30 + 800 * 0.03 + 80 * 2.50) / 1e6)
    assert any("(dont réflexion 50)" in ligne for ligne in resume_tau2(dossier))
    assert du_simulateur.cout_annonce_dollars == pytest.approx(0.000444)
    assert "cle-d-essai" not in (dossier / "fiche_de_run.json").read_text(encoding="utf-8")


def test_un_run_de_tau2_refuse_un_serveur_a_un_autre_contexte(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import ease.mesure_tau2 as mesure_tau2

    def version(adresse: str) -> str:
        return "version 0.27.1"

    def contexte(sonde: str) -> int:
        return 40960

    monkeypatch.setattr(mesure_tau2, "sonder", version)
    monkeypatch.setattr(mesure_tau2, "contexte_annonce", contexte)
    assert main(["reproduction_tau2_qwen_local_100k", "--taches", "31", "--repetitions", "1"]) == 3
    assert "en attend 102400" in capsys.readouterr().err
    contextes = {i: lire_candidat_tau2(i).lancement.contexte_serveur for i in declarations_tau2() if "qwen" in i}
    assert contextes == {
        "reproduction_tau2_qwen_flash_next_strata": None,
        "reproduction_tau2_qwen_local": 40960,
        "reproduction_tau2_qwen_local_100k": 102400,
    }
