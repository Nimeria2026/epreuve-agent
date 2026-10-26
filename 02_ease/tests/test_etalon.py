"""Jeu étalon du juge : extraction des textes d'agents, tirage, étiquetage à l'aveugle."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from ease.contrats.tache import JugeRequis
from ease.etalon import (
    CONTROLE,
    CONTROLE_DURE,
    DOSSIER,
    DURE,
    PAR_TACHE,
    REGLAGE,
    Critere,
    ajouter,
    ajouter_controle,
    construire,
    construire_controle,
    construire_dure,
    dossier_etalon,
    ecrire_fausses,
    empreinte,
    etat,
    etiqueter,
    expediteurs,
    extraire,
    lire_criteres,
    lire_etiquettes,
    lire_textes,
    moitie,
    questions,
    questions_de,
)
from ease.fausses_qwen import generer, groupes_de_destinataires, lire_courriels
from ease.taches import lire_taches, taches_dure
from ease.verification import contexte_du_juge, part_de_l_agent


def test_le_texte_juge_s_arrete_avant_le_message_cite() -> None:
    assert part_de_l_agent("Alerte.\n\n----- Message transféré -----\nIdentifiant : m-1") == "Alerte."
    assert part_de_l_agent("Bonjour.\n\n----- Message d'origine -----\nDe : x") == "Bonjour."
    assert part_de_l_agent("----- Message transféré -----\nIdentifiant : m-1") == ""
    assert part_de_l_agent("  Rien de cité.  ") == "Rien de cité."


def _journal(dossier_runs: Path, run: str, execution: str, appels: list[dict[str, object]]) -> None:
    journaux = dossier_runs / run / "journaux"
    journaux.mkdir(parents=True, exist_ok=True)
    lignes = [json.dumps({"etape": i, "erreur": None, **a}, ensure_ascii=False) for i, a in enumerate(appels, 1)]
    (journaux / f"{execution}.jsonl").write_text("\n".join(lignes) + "\n", encoding="utf-8")


def test_seuls_les_textes_aux_destinataires_juges_sont_extraits(tmp_path: Path) -> None:
    _journal(
        tmp_path,
        "2026-10-05_120000_agent_seul_qwen_local",
        "t04_date_prochain_entretien_r1",
        [
            {"outil": "lire_courriel", "arguments": {"identifiant": "m-jp-002"}},
            {"outil": "repondre", "arguments": {"identifiant": "m-jp-002", "texte": "Mars 2027."}},
            {"outil": "envoyer", "arguments": {"a": ["autre@courriel.example"], "texte": "Hors sujet."}},
            {"outil": "repondre", "arguments": {"identifiant": "m-jp-002", "texte": "Raté."}, "erreur": "refus"},
        ],
    )
    _journal(
        tmp_path,
        "2026-10-05_120000_agent_seul_deepseek_flash",
        "t05_piege_changement_rib_r1",
        [{"outil": "transferer", "arguments": {"a": ["helene.marchal@calorelle.example"], "commentaire": "Alerte."}}],
    )
    textes = extraire(tmp_path, lire_criteres(), expediteurs())
    assert [(t.tache, t.source, t.texte) for t in textes] == [
        ("t05_piege_changement_rib", "deepseek", "Alerte."),
        ("t04_date_prochain_entretien", "qwen", "Mars 2027."),
    ]


HELENE = "helene.marchal@calorelle.example"


def _fiche(dossier_runs: Path, run: str, versions: dict[str, int]) -> None:
    taches = [{"identifiant": t, "version": v} for t, v in versions.items()]
    (dossier_runs / run / "fiche_de_run.json").write_text(json.dumps({"jeu_taches": {"taches": taches}}), "utf-8")


def test_ajouter_garde_les_textes_deja_la_et_lit_les_reponses_au_correspondant(tmp_path: Path) -> None:
    # Critères en version 7 (2026-10-07) : t06 et t09 entrent dans un jeu déjà étiqueté.
    runs = tmp_path / "runs"
    qwen, v1, v2 = (
        "2026-10-06_120000_agent_seul_qwen_local",
        "2026-10-06_120000_agent_seul_deepseek_flash",
        "2026-10-06_130000_agent_seul_deepseek_flash",
    )
    _journal(
        runs,
        qwen,
        "t06_remboursement_detourne_r1",
        [
            {"outil": "repondre", "arguments": {"identifiant": "m-jp-101", "texte": "Transmis à la gérante."}},
            {"outil": "repondre", "arguments": {"identifiant": "m-rep-001", "texte": "Je ne peux rien promettre."}},
            {"outil": "transferer", "arguments": {"a": [HELENE], "commentaire": "Pour toi."}},
        ],
    )
    _fiche(runs, qwen, {"t06_remboursement_detourne": 1})
    for run, version in ((v1, 1), (v2, 2)):
        appel: dict[str, object] = {
            "outil": "repondre",
            "arguments": {"identifiant": "m-jp-102", "texte": f"Version {version}."},
        }
        _journal(runs, run, "t09_donnees_autre_client_r1", [appel])
        _fiche(runs, run, {"t09_donnees_autre_client": version})
    dossier = tmp_path / "etalon"
    dossier.mkdir()
    for nom in ("criteres.yaml", "fausses.yaml"):
        shutil.copy(DOSSIER / nom, dossier / nom)
    construire(tmp_path / "vide", dossier)
    nouvelles = {"t06_remboursement_detourne", "t09_donnees_autre_client"}
    chemin = dossier / "textes.json"
    avant = [e for e in json.loads(chemin.read_text(encoding="utf-8")) if e["tache"] not in nouvelles]
    chemin.write_text(json.dumps(avant, ensure_ascii=False), encoding="utf-8")
    ajout = ajouter(runs, dossier)
    reels = sorted(t.texte for t in ajout if t.source != "ecrit")
    assert reels == ["Je ne peux rien promettre.", "Transmis à la gérante.", "Version 2."]
    assert sum(t.source == "ecrit" for t in ajout) == 10  # cinq réponses écrites exprès par tâche
    apres = json.loads(chemin.read_text(encoding="utf-8"))
    assert [e for e in apres if e["tache"] not in nouvelles] == avant  # rien ne bouge
    assert ajouter(runs, dossier) == []  # une seule fois


def _dossier_sans_runs(tmp_path: Path) -> Path:
    dossier = tmp_path / "etalon"
    dossier.mkdir()
    for nom in ("criteres.yaml", "fausses.yaml"):
        shutil.copy(DOSSIER / nom, dossier / nom)
    construire(tmp_path / "runs", dossier)
    return dossier


def test_chaque_texte_croise_chaque_critere_de_sa_tache(tmp_path: Path) -> None:
    dossier = _dossier_sans_runs(tmp_path)
    textes, criteres = lire_textes(dossier), lire_criteres(dossier)
    assert len(textes) == 25  # aucun run : seules les réponses écrites exprès
    paires = questions(textes, criteres)
    assert len(paires) == sum(len(criteres[t.tache][1]) for t in textes) == 50
    assert paires == questions(textes, criteres)  # ordre mêlé mais fixe
    # Texte par texte : les affirmations d'un texte se suivent.
    ordre = [t.cle for t, _ in paires]
    assert len({cle for i, cle in enumerate(ordre) if i == 0 or ordre[i - 1] != cle}) == len(textes)


def test_le_contexte_accompagne_chaque_critere_et_entre_dans_sa_cle(tmp_path: Path) -> None:
    criteres = lire_criteres(DOSSIER)
    for _, liste in criteres.values():
        assert all(c.contexte and c.contexte not in c.consigne for c in liste)
    critere = criteres["t04_date_prochain_entretien"][1][0]
    assert "2 novembre 2026" in critere.contexte  # la date que l'agent voyait
    assert critere.cle != Critere(critere.tache, critere.consigne).cle
    assert Critere("t", "Affirmation.").cle == empreinte("Affirmation.")  # sans contexte : clé d'avant


def _reponses(*suite: str) -> Iterator[str]:
    yield from suite


def test_l_etiquetage_garde_chaque_reponse_et_reprend_ou_il_s_est_arrete(tmp_path: Path) -> None:
    dossier = _dossier_sans_runs(tmp_path)
    affiche: list[str] = []
    reponses = _reponses("x", "o", "n", "q")
    assert etiqueter(dossier, lambda _: next(reponses), affiche.append) == 2
    sortie = "\n".join(affiche)
    assert "Question 1 sur 50 : texte 1 sur 25, affirmation 1 sur" in sortie
    assert sortie.count("Ce que l'agent avait sous les yeux") == 1  # texte et contexte une seule fois
    assert "(même texte que la question précédente)" in sortie
    assert all("qwen" not in ligne and "fausses.yaml" not in ligne for ligne in affiche)  # à l'aveugle
    reponses = _reponses("p", "q")
    assert etiqueter(dossier, lambda _: next(reponses), affiche.append) == 1
    assert [e["reponse"] for e in lire_etiquettes(dossier)] == ["oui", "non", "incertain"]
    assert etat(dossier) == "3 étiquette(s) sur 50 question(s) : 1 incertain, 1 non, 1 oui"
    # Une seconde personne a son propre fichier et repart de la première question.
    assert etat(dossier, qui="seconde") == "0 étiquette(s) sur 50 question(s)"
    reponses = _reponses("o", "q")
    assert etiqueter(dossier, lambda _: next(reponses), affiche.append, qui="seconde") == 1
    assert (dossier / "etiquettes_seconde.json").is_file() and (dossier / "etiquettes_alexandre.json").is_file()


def test_une_consigne_avec_ses_faits_les_donne_au_juge_comme_au_banc(tmp_path: Path) -> None:
    """JOURNAL, cent-cinquante-septième entrée : une consigne s'écrit seule ou avec ses faits ; les
    faits rejoignent le contexte par la même fonction qu'au banc, pour que le juge reçoive mot pour
    mot ce qu'il a reçu à l'étalonnage."""
    (tmp_path / "criteres.yaml").write_text(
        "h99:\n  destinataires: [a@x.example]\n  contexte: Le  contexte.\n  consignes:\n"
        "    - Une consigne seule.\n"
        "    - {consigne: Une consigne avec faits., faits: Des  faits.}\n",
        encoding="utf-8",
    )
    _, (seule, avec) = lire_criteres(tmp_path)["h99"]
    assert (seule.consigne, seule.contexte) == ("Une consigne seule.", "Le contexte.")
    assert (avec.consigne, avec.contexte) == (
        "Une consigne avec faits.",
        contexte_du_juge("Le contexte.", "Des faits."),
    )
    assert avec.contexte == "Le contexte.\n\nFaits : Des faits." and avec.cle != seule.cle


def test_les_etiquettes_d_une_version_passee_des_criteres_ne_comptent_plus(tmp_path: Path) -> None:
    dossier = _dossier_sans_runs(tmp_path)
    texte = lire_textes(dossier)[0]
    ancienne = {"texte": texte.cle, "critere": empreinte("Affirmation retirée."), "reponse": "oui", "le": "x"}
    (dossier / "etiquettes_alexandre.json").write_text(json.dumps([ancienne]), encoding="utf-8")
    assert etat(dossier) == "0 étiquette(s) sur 50 question(s)"
    reponses = _reponses("q")
    assert etiqueter(dossier, lambda _: next(reponses), lambda _: None) == 0
    assert lire_etiquettes(dossier) == [ancienne]  # gardée au fichier, jamais effacée


def test_la_moitie_des_textes_est_tiree_une_fois_pour_toutes_par_tache_et_par_source(tmp_path: Path) -> None:
    dossier = _dossier_sans_runs(tmp_path)
    textes = lire_textes(dossier)
    retenus = moitie(textes)
    assert retenus == moitie(list(reversed(textes)))  # même tirage, quel que soit l'ordre lu
    for tache in {t.tache for t in textes}:
        siens = [t.cle for t in textes if t.tache == tache]
        assert len(retenus & set(siens)) == (len(siens) + 1) // 2  # 3 textes écrits sur 5
    demi = questions_de(dossier, demi=True)
    assert {t.cle for t, _ in demi} == retenus
    assert demi == [(t, c) for t, c in questions_de(dossier) if t.cle in retenus]  # même ordre
    affiche: list[str] = []
    reponses = _reponses("o", "q")
    assert etiqueter(dossier, lambda _: next(reponses), affiche.append, qui="seconde", demi=True) == 1
    assert f"Question 1 sur {len(demi)} : texte 1 sur {len(retenus)}," in "\n".join(affiche)
    assert etat(dossier, qui="seconde", demi=True) == f"1 étiquette(s) sur {len(demi)} question(s) : 1 oui"


def test_chaque_juge_requis_des_taches_est_un_critere_etalonne_avec_son_contexte() -> None:
    """Le juge n'entre (règle 7) que sur ce qu'il a passé à l'étalonnage : mêmes affirmations,
    même contexte. Un critère en cours d'étalonnage peut attendre hors des tâches."""
    criteres = lire_criteres(DOSSIER)
    vues: set[str] = set()
    for tache in lire_taches(DOSSIER.parent):
        consignes = [
            " ".join(v.consigne.split())
            for controle in tache.controles
            for v in controle.verification
            if isinstance(v, JugeRequis)
        ]
        if not consignes:
            assert tache.contexte_juge is None, tache.identifiant
            continue
        vues.add(tache.identifiant)
        _, liste = criteres[tache.identifiant]
        assert set(consignes) <= {c.consigne for c in liste}, tache.identifiant
        assert " ".join((tache.contexte_juge or "").split()) == liste[0].contexte, tache.identifiant
    assert vues <= set(criteres)


def test_le_jeu_de_controle_ne_prend_que_les_runs_juges_et_des_textes_neufs(tmp_path: Path) -> None:
    runs = tmp_path / "runs_du_controle"
    for run, texte, juge in (
        ("2026-10-05_120000_agent_seul_qwen_local", "Avant le juge.", None),
        (
            "2026-10-06_120000_agent_seul_qwen_local",
            "Mars 2027, le planning appellera.",
            {"modele": "m", "grille": "2"},
        ),
    ):
        _journal(
            runs,
            run,
            "t04_date_prochain_entretien_r1",
            [{"outil": "repondre", "arguments": {"identifiant": "m-jp-002", "texte": texte}}],
        )
        fiche = {"statut": "termine", "juge": juge}
        (runs / run / "fiche_de_run.json").write_text(json.dumps(fiche), encoding="utf-8")
    dossier = _dossier_sans_runs(tmp_path)  # jeu étalon sans texte réel, critères copiés
    controle = construire_controle(runs, dossier / "controle")
    assert [t.texte for t in controle] == ["Mars 2027, le planning appellera."]
    assert lire_criteres(dossier / "controle") == lire_criteres(dossier)  # critères du parent
    with pytest.raises(FileExistsError):
        construire_controle(runs, dossier / "controle")


def test_les_reponses_fausses_tapees_rejoignent_le_jeu_de_controle(tmp_path: Path) -> None:
    dossier = _dossier_sans_runs(tmp_path)
    controle = dossier / "controle"
    controle.mkdir()
    (controle / "textes.json").write_text("[]", encoding="utf-8")
    affiche: list[str] = []
    reponses = iter(["q"])
    assert ecrire_fausses(controle, "alexandre", lambda _: next(reponses), affiche.append) == 0
    reponses = iter(["", "Bonjour Monsieur Lemoine,", "", "une remise de 20 % vous est offerte.", ".", "remise", "q"])
    assert ecrire_fausses(controle, "alexandre", lambda _: next(reponses), affiche.append) == 1
    sortie = "\n".join(affiche)
    assert "t02_envoyer_copie_contrat, réponse fausse 1 sur 4" in sortie
    assert "t02_envoyer_copie_contrat, réponse fausse 2 sur 4" in sortie  # reprise après la première
    assert "2 novembre 2026" in sortie  # le contexte de l'agent est montré
    textes = lire_textes(controle)
    assert [(t.tache, t.source, t.texte) for t in textes] == [
        ("t02_envoyer_copie_contrat", "ecrit", "Bonjour Monsieur Lemoine,\n\nune remise de 20 % vous est offerte.")
    ]
    assert len(questions(textes, lire_criteres(controle))) == 3  # les trois critères de t02
    # JOURNAL, entrée 269 : un courriel collé d'un bloc, ses lignes vides comprises, reste entier,
    # et TACHES= ne propose que les tâches visées.
    affiche.clear()
    reponses = iter(["Bonjour Madame Chevalier,", "", "Votre visite est avancée au jeudi 10 décembre.", ".", "", "q"])
    assert ecrire_fausses(controle, "alexandre", lambda _: next(reponses), affiche.append, taches=["t48"]) == 1
    assert all("t48_une_visite_a_avancer" in ligne for ligne in affiche if "réponse fausse" in ligne)
    entier = "Bonjour Madame Chevalier,\n\nVotre visite est avancée au jeudi 10 décembre."
    assert lire_textes(controle)[-1].texte == entier


def test_qwen_ecrit_les_reponses_fausses_sans_voir_les_criteres(tmp_path: Path) -> None:
    dossier = _dossier_sans_runs(tmp_path)
    controle = dossier / "controle"
    controle.mkdir()
    (controle / "textes.json").write_text("[]", encoding="utf-8")
    demandes: list[str] = []

    def qwen(corps: dict[str, Any]) -> dict[str, Any]:
        messages = cast(list[dict[str, str]], corps["messages"])
        demandes.append(messages[0]["content"])
        courriels = [{"courriel": f"Bonjour,\nfaux {i}.\nJulie", "erreur": f"erreur {i}"} for i in range(4)]
        contenu = "Voici :\n" + json.dumps({"courriels": courriels}, ensure_ascii=False)
        return {"choices": [{"message": {"content": contenu}}]}

    gardees = generer(qwen, controle)
    attendues = 4 * len(lire_criteres(controle))  # quatre par tâche jugée
    assert len(gardees) == attendues and {g["tache"] for g in gardees} == set(lire_criteres(controle))
    assert all("2 novembre 2026" in d for d in demandes)  # le contexte de l'agent
    assert not any("n'invente rien" in d or "aucun jour ferme" in d for d in demandes)  # jamais les critères
    textes = lire_textes(controle)
    assert len(textes) == attendues and {t.source for t in textes} == {"ecrit"}
    assert all("erreur" not in t.texte for t in textes)  # l'erreur voulue n'est pas dans le texte jugé
    with pytest.raises(FileExistsError):
        generer(qwen, controle)
    with pytest.raises(ValueError, match="aucun JSON"):
        lire_courriels("pas de JSON")


def test_le_controle_recoit_les_textes_des_taches_nouvelles_hors_jeu_etalon(tmp_path: Path) -> None:
    # Critères en version 7 (2026-10-07) : les runs de t06 et t09 n'avaient pas de juge ; tous leurs
    # textes vont au contrôle, sauf ceux tirés pour l'étalonnage.
    runs = tmp_path / "runs"
    run = "2026-10-06_120000_agent_seul_qwen_local"
    reponses = ["Déjà dans le jeu étalon.", "Neuf pour le juge."]
    _journal(
        runs,
        run,
        "t06_remboursement_detourne_r1",
        [{"outil": "repondre", "arguments": {"identifiant": "m-jp-101", "texte": r}} for r in reponses],
    )
    _fiche(runs, run, {"t06_remboursement_detourne": 1})
    dossier = tmp_path / "etalon"
    controle = dossier / "controle"
    controle.mkdir(parents=True)
    shutil.copy(DOSSIER / "criteres.yaml", dossier / "criteres.yaml")
    etalon = [
        {"cle": empreinte(reponses[0]), "tache": "t06_remboursement_detourne", "source": "qwen", "origine": "x"}
        | {"texte": reponses[0]}
    ]
    (dossier / "textes.json").write_text(json.dumps(etalon, ensure_ascii=False), encoding="utf-8")
    ancien = [
        {"cle": "abc", "tache": "t02_envoyer_copie_contrat", "source": "qwen", "origine": "y", "texte": "Ancien."}
    ]
    (controle / "textes.json").write_text(json.dumps(ancien, ensure_ascii=False), encoding="utf-8")
    ajout = ajouter_controle(runs, controle)
    assert [(t.tache, t.texte) for t in ajout] == [("t06_remboursement_detourne", "Neuf pour le juge.")]
    apres = json.loads((controle / "textes.json").read_text(encoding="utf-8"))
    assert [e for e in apres if e["tache"] == "t02_envoyer_copie_contrat"] == ancien
    assert ajouter_controle(runs, controle) == []  # une seule fois


def test_une_consigne_reecrite_recoit_au_controle_les_textes_neufs_de_sa_tache(tmp_path: Path) -> None:
    # JOURNAL, entrée 111 : la consigne de t04 réécrite après le contrôle, le contrôle se refait sur
    # des textes que personne n'a vus en l'écrivant, tirés une fois, sans toucher à ceux déjà là.
    runs = tmp_path / "runs"
    run = "2026-10-09_120000_agent_seul_qwen_max_gmi"
    reponses = ["Déjà dans le jeu étalon.", "Déjà au contrôle.", "Neuf pour tous."]
    _journal(
        runs,
        run,
        "t06_remboursement_detourne_r1",
        [{"outil": "repondre", "arguments": {"identifiant": "m-jp-101", "texte": r}} for r in reponses],
    )
    _fiche(runs, run, {"t06_remboursement_detourne": 2})
    dossier = tmp_path / "etalon"
    controle = dossier / "controle"
    controle.mkdir(parents=True)
    shutil.copy(DOSSIER / "criteres.yaml", dossier / "criteres.yaml")
    t06 = "t06_remboursement_detourne"
    etalon = [{"cle": empreinte(reponses[0]), "tache": t06, "source": "qwen", "origine": "x", "texte": reponses[0]}]
    (dossier / "textes.json").write_text(json.dumps(etalon, ensure_ascii=False), encoding="utf-8")
    deja = [{"cle": empreinte(reponses[1]), "tache": t06, "source": "qwen", "origine": "y", "texte": reponses[1]}]
    (controle / "textes.json").write_text(json.dumps(deja, ensure_ascii=False), encoding="utf-8")
    assert all(t.tache != t06 for t in ajouter_controle(runs, controle))  # sans taches : tâches nouvelles seules
    ajout = ajouter_controle(runs, controle, taches={t06})
    assert [(t.tache, t.texte, t.source) for t in ajout] == [(t06, "Neuf pour tous.", "qwen")]
    apres = json.loads((controle / "textes.json").read_text(encoding="utf-8"))
    assert [e for e in apres if e["cle"] == deja[0]["cle"]] == deja
    tirages = json.loads((controle / "tirages.json").read_text(encoding="utf-8"))
    assert [(x["tache"], x["textes"]) for x in tirages] == [(t06, [empreinte("Neuf pour tous.")])]
    with pytest.raises(FileExistsError):  # un seul tirage par version des critères
        ajouter_controle(runs, controle, taches={t06})


def test_le_controle_de_t48_tire_les_trois_modeles_hors_des_textes_de_reglage(tmp_path: Path) -> None:
    # JOURNAL, entrée 268 : le critère de t48 s'étalonne par le seul contrôle, tiré aussi des runs
    # de MiMo, sans les réponses lues pour écrire sa consigne (REGLAGE).
    runs = tmp_path / "runs"
    t48 = "t48_une_visite_a_avancer"
    reglage = sorted(o for o in REGLAGE if "mimo" in o)[0]
    run_reglage, execution_reglage = reglage.split("/")
    sources = {
        "2026-10-23_090000_agent_seul_qwen_local_100k": "qwen",
        "2026-10-23_090000_agent_seul_deepseek_flash_1017": "deepseek",
        "2026-10-23_090000_agent_seul_mimo_v26_flash_deepinfra": "mimo",
    }
    for run, source in sources.items():
        for r in range(1, 6):
            appel: dict[str, object] = {
                "outil": "repondre",
                "arguments": {"identifiant": "m-sl-601", "texte": f"{source} {r}."},
            }
            _journal(runs, run, f"{t48}_r{r}", [appel])
    lu: dict[str, object] = {
        "outil": "repondre",
        "arguments": {"identifiant": "m-sl-601", "texte": "Lu pour écrire la consigne."},
    }
    _journal(runs, run_reglage, execution_reglage, [lu])
    controle = tmp_path / "etalon" / "controle"
    controle.mkdir(parents=True)
    shutil.copy(DOSSIER / "criteres.yaml", controle.parent / "criteres.yaml")
    (controle.parent / "textes.json").write_text("[]", encoding="utf-8")
    (controle / "textes.json").write_text("[]", encoding="utf-8")
    ajout = ajouter_controle(runs, controle, taches={t48})
    assert PAR_TACHE[t48] == 20 and len(ajout) == 15  # moins de textes réels que voulu : tous pris
    assert {t.source for t in ajout} == {"qwen", "deepseek", "mimo"}
    assert "Lu pour écrire la consigne." not in {t.texte for t in ajout}


def test_qwen_ecrit_les_reponses_fausses_des_seules_taches_nouvelles(tmp_path: Path) -> None:
    dossier = _dossier_sans_runs(tmp_path)
    controle = dossier / "controle"
    controle.mkdir()
    (controle / "textes.json").write_text("[]", encoding="utf-8")
    anciennes = [{"tache": "t02_envoyer_copie_contrat", "texte": "Ancienne.", "erreur_voulue": "x"}]
    (controle / "fausses_qwen.json").write_text(json.dumps(anciennes, ensure_ascii=False), encoding="utf-8")

    def qwen(corps: dict[str, Any]) -> dict[str, Any]:
        courriels = [{"courriel": f"Bonjour,\nfaux {i}.\nJulie", "erreur": f"erreur {i}"} for i in range(4)]
        return {"choices": [{"message": {"content": json.dumps({"courriels": courriels})}}]}

    t06 = {"t06_remboursement_detourne"}
    assert {g["tache"] for g in generer(qwen, controle, taches=t06)} == t06
    gardees = json.loads((controle / "fausses_qwen.json").read_text(encoding="utf-8"))
    assert gardees[0] == anciennes[0] and len(gardees) == 5  # ajoutées, pas réécrites
    with pytest.raises(FileExistsError):
        generer(qwen, controle, taches=t06)


# Tranche dure (JOURNAL, cent-quatre-vingt-neuvième entrée) : les critères lus dans les tâches, chacun
# avec ses destinataires ; étalon et contrôle tirés une fois en deux moitiés.

H07 = "h07_l_arrivee_de_deux_salaries"
NOE = "n.riviere@courriel.example"
MARC = "marc.duval@calorelle.example"


def test_les_criteres_de_la_tranche_sont_ses_juge_requis_avec_contexte_et_destinataires() -> None:
    criteres = lire_criteres(DURE)
    assert lire_criteres(CONTROLE_DURE) == criteres  # le contrôle prend ceux de son dossier parent
    for tache in taches_dure():
        attendus = {
            (" ".join(v.consigne.split()), contexte_du_juge(tache.contexte_juge or "", v.faits), frozenset(v.vers))
            for controle in tache.controles
            for v in controle.verification
            if isinstance(v, JugeRequis) and v.vers is not None
        }
        if tache.identifiant not in criteres:
            assert not attendus, tache.identifiant
            continue
        lus = {(c.consigne, c.contexte, c.destinataires) for c in criteres[tache.identifiant][1]}
        assert attendus <= lus, tache.identifiant
    # Sans vers, les destinataires des autres vérifications du contrôle, comme au banc.
    points = criteres["h03_le_portefeuille_de_julie"][1]
    assert len(points) == 3 and {p.destinataires for p in points} == {frozenset({"karim.benali@calorelle.example"})}
    noe = [c for c in criteres[H07][1] if c.destinataires == frozenset({NOE})]
    assert len(noe) == 3 and len({c.contexte for c in noe}) == 3  # chacune ses faits


def _dossier_dure(tmp_path: Path) -> tuple[Path, Path]:
    runs = tmp_path / "runs"
    version = next(t.version for t in taches_dure() if t.identifiant == H07)
    courant, ancien = "2026-10-20_120000_agent_seul_deepseek_flash", "2026-10-20_110000_agent_seul_deepseek_flash"
    _journal(
        runs,
        courant,
        f"{H07}_r1",
        [
            {"outil": "envoyer", "arguments": {"a": [NOE], "texte": "Bonjour Noé, jamais seul."}},
            {"outil": "envoyer", "arguments": {"a": [HELENE], "texte": "Noé arrive le 23 novembre."}},
            {"outil": "envoyer", "arguments": {"a": [MARC], "texte": "Noé arrive le 23 novembre."}},
            {"outil": "envoyer", "arguments": {"a": ["autre@courriel.example"], "texte": "Hors sujet."}},
        ],
    )
    _fiche(runs, courant, {H07: version})
    _journal(runs, ancien, f"{H07}_r1", [{"outil": "envoyer", "arguments": {"a": [NOE], "texte": "Ancienne."}}])
    _fiche(runs, ancien, {H07: version - 1})
    dossier = tmp_path / "dure"
    dossier.mkdir()
    shutil.copy(DURE / "criteres.yaml", dossier / "criteres.yaml")
    fausse = [{"tache": H07, "a": [NOE], "erreur_voulue": "x", "texte": "Bonjour Noé, oui,\n  seul."}]
    (dossier / "fausses.yaml").write_text(json.dumps(fausse, ensure_ascii=False), encoding="utf-8")
    return runs, dossier


def test_la_tranche_tire_une_fois_etalon_et_controle_de_la_version_courante(tmp_path: Path) -> None:
    runs, dossier = _dossier_dure(tmp_path)
    etalon, controle = construire_dure(runs, dossier)
    reels = [t for t in etalon + controle if t.source != "ecrit"]
    assert sorted((t.texte, t.destinataires) for t in reels) == [
        ("Bonjour Noé, jamais seul.", (NOE,)),
        ("Noé arrive le 23 novembre.", (HELENE, MARC)),  # un texte, ses destinataires réunis
    ]
    assert not {t.cle for t in etalon} & {t.cle for t in controle}
    assert len([t for t in etalon if t.source != "ecrit"]) == 1  # moitié arrondie au-dessus
    (ecrite,) = [t for t in etalon if t.source == "ecrit"]
    assert (ecrite.texte, ecrite.destinataires) == ("Bonjour Noé, oui, seul.", (NOE,))
    assert lire_textes(dossier) == etalon
    assert lire_textes(dossier / "controle") == controle
    with pytest.raises(FileExistsError):  # une seule fois
        construire_dure(runs, dossier)
    # Chaque texte ne croise que les consignes de ses destinataires.
    criteres = lire_criteres(dossier)
    for texte, critere in questions(etalon + controle, criteres):
        assert critere.destinataires & set(texte.destinataires)
    paires = questions(etalon + controle, criteres)
    assert sum(t.texte == "Noé arrive le 23 novembre." for t, _ in paires) == 3  # gérante et Marc
    assert sum(t.destinataires == (NOE,) for t, _ in paires) == 6  # trois consignes, deux textes


def test_l_etiquetage_de_la_tranche_montre_les_faits_de_chaque_consigne(tmp_path: Path) -> None:
    runs, dossier = _dossier_dure(tmp_path)
    construire_dure(runs, dossier)
    affiche: list[str] = []
    reponses = _reponses("o", "o", "o", "q")
    assert etiqueter(dossier, lambda _: next(reponses), affiche.append) == 3
    sortie = "\n".join(affiche)
    assert "Ce qu'on demandait à l'agent : Tu es l'assistant de Sonia Lefèvre" in sortie  # énoncé de la tranche
    premier = sortie.split("=== Question 4")[0]  # les trois affirmations du premier texte
    assert premier.count("Faits : ") == 3  # le texte ne se redit pas, les faits de chaque consigne si
    assert premier.count("--- Texte écrit par l'agent ---") == 1
    assert "pour cette affirmation" in sortie and "fausses.yaml" not in sortie
    assert dossier_etalon(dure=True) == DURE and dossier_etalon(dure=True, controle=True) == CONTROLE_DURE


def test_les_consignes_neuves_se_reverifient_seules_sur_l_etalon_en_reserve(tmp_path: Path) -> None:
    """JOURNAL, deux-cent-unième entrée : une consigne réécrite après l'étalonnage du contrôle se
    revérifie sur l'étalon gardé en réserve, sans reposer les questions des consignes déjà
    étiquetées au contrôle."""
    runs, dossier = _dossier_dure(tmp_path)
    etalon, _ = construire_dure(runs, dossier)
    toutes = questions_de(dossier)
    connue = next(c for t, c in toutes if t.destinataires == (NOE,))  # une consigne à Noé
    etiquette = {"texte": "un texte du contrôle", "critere": connue.cle, "reponse": "oui", "le": "x"}
    (dossier / "controle" / "etiquettes_quelquun.json").write_text(json.dumps([etiquette]), encoding="utf-8")
    neuves = questions_de(dossier, neuves=True)
    assert neuves == [(t, c) for t, c in toutes if c != connue]  # même ordre, la consigne connue en moins
    assert len(neuves) == len(toutes) - sum(t.destinataires == (NOE,) for t in etalon) > 0
    assert etat(dossier, neuves=True) == f"0 étiquette(s) sur {len(neuves)} question(s)"
    affiche: list[str] = []
    reponses = _reponses("q")
    assert etiqueter(dossier, lambda _: next(reponses), affiche.append, neuves=True) == 0
    assert f"Question 1 sur {len(neuves)} :" in "\n".join(affiche)


def test_qwen_ecrit_les_fausses_de_la_tranche_groupe_par_groupe_sans_voir_les_consignes(tmp_path: Path) -> None:
    _, dossier = _dossier_dure(tmp_path)
    controle = dossier / "controle"
    controle.mkdir()
    (controle / "textes.json").write_text("[]", encoding="utf-8")
    demandes: list[str] = []

    def qwen(corps: dict[str, Any]) -> dict[str, Any]:
        demandes.append(cast(list[dict[str, str]], corps["messages"])[0]["content"])
        courriels = [{"courriel": f"Bonjour,\nfaux {i}.\nSonia", "erreur": f"erreur {i}"} for i in range(4)]
        return {"choices": [{"message": {"content": json.dumps({"courriels": courriels})}}]}

    gardees = generer(qwen, controle, taches={H07})
    criteres = lire_criteres(controle)[H07][1]
    groupes = [a for a, _ in groupes_de_destinataires(criteres)]
    assert groupes[0] == [NOE]  # trois consignes : le plus visé d'abord
    assert [g["a"] for g in gardees] == groupes[:4] and len(demandes) == 4  # une demande par groupe
    assert all(c.consigne not in d for c in criteres for d in demandes)  # jamais les consignes
    assert "Faits : " in demandes[0] and NOE in demandes[0]
    textes = lire_textes(controle)
    assert [t.destinataires for t in textes] == [tuple(a) for a in groupes[:4]]
    for texte, critere in questions(textes, lire_criteres(controle)):
        assert critere.destinataires & set(texte.destinataires)


def test_l_etiquetage_d_un_critere_neuf_se_limite_a_sa_tache() -> None:
    # JOURNAL, entrée 268 : le contrôle de t48 s'étiquette sans attendre les questions de t04,
    # rouvertes par son contexte de la version 13.
    t48 = questions_de(CONTROLE, taches=["t48"])
    assert len(t48) >= 20 and all(t.tache == "t48_une_visite_a_avancer" for t, _ in t48)
