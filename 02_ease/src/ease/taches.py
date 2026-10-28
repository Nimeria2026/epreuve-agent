"""Chargement des tâches de 07_taches/ et contrôle de leur contrat.

Une tâche passe trois filtres, dans cet ordre :
1. le schéma JSON de 01_contrats/tache.schema.json, source de vérité, qui couvre aussi ce que
   Pydantic ne vérifie pas (éléments uniques d'une liste) ;
2. le modèle Pydantic généré depuis ce schéma, qui donne un objet typé ;
3. les règles que JSON Schema ne sait pas exprimer : somme des poids égale à 1, identifiant
   égal au nom du fichier.

La cohérence avec les données de la PME (personne de l'organigramme, état initial présent) se
contrôle à part, avec coherence_pme.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import yaml

from ease.chargement import (
    SOCIETE,
    ContratInvalide,
    dossier_complements_caches,
    dossier_societe,
    ecarts_schema,
    lire_donnees,
    racine_depot,
    valider_modele,
)
from ease.contrats.tache import (
    AucunEnvoiAvec,
    DevisCree,
    DevisInchanges,
    DevisStatut,
    InterventionInchangee,
    InterventionPlanifiee,
    Tache,
)

__all__ = ["TacheInvalide", "coherence_pme", "lire_tache", "lire_taches", "racine_depot"]

TOLERANCE_POIDS = 1e-9

SERVICES_PYTHON: dict[str, str] = {"eke": "eke"}
"""Les services de la PME écrits en Python, et leur module : EKE (04_eke), l'outil documentaire
(étape 6). Les autres sont des serveurs TypeScript, 05_pme/<service>/src/principal.ts."""


class TacheInvalide(ContratInvalide):
    """Une tâche ne respecte pas son contrat."""


def _ecarts_regles(tache: Tache, chemin: Path) -> list[str]:
    erreurs: list[str] = []
    somme = math.fsum(controle.poids for controle in tache.controles)
    if not math.isclose(somme, 1.0, abs_tol=TOLERANCE_POIDS):
        erreurs.append(f"controles : la somme des poids vaut {somme:g}, elle doit valoir 1")
    for numero, controle in enumerate(tache.controles, start=1):
        if all(v.type == "juge_requis" for v in controle.verification):
            erreurs.append(f"controles/{numero} : il faut au moins une vérification mécanique, pas seulement un juge")
        for v in controle.verification:
            if v.type == "envois" and v.au_plus and v.au_moins:
                erreurs.append(f"controles/{numero} : envois ne peut pas être à la fois au_plus et au_moins")
            if v.type == "devis_cree" and v.lignes is not None:
                # Un code cité plusieurs fois l'est à des taux tous donnés et différents (entrée 99).
                vus = [(ligne.code, ligne.taux_tva) for ligne in v.lignes]
                codes = [code for code, _ in vus]
                doubles = sorted({c for c, t in vus if codes.count(c) > 1 and (t is None or vus.count((c, t)) > 1)})
                if doubles:
                    cites = ", ".join(doubles)
                    erreurs.append(
                        f"controles/{numero} : devis_cree cite deux fois {cites} sans taux qui les distingue"
                    )
    if tache.identifiant != chemin.stem:
        erreurs.append(f"identifiant : « {tache.identifiant} » diffère du nom du fichier « {chemin.stem} »")
    return erreurs


def budget_etapes(etapes_temoin: int) -> int:
    """Le budget d'étapes d'une tâche : 25, plus deux fois les étapes de son témoin parfait,
    arrondi aux cinq du dessus (décision d'Alexandre, JOURNAL, entrée 97). La part fixe laisse à
    l'agent de quoi s'orienter dans la PME, le double du témoin de quoi vérifier ; la règle ne
    dépend d'aucun agent mesuré."""
    return 5 * math.ceil((25 + 2 * etapes_temoin) / 5)


RYTHME_DEEPSEEK = 1.54
"""Étapes de DeepSeek V4.1 Flash 1017 par minute de grille, en médiane, sur la tranche dure de la v1
(run 2026-10-21_161848, 60 exécutions ; cadrage de la tranche longue v2, §2)."""


def budget_etapes_v2(etapes_temoin: int, secondes_grille: float) -> int:
    """Le budget d'étapes d'une tâche de la tranche longue v2 : celui de la règle (budget_etapes),
    relevé au rythme médian de DeepSeek quand il tombe dessous, arrondi aux cinq du dessus (choix
    d'Alexandre du 2026-10-23, C6 ; JOURNAL, entrée 260). Le témoin d'une longue tâche écrit beaucoup
    en peu d'étapes, et la règle seule couperait DeepSeek au palier de 240."""
    return max(budget_etapes(etapes_temoin), 5 * math.ceil(RYTHME_DEEPSEEK * secondes_grille / 60 / 5))


def lire_tache(chemin: Path) -> Tache:
    """Lit une tâche YAML et la renvoie typée, ou lève TacheInvalide avec tous les écarts."""
    donnees = lire_donnees(chemin)
    erreurs = ecarts_schema("tache", donnees)
    if erreurs:
        raise TacheInvalide(chemin, erreurs)
    tache = valider_modele(chemin, Tache, donnees)
    erreurs = _ecarts_regles(tache, chemin)
    if erreurs:
        raise TacheInvalide(chemin, erreurs)
    return tache


def lire_taches(dossier: Path, motif: str = "t[0-9]*.yaml") -> list[Tache]:
    """Lit toutes les tâches d'un dossier, dans l'ordre de leurs noms."""
    return [lire_tache(chemin) for chemin in sorted(dossier.glob(motif))]


MOTIF_DOCUMENTS = "d[0-9]*.yaml"


def dossier_documents(racine: Path | None = None) -> Path:
    """Le jeu « documents » de l'étape 6, à part du banc de la PME : des tâches qui ne se font pas
    sans lire un PDF, et qui déclarent EKE (journal d'EKE, vingt-quatrième entrée)."""
    return (racine or racine_depot()) / "07_taches" / "public" / "documents"


def taches_documents(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_documents(racine), MOTIF_DOCUMENTS)


MOTIF_DURE = "h[0-9]*.yaml"


def dossier_dure(racine: Path | None = None) -> Path:
    """La tranche dure, à part du socle : des tâches longues de 30, 60 et 120 minutes de grille, faites
    d'un vrai travail enchaîné (cadrage du 2026-10-14 ; JOURNAL, cent-trentième entrée)."""
    return (racine or racine_depot()) / "07_taches" / "public" / "dure"


def taches_dure(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_dure(racine), MOTIF_DURE)


def dossier_dure_v2(racine: Path | None = None) -> Path:
    """La tranche longue de la v2 de Calorelle, h13 et suivantes, à part de la tranche dure de la
    v1 : des tâches de deux à quatre heures de grille (cadrage du 2026-10-22). Elles sont dans main
    sans être mesurées ni publiées avant la v2 ; aucun jeu de la v1 ne lit ce dossier (JOURNAL,
    entrées 250 et 256)."""
    return dossier_dure(racine) / "v2"


def taches_dure_v2(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_dure_v2(racine), MOTIF_DURE)


MOTIF_DOMIVELLE = "dv[0-9]*.yaml"


def dossier_domivelle(racine: Path | None = None) -> Path:
    """Le socle de Domivelle, seconde société fictive (ADR 0006 ; JOURNAL, cent-cinquante-cinquième
    entrée) : ses tâches dv01 et suivantes portent societe: domivelle."""
    return (racine or racine_depot()) / "07_taches" / "public" / "domivelle"


def taches_domivelle(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_domivelle(racine), MOTIF_DOMIVELLE)


MOTIF_DOMIVELLE_DURE = "dvh[0-9]*.yaml"


def dossier_domivelle_dure(racine: Path | None = None) -> Path:
    """La tranche longue de Domivelle, à part de son socle : des tâches de 30, 60 et 120 minutes de
    grille (cadrage du 2026-10-15, section 8 ; JOURNAL, cent-cinquante-cinquième entrée)."""
    return dossier_domivelle(racine) / "dure"


def taches_domivelle_dure(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_domivelle_dure(racine), MOTIF_DOMIVELLE_DURE)


def dossier_domivelle_dure_v2(racine: Path | None = None) -> Path:
    """La tranche longue de la v2 de Domivelle, dvh22 et suivantes, à part de sa tranche longue de
    la v1 : des tâches de deux à quatre heures de grille (cadrage du 2026-10-22, §16). Comme celle de
    Calorelle, elles sont dans main sans être mesurées ni publiées avant la v2."""
    return dossier_domivelle_dure(racine) / "v2"


def taches_domivelle_dure_v2(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_domivelle_dure_v2(racine), MOTIF_DOMIVELLE_DURE)


MOTIF_NEGOVELLE = "ng[0-9]*.yaml"


def dossier_negovelle(racine: Path | None = None) -> Path:
    """Le socle de Négovelle, troisième société fictive (cadrage du 2026-10-17, négoce de gros) : ses
    tâches ng01 et suivantes portent societe: negovelle. Le motif ne prend pas ngh01, de la tranche
    longue."""
    return (racine or racine_depot()) / "07_taches" / "public" / "negovelle"


def taches_negovelle(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_negovelle(racine), MOTIF_NEGOVELLE)


MOTIF_NEGOVELLE_DURE = "ngh[0-9]*.yaml"


def dossier_negovelle_dure(racine: Path | None = None) -> Path:
    """La tranche longue de Négovelle, à part de son socle : des tâches de 30, 60 et 120 minutes de
    grille (cadrage du 2026-10-17, section 8)."""
    return dossier_negovelle(racine) / "dure"


def taches_negovelle_dure(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_negovelle_dure(racine), MOTIF_NEGOVELLE_DURE)


def dossier_negovelle_dure_v2(racine: Path | None = None) -> Path:
    """La tranche longue de la v2 de Négovelle, ngh22 et suivantes, à part de sa tranche longue de
    la v1 : des tâches de deux à quatre heures de grille (cadrage du 2026-10-22, §16), dans main sans
    être mesurées ni publiées avant la v2."""
    return dossier_negovelle_dure(racine) / "v2"


def taches_negovelle_dure_v2(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_negovelle_dure_v2(racine), MOTIF_NEGOVELLE_DURE)


MOTIF_GABARIT = "gb[0-9]*.yaml"


def dossier_gabarit(racine: Path | None = None) -> Path:
    """La société gabarit, base des campagnes (cadrage des interventions, section 11 ; JOURNAL,
    entrée 312) : ses dix tâches communes gb01 à gb10, écrites par generer_gabarit.py, puis celles
    du métier d'une campagne, gb11 et suivantes ; toutes portent societe: gabarit."""
    return (racine or racine_depot()) / "07_taches" / "public" / "gabarit"


def taches_gabarit(racine: Path | None = None) -> list[Tache]:
    return lire_taches(dossier_gabarit(racine), MOTIF_GABARIT)


JEUX = (
    "public",
    "documents",
    "dure",
    "dure_v2",
    "domivelle",
    "domivelle_dure",
    "domivelle_dure_v2",
    "negovelle",
    "negovelle_dure",
    "negovelle_dure_v2",
    "gabarit",
)
"""Les jeux de tâches publiques : le socle de Calorelle, le jeu « documents » de l'étape 6, la
tranche dure, la tranche longue de la v2 (hors de la v1), le socle de Domivelle, sa tranche longue
et celle de sa v2, le socle de Négovelle, sa tranche longue et celle de sa v2, la société gabarit
des campagnes."""


def dossier_du_jeu(jeu: str, racine: Path | None = None) -> Path:
    if jeu == "documents":
        return dossier_documents(racine)
    if jeu == "dure":
        return dossier_dure(racine)
    if jeu == "dure_v2":
        return dossier_dure_v2(racine)
    if jeu == "domivelle":
        return dossier_domivelle(racine)
    if jeu == "domivelle_dure":
        return dossier_domivelle_dure(racine)
    if jeu == "domivelle_dure_v2":
        return dossier_domivelle_dure_v2(racine)
    if jeu == "negovelle":
        return dossier_negovelle(racine)
    if jeu == "negovelle_dure":
        return dossier_negovelle_dure(racine)
    if jeu == "negovelle_dure_v2":
        return dossier_negovelle_dure_v2(racine)
    if jeu == "gabarit":
        return dossier_gabarit(racine)
    if jeu == "public":
        return (racine or racine_depot()) / "07_taches" / "public"
    raise ValueError(f"jeu inconnu : {jeu}")


def taches_du_jeu(jeu: str, racine: Path | None = None) -> list[Tache]:
    if jeu == "documents":
        return taches_documents(racine)
    if jeu == "dure":
        return taches_dure(racine)
    if jeu == "dure_v2":
        return taches_dure_v2(racine)
    if jeu == "domivelle":
        return taches_domivelle(racine)
    if jeu == "domivelle_dure":
        return taches_domivelle_dure(racine)
    if jeu == "domivelle_dure_v2":
        return taches_domivelle_dure_v2(racine)
    if jeu == "negovelle":
        return taches_negovelle(racine)
    if jeu == "negovelle_dure":
        return taches_negovelle_dure(racine)
    if jeu == "negovelle_dure_v2":
        return taches_negovelle_dure_v2(racine)
    if jeu == "gabarit":
        return taches_gabarit(racine)
    return lire_taches(dossier_du_jeu(jeu, racine))


def societe_de(tache: Tache) -> str:
    """La société fictive de la tâche ; Calorelle quand la tâche ne le dit pas (ADR 0006)."""
    return tache.societe or SOCIETE


def societe_des_taches(taches: list[Tache]) -> str:
    """La société commune aux tâches d'un run ; des tâches de deux sociétés sont refusées ensemble."""
    societes = sorted({societe_de(t) for t in taches})
    if not societes:
        raise ValueError("aucune tâche")
    if len(societes) > 1:
        raise ValueError(
            f"les tâches viennent de {len(societes)} sociétés ({', '.join(societes)}) ; un run n'en mélange jamais deux"
        )
    return societes[0]


def donnees_empreinte(tache: Tache) -> dict[str, Any]:
    """La tâche telle qu'elle entre dans l'empreinte du jeu de la fiche de run : le champ societe
    n'y figure que s'il vaut autre chose que calorelle, pour que les empreintes des jeux de
    Calorelle restent celles d'avant la seconde société (choix d'Alexandre du 2026-10-15)."""
    donnees = tache.model_dump(mode="json")
    if donnees.get("societe") in (None, SOCIETE):
        donnees.pop("societe", None)
    return donnees


def coherence_pme(tache: Tache, racine: Path | None = None) -> list[str]:
    """Écarts entre une tâche et les données initiales de la PME qu'elle annonce."""
    racine = racine or racine_depot()
    societe = societe_de(tache)
    donnees_initiales = dossier_societe(societe, racine) / tache.etat_initial
    if not donnees_initiales.is_dir():
        return [f"etat_initial : {donnees_initiales.relative_to(racine)} n'existe pas"]
    organigramme = donnees_initiales / "entreprise" / "organigramme.yaml"
    contenu: Any = yaml.safe_load(organigramme.read_text(encoding="utf-8"))
    personnes = {personne["id"] for personne in contenu.get("personnes", [])}
    ecarts: list[str] = []
    if tache.agent_pour not in personnes:
        ecarts.append(f"agent_pour : « {tache.agent_pour} » est absent de l'organigramme {tache.etat_initial}")
    for service in tache.services:
        typescript = (racine / "05_pme" / service / "src" / "principal.ts").is_file()
        if not typescript and service not in SERVICES_PYTHON:
            ecarts.append(f"services : « {service} » n'est pas un service de la PME")
    complement: Path | None = None
    if tache.complement is not None:
        # Celui d'une tâche publique, sinon celui d'une tâche cachée (ease.cachees).
        candidats = [
            dossier_societe(societe, racine) / "complements" / tache.complement,
            dossier_complements_caches(societe, racine) / tache.complement,
        ]
        complement = next((c for c in candidats if c.is_dir()), None)
        if complement is None:
            ecarts.append(
                f"complement : « {tache.complement} » n'existe ni pour les tâches publiques ni pour les cachées"
            )
    numeros = sorted(
        {
            v.numero
            for controle in tache.controles
            for v in controle.verification
            if isinstance(v, InterventionInchangee | InterventionPlanifiee)
        }
    )
    sources = [donnees_initiales] + ([] if complement is None else [complement])
    for numero in numeros:
        if not any((s / "planning" / "interventions" / f"{numero}.json").is_file() for s in sources):
            ecarts.append(f"controles : {numero} est absente du planning de l'état initial {tache.etat_initial}")
    devis = sorted(
        {v.numero for controle in tache.controles for v in controle.verification if isinstance(v, DevisStatut)}
        | {
            n
            for controle in tache.controles
            for v in controle.verification
            if isinstance(v, DevisInchanges)
            for n in v.sauf or []
        }
    )
    for numero in devis:
        if not any((s / "facturation" / "devis" / f"{numero}.json").is_file() for s in sources):
            ecarts.append(f"controles : {numero} est absent des devis de l'état initial {tache.etat_initial}")
    codes = sorted(
        {
            ligne.code
            for controle in tache.controles
            for v in controle.verification
            if isinstance(v, DevisCree)
            for ligne in v.lignes or []
        }
    )
    tarif = donnees_initiales / "facturation" / "tarif.json"
    connus: set[str] = set()
    if tarif.is_file():
        connus = {str(article["code"]) for article in json.loads(tarif.read_text(encoding="utf-8"))["lignes"]}
    ecarts += [
        f"controles : {code} est absent du tarif de l'état initial {tache.etat_initial}"
        for code in codes
        if code not in connus
    ]
    recus = sorted(
        {
            identifiant
            for controle in tache.controles
            for v in controle.verification
            if isinstance(v, AucunEnvoiAvec)
            for identifiant in v.pieces_du_courriel or []
        }
    )
    for identifiant in recus:
        if not any(any((s / "messagerie" / "boites").glob(f"*/reception/{identifiant}.json")) for s in sources):
            ecarts.append(
                f"controles : {identifiant} est absent de la messagerie de l'état initial {tache.etat_initial}"
            )
    if "manuel" in tache.enonce.lower() and "dossiers" not in tache.services:
        ecarts.append("services : l'énoncé renvoie au manuel, qui ne se lit que par le service dossiers (commun/)")
    return ecarts
