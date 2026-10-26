"""Candidats déclarés : qui est mesuré, avec quels modèles, et comment le lancer.

Une déclaration (candidats/<identifiant>.yaml) réunit :

- fiche : la fiche candidat (contrat fiche_candidat) ;
- configuration : ce que la fiche de run note du candidat, modèles, réglages et tarifs ;
- machine : la machine qui sert un modèle local, ou null ;
- lancement : le module Python du candidat et ses arguments, ou, pour un candidat qui n'est pas
  en Python, sa commande (`commande`, module à null), son délai, les fichiers dont
  l'empreinte entre dans la fiche de run (consigne, configuration du modèle), la sonde, adresse
  où le serveur d'un modèle local doit répondre avant un run, le créneau imposé par le tarif
  (heures_creuses_deepseek) et la mesure d'énergie de la carte (nvidia_smi), ou null.

EASE lit ces fichiers et lance le candidat dans son propre processus ; il n'importe jamais son
code (règle 6).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

from ease.candidat_externe import CandidatExterne, Lancement
from ease.chargement import ContratInvalide, ecarts_schema, lire_donnees, racine_depot, valider_modele
from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import Configuration, Machine
from ease.empreintes import empreinte_texte
from ease.energie import COMMANDE as COMMANDE_NVIDIA_SMI
from ease.fiches import regles_fiche_candidat

DOSSIER = Path(__file__).parent / "candidats"
CLES = {"fiche", "configuration", "machine", "lancement"}
CLES_LANCEMENT = {"module", "arguments", "delai_secondes", "empreinte_de", "sonde", "creneau", "energie"}
FACULTATIVES_LANCEMENT = {"acces_lecture", "commande", "contexte_serveur"}
"""acces_lecture : vrai si le candidat reçoit aussi un accès en lecture seule (candidat_externe) ;
commande : le programme à lancer, depuis la racine du dépôt, quand le candidat n'est pas un module
Python, par exemple le poste humain en TypeScript (JOURNAL, cent-vingt-et-unième entrée) ;
contexte_serveur : le contexte que le serveur du modèle local doit annoncer, vérifié avant le run
(cadrage du second Qwen local, JOURNAL, deux-cent-vingt-deuxième entrée)."""
CRENEAUX = {None, "heures_creuses_deepseek"}
ENERGIES: dict[str | None, list[str] | None] = {None: None, "nvidia_smi": COMMANDE_NVIDIA_SMI}


def declarations() -> list[str]:
    """Identifiants des candidats déclarés."""
    return sorted(chemin.stem for chemin in DOSSIER.glob("*.yaml"))


def empreinte_fichiers(chemins: list[str]) -> str:
    """Empreinte de fichiers du dépôt : chaque chemin et son contenu, dans l'ordre donné."""
    racine = racine_depot()
    return empreinte_texte("\n".join(f"{c}\n{(racine / c).read_text(encoding='utf-8')}" for c in chemins))


def lire_candidat(identifiant: str, dossier: Path = DOSSIER) -> CandidatExterne:
    """Lit la déclaration d'un candidat, ou lève ContratInvalide avec ses écarts."""
    chemin = dossier / f"{identifiant}.yaml"
    if not chemin.is_file():
        raise ContratInvalide(chemin, [f"candidat inconnu ; déclarés : {', '.join(declarations()) or 'aucun'}"])
    donnees: Any = lire_donnees(chemin)
    if not isinstance(donnees, dict) or set(cast(dict[str, Any], donnees)) != CLES:
        raise ContratInvalide(chemin, [f"clés attendues : {', '.join(sorted(CLES))}"])
    valeurs = cast(dict[str, Any], donnees)
    erreurs = [f"fiche : {e}" for e in ecarts_schema("fiche_candidat", valeurs["fiche"])]
    if erreurs:
        raise ContratInvalide(chemin, erreurs)
    fiche = valider_modele(chemin, FicheCandidat, valeurs["fiche"])
    erreurs = regles_fiche_candidat(fiche)
    if fiche.identifiant != identifiant:
        erreurs.append(f"fiche.identifiant : « {fiche.identifiant} », le nom du fichier dit « {identifiant} »")
    lancement: Any = valeurs["lancement"]
    if (
        not isinstance(lancement, dict)
        or set(cast(dict[str, Any], lancement)) - FACULTATIVES_LANCEMENT != CLES_LANCEMENT
    ):
        erreurs.append(
            f"lancement : clés attendues {', '.join(sorted(CLES_LANCEMENT))}, "
            f"et facultatives {', '.join(sorted(FACULTATIVES_LANCEMENT))}"
        )
    else:
        reglages_lus = cast(dict[str, Any], lancement)
        if reglages_lus["creneau"] not in CRENEAUX:
            erreurs.append(f"lancement.creneau : « {reglages_lus['creneau']} » inconnu")
        if reglages_lus["energie"] not in ENERGIES:
            erreurs.append(f"lancement.energie : « {reglages_lus['energie']} » inconnue")
        if not isinstance(reglages_lus.get("acces_lecture", False), bool):
            erreurs.append("lancement.acces_lecture : vrai ou faux")
        contexte: Any = reglages_lus.get("contexte_serveur")
        if contexte is not None and (
            isinstance(contexte, bool)
            or not isinstance(contexte, int)
            or contexte <= 0
            or reglages_lus["sonde"] is None
        ):
            erreurs.append("lancement.contexte_serveur : un nombre de jetons positif, avec une sonde")
        programme: Any = reglages_lus.get("commande")
        if programme is None and not reglages_lus["module"]:
            erreurs.append("lancement : un module Python ou une commande")
        if programme is not None and (
            reglages_lus["module"] is not None
            or not isinstance(programme, list)
            or not programme
            or not all(isinstance(m, str) and m for m in cast(list[Any], programme))
        ):
            erreurs.append("lancement.commande : une liste de mots non vides, et le module à null")
    if erreurs:
        raise ContratInvalide(chemin, erreurs)
    configuration = valider_modele(chemin, Configuration, valeurs["configuration"])
    machine = None if valeurs["machine"] is None else valider_modele(chemin, Machine, valeurs["machine"])
    reglages = cast(dict[str, Any], lancement)
    debut = (
        [str(m) for m in cast(list[Any], reglages["commande"])]
        if reglages.get("commande") is not None
        else [sys.executable, "-m", str(reglages["module"])]
    )
    commande = [*debut, *(str(a) for a in reglages["arguments"])]
    return CandidatExterne(
        fiche=fiche,
        configuration=configuration,
        lancement=Lancement(
            commande,
            delai_secondes=float(reglages["delai_secondes"]),
            sonde=None if reglages["sonde"] is None else str(reglages["sonde"]),
            creneau=reglages["creneau"],
            wattmetre=ENERGIES[reglages["energie"]],
            acces_lecture=bool(reglages.get("acces_lecture", False)),
            contexte_serveur=None if reglages.get("contexte_serveur") is None else int(reglages["contexte_serveur"]),
        ),
        empreinte_prompts=empreinte_fichiers([str(c) for c in reglages["empreinte_de"]]),
        machine=machine,
    )
