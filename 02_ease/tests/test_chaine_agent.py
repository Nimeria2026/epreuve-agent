"""La chaîne complète d'un vrai candidat, sans vrai modèle.

L'agent seul de 03_orchestrations tourne dans son propre processus, parle à un modèle simulé
par HTTP (format compatible OpenAI) et agit sur la PME par le relais d'EASE. Le modèle simulé
appartient au banc : il reconnaît la tâche à l'énoncé et rejoue sa solution, un appel d'outil
par tour. La chaîne doit alors réussir t01 à t05, comme le témoin parfait.
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from ease.candidat_externe import CandidatExterne, Lancement
from ease.candidats import DOSSIER, declarations, lire_candidat
from ease.chargement import ContratInvalide
from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import Configuration, Modele
from ease.fiches import lire_resultat
from ease.mesure import demande_un_juge, resume_texte
from ease.temoins import Terrain, mesurer, terrain_pme


def _repondre(terrain: Terrain, corps: dict[str, Any]) -> dict[str, Any]:
    messages: list[dict[str, Any]] = corps["messages"]
    outils: list[dict[str, Any]] = corps.get("tools") or []
    if any(o["function"]["name"] == "verdict" for o in outils):
        # Le relecteur simulé lit le manuel au début de sa conversation, puis accorde.
        if not any(m["role"] == "assistant" for m in messages):
            nom, arguments = "lire", '{"chemin": "commun/manuel_procedures.md"}'
        else:
            nom, arguments = "verdict", '{"accord": true, "raison": "conforme"}'
        appel = {"id": nom, "type": "function", "function": {"name": nom, "arguments": arguments}}
        message: dict[str, Any] = {"role": "assistant", "content": None, "tool_calls": [appel]}
        usage = {"prompt_tokens": 50, "completion_tokens": 5}
        return {"model": "modele-simule", "choices": [{"index": 0, "message": message}], "usage": usage}
    actions = terrain.solutions[terrain.tache(messages[1]["content"])]
    faits = sum(1 for m in messages if m["role"] == "assistant")
    if not corps.get("tools"):
        message = {"role": "assistant", "content": "Aucun outil : je ne peux rien faire."}
    elif faits < len(actions):
        nom, arguments = actions[faits]
        appel = {
            "id": f"appel-{faits}",
            "type": "function",
            "function": {"name": nom, "arguments": json.dumps(arguments)},
        }
        message = {"role": "assistant", "content": None, "tool_calls": [appel]}
    else:
        message = {"role": "assistant", "content": "Travail terminé."}
    usage = {"prompt_tokens": len(json.dumps(messages)) // 4, "completion_tokens": 10}
    return {"model": "modele-simule", "choices": [{"index": 0, "message": message}], "usage": usage}


@pytest.fixture
def modele_simule(tmp_path: Path) -> Iterator[Path]:
    """Démarre le modèle simulé et rend le fichier de configuration qui y mène."""
    terrain = terrain_pme(tmp_path / "inutilise")

    class Gestionnaire(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            donnees = json.dumps(_repondre(terrain, corps)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def do_GET(self) -> None:
            donnees = json.dumps({"version": "simulee"}).encode("utf-8")
            self.send_response(200 if self.path == "/version" else 404)
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    configuration = tmp_path / "modele_simule.yaml"
    configuration.write_text(
        f"role: agent\nmodele: modele-demande\nadresse: http://127.0.0.1:{serveur.server_address[1]}/v1\n"
        "cle_env: null\nparametres: {}\nraisonnement_renvoye: null\ndelai_appel_secondes: 30\ntours_max: 40\n",
        encoding="utf-8",
    )
    yield configuration
    serveur.shutdown()
    fil.join(5)


def _agent_seul(configuration: Path) -> CandidatExterne:
    modele = Modele(
        role="agent", nom="modele-demande", fournisseur="local", version_renvoyee="?", parametres={}, tarif=None
    )
    fiche = FicheCandidat(
        identifiant="agent_seul_modele_simule",
        nom="Agent seul sur un modèle simulé",
        version="0.1.0",
        origine="fait_main",
        division="a_modele_egal",
        branchement="mcp",
        editeur="Épreuve d'agent",
        url=None,
        modeles="?",
        cout_mesurable=False,
        conditions_utilisation=None,
    )
    commande = [sys.executable, "-m", "orchestrations.agent_seul", "--configuration", str(configuration)]
    return CandidatExterne(fiche, Configuration(modeles=[modele]), Lancement(commande, delai_secondes=120))


def _premiere_tranche(terrain: Terrain) -> Terrain:
    """t01 à t05 : la chaîne s'y vérifie ; les pièges de t06 à t09 passent par les témoins."""
    taches = terrain.taches[:5]
    garder = {t.identifiant for t in taches}
    return Terrain(
        terrain.nom,
        taches,
        terrain.environnement,
        {i: a for i, a in terrain.solutions.items() if i in garder},
        {i: a for i, a in terrain.erreurs.items() if i in garder},
    )


def test_l_agent_seul_avec_un_modele_parfait_reussit_t01_a_t05(modele_simule: Path, tmp_path: Path) -> None:
    terrain = _premiere_tranche(terrain_pme(tmp_path / "pme"))
    assert [t.identifiant[:3] for t in terrain.taches] == ["t01", "t02", "t03", "t04", "t05"]
    dossier, resume = mesurer(_agent_seul(modele_simule), terrain, tmp_path / "runs", 1)
    assert (resume.reussites, resume.executions, resume.erreurs_techniques) == (5, 5, 0)
    fiche = json.loads((dossier / "fiche_de_run.json").read_text(encoding="utf-8"))
    assert fiche["configuration"]["modeles"][0]["version_renvoyee"] == "modele-simule"
    resultat = json.loads((dossier / "resultats" / "t05_piege_changement_rib_r1.json").read_text(encoding="utf-8"))
    assert resultat["jetons"]["entree"] > 0
    assert resultat["jetons"]["entree_en_cache"] == "?"
    appels = [json.loads(ligne) for ligne in (dossier / "journaux" / "t05_piege_changement_rib_r1.jsonl").open()]
    assert appels[-1]["outil"] == "envoyer"
    assert all(a["erreur"] is None for a in appels)
    lignes = resume_texte([lire_resultat(p) for p in sorted((dossier / "resultats").glob("*.json"))])
    assert lignes[0].startswith("Réussite : 5/5")


def test_auteur_et_relecteur_avec_un_modele_parfait_reussit_t01_a_t05_et_compte_les_deux_roles(
    modele_simule: Path, tmp_path: Path
) -> None:
    terrain = _premiere_tranche(terrain_pme(tmp_path / "pme"))
    roles = [
        Modele(role=r, nom="modele-demande", fournisseur="local", version_renvoyee="?", parametres={}, tarif=None)
        for r in ("auteur", "relecteur")
    ]
    seul = _agent_seul(modele_simule)
    commande = [
        sys.executable,
        "-m",
        "orchestrations.auteur_relecteur",
        "--configuration",
        str(modele_simule),
        "--relecteur",
        str(modele_simule),
    ]
    candidat = CandidatExterne(
        seul.fiche.model_copy(
            update={"identifiant": "auteur_relecteur_modele_simule", "nom": "Auteur et relecteur simulés"}
        ),
        Configuration(modeles=roles),
        Lancement(commande, delai_secondes=120, acces_lecture=True),
    )
    dossier, resume = mesurer(candidat, terrain, tmp_path / "runs", 1)
    assert (resume.reussites, resume.executions, resume.erreurs_techniques) == (5, 5, 0)
    fiche = json.loads((dossier / "fiche_de_run.json").read_text(encoding="utf-8"))
    assert [m["version_renvoyee"] for m in fiche["configuration"]["modeles"]] == ["modele-simule", "modele-simule"]
    journal = (dossier / "journaux" / "t05_piege_changement_rib_r1_candidat.log").read_text(encoding="utf-8")
    assert "=== relecture de envoyer ===" in journal and "verdict : accordée (conforme)" in journal
    assert "=== relecture de lire" not in journal
    # Les lectures du relecteur vont dans leur journal, hors du budget : l'auteur garde ses étapes.
    # Une seule conversation pour toute l'exécution (JOURNAL, entrée 111) : le manuel lu à la
    # première relecture sert aux suivantes.
    lectures = (dossier / "journaux" / "t05_piege_changement_rib_r1_lectures.jsonl").read_text(encoding="utf-8")
    lus = [json.loads(ligne)["outil"] for ligne in lectures.splitlines()]
    assert lus == ["lire"] and journal.count("=== relecture de ") > 1
    seul = len(terrain.solutions["t05_piege_changement_rib"])
    assert lire_resultat(dossier / "resultats" / "t05_piege_changement_rib_r1.json").etapes == seul


def test_les_candidats_declares_se_lisent() -> None:
    # Le candidat d'une campagne, campagne_<nom>, ne vit que dans son clone (02_ease/README.md,
    # « Brancher un agent externe ») : il s'ajoute à ceux de l'atelier sans changer ce test.
    assert [d for d in declarations() if not d.startswith("campagne_")] == [
        "agent_seul_deepseek_flash",
        "agent_seul_deepseek_flash_1017",
        "agent_seul_deepseek_flash_deepinfra",
        "agent_seul_gpt_oss_deepinfra",
        "agent_seul_mimo_v26_flash_deepinfra",
        "agent_seul_minimax_m31_flash_openrouter",
        "agent_seul_qwen_flash_next_strata",
        "agent_seul_qwen_flash_next_strata_choix_outil",
        "agent_seul_qwen_flash_next_strata_sans_mtp",
        "agent_seul_qwen_local",
        "agent_seul_qwen_local_100k",
        "agent_seul_qwen_max_gmi",
        "auteur_relecteur_deepseek_flash",
        "auteur_relecteur_qwen_local",
        "auteur_relecteur_qwen_max_gmi",
        "humain_p1",
    ]
    deepseek, qwen = (lire_candidat(nom) for nom in ("agent_seul_deepseek_flash", "agent_seul_qwen_local"))
    assert deepseek.configuration.modeles[0].tarif is not None
    assert qwen.machine is not None and qwen.machine.carte_graphique == "NVIDIA GeForce RTX 3090"
    assert deepseek.empreinte_prompts != qwen.empreinte_prompts
    assert (deepseek.lancement.creneau, deepseek.lancement.wattmetre) == ("heures_creuses_deepseek", None)
    assert qwen.lancement.creneau is None and qwen.lancement.wattmetre is not None
    qwen_max = lire_candidat("agent_seul_qwen_max_gmi")
    assert qwen_max.machine is None and qwen_max.lancement.creneau is None
    tarif = qwen_max.configuration.modeles[0].tarif
    assert tarif is not None and tarif.entree_en_cache_dollars_par_million == "?"
    # gpt-oss-120b chez DeepInfra : à toute heure, le seul paramètre est l'effort de l'éditeur
    # (JOURNAL, entrée 120).
    gpt_oss = lire_candidat("agent_seul_gpt_oss_deepinfra")
    assert gpt_oss.machine is None and gpt_oss.lancement.creneau is None
    assert dict(gpt_oss.configuration.modeles[0].parametres) == {"reasoning_effort": "medium"}
    # Le poste humain : une commande TypeScript, quatre heures par essai, l'accès en lecture seule
    # pour l'affichage, aucun modèle (JOURNAL, entrée 121).
    humain = lire_candidat("humain_p1")
    assert humain.lancement.commande[:2] == ["node", "05_pme/interface_web/src/principal.ts"]
    assert (humain.lancement.delai_secondes, humain.lancement.acces_lecture) == (14400.0, True)
    assert humain.configuration.modeles == [] and humain.fiche.origine == "humain"


def test_une_declaration_dont_le_nom_ne_suit_pas_l_identifiant_est_refusee(tmp_path: Path) -> None:
    source = DOSSIER / "agent_seul_qwen_local.yaml"
    (tmp_path / "autre_nom.yaml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ContratInvalide, match="le nom du fichier dit"):
        lire_candidat("autre_nom", tmp_path)


def test_une_commande_se_declare_avec_le_module_a_null(tmp_path: Path) -> None:
    texte = (DOSSIER / "agent_seul_qwen_local.yaml").read_text(encoding="utf-8")
    texte = texte.replace("  arguments:", "  commande: [node, principal.ts]\n  arguments:", 1)
    (tmp_path / "agent_seul_qwen_local.yaml").write_text(texte, encoding="utf-8")
    with pytest.raises(ContratInvalide, match="le module à null"):
        lire_candidat("agent_seul_qwen_local", tmp_path)


def test_un_creneau_ou_une_energie_inconnus_sont_refuses(tmp_path: Path) -> None:
    texte = (DOSSIER / "agent_seul_qwen_local.yaml").read_text(encoding="utf-8")
    texte = texte.replace("creneau: null", "creneau: la_nuit").replace("energie: nvidia_smi", "energie: compteur")
    (tmp_path / "agent_seul_qwen_local.yaml").write_text(texte, encoding="utf-8")
    with pytest.raises(ContratInvalide) as erreur:
        lire_candidat("agent_seul_qwen_local", tmp_path)
    debuts = [e.split(" :")[0] for e in erreur.value.erreurs]
    assert debuts == ["lancement.creneau", "lancement.energie"]
    assert "la_nuit" in erreur.value.erreurs[0] and "compteur" in erreur.value.erreurs[1]


def test_un_second_run_du_meme_candidat_est_refuse_tant_que_le_premier_tourne(tmp_path: Path) -> None:
    from ease.mesure import verrouiller

    chemin = tmp_path / "pme_essai.verrou"
    premier = verrouiller(chemin)
    assert premier is not None
    assert verrouiller(chemin) is None
    premier.close()
    second = verrouiller(chemin)
    assert second is not None
    second.close()


def test_la_sonde_dit_si_le_serveur_du_modele_repond(modele_simule: Path) -> None:
    from ease.mesure import sonder

    adresse = modele_simule.read_text(encoding="utf-8").split("adresse: ")[1].split("\n")[0].removesuffix("/v1")
    with pytest.raises(ConnectionError, match="ne répond pas"):
        sonder("http://127.0.0.1:9/version")  # port 9 : rien n'y écoute
    assert sonder(adresse + "/version") == "version simulee"


def test_seules_les_taches_a_juge_requis_demandent_le_juge() -> None:
    taches = {t.identifiant[:3]: t for t in terrain_pme().taches}
    juges = ["t02", "t04", "t05", "t06", "t09", "t48"]  # t48 en version 8 (JOURNAL, entrée 269)
    assert [nom for nom in sorted(taches) if demande_un_juge([taches[nom]])] == juges
    assert not demande_un_juge([taches["t01"], taches["t03"]])
