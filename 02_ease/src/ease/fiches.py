"""Fiches de run, résultats d'exécution, fiches candidat et sorties de candidat : lecture et règles
hors schéma.

Convention commune aux trois contrats : « ? » signifie inconnu, et le rapport le montre ; None
(null en JSON) signifie sans objet.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ease.chargement import ContratInvalide, ecarts_schema, ecarts_utc, lire_donnees, valider_modele
from ease.contrats.fiche_candidat import FicheCandidat
from ease.contrats.fiche_de_run import FicheDeRun, SimulateurDuRun
from ease.contrats.resultat_execution import ResultatExecution
from ease.contrats.sortie_candidat import SortieCandidat
from ease.contrats.tache import Tache

TOLERANCE = 1e-9


def _lire[M: BaseModel](chemin: Path, contrat: str, modele: type[M], regles: Callable[[M], list[str]]) -> M:
    donnees: Any = lire_donnees(chemin)
    erreurs = ecarts_schema(contrat, donnees)
    if erreurs:
        raise ContratInvalide(chemin, erreurs)
    objet = valider_modele(chemin, modele, donnees)
    erreurs = regles(objet)
    if erreurs:
        raise ContratInvalide(chemin, erreurs)
    return objet


# ------------------------------------------------------------------------- fiche de run


def regles_fiche_de_run(fiche: FicheDeRun) -> list[str]:
    """Règles que le schéma de la fiche de run ne sait pas exprimer."""
    erreurs = ecarts_utc(debut_utc=fiche.debut_utc, fin_utc=fiche.fin_utc)
    if (fiche.statut == "en_cours") != (fiche.fin_utc is None):
        erreurs.append("fin_utc : vide si et seulement si le run est en cours")
    if (fiche.statut == "interrompu") != (fiche.raison_interruption is not None):
        erreurs.append("raison_interruption : renseignée si et seulement si le run est interrompu")
    if fiche.fin_utc is not None and fiche.fin_utc < fiche.debut_utc:
        erreurs.append("fin_utc : antérieure au début")
    if fiche.identifiant[:10] != fiche.debut_utc.date().isoformat():
        erreurs.append("identifiant : sa date doit être celle du début du run, en UTC")
    identifiants = [tache.identifiant for tache in fiche.jeu_taches.taches]
    if len(identifiants) != len(set(identifiants)):
        erreurs.append("jeu_taches/taches : une tâche figure deux fois")
    roles = [modele.role for modele in fiche.configuration.modeles]
    if len(roles) != len(set(roles)):
        erreurs.append("configuration/modeles : deux modèles portent le même rôle")
    if fiche.banc_public is not None:
        erreurs += _regles_simulateur(fiche.banc_public.simulateur, fiche.statut)
    return erreurs


SANS_MODELE = ("ecrit_d_avance", "rejoue:")
"""Les simulateurs d'utilisateur sans modèle d'un banc public : écrit d'avance, ou rejoué."""


def _regles_simulateur(simulateur: SimulateurDuRun, statut: str) -> list[str]:
    """Un simulateur sans modèle n'a rien à payer ; un modèle a un fournisseur, et ses comptes à
    la fin du run (« ? » s'ils sont inconnus, jamais vides)."""
    comptes = (simulateur.jetons, simulateur.cout_dollars, simulateur.cout_annonce_dollars)
    sans = simulateur.modele == SANS_MODELE[0] or simulateur.modele.startswith(SANS_MODELE[1])
    renseignes = [c is not None for c in (simulateur.fournisseur, simulateur.tarif, *comptes)]
    if sans and any(renseignes):
        return ["banc_public/simulateur : un utilisateur sans modèle n'a ni fournisseur, ni tarif, ni jetons, ni coût"]
    if not sans and simulateur.fournisseur is None:
        return ["banc_public/simulateur/fournisseur : requis pour un modèle"]
    if not sans and statut != "en_cours" and any(c is None for c in comptes):
        return ["banc_public/simulateur : jetons et coûts renseignés à la fin du run, « ? » s'ils sont inconnus"]
    if not sans and statut == "en_cours" and any(c is not None for c in comptes):
        return ["banc_public/simulateur : jetons et coûts vides tant que le run tourne"]
    return []


def lire_fiche_de_run(chemin: Path) -> FicheDeRun:
    """Lit une fiche de run, ou lève ContratInvalide avec tous les écarts."""
    return _lire(chemin, "fiche_de_run", FicheDeRun, regles_fiche_de_run)


# ------------------------------------------------------------------ résultat d'exécution


def regles_resultat(resultat: ResultatExecution) -> list[str]:
    """Règles que le schéma du résultat d'exécution ne sait pas exprimer."""
    erreurs = ecarts_utc(debut_utc=resultat.debut_utc, fin_utc=resultat.fin_utc)
    if resultat.fin_utc < resultat.debut_utc:
        erreurs.append("fin_utc : antérieure au début")
    numeros = [controle.numero for controle in resultat.controles]
    if numeros != list(range(1, len(numeros) + 1)):
        erreurs.append("controles : les numéros doivent aller de 1 à n, dans l'ordre")
    somme_poids = math.fsum(controle.poids for controle in resultat.controles)
    if not math.isclose(somme_poids, 1.0, abs_tol=TOLERANCE):
        erreurs.append(f"controles : la somme des poids vaut {somme_poids:g}, elle doit valoir 1")
    score = math.fsum(controle.poids * controle.score for controle in resultat.controles)
    if not math.isclose(score, resultat.score, abs_tol=TOLERANCE):
        erreurs.append(f"score : {resultat.score:g} déclaré, {score:g} recalculé depuis les contrôles")
    reussie = resultat.arret == "termine" and all(controle.score == 1 for controle in resultat.controles)
    if reussie != resultat.reussie:
        erreurs.append(
            "reussie : vraie si et seulement si l'exécution s'est terminée normalement "
            "et que chaque contrôle a son score plein"
        )
    if resultat.arret in ("erreur_technique", "contexte_depasse", "delai_depasse") and resultat.detail_arret is None:
        erreurs.append(f"detail_arret : obligatoire pour l'arrêt {resultat.arret}")
    if ".." in Path(resultat.journal).parts:
        erreurs.append("journal : le chemin ne doit pas sortir du dossier du run")
    jetons = resultat.jetons
    entree, cache = jetons.entree, jetons.entree_en_cache
    if isinstance(entree, int) and isinstance(cache, int) and cache > entree:
        erreurs.append("jetons : la part en cache dépasse l'entrée totale")
    return erreurs


def lire_resultat(chemin: Path) -> ResultatExecution:
    """Lit un résultat d'exécution, ou lève ContratInvalide avec tous les écarts."""
    return _lire(chemin, "resultat_execution", ResultatExecution, regles_resultat)


def coherence_resultat(resultat: ResultatExecution, tache: Tache) -> list[str]:
    """Écarts entre un résultat et la tâche qu'il dit avoir exécutée."""
    if (resultat.tache.identifiant, resultat.tache.version) != (tache.identifiant, tache.version):
        return [
            f"tache : le résultat porte sur {resultat.tache.identifiant} v{resultat.tache.version}, "
            f"pas sur {tache.identifiant} v{tache.version}"
        ]
    if len(resultat.controles) != len(tache.controles):
        return [f"controles : {len(resultat.controles)} dans le résultat, {len(tache.controles)} dans la tâche"]
    erreurs: list[str] = []
    for obtenu, attendu in zip(resultat.controles, tache.controles, strict=True):
        if obtenu.famille != attendu.famille or not math.isclose(obtenu.poids, attendu.poids, abs_tol=TOLERANCE):
            erreurs.append(f"controles/{obtenu.numero} : famille ou poids différents de la tâche")
    return erreurs


# ------------------------------------------------------------------------ fiche candidat


def regles_fiche_candidat(candidat: FicheCandidat) -> list[str]:
    """Règles que le schéma de la fiche candidat ne sait pas exprimer."""
    erreurs: list[str] = []
    hors_classement = candidat.origine in ("temoin", "humain")
    if hors_classement != (candidat.division is None):
        erreurs.append("division : vide pour un témoin ou un humain, renseignée pour tout autre candidat")
    if hors_classement and candidat.modeles != []:
        erreurs.append("modeles : un témoin ou un humain n'appelle aucun modèle")
    if candidat.origine == "humain" and candidat.cout_mesurable:
        erreurs.append("cout_mesurable : faux pour un humain, qui ne consomme aucun jeton")
    if candidat.origine == "pret_a_l_emploi" and candidat.conditions_utilisation is None:
        erreurs.append("conditions_utilisation : obligatoires pour un produit prêt à l'emploi")
    if candidat.origine != "pret_a_l_emploi" and candidat.conditions_utilisation is not None:
        erreurs.append("conditions_utilisation : sans objet pour un candidat fait main, un témoin ou un humain")
    return erreurs


def lire_fiche_candidat(chemin: Path) -> FicheCandidat:
    """Lit une fiche candidat, ou lève ContratInvalide avec tous les écarts."""
    return _lire(chemin, "fiche_candidat", FicheCandidat, regles_fiche_candidat)


def raisons_non_classable(candidat: FicheCandidat) -> list[str]:
    """Pourquoi un candidat ne peut pas figurer dans un classement ; liste vide s'il le peut."""
    raisons: list[str] = []
    if candidat.origine == "temoin":
        raisons.append("témoin : sert à vérifier le banc, jamais classé")
    if candidat.origine == "humain":
        raisons.append("humain : la référence humaine du poste humain, jamais classée")
    if candidat.branchement == "aucun":
        raisons.append("non évaluable : aucun branchement possible")
    conditions = candidat.conditions_utilisation
    if candidat.origine == "pret_a_l_emploi" and (conditions is None or conditions.publication_permise != "oui"):
        raisons.append("publication des résultats non permise ou non vérifiée")
    return raisons


# ------------------------------------------------------------------- sortie d'un candidat


def regles_sortie_candidat(sortie: SortieCandidat) -> list[str]:
    """Une fin anormale s'explique, et une consommation suppose au moins un appel de modèle."""
    erreurs: list[str] = []
    if sortie.fin in ("tours_max", "erreur", "contexte_depasse", "delai_depasse") and not sortie.detail:
        erreurs.append(f"detail : obligatoire quand fin vaut « {sortie.fin} »")
    if sortie.consommation and sortie.appels_modele == 0:
        erreurs.append("consommation : des jetons consommés sans aucun appel de modèle")
    return erreurs


def lire_sortie_candidat(chemin: Path) -> SortieCandidat:
    """Lit la sortie d'un candidat externe, ou lève ContratInvalide avec tous les écarts."""
    return _lire(chemin, "sortie_candidat", SortieCandidat, regles_sortie_candidat)
