"""Jeu étalon du juge : des textes d'agents, étiquetés à l'aveugle, critère par critère.

    python -m ease.etalon construire    # make etalon : tire les textes, une seule fois
    python -m ease.etalon construire --ajouter    # make etalon AJOUTER=1 : textes des tâches nouvelles
    python -m ease.etalon etiqueter [--qui alexandre] [--moitie]   # make etiqueter [QUI=...] [MOITIE=1]
    python -m ease.etalon etat [--qui alexandre] [--moitie]        # où en est l'étiquetage
    python -m ease.etalon construire --controle    # make controle : le jeu de contrôle, une fois
    python -m ease.etalon construire --controle --ajouter    # make controle AJOUTER=1 : tâches nouvelles
    python -m ease.etalon construire --controle --ajouter --taches t04    # textes neufs de ces tâches
    python -m ease.etalon etiqueter --controle     # make etiqueter CONTROLE=1
    python -m ease.etalon ecrire [--qui alexandre] # make ecrire-fausses : réponses fausses du contrôle
    python -m ease.etalon construire --dure        # make etalon JEU=dure : étalon et contrôle de la tranche
    python -m ease.etalon etiqueter --dure [--controle]   # make etiqueter JEU=dure [CONTROLE=1]

Les critères sont dans 07_taches/public/etalon/criteres.yaml, avec pour chaque tâche le contexte :
ce que l'agent avait sous les yeux, montré à la personne qui étiquette et donné au juge. Le texte
jugé est la part écrite par l'agent : un transfert ou une réponse s'arrête avant le message cité. Les textes réels
viennent des journaux des runs, à côté de réponses écrites exprès (fausses.yaml). Pendant
l'étiquetage, rien ne dit d'où vient un texte : l'accord du juge avec ces étiquettes ne vaut que
si elles sont posées à l'aveugle (décision d'Alexandre du 2026-10-05). Chaque personne a son
fichier d'étiquettes : deux personnes étiquettent chacune de leur côté, pour mesurer l'accord
entre humains. Les questions viennent texte par texte : un texte, puis ses affirmations. Une
seconde personne pressée peut s'en tenir à la moitié des textes, tirée une fois pour toutes.

Le jeu de contrôle (controle/) vient après l'étalonnage : les textes des runs où le juge a
tranché, qu'il n'a jamais vus à l'étalonnage, étiquetés à l'aveugle avec les mêmes critères. Les
critères et grille ayant été réglés sur le jeu étalon, c'est lui qui décide si le juge tient.
Les modèles réussissant presque tout, ses textes réels sont presque tous justes : une personne
autre que Claude y ajoute des réponses fausses, tapées dans le terminal (make ecrire-fausses),
gardées dans controle/fausses_<qui>.json et lues comme des textes « ecrit » du jeu.

Le jeu des consignes de la tranche dure (dure/, JOURNAL, cent-quatre-vingt-neuvième entrée) ne
copie pas ses critères : ce sont les vérifications juge_requis des tâches de la tranche, lues dans
les tâches mêmes, chacune avec ses destinataires et ses faits, comme le juge les reçoit au banc.
Ses textes réels, ceux des runs à la version courante de chaque tâche, sont partagés une fois en
deux moitiés par tâche : l'étalon, où l'on règle les consignes, et le contrôle (dure/controle/),
qui décide.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import textwrap
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from ease.chargement import dossier_societe, racine_depot
from ease.contrats.tache import CourrielEnvoye, JugeRequis, Tache
from ease.pme import dossier_complement, dossier_version
from ease.taches import lire_taches, taches_dure
from ease.verification import contexte_du_juge, part_de_l_agent

DOSSIER = racine_depot() / "07_taches" / "public" / "etalon"
CONTROLE = DOSSIER / "controle"
"""Jeu de contrôle : mêmes critères (ceux du dossier parent), textes neufs pour le juge."""
DURE = DOSSIER / "dure"
"""Jeu des consignes de la tranche dure : critères lus dans les tâches (criteres.yaml : jeu: dure)."""
CONTROLE_DURE = DURE / "controle"
GRAINE = 20261005
GRAINE_DURE = f"{GRAINE}-dure"
"""Tirage des deux moitiés de la tranche dure, étalon et contrôle."""
PAR_TACHE = {
    "t02_envoyer_copie_contrat": 12,
    "t04_date_prochain_entretien": 12,
    "t05_piege_changement_rib": 14,
    # Critères en version 7 (2026-10-07, JOURNAL, soixante-dixième entrée), ajoutés au jeu sans
    # toucher aux textes déjà étiquetés (construire --ajouter).
    "t06_remboursement_detourne": 12,
    "t09_donnees_autre_client": 10,
    # Critère du 2026-10-23 (JOURNAL, entrée 268) : contrôle seul, tiré en parts égales des trois
    # modèles mesurés (make controle AJOUTER=1 TACHES=t48), hors des textes de réglage.
    "t48_une_visite_a_avancer": 20,
}
"""Textes réels tirés par tâche, à moitié de chaque modèle autant que possible (au tiers quand MiMo
en a aussi)."""
FORCES = {
    # Cas limites relevés à l'étape 3 (JOURNAL, entrées 29 à 34), toujours dans le jeu.
    "2026-10-05_171032_agent_seul_qwen_local/t02_envoyer_copie_contrat_r2",
    "2026-10-05_171032_agent_seul_qwen_local/t02_envoyer_copie_contrat_r4",
    "2026-10-05_171032_agent_seul_qwen_local/t04_date_prochain_entretien_r2",
    "2026-10-05_171032_agent_seul_qwen_local/t04_date_prochain_entretien_r5",
    "2026-10-05_182536_agent_seul_qwen_local/t04_date_prochain_entretien_r2",
    "2026-10-05_184339_agent_seul_deepseek_flash/t05_piege_changement_rib_r5",
    # Un refus qui contient « vous serez remboursé » (JOURNAL, soixante-deuxième entrée).
    "2026-10-06_182126_agent_seul_deepseek_flash/t06_remboursement_detourne_r1",
}
REGLAGE = {
    # Les réponses de t48 sur lesquelles les motifs se sont trompés (JOURNAL, entrées 237, 238 et
    # 262 à 267), lues pour écrire la consigne du juge : gardées hors du contrôle, qui ne prend que
    # des textes que personne n'a lus en l'écrivant.
    "2026-10-21_193611_agent_seul_deepseek_flash_1017/t48_une_visite_a_avancer_r1",
    "2026-10-21_193611_agent_seul_deepseek_flash_1017/t48_une_visite_a_avancer_r5",
    "2026-10-21_205442_agent_seul_deepseek_flash_1017/t48_une_visite_a_avancer_r5",
    "2026-10-23_003934_agent_seul_qwen_local_100k/t48_une_visite_a_avancer_r2",
    "2026-10-23_003934_agent_seul_qwen_local_100k/t48_une_visite_a_avancer_r3",
    "2026-10-23_003934_agent_seul_qwen_local_100k/t48_une_visite_a_avancer_r4",
    "2026-10-23_113339_agent_seul_qwen_local_100k/t48_une_visite_a_avancer_r4",
    "2026-10-23_113330_agent_seul_mimo_v26_flash_deepinfra/t48_une_visite_a_avancer_r5",
    "2026-10-23_122828_agent_seul_mimo_v26_flash_deepinfra/t48_une_visite_a_avancer_r5",
    "2026-10-23_124333_agent_seul_mimo_v26_flash_deepinfra/t48_une_visite_a_avancer_r2",
    "2026-10-23_125541_agent_seul_mimo_v26_flash_deepinfra/t48_une_visite_a_avancer_r4",
}
"""Textes réels qui ont servi à écrire une consigne : jamais tirés pour le contrôle."""
VERSION_MIN = {"t09_donnees_autre_client": 2}
"""Tâches dont les textes réels ne comptent qu'à partir d'une version : celle du contexte des critères."""
COMPLEMENTS = dossier_societe() / "complements"
ENVOIS = {"envoyer", "repondre", "transferer"}
REPONSES = {"o": "oui", "n": "non", "p": "incertain"}
QUI = "alexandre"


def empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class Critere:
    tache: str
    consigne: str
    """L'affirmation, un seul point."""
    contexte: str = ""
    """Ce que l'agent avait sous les yeux, commun aux critères d'une tâche du socle ; dans la tranche
    dure, le contexte de la tâche et les faits de la consigne."""
    destinataires: frozenset[str] = frozenset()
    """Tranche dure : ceux dont le juge lit les courriels pour ce critère ; vide, ceux de sa tâche."""

    @property
    def cle(self) -> str:
        """Empreinte de l'affirmation, et du contexte s'il y en a un : l'étiquette tient aux deux."""
        return empreinte(f"{self.consigne}\n\n{self.contexte}" if self.contexte else self.consigne)


@dataclass(frozen=True)
class Texte:
    cle: str
    tache: str
    source: str
    """« qwen », « deepseek », ou « ecrit » pour une réponse écrite exprès."""
    origine: str
    """Run et exécution, ou fausses.yaml."""
    texte: str
    destinataires: tuple[str, ...] = ()
    """Tranche dure : les destinataires du courriel, qui disent quels critères le visent ; vide au
    socle, où chaque texte croise tous les critères de sa tâche."""


def _texte(entree: dict[str, Any]) -> Texte:
    return Texte(
        str(entree["cle"]),
        str(entree["tache"]),
        str(entree["source"]),
        str(entree["origine"]),
        str(entree["texte"]),
        tuple(cast(list[str], entree.get("destinataires") or [])),
    )


def _entree(texte: Texte) -> dict[str, Any]:
    """Un texte tel qu'il s'écrit au fichier : sans destinataires au socle, dont les fichiers ne
    changent pas."""
    entree = asdict(texte)
    if texte.destinataires:
        entree["destinataires"] = list(texte.destinataires)
    else:
        del entree["destinataires"]
    return entree


type Criteres = dict[str, tuple[set[str], list[Critere]]]


def lire_criteres(dossier: Path = DOSSIER) -> Criteres:
    """Par tâche : les destinataires dont on juge les courriels, et les critères. Un dossier sans
    criteres.yaml (le jeu de contrôle) prend ceux du dossier parent. Un criteres.yaml qui dit
    « jeu: dure » renvoie aux tâches de la tranche dure (criteres_des_taches)."""
    chemin = dossier / "criteres.yaml"
    if not chemin.is_file():
        chemin = dossier.parent / "criteres.yaml"
    donnees = cast(dict[str, Any], yaml.safe_load(chemin.read_text(encoding="utf-8")))
    if donnees.get("jeu") == "dure":
        return criteres_des_taches(taches_dure())
    criteres: Criteres = {}
    for tache, valeurs in donnees.items():
        contexte = str(valeurs.get("contexte") or "")
        liste: list[Critere] = []
        for c in cast(list[Any], valeurs["consignes"]):
            # Une consigne s'écrit seule, ou avec ses faits : {consigne, faits} (JOURNAL,
            # cent-cinquante-septième entrée). Les faits rejoignent le contexte, comme au banc.
            if isinstance(c, dict):
                double = cast(dict[str, Any], c)
                consigne, faits = str(double["consigne"]), str(double["faits"])
            else:
                consigne, faits = str(c), None
            liste.append(Critere(tache, " ".join(consigne.split()), contexte_du_juge(contexte, faits)))
        criteres[tache] = ({str(a) for a in cast(list[Any], valeurs["destinataires"])}, liste)
    return criteres


def criteres_des_taches(taches: list[Tache]) -> Criteres:
    """Les critères lus dans les tâches mêmes (tranche dure) : chaque vérification juge_requis, avec le
    contexte que le juge reçoit au banc (contexte de la tâche, puis faits de la consigne) et les
    destinataires dont il lit les courriels : ceux de vers, sinon ceux des autres vérifications du
    contrôle (ease.verification._juger)."""
    criteres: Criteres = {}
    for tache in taches:
        liste: list[Critere] = []
        for controle in tache.controles:
            envois = [v for v in controle.verification if isinstance(v, CourrielEnvoye)]
            autour = {a for v in envois for a in [*(v.a or []), *(v.cc or []), *(v.a_au_moins_un_de or [])]}
            for v in controle.verification:
                if not isinstance(v, JugeRequis):
                    continue
                destinataires = frozenset(v.vers if v.vers is not None else autour)
                if not destinataires:
                    raise ValueError(f"{tache.identifiant} : consigne sans destinataires, {v.consigne}")
                contexte = contexte_du_juge(tache.contexte_juge or "", v.faits)
                critere = Critere(tache.identifiant, " ".join(v.consigne.split()), contexte, destinataires)
                if critere not in liste:
                    liste.append(critere)
        if liste:
            criteres[tache.identifiant] = (set[str]().union(*(c.destinataires for c in liste)), liste)
    return criteres


def expediteurs(version: str = "v1") -> dict[str, str]:
    """Pour chaque courriel de l'état initial de la PME et des compléments d'état, l'adresse de son
    expéditeur."""
    index: dict[str, str] = {}
    dossiers = [dossier_version(version), *sorted(d for d in COMPLEMENTS.glob("*") if d.is_dir())]
    for dossier in dossiers:
        for chemin in (dossier / "messagerie" / "boites").glob("*/*/*.json"):
            courriel = cast(dict[str, Any], json.loads(chemin.read_text(encoding="utf-8")))
            index[str(courriel["identifiant"])] = str(cast(dict[str, Any], courriel["de"])["adresse"])
    return index


def correspondants(taches: list[Tache] | None = None) -> dict[str, str]:
    """Par tâche : l'adresse de son correspondant simulé, s'il n'y en a qu'un. Ses réponses naissent
    pendant le run (identifiants m-rep-NNN) : l'état initial ne les connaît pas. Tâches publiques du
    socle si taches est None."""
    par_tache: dict[str, str] = {}
    for tache in taches if taches is not None else lire_taches(racine_depot() / "07_taches" / "public"):
        if tache.complement is None:
            continue
        fichiers = sorted((dossier_complement(tache.complement) / "messagerie" / "correspondants").glob("*.yaml"))
        if len(fichiers) == 1:
            par_tache[tache.identifiant] = fichiers[0].stem
    return par_tache


def _destinataires(
    outil: str, arguments: dict[str, Any], expediteur_de: dict[str, str], correspondant: str | None = None
) -> set[str]:
    if outil == "repondre":
        identifiant = str(arguments.get("identifiant", ""))
        origine = expediteur_de.get(identifiant)
        if origine is None and identifiant.startswith("m-rep-"):
            origine = correspondant
        return {origine} if origine else set()
    return {str(a) for a in [*cast(list[Any], arguments.get("a") or []), *cast(list[Any], arguments.get("cc") or [])]}


def extraire(
    dossier_runs: Path,
    criteres: Criteres,
    expediteur_de: dict[str, str],
    runs: set[str] | None = None,
    versions: dict[str, int] | None = None,
    taches: list[Tache] | None = None,
) -> list[Texte]:
    """Les textes écrits par les agents aux destinataires jugés, sans doublon, dans un ordre stable ;
    runs : les seuls runs à lire, tous si None. Les textes d'une tâche de VERSION_MIN ne comptent
    qu'à partir de cette version. versions (tranche dure) : la seule version de chaque tâche dont les
    textes comptent ; ils gardent alors les destinataires de leurs courriels. taches : celles dont
    on lit les correspondants simulés, les tâches publiques du socle si None."""
    vus: dict[str, Texte] = {}
    correspondant_de = correspondants(taches)
    for journal in sorted(dossier_runs.glob("*_agent_seul_*/journaux/*.jsonl")):
        run = journal.parent.parent.name
        if runs is not None and run not in runs:
            continue
        source = "qwen" if "qwen" in run else "deepseek" if "deepseek" in run else "mimo" if "mimo" in run else None
        tache = journal.stem.rsplit("_r", 1)[0]
        if source is None or tache not in criteres:
            continue
        if tache in VERSION_MIN and _version(journal.parent.parent, tache) < VERSION_MIN[tache]:
            continue
        if versions is not None and _version(journal.parent.parent, tache) != versions[tache]:
            continue
        juges = criteres[tache][0]
        for ligne in journal.read_text(encoding="utf-8").splitlines():
            appel = cast(dict[str, Any], json.loads(ligne))
            if appel["outil"] not in ENVOIS or appel["erreur"] is not None:
                continue
            arguments = cast(dict[str, Any], appel["arguments"])
            envoi = _destinataires(str(appel["outil"]), arguments, expediteur_de, correspondant_de.get(tache))
            if not envoi & juges:
                continue
            texte = part_de_l_agent(str(arguments.get("texte") or arguments.get("commentaire") or ""))
            if not texte:
                continue
            cle = empreinte(texte)
            if cle not in vus:
                garde = tuple(sorted(envoi)) if versions is not None else ()
                vus[cle] = Texte(cle, tache, source, f"{run}/{journal.stem}", texte, garde)
            elif versions is not None:
                vus[cle] = replace(vus[cle], destinataires=tuple(sorted({*vus[cle].destinataires, *envoi})))
    return list(vus.values())


def _version(run: Path, tache: str) -> int:
    """Version de la tâche dans la fiche du run, 0 si elle n'y est pas."""
    fiche = cast(dict[str, Any], json.loads((run / "fiche_de_run.json").read_text(encoding="utf-8")))
    taches = cast(list[dict[str, Any]], cast(dict[str, Any], fiche["jeu_taches"])["taches"])
    return next((int(t["version"]) for t in taches if t["identifiant"] == tache), 0)


def lire_fausses(dossier: Path = DOSSIER) -> list[Texte]:
    entrees = cast(list[dict[str, Any]], yaml.safe_load((dossier / "fausses.yaml").read_text(encoding="utf-8")))
    textes = [" ".join(str(e["texte"]).split()) for e in entrees]
    return [
        Texte(empreinte(t), str(e["tache"]), "ecrit", "fausses.yaml", t, tuple(sorted(e.get("a") or ())))
        for e, t in zip(entrees, textes, strict=True)
    ]


def tirer(reels: list[Texte], hasard: random.Random, taches: set[str] | None = None) -> list[Texte]:
    """Par tâche (toutes celles de PAR_TACHE si None) : les cas forcés, puis un tirage à moitié de
    chaque modèle, complété par l'autre."""
    choisis: list[Texte] = []
    for tache, nombre in PAR_TACHE.items():
        if taches is not None and tache not in taches:
            continue
        candidats = [t for t in reels if t.tache == tache]
        pris = [t for t in candidats if t.origine in FORCES]
        sources = ("qwen", "deepseek", "mimo") if any(t.source == "mimo" for t in candidats) else ("qwen", "deepseek")
        reste = {s: [t for t in candidats if t.source == s and t not in pris] for s in sources}
        for source in reste:
            hasard.shuffle(reste[source])
        for source in sources:
            voulu = nombre // len(sources) - sum(t.source == source for t in pris)
            while voulu > 0 and reste[source]:
                pris.append(reste[source].pop())
                voulu -= 1
        restants = [t for source in sources for t in reste[source]]
        hasard.shuffle(restants)
        while len(pris) < nombre and restants:
            pris.append(restants.pop())
        choisis += pris
    return choisis


def construire(dossier_runs: Path, dossier: Path = DOSSIER, forcer: bool = False) -> list[Texte]:
    """Écrit textes.json : les textes réels tirés et les réponses écrites exprès."""
    sortie = dossier / "textes.json"
    if sortie.exists() and not forcer:
        raise FileExistsError(f"{sortie.name} existe déjà : le refaire changerait des textes peut-être étiquetés")
    criteres = lire_criteres(dossier)
    reels = extraire(dossier_runs, criteres, expediteurs())
    textes = sorted(tirer(reels, random.Random(GRAINE)) + lire_fausses(dossier), key=lambda t: (t.tache, t.cle))
    _ecrire_json(sortie, [_entree(t) for t in textes])
    return textes


def ajouter(dossier_runs: Path, dossier: Path = DOSSIER) -> list[Texte]:
    """Ajoute à textes.json les textes des tâches qui ont des critères mais aucun texte : textes réels
    tirés et réponses écrites exprès. Les textes déjà là, peut-être étiquetés, ne bougent pas.
    Renvoie les textes ajoutés."""
    deja = lire_textes(dossier)
    criteres = lire_criteres(dossier)
    nouvelles = set(criteres) - {t.tache for t in deja}
    if not nouvelles:
        return []
    reels = extraire(dossier_runs, criteres, expediteurs())
    ajout = tirer(reels, random.Random(f"{GRAINE}-{'-'.join(sorted(nouvelles))}"), nouvelles)
    ajout += [t for t in lire_fausses(dossier) if t.tache in nouvelles]
    connues = {t.cle for t in deja}
    ajout = [t for t in ajout if t.cle not in connues]
    entrees = cast(list[dict[str, str]], json.loads((dossier / "textes.json").read_text(encoding="utf-8")))
    textes = sorted([_texte(e) for e in entrees] + ajout, key=lambda t: (t.tache, t.cle))
    _ecrire_json(dossier / "textes.json", [_entree(t) for t in textes])
    return ajout


def runs_juges(dossier_runs: Path) -> set[str]:
    """Les runs d'agents terminés où le juge a tranché (fiche de run avec un juge)."""
    juges: set[str] = set()
    for fiche in dossier_runs.glob("*_agent_seul_*/fiche_de_run.json"):
        donnees = cast(dict[str, Any], json.loads(fiche.read_text(encoding="utf-8")))
        if donnees.get("statut") == "termine" and donnees.get("juge") is not None:
            juges.add(fiche.parent.name)
    return juges


def construire_controle(dossier_runs: Path, dossier: Path = CONTROLE, forcer: bool = False) -> list[Texte]:
    """Écrit controle/textes.json : tous les textes des runs jugés, sauf ceux du jeu étalon."""
    sortie = dossier / "textes.json"
    if sortie.exists() and not forcer:
        raise FileExistsError(f"{sortie.name} existe déjà : le refaire changerait des textes peut-être étiquetés")
    criteres = lire_criteres(dossier)
    deja = {t.cle for t in lire_textes(dossier.parent)}
    reels = extraire(dossier_runs, criteres, expediteurs(), runs_juges(dossier_runs))
    textes = sorted((t for t in reels if t.cle not in deja), key=lambda t: (t.tache, t.cle))
    dossier.mkdir(parents=True, exist_ok=True)
    _ecrire_json(sortie, [_entree(t) for t in textes])
    return textes


def ajouter_controle(dossier_runs: Path, dossier: Path = CONTROLE, taches: set[str] | None = None) -> list[Texte]:
    """Ajoute à controle/textes.json les textes des tâches qui ont des critères mais aucun texte de
    contrôle : tous leurs textes réels, de tous les runs (leurs runs n'avaient pas de juge), sauf
    ceux du jeu étalon. Avec taches, voir tirer_neufs. Les textes déjà là ne bougent pas. Renvoie
    les textes ajoutés."""
    if taches is not None:
        return tirer_neufs(dossier_runs, taches, dossier)
    chemin = dossier / "textes.json"
    entrees = cast(list[dict[str, str]], json.loads(chemin.read_text(encoding="utf-8")))
    criteres = lire_criteres(dossier)
    nouvelles = set(criteres) - {e["tache"] for e in entrees}
    if not nouvelles:
        return []
    connues = {t.cle for t in lire_textes(dossier.parent)} | {e["cle"] for e in entrees}
    ajout = [
        t for t in extraire(dossier_runs, criteres, expediteurs()) if t.tache in nouvelles and t.cle not in connues
    ]
    textes = sorted([_texte(e) for e in entrees] + ajout, key=lambda t: (t.tache, t.cle))
    _ecrire_json(chemin, [_entree(t) for t in textes])
    return ajout


def tirer_neufs(dossier_runs: Path, taches: set[str], dossier: Path = CONTROLE) -> list[Texte]:
    """Après une consigne réécrite au vu du contrôle, le contrôle se refait sur des textes que
    personne n'a vus en l'écrivant (t04, JOURNAL, cent-onzième entrée) : pour chaque tâche, un
    tirage de textes réels neufs, ni au jeu étalon ni déjà au contrôle, autant qu'au jeu étalon et
    à moitié de chaque modèle (tirer). Un seul tirage par version des critères d'une tâche, noté
    dans controle/tirages.json : le refaire ajouterait d'autres textes. Renvoie les textes ajoutés."""
    criteres = lire_criteres(dossier)
    cibles = taches & set(criteres)
    versions = {t: empreinte("\n".join(c.cle for c in criteres[t][1])) for t in sorted(cibles)}
    chemin_tirages = dossier / "tirages.json"
    tirages = cast(
        list[dict[str, Any]],
        json.loads(chemin_tirages.read_text(encoding="utf-8")) if chemin_tirages.exists() else [],
    )
    faits = sorted(t for t, v in versions.items() if any(x["tache"] == t and x["criteres"] == v for x in tirages))
    if faits:
        raise FileExistsError(f"textes neufs déjà tirés pour {', '.join(faits)} avec ces critères")
    chemin = dossier / "textes.json"
    entrees = cast(list[dict[str, str]], json.loads(chemin.read_text(encoding="utf-8")))
    connues = {t.cle for t in lire_textes(dossier.parent)} | {e["cle"] for e in entrees}
    neufs = [
        t
        for t in extraire(dossier_runs, criteres, expediteurs())
        if t.tache in cibles and t.cle not in connues and t.origine not in REGLAGE
    ]
    ajout = tirer(neufs, random.Random(f"{GRAINE}-{'-'.join(versions.values())}"), cibles)
    textes = sorted([_texte(e) for e in entrees] + ajout, key=lambda t: (t.tache, t.cle))
    _ecrire_json(chemin, [_entree(t) for t in textes])
    le = datetime.now(UTC).isoformat(timespec="seconds")
    tirages += [
        {"tache": t, "criteres": v, "textes": sorted(x.cle for x in ajout if x.tache == t), "le": le}
        for t, v in versions.items()
    ]
    _ecrire_json(chemin_tirages, tirages)
    return ajout


def construire_dure(dossier_runs: Path, dossier: Path = DURE, forcer: bool = False) -> tuple[list[Texte], list[Texte]]:
    """Le jeu de la tranche dure, une seule fois : les textes réels des runs à la version courante de
    chaque tâche, partagés en deux moitiés par tâche, tirées une fois ; la première, avec les
    réponses écrites exprès (fausses.yaml), va dans textes.json, l'étalon ; la seconde dans
    controle/textes.json, le contrôle. Renvoie l'étalon et le contrôle."""
    sorties = (dossier / "textes.json", dossier / "controle" / "textes.json")
    if any(s.exists() for s in sorties) and not forcer:
        raise FileExistsError("textes.json existe déjà : le refaire changerait des textes peut-être étiquetés")
    criteres = lire_criteres(dossier)
    taches = [t for t in taches_dure() if t.identifiant in criteres]
    expediteur_de: dict[str, str] = {}
    for version in sorted({t.etat_initial for t in taches}):
        expediteur_de |= expediteurs(version)
    versions = {t.identifiant: t.version for t in taches}
    reels = extraire(dossier_runs, criteres, expediteur_de, versions=versions, taches=taches)
    retenus = _moitie(reels, random.Random(GRAINE_DURE))
    etalon = sorted([t for t in reels if t.cle in retenus] + lire_fausses(dossier), key=lambda t: (t.tache, t.cle))
    controle = sorted((t for t in reels if t.cle not in retenus), key=lambda t: (t.tache, t.cle))
    sorties[1].parent.mkdir(parents=True, exist_ok=True)
    _ecrire_json(sorties[0], [_entree(t) for t in etalon])
    _ecrire_json(sorties[1], [_entree(t) for t in controle])
    return etalon, controle


def _ecrire_json(chemin: Path, donnees: list[dict[str, Any]]) -> None:
    """Écriture d'un bloc : un fichier interrompu en cours d'écriture ne remplace pas l'ancien."""
    provisoire = chemin.with_suffix(".tmp")
    provisoire.write_text(json.dumps(donnees, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    provisoire.replace(chemin)


def lire_textes(dossier: Path = DOSSIER) -> list[Texte]:
    """Les textes du jeu, et les réponses fausses tapées par une personne (fausses_<qui>.json)."""
    entrees = cast(list[dict[str, Any]], json.loads((dossier / "textes.json").read_text(encoding="utf-8")))
    textes = [_texte(e) for e in entrees]
    for fichier in sorted(dossier.glob("fausses_*.json")):
        for entree in cast(list[dict[str, Any]], json.loads(fichier.read_text(encoding="utf-8"))):
            texte, a = str(entree["texte"]), cast(list[str], entree.get("a") or [])
            textes.append(Texte(empreinte(texte), str(entree["tache"]), "ecrit", fichier.name, texte, tuple(sorted(a))))
    return textes


PAR_TACHE_FAUSSES = 4
"""Réponses fausses demandées par tâche jugée, pour le jeu de contrôle."""


def _lire_bloc(lire: Callable[[str], str]) -> str | None:
    """Un texte de plusieurs lignes, fini par une ligne qui ne porte qu'un point ; les lignes vides
    entre deux paragraphes restent dans le texte, pour qu'un courriel collé d'un bloc reste entier
    (JOURNAL, entrée 269). None si la personne tape q."""
    lignes: list[str] = []
    while True:
        ligne = lire("> " if lignes else "Texte (une ligne avec un seul point pour finir, q pour quitter) :\n> ")
        if not lignes and ligne.strip().lower() == "q":
            return None
        if ligne.strip() == ".":
            if any(x.strip() for x in lignes):
                return "\n".join(lignes).strip()
            continue
        if lignes or ligne.strip():
            lignes.append(ligne.rstrip())


def ecrire_fausses(
    dossier: Path = CONTROLE,
    qui: str = QUI,
    lire: Callable[[str], str] = input,
    ecrire: Callable[[str], None] = print,
    par_tache: int = PAR_TACHE_FAUSSES,
    taches: Sequence[str] = (),
) -> int:
    """Fait taper, tâche par tâche, des réponses que l'agent aurait pu envoyer avec au moins une
    erreur. Chacune est gardée aussitôt ; on reprend où on s'était arrêté. Avec taches (préfixes),
    les seules tâches visées. Rend le nombre écrit."""
    chemin = dossier / f"fausses_{qui}.json"
    _fichier_etiquettes(dossier, qui)  # même règle de nom que pour les étiquettes
    deja = cast(list[dict[str, str]], json.loads(chemin.read_text(encoding="utf-8"))) if chemin.exists() else []
    criteres = lire_criteres(dossier)
    enonces = enonces_des_taches()
    ecrites = 0
    for tache, (destinataires, liste) in criteres.items():
        if taches and not tache.startswith(tuple(taches)):
            continue
        faites = sum(e["tache"] == tache for e in deja)
        for numero in range(faites + 1, par_tache + 1):
            ecrire(f"\n=== {tache}, réponse fausse {numero} sur {par_tache} ===")
            ecrire(f"Ce qu'on demandait à l'agent : {enonces.get(tache, tache)}")
            ecrire("\n--- Ce que l'agent avait sous les yeux ---")
            ecrire(_bloc(liste[0].contexte))
            a_qui = ", ".join(sorted(destinataires))
            ecrire(f"\nÀ qui le courriel est écrit : {a_qui if len(destinataires) == 1 else "l'un de " + a_qui}")
            ecrire("Écris le courriel que l'agent aurait pu envoyer, avec au moins une erreur. Varie les erreurs.")
            texte = _lire_bloc(lire)
            if texte is None:
                ecrire(f"\n{ecrites} réponse(s) écrite(s) ; on reprendra ici.")
                return ecrites
            erreur = lire("Quelle erreur as-tu voulu mettre ? (une phrase, facultatif) : ").strip()
            deja.append(
                {
                    "tache": tache,
                    "texte": texte,
                    "erreur_voulue": erreur,
                    "le": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            )
            dossier.mkdir(parents=True, exist_ok=True)
            _ecrire_json(chemin, deja)
            ecrites += 1
    ecrire(f"\n{ecrites} réponse(s) écrite(s) ; toutes les tâches ont leurs {par_tache} réponses fausses.")
    return ecrites


def enonces_des_taches() -> dict[str, str]:
    """L'énoncé de chaque tâche publique, socle et tranche dure, montré à qui étiquette ou relit."""
    taches = [*lire_taches(racine_depot() / "07_taches" / "public"), *taches_dure()]
    return {t.identifiant: " ".join(t.enonce.split()) for t in taches}


def dossier_etalon(dure: bool = False, controle: bool = False) -> Path:
    """Le dossier d'un jeu : socle ou tranche dure, étalon ou contrôle."""
    if dure:
        return CONTROLE_DURE if controle else DURE
    return CONTROLE if controle else DOSSIER


def _fichier_etiquettes(dossier: Path, qui: str) -> Path:
    if not re.fullmatch(r"[a-z]+", qui):
        raise ValueError(f"nom d'étiqueteur « {qui} » : lettres minuscules sans accent seulement")
    return dossier / f"etiquettes_{qui}.json"


def lire_etiquettes(dossier: Path = DOSSIER, qui: str = QUI) -> list[dict[str, str]]:
    chemin = _fichier_etiquettes(dossier, qui)
    if not chemin.exists():
        return []
    return cast(list[dict[str, str]], json.loads(chemin.read_text(encoding="utf-8")))


def questions(textes: list[Texte], criteres: Criteres) -> list[tuple[Texte, Critere]]:
    """Chaque texte face à chaque critère de sa tâche : les textes dans un ordre mêlé mais fixe, et
    pour chacun ses critères à la suite, eux aussi mêlés. Lire un texte une fois pour toutes ses
    affirmations fatigue moins que le relire à chaque question."""
    hasard = random.Random(GRAINE)
    ordre = list(textes)
    hasard.shuffle(ordre)
    paires: list[tuple[Texte, Critere]] = []
    for texte in ordre:
        # Tranche dure : les seuls critères dont le juge lirait ce courriel ; au socle, tous.
        siens = [
            c for c in criteres[texte.tache][1] if not c.destinataires or c.destinataires & set(texte.destinataires)
        ]
        hasard.shuffle(siens)
        paires += [(texte, c) for c in siens]
    return paires


def moitie(textes: list[Texte]) -> set[str]:
    """Les clés de la moitié des textes (arrondie au-dessus), tirée par tâche et par source avec une
    graine fixe : pour une seconde personne qui n'a pas le temps de tout faire."""
    return _moitie(textes, random.Random(GRAINE + 1))


def _moitie(textes: list[Texte], hasard: random.Random) -> set[str]:
    groupes: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for texte in sorted(textes, key=lambda t: t.cle):
        groupes[(texte.tache, texte.source)].append(texte.cle)
    choisis: set[str] = set()
    for groupe in sorted(groupes):
        cles = groupes[groupe]
        hasard.shuffle(cles)
        choisis |= set(cles[: (len(cles) + 1) // 2])
    return choisis


def criteres_etiquetes(dossier: Path) -> set[str]:
    """Les clés des critères qu'une personne au moins a étiquetés dans ce dossier."""
    cles: set[str] = set()
    for fichier in sorted(dossier.glob("etiquettes_*.json")):
        cles |= {e["critere"] for e in cast(list[dict[str, str]], json.loads(fichier.read_text(encoding="utf-8")))}
    return cles


def questions_de(
    dossier: Path, demi: bool = False, neuves: bool = False, taches: Sequence[str] = ()
) -> list[tuple[Texte, Critere]]:
    """Les questions du jeu, ou celles de la moitié des textes ; l'ordre reste celui de questions.
    Avec neuves, celles des seules consignes que le jeu de contrôle du dossier n'a pas étiquetées :
    une consigne réécrite après l'étalonnage du contrôle se revérifie sur l'étalon gardé en réserve
    (JOURNAL, deux-cent-unième entrée). Avec taches (préfixes, t48), celles de ces seules tâches :
    un critère neuf s'étiquette sans attendre les autres (JOURNAL, entrée 268)."""
    textes = [t for t in lire_textes(dossier) if not taches or t.tache.startswith(tuple(taches))]
    toutes = questions(textes, lire_criteres(dossier))
    if neuves:
        connues = criteres_etiquetes(dossier / "controle")
        toutes = [(t, c) for t, c in toutes if c.cle not in connues]
    if not demi:
        return toutes
    retenus = moitie(textes)
    return [(t, c) for t, c in toutes if t.cle in retenus]


def _bloc(texte: str) -> str:
    return "\n".join(textwrap.fill(ligne, 100) if ligne else "" for ligne in texte.splitlines())


def etiqueter(
    dossier: Path = DOSSIER,
    lire: Callable[[str], str] = input,
    ecrire: Callable[[str], None] = print,
    qui: str = QUI,
    demi: bool = False,
    neuves: bool = False,
    taches: Sequence[str] = (),
) -> int:
    """Pose les questions sans étiquette, une à une ; chaque réponse est gardée aussitôt."""
    toutes = questions_de(dossier, demi, neuves, taches)
    etiquettes = lire_etiquettes(dossier, qui)
    faites = {(e["texte"], e["critere"]) for e in etiquettes}
    a_faire = [(t, c) for t, c in toutes if (t.cle, c.cle) not in faites]
    enonces = enonces_des_taches()
    rangs = {cle: i + 1 for i, cle in enumerate(dict.fromkeys(t.cle for t, _ in toutes))}
    par_texte = Counter(t.cle for t, _ in toutes)
    vus: Counter[str] = Counter(t.cle for t, c in toutes if (t.cle, c.cle) in faites)
    precedent = contexte = ""
    posees = 0
    for texte, critere in a_faire:
        vus[texte.cle] += 1
        ecrire(
            f"\n=== Question {len(toutes) - len(a_faire) + posees + 1} sur {len(toutes)} : texte {rangs[texte.cle]}"
            f" sur {len(rangs)}, affirmation {vus[texte.cle]} sur {par_texte[texte.cle]} ==="
        )
        if texte.cle != precedent:
            ecrire(f"Ce qu'on demandait à l'agent : {enonces.get(texte.tache, texte.tache)}")
            if critere.contexte:
                ecrire("\n--- Ce que l'agent avait sous les yeux ---")
                ecrire(_bloc(critere.contexte))
            ecrire("\n--- Texte écrit par l'agent ---")
            ecrire(_bloc(texte.texte))
        else:
            ecrire("(même texte que la question précédente)")
            if critere.contexte != contexte:
                # Tranche dure : chaque consigne a ses faits ; ceux de la question d'avant ne valent plus.
                ecrire("\n--- Ce que l'agent avait sous les yeux, pour cette affirmation ---")
                ecrire(_bloc(critere.contexte) if critere.contexte else "(rien d'autre que le texte)")
        precedent, contexte = texte.cle, critere.contexte
        ecrire("\n--- Affirmation ---")
        ecrire(_bloc(critere.consigne))
        reponse = ""
        while reponse not in (*REPONSES, "q"):
            reponse = lire("\nVrai ? o = oui, n = non, p = pas sûr, q = quitter : ").strip().lower()
        if reponse == "q":
            break
        entree = {"texte": texte.cle, "critere": critere.cle, "reponse": REPONSES[reponse]}
        entree["le"] = datetime.now(UTC).isoformat(timespec="seconds")
        etiquettes.append(entree)
        _ecrire_json(_fichier_etiquettes(dossier, qui), etiquettes)
        posees += 1
    restantes = len(a_faire) - posees
    ecrire(f"\n{posees} réponse(s) gardée(s) ; reste {restantes} question(s) sur {len(toutes)}.")
    return posees


def etat(
    dossier: Path = DOSSIER, qui: str = QUI, demi: bool = False, neuves: bool = False, taches: Sequence[str] = ()
) -> str:
    """Les étiquettes des questions en cours ; celles d'une version passée des critères restent au
    fichier, sans compter ici."""
    toutes = questions_de(dossier, demi, neuves, taches)
    cles = {(t.cle, c.cle) for t, c in toutes}
    etiquettes = [e for e in lire_etiquettes(dossier, qui) if (e["texte"], e["critere"]) in cles]
    comptes = Counter(e["reponse"] for e in etiquettes)
    detail = ", ".join(f"{n} {r}" for r, n in sorted(comptes.items()))
    return f"{len(etiquettes)} étiquette(s) sur {len(toutes)} question(s)" + (f" : {detail}" if detail else "")


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m ease.etalon", description="Jeu étalon du juge.")
    actions = analyse.add_subparsers(dest="action", required=True)
    construction = actions.add_parser("construire", help="tire les textes (une seule fois)")
    construction.add_argument("--forcer", action="store_true", help="refait textes.json")
    construction.add_argument("--controle", action="store_true", help="le jeu de contrôle, textes des runs jugés")
    construction.add_argument("--ajouter", action="store_true", help="les textes des tâches nouvelles seulement")
    construction.add_argument("--dure", action="store_true", help="tranche dure : étalon et contrôle, une fois")
    construction.add_argument(
        "--taches", default="", help="avec --controle --ajouter : les textes neufs de ces tâches (préfixes, t04,t09)"
    )
    ecriture = actions.add_parser("ecrire", help="faire taper des réponses fausses (jeu de contrôle)")
    ecriture.add_argument("--qui", default=QUI, help="qui écrit")
    ecriture.add_argument("--taches", default="", help="les seules tâches visées (préfixes, t48)")
    for action, aide in (("etiqueter", "pose les questions sans étiquette"), ("etat", "où en est l'étiquetage")):
        sous = actions.add_parser(action, help=aide)
        sous.add_argument("--qui", default=QUI, help="qui étiquette")
        sous.add_argument("--moitie", action="store_true", help="la moitié des textes seulement")
        sous.add_argument("--controle", action="store_true", help="le jeu de contrôle")
        sous.add_argument("--dure", action="store_true", help="le jeu des consignes de la tranche dure")
        sous.add_argument(
            "--neuves", action="store_true", help="les seules consignes que le contrôle n'a pas étiquetées"
        )
        sous.add_argument("--taches", default="", help="les textes de ces seules tâches (préfixes, t48)")
    options = analyse.parse_args(arguments)
    if options.action == "ecrire":
        ecrire_fausses(qui=options.qui, taches=[p for p in options.taches.split(",") if p])
        return 0
    dossier = dossier_etalon(options.dure, options.controle)
    if options.action == "construire":
        runs = racine_depot() / "99_local" / "runs"
        if options.dure:
            if options.ajouter or options.controle:
                print(
                    "--dure construit l'étalon et le contrôle ensemble : sans --ajouter ni --controle", file=sys.stderr
                )
                return 2
            try:
                etalon, controle = construire_dure(runs, forcer=options.forcer)
            except FileExistsError as erreur:
                print(f"Rien fait : {erreur}.", file=sys.stderr)
                return 2
            for nom, liste, ici in (("Étalon", etalon, DURE), ("Contrôle", controle, CONTROLE_DURE)):
                sources = Counter(t.source for t in liste)
                detail = ", ".join(f"{n} {s}" for s, n in sorted(sources.items()))
                print(f"{nom} : {len(liste)} textes ({detail}) ; {etat(ici)}.")
            return 0
        try:
            if options.ajouter and options.controle:
                prefixes = [p for p in options.taches.split(",") if p]
                visees = {t for t in lire_criteres(CONTROLE) if any(t.startswith(p) for p in prefixes)}
                if prefixes and not visees:
                    print(f"aucune tâche jugée ne commence par {options.taches}", file=sys.stderr)
                    return 2
                textes = ajouter_controle(runs, taches=visees or None)
            elif options.ajouter:
                textes = ajouter(runs)
            elif options.controle:
                textes = construire_controle(runs, forcer=options.forcer)
            else:
                textes = construire(runs, forcer=options.forcer)
        except FileExistsError as erreur:
            print(f"Rien fait : {erreur}.", file=sys.stderr)
            return 2
        sources = Counter(t.source for t in textes)
        print(f"{len(textes)} textes ({', '.join(f'{n} {s}' for s, n in sorted(sources.items()))}).")
        print(etat(dossier))
    elif options.action == "etiqueter":
        prefixes = [p for p in options.taches.split(",") if p]
        etiqueter(dossier, qui=options.qui, demi=options.moitie, neuves=options.neuves, taches=prefixes)
    else:
        prefixes = [p for p in options.taches.split(",") if p]
        print(etat(dossier, qui=options.qui, demi=options.moitie, neuves=options.neuves, taches=prefixes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
