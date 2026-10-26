# Généré depuis 01_contrats/fiche_de_run.schema.json par make contrats.
# Ne pas modifier à la main : modifier le schéma, puis régénérer.

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

type RaisonInterruption = Annotated[str, Field(min_length=1)]


type Inconnu = Literal["?"]
"""
Valeur inconnue ; le rapport la montre comme telle.
"""


type Empreinte = Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
"""
Empreinte sha256, préfixée par « sha256: ».
"""


type HorodatageUTC = AwareDatetime
"""
Date et heure en UTC, au format RFC 3339 (par exemple 2026-11-03T14:00:00Z).
"""


type IdentifiantRun = Annotated[
    str, Field(pattern="^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9_]+$")
]
"""
Date de début du run en UTC, puis un nom ; c'est aussi le nom du dossier du run.
"""


class Code(BaseModel):
    """
    Version du code qui a produit le run.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    commit: Annotated[str, Field(pattern="^[0-9a-f]{40}$")]
    """
    Commit git complet.
    """
    modifications_non_commitees: bool
    """
    Vrai si le dépôt avait des modifications non commitées : le run n'est alors pas rejouable à l'identique.
    """


class ReferenceCandidat(BaseModel):
    """
    Fiche candidat utilisée pour ce run.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    identifiant: Annotated[str, Field(pattern="^[a-z0-9_]+$")]
    version: Annotated[str, Field(min_length=1)]


type EntreeEnCacheDollarsParMillion = Annotated[float, Field(ge=0.0)]


class Tarif(BaseModel):
    """
    Prix appliqués au calcul du coût, recopiés avec leur source pour qu'un coût publié se recalcule sans dépendre des prix du jour.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    entree_dollars_par_million: Annotated[float, Field(ge=0.0)]
    entree_en_cache_dollars_par_million: EntreeEnCacheDollarsParMillion | Inconnu
    sortie_dollars_par_million: Annotated[float, Field(ge=0.0)]
    source: Annotated[str, Field(min_length=1)]
    """
    Adresse ou nom de la source des prix.
    """
    releve_le: date
    """
    Date du relevé des prix.
    """


type VersionRenvoyee = Annotated[str, Field(min_length=1)]


class Modele(BaseModel):
    """
    Un modèle appelé pendant le run.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    role: Annotated[str, Field(pattern="^[a-z_]+$")]
    """
    Rôle du modèle dans l'orchestration, par exemple agent ou superviseur.
    """
    nom: Annotated[str, Field(min_length=1)]
    """
    Nom du modèle demandé.
    """
    fournisseur: Annotated[str, Field(min_length=1)]
    """
    Fournisseur de l'API, ou local.
    """
    version_renvoyee: VersionRenvoyee | Inconnu
    parametres: dict[str, float | str | bool | None]
    """
    Réglages d'appel : température, nombre maximal de jetons, effort de raisonnement.
    """
    tarif: Tarif | None


class Configuration(BaseModel):
    """
    Configuration exacte du candidat pendant ce run.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    modeles: list[Modele]
    """
    Modèles appelés ; liste vide pour un témoin qui n'appelle aucun modèle.
    """


class TacheDuJeu(BaseModel):
    """
    Une tâche du jeu, avec la version mesurée et, si elle en a un, l'empreinte de son complément d'état.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    identifiant: Annotated[str, Field(pattern="^[a-z0-9_]+$")]
    version: Annotated[int, Field(ge=1)]
    empreinte_complement: Empreinte | None = None
    """
    Empreinte du complément d'état propre à la tâche (étape 4) ; null ou absent si elle n'en a pas.
    """


class JeuDeTaches(BaseModel):
    """
    Jeu de tâches identifié par la liste de ses tâches, leurs versions et une empreinte.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    nom: Annotated[str, Field(pattern="^[a-z0-9_]+$")]
    """
    Nom du jeu, par exemple public.
    """
    taches: Annotated[list[TacheDuJeu], Field(min_length=1)]
    empreinte: Empreinte


type Societe = Annotated[str, Field(pattern="^[a-z][a-z0-9_]*$")]
"""
Société fictive de l'état (ADR 0006) ; null : terrain qui n'est pas une société (tau2). Absent des fiches écrites avant la seconde société, toutes de Calorelle.
"""


class EtatPME(BaseModel):
    """
    État initial de la PME chargé avant chaque exécution.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Annotated[str, Field(pattern="^v[0-9]+$")]
    empreinte: Empreinte
    societe: Societe | None = None
    """
    Société fictive de l'état (ADR 0006) ; null : terrain qui n'est pas une société (tau2). Absent des fiches écrites avant la seconde société, toutes de Calorelle.
    """


class JugeDuRun(BaseModel):
    """
    Le juge étalonné d'EASE (étape 4) : son modèle, la version de sa grille, et le nombre d'avis qu'il rend au plus quand le premier ne dit pas vrai.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    modele: Annotated[str, Field(min_length=1)]
    grille: Annotated[str, Field(min_length=1)]
    avis: Annotated[int | None, Field(ge=1)] = None
    """
    Avis au plus quand le premier ne dit pas vrai, faux ou illisible, la majorité tranchant (JOURNAL, 161e et 168e entrées) ; absent, un seul avis, comme dans les runs d'avant le 2026-10-15 au soir.
    """


type Fournisseur = Annotated[str, Field(min_length=1)]
"""
null sans modèle.
"""


type CoutDollars = Annotated[float, Field(ge=0.0)]
"""
Coût du simulateur sur tout le run, calculé par EASE avec le tarif ; null sans modèle ou tant que le run n'est pas fini.
"""


type CoutAnnonceDollars = Annotated[float, Field(ge=0.0)]
"""
Coût annoncé par le fournisseur dans ses réponses, s'il en annonce un ; « ? » s'il manque à une réponse ; null sans modèle ou tant que le run n'est pas fini.
"""


type Entree = Annotated[int, Field(ge=0)]


type EntreeEnCache = Annotated[int, Field(ge=0)]


type Sortie = Annotated[int, Field(ge=0)]


type DontReflexion = Annotated[int, Field(ge=0)]
"""
Jetons de réflexion compris dans la sortie, tels que l'API les donne (completion_tokens_details.reasoning_tokens) ; « ? » s'ils manquent à une réponse.
"""


class JetonsSimulateur(BaseModel):
    """
    Jetons consommés par le simulateur d'utilisateur ; la réflexion compte en sortie, et dont_reflexion en donne la part.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    entree: Entree | Inconnu
    entree_en_cache: EntreeEnCache | Inconnu
    sortie: Sortie | Inconnu
    dont_reflexion: DontReflexion | Inconnu
    """
    Jetons de réflexion compris dans la sortie, tels que l'API les donne (completion_tokens_details.reasoning_tokens) ; « ? » s'ils manquent à une réponse.
    """


class ReglesGardien(BaseModel):
    """
    Version des règles du gardien (étape 4).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Annotated[str, Field(min_length=1)]
    empreinte: Empreinte


class Machine(BaseModel):
    """
    Machine qui sert un modèle local. Chaque champ vaut « ? » si inconnu.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    systeme: Annotated[str, Field(min_length=1)]
    processeur: Annotated[str, Field(min_length=1)]
    carte_graphique: Annotated[str, Field(min_length=1)]
    service_modele: Annotated[str, Field(min_length=1)]
    """
    Logiciel qui sert le modèle et sa version, par exemple vLLM.
    """


class SimulateurDuRun(BaseModel):
    """
    Celui qui joue le client face à l'agent : un modèle, payé à part du candidat, ou un utilisateur sans modèle (écrit d'avance, rejoué).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    modele: Annotated[str, Field(min_length=1)]
    """
    Nom du modèle au format de litellm, par exemple openrouter/google/gemini-2.5-flash ; ecrit_d_avance ou rejoue:<agent> sans modèle.
    """
    fournisseur: Fournisseur | None
    """
    null sans modèle.
    """
    parametres: dict[str, Any]
    """
    Réglages envoyés au modèle à chaque appel, tels quels.
    """
    tarif: Tarif | None
    """
    null sans modèle.
    """
    jetons: JetonsSimulateur | None
    """
    Jetons du simulateur sur tout le run, lus dans les réponses de son API ; null sans modèle ou tant que le run n'est pas fini.
    """
    cout_dollars: CoutDollars | Inconnu | None
    """
    Coût du simulateur sur tout le run, calculé par EASE avec le tarif ; null sans modèle ou tant que le run n'est pas fini.
    """
    cout_annonce_dollars: CoutAnnonceDollars | Inconnu | None
    """
    Coût annoncé par le fournisseur dans ses réponses, s'il en annonce un ; « ? » s'il manque à une réponse ; null sans modèle ou tant que le run n'est pas fini.
    """


class BancPublic(BaseModel):
    """
    Un banc public d'agents construit par d'autres (ADR 0004), servi à EASE par MCP : ce qu'il faut pour rejouer le run et le comparer aux scores publiés.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    nom: Annotated[str, Field(pattern="^[a-z0-9_]+$")]
    """
    Nom du banc, par exemple tau2_bench.
    """
    version: Annotated[str, Field(min_length=1)]
    """
    Version du paquet du banc installée par uv.lock, par exemple 1.0.1.
    """
    domaine: Annotated[str, Field(pattern="^[a-z0-9_]+$")]
    """
    Domaine du banc, par exemple airline.
    """
    jeu: Annotated[str, Field(pattern="^[a-z0-9_]+$")]
    """
    Jeu de tâches du domaine, par exemple verified.
    """
    simulateur: SimulateurDuRun


class FicheDeRun(BaseModel):
    """
    Une campagne de mesure : un candidat passé sur un jeu de tâches, chaque tâche répétée k fois. Elle permet de rejouer le run (règle 1 du BRIEF). « ? » signifie inconnu, et le rapport le montre ; null signifie sans objet. EASE vérifie au chargement ce que le schéma ne sait pas exprimer : statut et fin cohérents, dates en UTC, date de l'identifiant.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    identifiant: IdentifiantRun
    debut_utc: HorodatageUTC
    fin_utc: HorodatageUTC | None
    statut: Literal["en_cours", "termine", "interrompu"]
    raison_interruption: RaisonInterruption | None
    code: Code
    candidat: ReferenceCandidat
    configuration: Configuration
    empreinte_prompts: Empreinte | Inconnu | None
    """
    Empreinte des prompts ; null pour un candidat sans prompt.
    """
    jeu_taches: JeuDeTaches
    etat_pme: EtatPME
    regles_gardien: ReglesGardien | None
    repetitions: Annotated[int, Field(ge=1)]
    """
    Nombre de répétitions de chaque tâche.
    """
    machine: Machine | None
    juge: JugeDuRun | None = None
    """
    Le juge qui a tranché les vérifications juge_requis ; null : aucun juge. Absent des runs d'avant le juge (étape 4).
    """
    banc_public: BancPublic | None = None
    """
    Le banc public sur lequel le candidat a été mesuré, hors de la PME (étape 7) ; null ou absent : un run de la PME. etat_pme porte alors la version et l'empreinte des données du banc.
    """
