"""Le résumé de make mesure (ease.mesure.resume_texte) : les tâches cachées y sont comptées
ensemble, jamais nommées, pour que la séance qui lit la sortie ne les apprenne pas (JOURNAL,
cent-douzième entrée)."""

from __future__ import annotations

import math
import urllib.request
from typing import Any

import pytest
from ease import mesure
from ease.candidats import lire_candidat
from ease.chargement import racine_depot
from ease.contrats.resultat_execution import ResultatExecution
from ease.contrats.tache import Tache
from ease.mesure import resume_texte
from ease.taches import lire_taches

TACHES = lire_taches(racine_depot() / "07_taches" / "public")
T01, T02, T03 = TACHES[0], TACHES[1], TACHES[2]


def _resultat(tache: Tache, repetition: int, reussie: bool, arret: str = "termine") -> ResultatExecution:
    controles: list[dict[str, Any]] = [
        {"numero": i, "famille": c.famille, "poids": c.poids, "score": 1.0 if reussie else 0.0, "detail": None}
        for i, c in enumerate(tache.controles, start=1)
    ]
    return ResultatExecution.model_validate(
        {
            "run": "2026-10-13_120000_agent_essai",
            "tache": {"identifiant": tache.identifiant, "version": tache.version},
            "repetition": repetition,
            "debut_utc": "2026-10-13T12:00:00Z",
            "fin_utc": "2026-10-13T12:01:00Z",
            "arret": arret,
            "detail_arret": None,
            "controles": controles,
            "score": math.fsum(c["poids"] * c["score"] for c in controles),
            "reussie": reussie,
            "etapes": 10,
            "jetons": {"entree": 1000, "entree_en_cache": 0, "sortie": 100},
            "cout_dollars": 0.001,
            "energie_wh": None,
            "duree_secondes": 60.0,
            "journal": f"journaux/{tache.identifiant}_r{repetition}.jsonl",
        }
    )


def test_sans_tache_cachee_chaque_tache_a_sa_ligne() -> None:
    resultats = [_resultat(T01, 1, True), _resultat(T02, 1, False)]
    lignes = resume_texte(resultats)
    assert any(ligne.startswith(f"  {T01.identifiant} : 1/1 réussies") for ligne in lignes)
    assert any(ligne.startswith(f"  {T02.identifiant} : 0/1 réussies") for ligne in lignes)
    assert not any("tâches cachées" in ligne for ligne in lignes)


def test_les_taches_cachees_sont_comptees_ensemble_sans_leurs_noms() -> None:
    resultats = [
        _resultat(T01, 1, True),
        _resultat(T02, 1, True),
        _resultat(T02, 2, False, arret="budget_etapes"),
        _resultat(T03, 1, True),
        _resultat(T03, 2, False, arret="erreur_technique"),
    ]
    lignes = resume_texte(resultats, {T02.identifiant, T03.identifiant})
    assert lignes[0].startswith("Réussite : 3/4")
    assert any(ligne.startswith(f"  {T01.identifiant} : 1/1 réussies") for ligne in lignes)
    assert lignes[-1] == (
        "  tâches cachées (2) : 2/3 réussies, score moyen 0,67, arrêts : budget_etapes 1, erreur_technique 1"
    )
    assert not any(t.identifiant in ligne for t in (T02, T03) for ligne in lignes)


class _Reponse:
    """Une réponse HTTP imitée, le temps d'un with."""

    def __init__(self, corps: str) -> None:
        self._corps = corps.encode("utf-8")

    def __enter__(self) -> _Reponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._corps


def test_le_contexte_annonce_par_le_serveur_se_lit_dans_v1_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cadrage du second Qwen local : deux candidats au même modèle, à deux contextes, ne se confondent pas."""
    lues: list[str] = []

    def ouvrir(adresse: str, timeout: float) -> _Reponse:
        del timeout
        lues.append(adresse)
        return _Reponse('{"object": "list", "data": [{"id": "qwen3.8-27b-w4a16", "max_model_len": 102400}]}')

    monkeypatch.setattr(urllib.request, "urlopen", ouvrir)
    assert mesure.contexte_annonce("http://127.0.0.1:30100/version") == 102400
    assert lues == ["http://127.0.0.1:30100/v1/models"]

    def muet(adresse: str, timeout: float) -> _Reponse:
        del adresse, timeout
        return _Reponse('{"data": []}')

    monkeypatch.setattr(urllib.request, "urlopen", muet)
    with pytest.raises(ConnectionError, match="ne dit pas son contexte"):
        mesure.contexte_annonce("http://127.0.0.1:30100/version")


def test_les_deux_qwen_locaux_attendent_chacun_leur_contexte() -> None:
    contextes = {
        i: lire_candidat(i).lancement.contexte_serveur for i in ("agent_seul_qwen_local", "agent_seul_qwen_local_100k")
    }
    assert contextes == {"agent_seul_qwen_local": 40960, "agent_seul_qwen_local_100k": 102400}
