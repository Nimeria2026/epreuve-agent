"""La grille de la durée humaine estimée : le temps d'un employé du métier qui sait déjà quoi faire,
sur le chemin du témoin parfait (cadrage de l'horizon de temps, suite du 2026-10-14 ; JOURNAL,
cent-vingt-cinquième entrée). Une borne basse : ni hésitation, ni vérification, ni erreur, ni
attente des pages ; jamais une durée mesurée.

Quatre parts, en secondes :

- lire : courriels, documents en prose et sections du manuel dont la tâche se sert, à 238 mots par
  minute (Brysbaert, 2019, lecture silencieuse d'un texte documentaire en anglais) ;
- chercher : listes et tableaux balayés pour trouver une ligne, à 667 mots par minute (le balayage
  que cite Brysbaert, d'après une estimation de presse ; source faible) ;
- écrire : textes libres (corps, objet, commentaire, motif), à 19 mots par minute (Karat,
  Halverson, Horn et Karat, 1999, composition au clavier, cités par Human Factors International) ;
- agir : chaque ouverture et chaque geste au modèle KLM (Card, Moran et Newell, 1980) : 1,35 s de
  préparation, 1,1 s par pointage, 0,28 s par touche.

Le manuel s'ouvre une fois par tâche et ne compte que pour ses sections utiles (choix G1
d'Alexandre), que le témoin l'ait lu ou non ; ses lectures par le témoin ne comptent pas en plus. Un
outil que la grille ne connaît pas est refusé, jamais classé en silence. Le classer change la version
de la grille s'il change une durée déjà estimée ; les outils d'une société nouvelle, dont aucune
tâche estimée ne se sert, s'ajoutent à la même version.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

VERSION = "1"

MOTS_LUS_PAR_MINUTE = 238.0
MOTS_BALAYES_PAR_MINUTE = 667.0
MOTS_ECRITS_PAR_MINUTE = 19.0
PREPARATION_S = 1.35
POINTAGE_S = 1.1
TOUCHE_S = 0.28
OUVRIR_S = PREPARATION_S + POINTAGE_S + TOUCHE_S
"""Ouvrir un courriel, un document ou une liste : préparer, pointer, cliquer."""

MANUEL = "commun/manuel_procedures.md"
OUTILS_LUS = frozenset(
    {
        "lire",
        "lire_courriel",
        "consulter_devis",
        "consulter_fournisseur",
        "consulter_client",
        "consulter_article",
        "consulter_commande",
        "consulter_livraison",
    }
)
OUTILS_BALAYES = frozenset(
    {
        "lister",
        "lister_boites",
        "lister_courriels",
        "lister_devis",
        "lister_techniciens",
        "consulter_tarif",
        "consulter_planning",
        "chercher_creneaux",
        "consulter_compte_client",
        "chercher_articles",
        "lister_commandes",
    }
)
DOCUMENTS_BALAYES = frozenset(
    {
        "clients/liste_clients.md",
        "administration/echeancier_fournisseurs.md",
        "commun/annuaire.md",
        "rh/conges_2026.txt",
        "commun/immeubles.md",
        "clients/liste.csv",
        "comptabilite/echeancier_fournisseurs.csv",
    }
)
MOTIFS_BALAYES = (
    "gerance/*/registre.yaml",
    "coproprietes/*/coproprietaires.csv",
    "proprietaires/liste_*.csv",
    "comptabilite/releves/*.csv",
)
"""Les listes de Domivelle qui se déclinent par immeuble, par copropriété ou par secteur (JOURNAL,
cent-cinquante-cinquième entrée), et les relevés de banque mensuels de Négovelle (JOURNAL,
cent-quatre-vingt-onzième entrée) ; aucun chemin de Calorelle n'y répond, ses durées ne changent
pas."""


def balaye(chemin: str) -> bool:
    """Vrai pour une liste ou un tableau qu'on balaie pour trouver une ligne."""
    return chemin in DOCUMENTS_BALAYES or any(fnmatch(chemin, motif) for motif in MOTIFS_BALAYES)


OUTILS_ACTIONS = frozenset(
    {
        "transferer",
        "repondre",
        "envoyer",
        "enregistrer_piece_jointe",
        "deplacer",
        "copier",
        "modifier_rib_fournisseur",
        "emettre_avoir",
        "creer_devis",
        "enregistrer_envoi",
        "abandonner_devis",
        "enregistrer_reponse",
        "planifier_intervention",
        "deplacer_intervention",
        "annuler_intervention",
        "creer_commande",
        "modifier_commande",
        "valider_commande",
        "debloquer_commande",
        "accorder_prix",
        "livrer_a_une_adresse_ponctuelle",
        "enregistrer_retour",
        "bloquer_client",
    }
)
"""Les fiches que l'employé lit, les listes qu'il balaie et les gestes du service de ventes de
Négovelle s'y ajoutent sans changer la version de la grille (JOURNAL, cent-quatre-vingt-onzième
entrée) : aucune tâche de Calorelle ni de Domivelle ne s'en sert, leurs durées ne changent pas."""
CHAMPS_LIBRES = frozenset({"texte", "commentaire", "objet", "motif"})
"""Textes composés par l'employé : ils passent au temps d'écrire."""
CHAMPS_PRE_REMPLIS = frozenset({"boite", "identifiant"})
"""Remplis par la page du courriel d'où part le geste."""


class OutilInconnu(ValueError):
    """Un outil que la grille ne classe pas : à classer, avec une nouvelle version de la grille si une
    durée déjà estimée en change."""


@dataclass(frozen=True)
class Parts:
    """Les quatre parts d'une durée estimée, en secondes."""

    lire: float = 0.0
    chercher: float = 0.0
    ecrire: float = 0.0
    agir: float = 0.0

    def __add__(self, autre: Parts) -> Parts:
        return Parts(
            self.lire + autre.lire,
            self.chercher + autre.chercher,
            self.ecrire + autre.ecrire,
            self.agir + autre.agir,
        )

    @property
    def total(self) -> float:
        return self.lire + self.chercher + self.ecrire + self.agir


@dataclass(frozen=True)
class Appel:
    """Un appel d'outil du témoin, tel que son journal le garde."""

    outil: str
    arguments: Mapping[str, Any]
    resultat: str


def mots(texte: str) -> int:
    return len(texte.split())


def sections(texte_manuel: str, numeros: Iterable[int]) -> str:
    """Le texte des sections du manuel aux numéros donnés, titres compris ; une section absente est
    refusée."""
    par_numero: dict[int, str] = {}
    for bloc in re.split(r"(?m)^## ", texte_manuel)[1:]:
        numero = re.match(r"(\d+)\.", bloc)
        if numero is not None:
            par_numero[int(numero.group(1))] = "## " + bloc.rstrip()
    voulus = sorted(set(numeros))
    absents = [n for n in voulus if n not in par_numero]
    if absents:
        raise ValueError(f"section(s) absente(s) du manuel : {', '.join(map(str, absents))}")
    return "\n\n".join(par_numero[n] for n in voulus)


def _saisie(cle: str, valeur: object) -> Parts:
    """Remplir un champ : le pointer et cliquer, puis taper sa valeur, ou la composer si c'est un
    texte libre ; une liste ou un objet se remplit élément par élément."""
    if isinstance(valeur, Mapping):
        total = Parts()
        for sous_cle, sous_valeur in valeur.items():  # pyright: ignore[reportUnknownVariableType]
            total += _saisie(str(sous_cle), sous_valeur)  # pyright: ignore[reportUnknownArgumentType]
        return total
    if isinstance(valeur, list):
        total = Parts()
        for element in valeur:  # pyright: ignore[reportUnknownVariableType]
            total += _saisie(cle, element)  # pyright: ignore[reportUnknownArgumentType]
        return total
    if valeur is None or valeur == "":
        return Parts()
    pointer = POINTAGE_S + TOUCHE_S
    if isinstance(valeur, bool):
        return Parts(agir=pointer)
    texte = str(valeur)
    if cle in CHAMPS_LIBRES:
        return Parts(ecrire=mots(texte) / MOTS_ECRITS_PAR_MINUTE * 60, agir=pointer)
    return Parts(agir=pointer + len(texte) * TOUCHE_S)


def geste(arguments: Mapping[str, Any]) -> Parts:
    """Un geste : préparer, remplir chaque champ que la page ne remplit pas, puis valider."""
    total = Parts(agir=PREPARATION_S + POINTAGE_S + TOUCHE_S)
    for cle, valeur in arguments.items():
        if cle not in CHAMPS_PRE_REMPLIS:
            total += _saisie(cle, valeur)
    return total


def estimer(appels: Iterable[Appel], texte_manuel: str, sections_manuel: Iterable[int]) -> Parts:
    """La durée estimée d'un chemin d'appels, avec les sections utiles du manuel lues une fois."""
    utiles = sections(texte_manuel, sections_manuel)
    total = Parts(lire=mots(utiles) / MOTS_LUS_PAR_MINUTE * 60, agir=OUVRIR_S if utiles else 0.0)
    for appel in appels:
        if appel.outil in OUTILS_LUS:
            chemin = str(appel.arguments.get("chemin", ""))
            if appel.outil == "lire" and chemin == MANUEL:
                continue
            if appel.outil == "lire" and balaye(chemin):
                total += Parts(chercher=mots(appel.resultat) / MOTS_BALAYES_PAR_MINUTE * 60, agir=OUVRIR_S)
            else:
                total += Parts(lire=mots(appel.resultat) / MOTS_LUS_PAR_MINUTE * 60, agir=OUVRIR_S)
        elif appel.outil in OUTILS_BALAYES:
            total += Parts(chercher=mots(appel.resultat) / MOTS_BALAYES_PAR_MINUTE * 60, agir=OUVRIR_S)
        elif appel.outil in OUTILS_ACTIONS:
            total += geste(appel.arguments)
        else:
            raise OutilInconnu(f"outil que la grille {VERSION} ne classe pas : {appel.outil}")
    return total
