"""Le rapport d'une campagne, remis à l'entreprise qui a fait mesurer son agent (cadrage des
interventions, annexe C ; JOURNAL, entrée 316).

    make rapport-campagne CANDIDATS=campagne_<nom>[,<référence>] [REPETITIONS=5] [GARDIEN=1]

Le rapport d'EASE (make rapport) est écrit pour le constat public. Celui-ci est écrit pour
l'entreprise, en Markdown, pour se compléter à la main. Il tire des runs de la campagne ce qui se
calcule : ce qui a été mesuré, les quatre réponses chiffrées avec leurs marges, les échecs tâche par
tâche avec les gestes de l'agent, les runs. Il écrit une fois pour toutes ce qui se dit de la même
façon à chaque entreprise : les limites de la mesure et ce qu'elle ne dit pas. Restent à écrire à
la main les passages marqués « À écrire » : la réponse en bref, la lecture et les recommandations.

Le premier candidat est l'agent de l'entreprise ; les suivants sont les références du poste. Le
rapport s'écrit dans 99_local/rapports/, que la clôture supprime avec la campagne, et ne remplace
jamais un rapport existant : un rapport complété à la main ne se perd pas.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ease.candidats import declarations, lire_candidat
from ease.chargement import racine_depot
from ease.contrats.resultat_execution import ResultatExecution
from ease.contrats.tache import Tache
from ease.gabarit import SOCIETE as GABARIT
from ease.gabarit import de, lire_monde
from ease.gravite import Gravite, fautes_graves, lire_gravite, numeros_graves
from ease.rapport import (
    GRAINE,
    TIRAGES,
    Bilan,
    Mesures,
    RapportImpossible,
    faire_bilan,
    nom_de_la_pme,
    planchers,
    rassembler,
)
from ease.taches import JEUX, dossier_du_jeu, taches_du_jeu

A_ECRIRE = "**À écrire.**"
LECTURES = ("lire", "lister", "consulter", "chercher", "rechercher", "voir", "obtenir")
"""Les préfixes des outils qui ne font que lire ; les autres sont des gestes de l'agent."""
GESTES_MAX = 3
TEXTE_MAX = 160


@dataclass(frozen=True)
class Contexte:
    """Ce que le rapport dit de la campagne, hors des runs."""

    campagne: str
    entreprise: str
    pme: str
    metier: str | None
    jour: str


def _fiche_de_campagne(racine: Path) -> Path | None:
    fiches = sorted((racine / "00_docs" / "sources").glob("*_campagne_*.md"))
    return fiches[-1] if fiches else None


def contexte(racine: Path, jeu: str, taches: list[Tache], jour: str) -> Contexte:
    """La campagne et l'entreprise, lues dans la fiche de la campagne ; la société fictive, dans les
    variables du gabarit (ou l'état de la société pour un autre jeu)."""
    fiche = _fiche_de_campagne(racine)
    campagne, entreprise = "?", "?"
    if fiche is not None:
        campagne = fiche.stem.split("_campagne_", 1)[1]
        ligne = re.search(r"^\| Entreprise \| (.*?) \|$", fiche.read_text(encoding="utf-8"), re.MULTILINE)
        entreprise = ligne.group(1).strip() if ligne else "?"
    if jeu == GABARIT:
        monde = lire_monde()
        return Contexte(campagne, entreprise, monde.nom, monde.metier, jour)
    return Contexte(campagne, entreprise, nom_de_la_pme(taches), None, jour)


# --- les nombres -----------------------------------------------------------------------------


def que(nom: str) -> str:
    """« que » devant un nom, élidé devant une voyelle ou un h."""
    return f"qu'{nom}" if de(nom).startswith("d'") else f"que {nom}"


def pourcent(valeur: float) -> str:
    return f"{valeur * 100:.0f} %"


def marge(intervalle: tuple[float, float]) -> str:
    return f"de {pourcent(intervalle[0])} à {pourcent(intervalle[1])}"


def dollars(valeur: float) -> str:
    return f"{valeur:.4f}".replace(".", ",") + " $"


def secondes(valeur: float) -> str:
    return f"{valeur:.0f} s" if valeur < 120 else f"{valeur / 60:.1f}".replace(".", ",") + " min"


# --- les gestes de l'agent -------------------------------------------------------------------


def _court(valeur: object) -> str:
    texte = valeur if isinstance(valeur, str) else json.dumps(valeur, ensure_ascii=False)
    texte = " ".join(texte.split())
    return texte if len(texte) <= TEXTE_MAX else texte[: TEXTE_MAX - 1] + " [coupé]"


def gestes(mesures: Mesures, resultat: ResultatExecution) -> list[str]:
    """Les gestes de l'exécution, ses appels qui ne font pas que lire, les premiers d'abord, ou ce
    qu'il faut dire s'il n'y en a aucun."""
    journal = mesures.sources[resultat.tache.identifiant].dossier / resultat.journal
    if not journal.is_file():
        return ["(journal absent)"]
    appels = [
        cast(dict[str, Any], json.loads(ligne))
        for ligne in journal.read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]
    actes = [a for a in appels if not str(a.get("outil", "")).startswith(LECTURES)]
    if not actes:
        return [f"aucun geste : {len(appels)} lecture(s), rien d'envoyé, de rangé ni de modifié"]
    lignes: list[str] = []
    for appel in actes[:GESTES_MAX]:
        arguments = cast(dict[str, Any], appel.get("arguments") or {})
        detail = ", ".join(f"{cle} : {_court(valeur)}" for cle, valeur in arguments.items())
        refus = f" (refusé : {_court(appel['erreur'])})" if appel.get("erreur") else ""
        lignes.append(f"`{appel.get('outil')}` ; {detail}{refus}")
    if len(actes) > GESTES_MAX:
        lignes.append(f"et {len(actes) - GESTES_MAX} autre(s) geste(s)")
    return lignes


# --- la rédaction ----------------------------------------------------------------------------


def _demande(tache: Tache) -> str:
    """L'énoncé, sans la phrase qui dit pour qui l'agent travaille."""
    return re.sub(r"^Tu es l'assistant[^.]*\.\s*", "", " ".join(tache.enonce.split()))


def _graves_de(tache: Tache, gravite: Gravite) -> str:
    graves = numeros_graves(tache, gravite)
    if not graves:
        return "aucun"
    return " ; ".join(f"{tache.controles[n - 1].etape} ({c})" for n, c in graves.items())


def _reponses(mesures: list[Mesures], bilans: list[Bilan], repetitions: int) -> list[str]:
    noms = " | ".join(m.nom for m in mesures)
    separation = "|".join(["---"] * (len(mesures) + 1))
    lignes = [f"| | {noms} |", f"|{separation}|"]

    def ligne(titre: str, valeurs: list[str]) -> None:
        lignes.append(f"| {titre} | " + " | ".join(valeurs) + " |")

    ligne(
        "Réussit-il les tâches ?",
        [
            f"{b.reussites} sur {b.executions} ({pourcent(b.reussites / b.executions)}), {marge(b.taux_ic)}"
            for b in bilans
        ],
    )
    essais = f"{repetitions} essai{'s' if repetitions > 1 else ''}"
    ligne(
        f"À chaque fois ? ({essais} sur {repetitions})",
        [pourcent(b.pass_k[max(b.pass_k)]) if b.pass_k else "?" for b in bilans],
    )
    ligne(
        "Que tente-t-il de dangereux ?",
        [
            "sans objet"
            if b.graves is None or b.graves.wilson is None
            else f"{b.graves.fautives} faute(s) grave(s) sur {b.graves.exposees} ({marge(b.graves.wilson)})"
            for b in bilans
        ],
    )
    ligne(
        "Combien coûte-t-il ?",
        [
            "non mesuré (jetons non déclarés)"
            if b.dollars_par_reussite is None
            else f"{dollars(b.dollars or 0)} en tout, aucune tâche réussie"
            if b.reussites == 0
            else f"{dollars(b.dollars_par_reussite[0])} par tâche réussie ({dollars(b.dollars or 0)} en tout)"
            for b in bilans
        ],
    )
    ligne("Durée d'une exécution (médiane)", [secondes(b.duree_mediane_secondes) for b in bilans])
    ligne("Erreurs techniques (hors des chiffres)", [str(b.erreurs_techniques) for b in bilans])
    return lignes


def _section_tache(tache: Tache, mesures: list[Mesures], gravite: Gravite) -> list[str]:
    principal = mesures[0]
    lignes = [f"### {tache.identifiant}", "", _demande(tache), ""]
    for m in mesures:
        resultats = m.executions.get(tache.identifiant, [])
        reussies = sum(r.reussie for r in resultats)
        lignes.append(f"- {m.nom} : {reussies} sur {len(resultats)} réussie(s).")
    echecs = [r for r in principal.executions.get(tache.identifiant, []) if not r.reussie]
    numeros = numeros_graves(tache, gravite)
    for resultat in echecs:
        manques = [c for c in resultat.controles if c.score < 1]
        graves = fautes_graves(resultat, tache, gravite)
        entete = f"Essai {resultat.repetition} de {principal.nom}, échoué"
        if resultat.arret != "termine":
            entete += f", arrêt : {resultat.arret}"
        if graves:
            entete += f", **faute grave ({', '.join(graves)})**"
        lignes += ["", f"{entete}.", ""]
        for c in manques:
            marque = " (grave)" if c.numero in numeros else ""
            lignes.append(f"- Manqué{marque} : {tache.controles[c.numero - 1].etape}.")
        lignes.append("- Ce que l'agent a fait :")
        lignes += [f"  - {g}" for g in gestes(principal, resultat)]
    return [*lignes, ""]


def rediger(
    mesures: list[Mesures],
    taches: list[Tache],
    gravite: Gravite,
    ctx: Contexte,
    repetitions: int,
    gardien: bool,
) -> str:
    """Le rapport en Markdown ; RapportImpossible si aucune tâche n'est mesurée pour tous."""
    communes = [t.identifiant for t in taches if all(t.identifiant in m.executions for m in mesures)]
    if not communes:
        raise RapportImpossible("aucune tâche mesurée pour tous les candidats")
    retenues = [t for t in taches if t.identifiant in communes]
    bilans = [faire_bilan(m, communes, planchers(retenues), retenues, gravite) for m in mesures]
    principal, references = mesures[0], mesures[1:]
    fiche = lire_candidat(principal.identifiant).fiche if principal.identifiant in declarations() else None
    runs = sorted({r.dossier.name: r for m in mesures for r in m.sources.values()}.items())
    debut = min(r.fiche.debut_utc for _, r in runs)
    fin = max(r.fiche.fin_utc or r.fiche.debut_utc for _, r in runs)
    commits = sorted({r.fiche.code.commit[:8] for _, r in runs})
    exposees = sum(1 for t in retenues if numeros_graves(t, gravite))
    total = len(communes) * repetitions
    lignes = [
        f"# Mesure de l'agent : {principal.nom}",
        "",
        f"{ctx.entreprise} ; campagne `{ctx.campagne}` ; rapport du {ctx.jour}. Alexandre Do, Épreuve d'agent.",
        "",
        "> Avant remise : écrire les passages marqués « À écrire », relire, puis retirer cet encadré.",
        "> Le reste vient des runs de la campagne et se régénère par make rapport-campagne.",
        "",
        "## En bref",
        "",
        f"{A_ECRIRE} En trois phrases, la réponse à la question {que(ctx.entreprise)} a posée (fiche de "
        "demande) : ce que l'agent fait bien, ce qu'il manque, et le risque qui compte.",
        "",
        "## 1. Ce qui a été mesuré",
        "",
        f"- L'agent : {principal.nom}" + (f", {fiche.editeur}, version {fiche.version}." if fiche is not None else "."),
        f"- Les références : {', '.join(m.nom for m in references)}."
        if references
        else "- Les références : aucune dans ce rapport.",
        f"- Le terrain : {ctx.pme}, une société inventée"
        + (f" {de(ctx.metier)}" if ctx.metier else "")
        + f", bâtie d'après ce {que(ctx.entreprise)} a décrit de son travail. Aucune donnée réelle : les "
        "clients, les fournisseurs, les personnes et les courriels sont fictifs.",
        f"- Les conditions : {len(communes)} tâches, {repetitions} essai(s) chacune, soit {total} exécutions "
        f"par candidat ; {'derrière le gardien, qui bloque les gestes interdits' if gardien else 'sans gardien'}"
        f" ; du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} ; code {', '.join(commits)}.",
        "- La vérification : chaque tâche se juge sur l'état final de la société (fichiers, courriels,"
        " fiches), par des contrôles écrits avant la mesure ; personne ne note l'agent à la main.",
        "",
        "| Tâche | Ce qu'elle demande | Le piège | Contrôle grave |",
        "|---|---|---|---|",
    ]
    lignes += [
        f"| {t.identifiant[:4]} | {_demande(t)} | {' ; '.join(t.pieges) or 'aucun'} | {_graves_de(t, gravite)} |"
        for t in retenues
    ]
    lignes += [
        "",
        "## 2. Les quatre réponses",
        "",
        "Chaque chiffre porte sa marge à 95 % : avec si peu d'essais, elle est large, et deux chiffres",
        "dont les marges se recouvrent ne se départagent pas.",
        "",
        *_reponses(mesures, bilans, repetitions),
        "",
        f"Une faute grave est un geste que {ctx.pme} interdit, compté à part de la réussite, sur les "
        f"{exposees} tâches qui en exposent un :",
        "",
        *[
            f"- {nom} : {definition}"
            for nom, definition in gravite.categories.items()
            if any(nom in numeros_graves(t, gravite).values() for t in retenues)
        ],
        "",
        "## 3. Tâche par tâche",
        "",
        f"Pour chaque tâche, les réussites de chaque candidat ; pour chaque échec de {principal.nom}, les "
        "contrôles manqués et ses premiers gestes, tels que le journal les garde.",
        "",
    ]
    for tache in retenues:
        lignes += _section_tache(tache, mesures, gravite)
    lignes += [
        "## 4. Les limites de la mesure",
        "",
        f"- {len(communes)} tâches : un échantillon de situations, choisi avec {ctx.entreprise}, pas tout son travail.",
        f"- {repetitions} essai(s) par tâche : un agent ne refait pas toujours la même chose ; les marges"
        " disent l'incertitude qui en reste.",
        f"- Des outils fictifs : l'agent a travaillé dans {ctx.pme}, avec une messagerie, des dossiers et des "
        "fiches fictifs, branché par un relais à la place de ses outils habituels.",
        f"- L'agent tel qu'il était du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} : une autre version, un autre "
        "modèle ou d'autres consignes demandent une autre mesure.",
        "- Une obligation de moyens : la mesure dit ce que l'agent a fait ici, dans ces conditions, et rien de plus.",
        "",
        "## 5. Ce que la mesure ne dit pas",
        "",
        f"- Ce que l'agent ferait sur les vraies données {de(ctx.entreprise)}.",
        "- La qualité de son branchement aux vrais systèmes (messagerie, logiciel métier).",
        "- Ce qu'il fait gagner, en temps ou en argent : la mesure compte ses réussites et ses fautes, pas"
        " leur valeur pour l'entreprise.",
        "",
        "## 6. Lecture et recommandations",
        "",
        f"{A_ECRIRE} Ce que les échecs ont en commun ; les fautes graves, une par une ; ce qui changerait",
        "le résultat (une consigne, un garde-fou, un autre modèle) ; ce qu'il faudrait mesurer ensuite.",
        "",
        "## Annexe technique",
        "",
        "| Run | Candidat | Commit | Début (UTC) | Essais | Gardien |",
        "|---|---|---|---|---|---|",
    ]
    lignes += [
        f"| {nom} | {r.fiche.candidat.identifiant} | {r.fiche.code.commit[:8]} | {r.fiche.debut_utc:%Y-%m-%d %H:%M}"
        f" | {r.fiche.repetitions} | {'oui' if r.fiche.regles_gardien is not None else 'non'} |"
        for nom, r in runs
    ]
    tirages = f"{TIRAGES:,}".replace(",", "\u00a0")
    lignes += [
        "",
        "Marges de la réussite et du coût : bootstrap à deux niveaux (tâches, puis essais), "
        f"{tirages} tirages, graine {GRAINE}. Marges des fautes graves : intervalle de Wilson. Le rapport détaillé, "
        "avec chaque essai raconté pas à pas, se produit par make rapport, sur les mêmes runs.",
        "",
    ]
    return "\n".join(lignes)


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m ease.rapport_campagne", description=__doc__)
    analyse.add_argument("--candidats", required=True, help="l'agent de l'entreprise, puis les références")
    analyse.add_argument("--repetitions", type=int, default=5)
    analyse.add_argument("--gardien", action="store_true", help="les runs passés par le gardien")
    analyse.add_argument("--jeu", choices=JEUX, default=GABARIT)
    analyse.add_argument("--sortie", type=Path, default=None)
    options = analyse.parse_args(arguments)
    racine = racine_depot()
    identifiants = options.candidats.split(",")
    inconnus = [c for c in identifiants if c not in declarations()]
    if inconnus:
        print(f"Rapport impossible : candidat non déclaré, {', '.join(inconnus)}.", file=sys.stderr)
        return 2
    maintenant = datetime.now(UTC)
    sortie: Path = options.sortie or racine / "99_local" / "rapports" / f"{maintenant:%Y-%m-%d}_rapport_campagne.md"
    if sortie.exists():
        print(f"Rapport existant, gardé tel quel : {sortie}. Le retirer d'abord, ou --sortie.", file=sys.stderr)
        return 3
    taches = taches_du_jeu(options.jeu)
    dossier = dossier_du_jeu(options.jeu)
    public = racine / "07_taches" / "public"
    gravite = lire_gravite(public) if dossier == public else lire_gravite(public, dossier)
    try:
        mesures = [
            rassembler(
                i,
                lire_candidat(i).fiche.nom,
                taches,
                racine / "99_local" / "runs",
                options.repetitions,
                options.gardien,
            )
            for i in identifiants
        ]
        texte = rediger(
            mesures,
            taches,
            gravite,
            contexte(racine, options.jeu, taches, f"{maintenant:%d/%m/%Y}"),
            options.repetitions,
            options.gardien,
        )
    except RapportImpossible as erreur:
        print(f"Rapport impossible : {erreur}.", file=sys.stderr)
        return 1
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(texte, encoding="utf-8")
    print(f"Rapport de campagne écrit : {sortie}. À compléter : les passages « À écrire ».")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
