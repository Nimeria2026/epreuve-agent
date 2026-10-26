"""Relecture des désaccords : une décision par désaccord, gardée à part, reprise où on s'était arrêté."""

from __future__ import annotations

import json
from pathlib import Path

from ease.etalon import empreinte
from ease.relecture import desaccords, lire_decisions, relire


def _etalonnage(tmp_path: Path) -> Path:
    def comparaison(cle: str, humain: bool, vrai: bool | None) -> dict[str, object]:
        texte = {"cle": cle, "tache": "t04_date_prochain_entretien", "source": "qwen", "origine": "x", "texte": "Mars."}
        verdict = {"vrai": vrai, "preuve": "Mars.", "entree": 1, "entree_en_cache": 0, "sortie": 1, "cout_dollars": 0}
        return {"texte": texte, "affirmation": "Le courriel donne mars 2027.", "humain": humain, "verdict": verdict}

    chemin = tmp_path / "etalonnage_2026-10-06_120000_alexandre.json"
    lignes = [comparaison("a", True, True), comparaison("b", True, False), comparaison("c", False, None)]
    chemin.write_text(json.dumps(lignes), encoding="utf-8")
    return chemin


def test_seuls_les_desaccords_sont_relus_et_chaque_decision_est_gardee(tmp_path: Path) -> None:
    etalonnage = _etalonnage(tmp_path)
    assert [d["texte"]["cle"] for d in desaccords(etalonnage)] == ["b", "c"]
    affiche: list[str] = []
    reponses = iter(["x", "2", "q"])
    assert relire(etalonnage, tmp_path, "alexandre", lambda _: next(reponses), affiche.append) == 1
    assert "Ta réponse : vrai. Le juge : faux." in "\n".join(affiche)
    reponses = iter(["1"])
    assert relire(etalonnage, tmp_path, "alexandre", lambda _: next(reponses), affiche.append) == 1
    decisions = lire_decisions(tmp_path, "alexandre")
    assert [(d["texte"], d["decision"]) for d in decisions] == [("b", "juge_errone"), ("c", "etiquette_fausse")]
    assert decisions[0]["critere"] == empreinte("Le courriel donne mars 2027.")
    assert "2 désaccord(s) tranché(s) sur 2" in affiche[-1]


def test_un_etalonnage_avec_contexte_garde_la_cle_du_critere_et_montre_le_contexte(tmp_path: Path) -> None:
    texte = {"cle": "d", "tache": "t04_date_prochain_entretien", "source": "ecrit", "origine": "x", "texte": "Mars."}
    verdict = {"vrai": True, "preuve": "", "entree": 1, "entree_en_cache": 0, "sortie": 1, "cout_dollars": 0}
    ligne = {
        "texte": texte,
        "affirmation": "Le courriel donne mars 2027.",
        "contexte": "Demande du 2 novembre 2026.",
        "critere": "cle-avec-contexte",
        "humain": False,
        "verdict": verdict,
    }
    chemin = tmp_path / "etalonnage_2026-10-07_120000_alexandre.json"
    chemin.write_text(json.dumps([ligne]), encoding="utf-8")
    affiche: list[str] = []
    assert relire(chemin, tmp_path, "alexandre", lambda _: "3", affiche.append) == 1
    assert "Demande du 2 novembre 2026." in "\n".join(affiche)
    assert lire_decisions(tmp_path, "alexandre")[0]["critere"] == "cle-avec-contexte"


def test_le_bilan_ne_compte_que_les_desaccords_de_cet_etalonnage(tmp_path: Path) -> None:
    ancienne = {"texte": "z", "critere": "k", "humain": "vrai", "juge": "faux", "decision": "juge_errone", "le": "x"}
    (tmp_path / "relecture_alexandre.json").write_text(json.dumps([ancienne]), encoding="utf-8")
    affiche: list[str] = []
    reponses = iter(["1", "2"])
    assert relire(_etalonnage(tmp_path), tmp_path, "alexandre", lambda _: next(reponses), affiche.append) == 2
    assert affiche[-1].strip().startswith("2 désaccord(s) tranché(s) sur 2 :")
    assert len(lire_decisions(tmp_path, "alexandre")) == 3  # l'ancienne décision reste au fichier
