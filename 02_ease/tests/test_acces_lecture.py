"""L'accès en lecture seule (JOURNAL, entrée 94) : seuls les outils que leur service déclare en
lecture seule y passent, ses appels se comptent hors du budget de la tâche, dans un journal à
part ; le relais l'ouvre sur une seconde adresse pour le candidat qui le demande."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio
import pytest
from ease.chargement import racine_depot
from ease.contrats.fiche_de_run import ReglesGardien
from ease.etat_pme import Instantane
from ease.executeur import BudgetEtapesDepasse, DescriptionOutil, ErreurOutil, Outils
from ease.relais import Relais
from mcp import Client
from mcp.types import TextContent

SCHEMA: Mapping[str, Any] = {"type": "object", "properties": {}}


class EnvironnementEssai:
    """Trois outils : lire (lecture seule), envoyer (écrit), archiver (ne dit rien)."""

    version = "essai"

    def __init__(self) -> None:
        self.appels: list[str] = []

    def empreinte(self) -> str:
        return "essai"

    @property
    def regles_gardien(self) -> ReglesGardien | None:
        return None

    def empreinte_complement(self, tache: Any) -> str | None:
        return None

    def ouvrir(self, tache: Any) -> None: ...

    def fermer(self) -> None: ...

    def preambule(self) -> str | None:
        return None

    def outils(self) -> list[DescriptionOutil]:
        return [
            DescriptionOutil("lire", "Lit.", SCHEMA, True),
            DescriptionOutil("envoyer", "Envoie.", SCHEMA, False),
            DescriptionOutil("archiver", "Archive.", SCHEMA),
        ]

    def appeler(self, nom: str, arguments: Mapping[str, Any], lecture_seule: bool = False) -> Any:
        self.appels.append(f"{nom} (lecture seule)" if lecture_seule else nom)
        return f"{nom} fait"

    def etat(self) -> Instantane:
        return Instantane()


def _outils(tmp_path: Path, etapes_max: int = 2) -> tuple[Outils, EnvironnementEssai]:
    environnement = EnvironnementEssai()
    return Outils(environnement, etapes_max, tmp_path / "t99_r1.jsonl"), environnement


def test_les_lectures_se_comptent_a_part_et_ne_touchent_pas_au_budget(tmp_path: Path) -> None:
    outils, environnement = _outils(tmp_path)
    assert [o.nom for o in outils.lister_lectures()] == ["lire"]
    for _ in range(5):
        assert outils.lire_avec("lire", {}) == "lire fait"
    assert (outils.lectures, outils.etapes) == (5, 0)
    outils.appeler_avec("envoyer", {})
    outils.appeler_avec("lire", {})
    with pytest.raises(BudgetEtapesDepasse):
        outils.appeler_avec("lire", {})
    assert environnement.appels == ["lire (lecture seule)"] * 5 + ["envoyer", "lire"]
    lignes = [json.loads(ligne) for ligne in (tmp_path / "t99_r1_lectures.jsonl").read_text("utf-8").splitlines()]
    assert [ligne["lecture"] for ligne in lignes] == [1, 2, 3, 4, 5]
    assert len((tmp_path / "t99_r1.jsonl").read_text("utf-8").splitlines()) == 2


def test_un_outil_qui_ecrit_ou_ne_dit_rien_est_refuse_sans_partir(tmp_path: Path) -> None:
    outils, environnement = _outils(tmp_path)
    for nom in ("envoyer", "archiver"):
        with pytest.raises(ErreurOutil, match=f"outil hors de l'accès en lecture seule : {nom}"):
            outils.lire_avec(nom, {})
    assert environnement.appels == [] and outils.lectures == 0
    # Le refus laisse une trace au journal des lectures, sans numéro de lecture (relecture, B7).
    lignes = [json.loads(ligne) for ligne in (tmp_path / "t99_r1_lectures.jsonl").read_text("utf-8").splitlines()]
    assert [(ligne["lecture"], ligne["outil"], ligne["erreur"]) for ligne in lignes] == [
        (None, "envoyer", "outil hors de l'accès en lecture seule : envoyer"),
        (None, "archiver", "outil hors de l'accès en lecture seule : archiver"),
    ]


def test_les_lectures_ont_un_plafond_de_trois_par_etape_du_budget(tmp_path: Path) -> None:
    outils, _ = _outils(tmp_path, etapes_max=2)
    for _ in range(6):
        outils.lire_avec("lire", {})
    with pytest.raises(ErreurOutil, match="plafond de 6 lectures atteint"):
        outils.lire_avec("lire", {})
    assert not outils.budget_atteint
    lignes = [json.loads(ligne) for ligne in (tmp_path / "t99_r1_lectures.jsonl").read_text("utf-8").splitlines()]
    assert [ligne["lecture"] for ligne in lignes] == [1, 2, 3, 4, 5, 6, None]
    assert lignes[-1]["erreur"] == "plafond de 6 lectures atteint" and outils.lectures == 6


def test_le_relais_ouvre_l_acces_en_lecture_seule_sur_une_seconde_adresse(tmp_path: Path) -> None:
    outils, _ = _outils(tmp_path)

    async def interroger(adresse: str) -> tuple[list[tuple[str, bool | None]], str, bool]:
        async with Client(adresse, mode="legacy", cache=None) as client:
            listes = (await client.list_tools()).tools
            resultat = await client.call_tool("envoyer", {})
            texte = "".join(b.text for b in resultat.content if isinstance(b, TextContent))
            return (
                [(o.name, None if o.annotations is None else o.annotations.read_only_hint) for o in listes],
                texte,
                bool(resultat.is_error),
            )

    with Relais(outils, lecture=True) as relais:
        assert relais.url_lecture and relais.url_lecture != relais.url
        principal = anyio.run(interroger, relais.url)
        lecture = anyio.run(interroger, relais.url_lecture)
    assert principal[0] == [("lire", True), ("envoyer", False), ("archiver", None)]
    assert principal[1:] == ("envoyer fait", False)
    assert lecture == ([("lire", True)], "outil hors de l'accès en lecture seule : envoyer", True)
    with Relais(outils) as relais:
        assert relais.url_lecture == ""


@pytest.mark.parametrize("avec_gardien", [False, True], ids=["sans_gardien", "avec_gardien"])
def test_un_courriel_lu_par_l_acces_en_lecture_seule_reste_non_lu(tmp_path: Path, avec_gardien: bool) -> None:
    """Le relecteur regarde sans rien changer : la marque poa/lecture_seule va jusqu'à la
    messagerie, gardien compris, qui ne marque pas le courriel lu."""
    from ease.pme import REGLES_GARDIEN, EnvironnementPME
    from ease.taches import lire_tache

    tache = lire_tache(racine_depot() / "07_taches" / "public" / "t03_trier_boite_contact.yaml")
    environnement = EnvironnementPME("v3", tmp_path / "pme", REGLES_GARDIEN if avec_gardien else None)
    try:
        environnement.ouvrir(tache)
        outils = Outils(environnement, tache.budget.etapes_max, tmp_path / "t03_r1.jsonl")
        arguments = {"boite": "contact@calorelle.example", "identifiant": "m-ctc-001"}
        assert "De :" in outils.lire_avec("lire_courriel", arguments)
        non_lus = outils.appeler_avec(
            "lister_courriels", {"boite": "contact@calorelle.example", "non_lus_seulement": True}
        )
        assert "m-ctc-001" in non_lus
        outils.appeler_avec("lire_courriel", arguments)
        non_lus = outils.appeler_avec(
            "lister_courriels", {"boite": "contact@calorelle.example", "non_lus_seulement": True}
        )
        assert "m-ctc-001" not in non_lus
    finally:
        environnement.fermer()
