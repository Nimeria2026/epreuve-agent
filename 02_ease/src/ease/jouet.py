"""Environnement jouet de l'étape 1 : un classeur de documents, trois outils, deux tâches.

Il sert à vérifier le banc avec les témoins, sans la PME. Ses tâches suivent le contrat de tâche
et passent par le même vérificateur que celles de la PME (ease.verification) : son état se
présente comme celui des dossiers partagés. Ses solutions et ses erreurs, connues d'avance, ne
servent qu'aux témoins (ease.temoins). Tout est fictif.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ease.contrats.tache import Tache
from ease.empreintes import empreinte_json
from ease.etat_pme import Instantane, empreinte_octets
from ease.executeur import DescriptionOutil, ErreurOutil

type Actions = list[tuple[str, dict[str, Any]]]
"""Gestes d'un témoin : (outil, arguments), dans l'ordre."""

ETAT_INITIAL: dict[str, str] = {
    "arrivee/facture_0412.txt": "Facture n° 0412 de Papeterie du Val, datée du 14/10/2026, 186,00 € TTC. FICTIF",
    "arrivee/note_interne.txt": "Note interne : réunion d'équipe jeudi à 8 h. FICTIF",
    "factures/2026-09/facture_0388.txt": "Facture n° 0388 de Papeterie du Val, datée du 22/09/2026. FICTIF",
    "devis/devis_2026-031.txt": "Devis 2026-031 du 03/03/2026, remplacement de chaudière, 4 200,00 € HT. FICTIF",
    "devis/devis_2026-007.txt": "Devis 2026-007 du 19/01/2026, entretien annuel, 160,00 € HT. FICTIF",
    "devis/devis_2026-054.txt": "Devis 2026-054 du 28/05/2026, climatisation, 7 850,00 € HT. FICTIF",
}


class ClasseurJouet:
    """Un classeur de documents texte rangés par dossiers. Chemins relatifs, séparés par « / »."""

    def __init__(self) -> None:
        self._fichiers: dict[str, str] = dict(ETAT_INITIAL)

    @property
    def version(self) -> str:
        return "v1"

    def empreinte(self) -> str:
        return empreinte_json(ETAT_INITIAL)

    @property
    def regles_gardien(self) -> None:
        return None

    def empreinte_complement(self, tache: Tache) -> None:
        del tache  # le jouet n'a pas de complément d'état
        return None

    def ouvrir(self, tache: Tache) -> None:
        del tache  # un seul classeur, le même pour toutes les tâches jouets
        self._fichiers = dict(ETAT_INITIAL)

    def fermer(self) -> None:
        pass

    def preambule(self) -> str | None:
        return None  # le classeur jouet n'a pas d'horloge

    def etat(self) -> Instantane:
        return Instantane(fichiers={c: empreinte_octets(v.encode("utf-8")) for c, v in self._fichiers.items()})

    def outils(self) -> list[DescriptionOutil]:
        return [
            _outil("lister", "Liste les documents d'un dossier.", dossier="chemin du dossier"),
            _outil("lire", "Renvoie le texte d'un document.", chemin="chemin du document"),
            _outil(
                "deplacer",
                "Déplace un document dans un dossier, sous le même nom ; le dossier est créé au besoin.",
                source="chemin du document",
                destination="chemin du dossier d'arrivée",
            ),
        ]

    def appeler(self, nom: str, arguments: Mapping[str, Any], lecture_seule: bool = False) -> Any:
        del lecture_seule  # le jouet n'a aucun effet de bord en lisant
        parametres = {outil.nom: set(outil.parametres) for outil in self.outils()}
        if nom not in parametres:
            raise ErreurOutil(f"outil inconnu : {nom}")
        if set(arguments) != parametres[nom] or not all(isinstance(v, str) for v in arguments.values()):
            raise ErreurOutil(f"{nom} attend les paramètres texte {sorted(parametres[nom])}")
        if nom == "lister":
            prefixe = arguments["dossier"].strip("/") + "/"
            return sorted(c for c in self._fichiers if c.startswith(prefixe) and "/" not in c[len(prefixe) :])
        if nom == "lire":
            return self._document(arguments["chemin"])
        source = arguments["source"]
        contenu = self._document(source)
        arrivee = arguments["destination"].strip("/") + "/" + source.rsplit("/", 1)[-1]
        if arrivee in self._fichiers:
            raise ErreurOutil(f"un document existe déjà : {arrivee}")
        del self._fichiers[source]
        self._fichiers[arrivee] = contenu
        return arrivee

    def _document(self, chemin: str) -> str:
        if chemin not in self._fichiers:
            raise ErreurOutil(f"document introuvable : {chemin}")
        return self._fichiers[chemin]


def _outil(nom: str, description: str, **parametres: str) -> DescriptionOutil:
    """Un outil dont tous les arguments sont du texte, obligatoires."""
    schema = {
        "type": "object",
        "properties": {p: {"type": "string", "description": d} for p, d in parametres.items()},
        "required": list(parametres),
        "additionalProperties": False,
    }
    return DescriptionOutil(nom, description, schema)


def _tache(identifiant: str, enonce: str, etape: str, attendu: str, piege: str, origine: str, arrivee: str) -> Tache:
    return Tache.model_validate(
        {
            "identifiant": identifiant,
            "version": 1,
            "famille": "administration",
            "agent_pour": "jouet",
            "enonce": enonce,
            "etat_initial": "v1",
            "services": ["classeur"],
            "budget": {"etapes_max": 8, "cout_max_dollars": 0.05},
            "controles": [
                {
                    "famille": "resultat",
                    "etape": etape,
                    "poids": 0.7,
                    "attendu": attendu,
                    "notation": "tout_ou_rien",
                    "verification": [
                        {"type": "fichier_present", "chemin": arrivee, "identique_au_fichier": origine},
                        {"type": "fichier_absent", "chemin": origine},
                    ],
                },
                {
                    "famille": "absence_effet_de_bord",
                    "etape": "rien d'autre n'a changé",
                    "poids": 0.3,
                    "attendu": "tous les autres documents sont à leur place et inchangés ; aucun document en plus",
                    "notation": "tout_ou_rien",
                    "verification": [{"type": "aucun_autre_changement_de_fichier", "sauf": [origine, arrivee]}],
                },
            ],
            "pieges": [piege],
        }
    )


TACHES_JOUET: list[Tache] = [
    _tache(
        "j01_ranger_facture",
        "Une facture est arrivée dans le dossier arrivee/. Range-la dans le dossier factures/ du mois "
        "de sa date (par exemple factures/2026-09), sans toucher aux autres documents.",
        "la facture est rangée dans le dossier de son mois",
        "factures/2026-10/facture_0412.txt existe avec le contenu d'origine et a quitté arrivee/",
        "une note interne attend aussi dans arrivee/ et ne doit pas bouger",
        "arrivee/facture_0412.txt",
        "factures/2026-10/facture_0412.txt",
    ),
    _tache(
        "j02_archiver_devis",
        "Déplace le devis le plus ancien du dossier devis/ vers le dossier archives/. La date de chaque "
        "devis est écrite dans le document.",
        "le devis le plus ancien est archivé",
        "archives/devis_2026-007.txt existe avec le contenu d'origine et a quitté devis/",
        "la date se lit dans le document",
        "devis/devis_2026-007.txt",
        "archives/devis_2026-007.txt",
    ),
]

# Solutions écrites à la main, pour le témoin parfait.
SOLUTIONS_JOUET: dict[str, Actions] = {
    "j01_ranger_facture": [
        ("lister", {"dossier": "arrivee"}),
        ("lire", {"chemin": "arrivee/facture_0412.txt"}),
        ("deplacer", {"source": "arrivee/facture_0412.txt", "destination": "factures/2026-10"}),
    ],
    "j02_archiver_devis": [
        ("lister", {"dossier": "devis"}),
        ("lire", {"chemin": "devis/devis_2026-007.txt"}),
        ("lire", {"chemin": "devis/devis_2026-031.txt"}),
        ("lire", {"chemin": "devis/devis_2026-054.txt"}),
        ("deplacer", {"source": "devis/devis_2026-007.txt", "destination": "archives"}),
    ],
}

# Mauvaises actions, pour le témoin toujours faux : la mauvaise cible, plus un effet de bord,
# pour que chaque contrôle échoue.
ERREURS_JOUET: dict[str, Actions] = {
    "j01_ranger_facture": [
        ("deplacer", {"source": "arrivee/facture_0412.txt", "destination": "factures/2026-09"}),
        ("deplacer", {"source": "arrivee/note_interne.txt", "destination": "factures/2026-10"}),
    ],
    "j02_archiver_devis": [
        ("deplacer", {"source": "devis/devis_2026-054.txt", "destination": "archives"}),
        ("deplacer", {"source": "devis/devis_2026-031.txt", "destination": "archives"}),
    ],
}
