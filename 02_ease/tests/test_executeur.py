"""Exécuteur : budgets, erreurs, coût, interruption, frontière de la règle 6."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from ease.chargement import racine_depot
from ease.contrats.fiche_de_run import Configuration, Modele, Tarif
from ease.contrats.resultat_execution import Jetons
from ease.executeur import (
    Consommation,
    ErreurOutil,
    Outils,
    cout_dollars,
    lancer_run,
    nouveau_dossier_de_run,
    version_code,
)
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.jouet import SOLUTIONS_JOUET, TACHES_JOUET, ClasseurJouet
from ease.statistiques import resumer
from ease.temoins import Temoin, terrain_jouet
from ease.verification import verifier

JOUET = terrain_jouet()


class _Bavard(Temoin):
    identifiant, nom = "bavard", "Lit sans fin"

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        while True:
            outils.appeler("lister", dossier="arrivee")


class _EnPanne(Temoin):
    identifiant, nom = "en_panne", "Tombe en panne"

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        raise ConnectionError("API indisponible (HTTP 503)")


class _Maladroit(Temoin):
    """Se trompe d'outil, s'en rend compte, puis joue la solution."""

    identifiant, nom = "maladroit", "Se trompe d'outil puis se reprend"

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        with pytest.raises(ErreurOutil):
            outils.appeler("supprimer", chemin="arrivee/note_interne.txt")
        return self._jouer(self.terrain.solutions, enonce, outils)


class _ClasseurDate(ClasseurJouet):
    """Le classeur jouet, avec une horloge."""

    def preambule(self) -> str | None:
        return "Nous sommes le lundi 2 novembre 2026, il est 9 h."


class _Lecteur(Temoin):
    """Note chaque énoncé reçu, puis joue la solution."""

    identifiant, nom = "lecteur", "Note l'énoncé reçu"

    def __init__(self, terrain: Any) -> None:
        super().__init__(terrain)
        self.recus: list[str] = []

    def executer(self, enonce: str, outils: Outils) -> Consommation:
        self.recus.append(enonce)
        return self._jouer(self.terrain.solutions, enonce, outils)


def _run(candidat: Temoin, dossier: Path, **options: Any) -> Path:
    return lancer_run(
        candidat=candidat,
        environnement=ClasseurJouet(),
        taches=options.get("taches", TACHES_JOUET),
        controleur=options.get("controleur", verifier),
        repetitions=options.get("repetitions", 2),
        nom_jeu="jouet",
        dossier_runs=dossier,
    )


def _resultats(dossier: Path) -> list[Any]:
    return [lire_resultat(chemin) for chemin in sorted((dossier / "resultats").glob("*.json"))]


def test_l_agent_recoit_la_date_de_l_environnement_avant_l_enonce(tmp_path: Path) -> None:
    lecteur = _Lecteur(JOUET)
    dossier = lancer_run(
        candidat=lecteur,
        environnement=_ClasseurDate(),
        taches=TACHES_JOUET[:1],
        controleur=verifier,
        repetitions=1,
        nom_jeu="jouet",
        dossier_runs=tmp_path,
    )
    assert lecteur.recus == [f"Nous sommes le lundi 2 novembre 2026, il est 9 h.\n\n{TACHES_JOUET[0].enonce}"]
    assert all(resultat.reussie for resultat in _resultats(dossier))


def test_sans_horloge_l_agent_recoit_l_enonce_seul(tmp_path: Path) -> None:
    lecteur = _Lecteur(JOUET)
    _run(lecteur, tmp_path, taches=TACHES_JOUET[:1], repetitions=1)
    assert lecteur.recus == [TACHES_JOUET[0].enonce]


def test_le_budget_d_etapes_arrete_l_agent_et_compte_comme_un_echec(tmp_path: Path) -> None:
    for resultat in _resultats(_run(_Bavard(JOUET), tmp_path)):
        assert resultat.arret == "budget_etapes"
        assert resultat.etapes == TACHES_JOUET[0].budget.etapes_max
        assert not resultat.reussie


def test_une_erreur_technique_est_notee_et_sort_du_taux(tmp_path: Path) -> None:
    resultats = _resultats(_run(_EnPanne(JOUET), tmp_path))
    assert all(r.arret == "erreur_technique" and "HTTP 503" in (r.detail_arret or "") for r in resultats)
    with pytest.raises(ValueError, match="aucune exécution retenue"):
        resumer(resultats)


def test_une_erreur_d_outil_revient_a_l_agent_et_compte_comme_une_etape(tmp_path: Path) -> None:
    resultats = _resultats(_run(_Maladroit(JOUET), tmp_path, repetitions=1))
    assert all(r.reussie for r in resultats)
    assert resultats[0].etapes == len(SOLUTIONS_JOUET["j01_ranger_facture"]) + 1


def test_un_controleur_defaillant_interrompt_le_run_et_le_dit(tmp_path: Path) -> None:
    def casse(*_: Any) -> list[tuple[float, str | None]]:
        raise RuntimeError("contrôleur cassé")

    with pytest.raises(RuntimeError):
        _run(_Bavard(JOUET), tmp_path, controleur=casse)
    (dossier,) = tmp_path.iterdir()
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    assert fiche.statut == "interrompu"
    assert "contrôleur cassé" in (fiche.raison_interruption or "")


def _configuration(prix_cache: float | str) -> Configuration:
    tarif = Tarif.model_validate(
        {
            "entree_dollars_par_million": 0.15,
            "entree_en_cache_dollars_par_million": prix_cache,
            "sortie_dollars_par_million": 0.60,
            "source": "https://api-docs.deepseek.com/quick_start/pricing",
            "releve_le": "2026-10-05",
        }
    )
    modele = Modele(
        role="agent", nom="deepseek-flash", fournisseur="DeepSeek", version_renvoyee="?", parametres={}, tarif=tarif
    )
    return Configuration(modeles=[modele])


def test_deux_runs_du_meme_candidat_dans_la_meme_seconde_ont_deux_dossiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instant = datetime(2026, 10, 6, 17, 32, 30, 400_000, tzinfo=UTC)
    instants = iter([instant, instant, instant + timedelta(seconds=1)])
    attentes: list[float] = []
    monkeypatch.setattr("ease.executeur.maintenant", lambda: next(instants))
    monkeypatch.setattr("ease.executeur.time.sleep", attentes.append)
    _, premier, _ = nouveau_dossier_de_run(tmp_path, "temoin_parfait")
    debut, second, dossier = nouveau_dossier_de_run(tmp_path, "temoin_parfait")
    assert (premier, second) == ("2026-10-06_173230_temoin_parfait", "2026-10-06_173231_temoin_parfait")
    assert dossier.is_dir() and debut == instant + timedelta(seconds=1)
    assert attentes == [pytest.approx(0.61)]


def test_le_cout_suit_le_tarif_de_la_fiche_de_run() -> None:
    consommation = Consommation({"agent": Jetons(entree=52000, entree_en_cache=41000, sortie=2100)})
    assert cout_dollars(consommation, _configuration(0.003)) == pytest.approx(0.003033)


def test_un_cache_au_prix_de_l_entree_laisse_le_cout_connu() -> None:
    """DeepInfra ne dit pas la part lue en cache, mais la facture au prix de l'entrée (entrée 120)."""
    consommation = Consommation({"agent": Jetons(entree=1000, entree_en_cache="?", sortie=10)})
    assert cout_dollars(consommation, _configuration(0.15)) == pytest.approx(0.000156)
    assert cout_dollars(consommation, _configuration(0.003)) == "?"


def test_le_cout_devient_inconnu_des_qu_un_element_manque() -> None:
    connue = Consommation({"agent": Jetons(entree=1000, entree_en_cache=500, sortie=10)})
    assert cout_dollars(connue, _configuration("?")) == "?"
    inconnue = Consommation({"agent": Jetons(entree="?", entree_en_cache=0, sortie=10)})
    assert cout_dollars(inconnue, _configuration(0.003)) == "?"
    autre_role = Consommation({"superviseur": Jetons(entree=10, entree_en_cache=0, sortie=10)})
    assert cout_dollars(autre_role, _configuration(0.003)) == "?"
    assert cout_dollars(Consommation(), Configuration(modeles=[])) == 0.0


def test_ease_n_importe_ni_orchestration_ni_gardien_ni_eke() -> None:
    """Règle 6 : EASE parle aux autres composants par MCP ou HTTP, jamais par import. Depuis
    l'étape 7, ni τ²-bench (tau2) ni le pont qui le sert (bancs_publics) : un terrain de mesure."""
    interdit = re.compile(r"^\s*(from|import)\s+(orchestrations|gardien|eke|pme|tau2|bancs_publics)\b", re.MULTILINE)
    sources = (racine_depot() / "02_ease" / "src").rglob("*.py")
    fautifs = [str(source) for source in sources if interdit.search(source.read_text(encoding="utf-8"))]
    assert fautifs == []


def test_version_code_ne_prend_pas_le_verrou_de_l_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un run ne prend pas `.git/index.lock` : un commit lancé en même temps ne bute pas dessus."""
    monkeypatch.delenv("POA_COMMIT_IMAGE", raising=False)
    environnements: list[dict[str, str]] = []

    class Sortie:
        stdout = "0123456789abcdef0123456789abcdef01234567\n"

    def faux_run(arguments: list[str], **options: Any) -> Sortie:
        environnements.append(options["env"])
        return Sortie()

    monkeypatch.setattr("ease.executeur.subprocess.run", faux_run)
    code = version_code(racine_depot())
    assert code.commit == "0123456789abcdef0123456789abcdef01234567"
    assert len(environnements) == 2
    assert all(env["GIT_OPTIONAL_LOCKS"] == "0" for env in environnements)


def test_version_code_dans_l_image_du_banc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Dans l'image du banc (étape 8), sans dépôt git, le commit vient de POA_COMMIT_IMAGE ; avec
    un dépôt git, git reste la source, même si la variable est posée."""
    commit = "fedcba9876543210fedcba9876543210fedcba98"
    monkeypatch.setenv("POA_COMMIT_IMAGE", commit)

    def git_interdit(arguments: list[str], **options: Any) -> None:
        raise AssertionError(f"git appelé dans l'image : {arguments}")

    monkeypatch.setattr("ease.executeur.subprocess.run", git_interdit)
    code = version_code(tmp_path)
    assert code.commit == commit
    assert code.modifications_non_commitees is False

    (tmp_path / ".git").mkdir()
    with pytest.raises(AssertionError, match="git appelé"):
        version_code(tmp_path)
