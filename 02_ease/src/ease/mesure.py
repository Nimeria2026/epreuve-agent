"""Mesure d'un candidat déclaré sur la PME : make mesure CANDIDAT=<identifiant>.

    python -m ease.mesure agent_seul_qwen_local [--taches t01,t03] [--repetitions 5] [--gardien] [--cachees]

Lance le candidat sur les tâches publiques de la PME (état v2), toutes ou celles dont l'identifiant
commence par l'un des préfixes donnés, écrit le run dans 99_local/runs/, puis affiche un résumé
court et la commande pour lire les traces.

Chaque candidat a son propre état de travail de la PME (99_local/travail/pme_<candidat>/) : deux
candidats différents peuvent tourner en même temps. Un verrou refuse un second run du même
candidat tant que le premier tourne. Le run ne part que d'un poste de mesure propre, sur un commit de
main (ease.poste) : ce refus vient après les autres contrôles, juste avant le run.

Dès qu'une tâche du run porte une vérification juge_requis, le juge étalonné (ease.juge) tranche
ces points. Il appelle l'API de DeepSeek à toute heure : son coût, de l'ordre du centime par run,
est affiché à part et n'entre pas dans celui du candidat (décision d'Alexandre du 2026-10-06 : un
run de Qwen n'attend pas les heures creuses pour le juge).

Avec --cachees, les tâches cachées (07_taches/prive/, ease.cachees) s'ajoutent aux publiques ; le run
les nomme dans sa fiche, hors git comme elles. La sortie ne les nomme pas : elles y sont résumées
ensemble, réussite, fautes graves et refus du gardien (JOURNAL, cent-douzième entrée).

Avec --jeu documents, le run passe le jeu « documents » de l'étape 6 (07_taches/public/documents/,
ease.taches.taches_documents) au lieu des tâches publiques : des tâches qui déclarent EKE, que la
PME lance pour elles seules. Le run se nomme alors documents_<état>, et ses contrôles graves sont
ceux de ce jeu (07_taches/public/documents/gravite.yaml). Avec --jeu dure, de même pour la tranche
dure (07_taches/public/dure/, JOURNAL, cent-trentième entrée) : le run se nomme dure_<état>.
--cachees et --cachees-seules y prennent la part cachée de la tranche (07_taches/prive/dure/, JOURNAL,
cent-soixante-et-onzième entrée), résumée de même sans ses noms ; avec --jeu domivelle ou
domivelle_dure, celles de Domivelle (prive/domivelle/ et prive/domivelle/dure/, entrée 180) ; avec
--jeu negovelle ou negovelle_dure, celles de Négovelle (prive/negovelle/ et prive/negovelle/dure/,
entrée 202) ; les autres jeux n'ont pas de part cachée.

Avec --gardien, le gardien (06_gardien, règles courantes) se place entre l'agent et la PME ; son
journal est recopié dans le dossier du run (gardien.jsonl), et le résumé compte ses refus, tâche
par tâche et règle par règle, puis les validations qu'il a demandées. Le rapport tient ces runs à
part (make rapport GARDIEN=1).
"""

from __future__ import annotations

import argparse
import fcntl
import functools
import json
import math
import re
import shutil
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Collection
from pathlib import Path
from typing import TextIO, cast

from ease.cachees import cachees_du_jeu, dossier_cachees_du_jeu
from ease.candidat_externe import CandidatExterne
from ease.candidats import declarations, lire_candidat
from ease.chargement import racine_depot
from ease.contrats.resultat_execution import ResultatExecution
from ease.contrats.tache import JugeRequis, Tache
from ease.creneaux import refus_heures_creuses
from ease.executeur import ArretDuRun, lancer_run, maintenant
from ease.fiches import lire_resultat
from ease.gravite import lire_gravite, resume_graves
from ease.juge import DU_RUN, JugeIndisponible, juge_du_banc, jugement
from ease.pme import EnvironnementPME, blocages_du_gardien, etat_des_taches, regles_gardien
from ease.poste import refus_hors_poste
from ease.statistiques import resumer
from ease.taches import JEUX, dossier_du_jeu, societe_des_taches, taches_du_jeu
from ease.verification import verifier


def dossier_pme(identifiant: str) -> Path:
    """État de travail de la PME propre à un candidat, avec son verrou et ses journaux à côté, dans
    99_local/travail/ (cadrage du dépôt public et de l'organisation, section 8)."""
    return racine_depot() / "99_local" / "travail" / f"pme_{identifiant}"


def verrouiller(chemin: Path) -> TextIO | None:
    """Verrou exclusif, tenu tant que le fichier rendu reste ouvert ; None si un autre le tient."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fichier = chemin.open("w", encoding="utf-8")
    try:
        fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fichier.close()
        return None
    return fichier


def demande_un_juge(taches: list[Tache]) -> bool:
    """Vrai si une des tâches porte une vérification juge_requis."""
    return any(isinstance(v, JugeRequis) for t in taches for c in t.controles for v in c.verification)


def _pourcent(valeur: float) -> str:
    return f"{valeur * 100:.1f}".replace(".", ",").removesuffix(",0") + " %"


def _virgule(valeur: float, decimales: int) -> str:
    return f"{valeur:.{decimales}f}".replace(".", ",")


def resume_texte(resultats: list[ResultatExecution], cachees: Collection[str] = ()) -> list[str]:
    """Le résumé d'un run en quelques lignes : réussite, score, coût, durée, puis tâche par tâche.

    Les tâches de cachees n'ont pas de ligne à elles : elles sont résumées ensemble, sans leurs noms,
    pour que la séance qui lit la sortie ne les apprenne pas (JOURNAL, cent-douzième entrée)."""
    lignes: list[str] = []
    techniques = sum(1 for r in resultats if r.arret == "erreur_technique")
    if techniques == len(resultats):
        return [f"Aucune exécution retenue : {techniques} erreur(s) technique(s). Voir les journaux du run."]
    resume = resumer(resultats)
    bas, haut = resume.intervalle
    couts = [r.cout_dollars for r in resultats]
    connus = [float(c) for c in couts if not isinstance(c, str)]
    cout = "?" if len(connus) < len(couts) else _virgule(math.fsum(connus), 4) + " $"
    lignes.append(
        f"Réussite : {resume.reussites}/{resume.executions} ({_pourcent(resume.taux)}, "
        f"IC 95 % de {_pourcent(bas)} à {_pourcent(haut)}) ; score moyen {_virgule(resume.score_moyen, 2)}"
    )
    energies = [r.energie_wh for r in resultats if r.energie_wh is not None]
    energie = ""
    if energies:
        connues = [float(e) for e in energies if not isinstance(e, str)]
        total = "?" if len(connues) < len(energies) else _virgule(math.fsum(connues), 1) + " Wh"
        energie = f" ; énergie de la carte : {total}"
    lignes.append(
        f"Erreurs techniques : {techniques} ; coût : {cout}{energie} ; "
        f"durée : {_virgule(math.fsum(r.duree_secondes for r in resultats) / 60, 1)} min"
    )
    par_tache: dict[str, list[ResultatExecution]] = defaultdict(list)
    for resultat in resultats:
        par_tache[resultat.tache.identifiant].append(resultat)
    for tache, liste in sorted(par_tache.items()):
        if tache in cachees:
            continue
        retenus = [r for r in liste if r.arret != "erreur_technique"]
        score = math.fsum(r.score for r in retenus) / len(retenus) if retenus else math.nan
        arrets = sorted({r.arret for r in liste if r.arret != "termine"})
        lignes.append(
            f"  {tache} : {sum(r.reussie for r in retenus)}/{len(retenus)} réussies, score moyen "
            f"{_virgule(score, 2)}, {math.fsum(r.etapes for r in liste) / len(liste):.0f} étapes"
            + (f", arrêts : {', '.join(arrets)}" if arrets else "")
        )
    caches = [r for t, liste in par_tache.items() if t in cachees for r in liste]
    if caches:
        retenus = [r for r in caches if r.arret != "erreur_technique"]
        score = math.fsum(r.score for r in retenus) / len(retenus) if retenus else math.nan
        arrets = Counter(r.arret for r in caches if r.arret != "termine")
        nombre = len({r.tache.identifiant for r in caches})
        lignes.append(
            f"  tâches cachées ({nombre}) : {sum(r.reussie for r in retenus)}/{len(retenus)} réussies, "
            f"score moyen {_virgule(score, 2)}"
            + (f", arrêts : {', '.join(f'{a} {n}' for a, n in sorted(arrets.items()))}" if arrets else "")
        )
    return lignes


REGLE_DU_REFUS = re.compile(r"\(règle ([\w-]+)\)")


JOURNAL_GARDIEN = "gardien.jsonl"
"""Le journal du gardien d'un run, recopié dans le dossier du run à sa fin (make mesure GARDIEN=1)."""


def validations_du_gardien(dossier: Path) -> Counter[str]:
    """Les validations demandées par le gardien pendant un run, comptées par réponse simulée."""
    chemin = dossier / JOURNAL_GARDIEN
    if not chemin.is_file():
        return Counter()
    lignes = [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne]
    return Counter(str(ligne.get("reponse")) for ligne in lignes if ligne.get("verdict") == "validation")


def resume_gardien(dossier: Path, resultats: list[ResultatExecution], cachees: Collection[str] = ()) -> list[str]:
    """Les refus du gardien dans un run : le total, puis tâche par tâche avec la règle de chacun ;
    puis les validations qu'il a demandées, acceptées ou refusées par la personne simulée. Un refus
    se voit dans le journal de l'agent ; une validation acceptée, seulement dans celui du gardien."""
    par_tache: dict[str, Counter[str]] = defaultdict(Counter)
    for resultat in resultats:
        for refus in blocages_du_gardien(dossier / resultat.journal):
            regle = REGLE_DU_REFUS.search(refus)
            par_tache[resultat.tache.identifiant][regle.group(1) if regle else "?"] += 1
    total = sum(sum(c.values()) for c in par_tache.values())
    lignes = [f"Refus du gardien : {total}"]
    caches: Counter[str] = Counter()
    for tache, compte in sorted(par_tache.items()):
        if tache in cachees:
            caches.update(compte)
            continue
        detail = ", ".join(f"{regle} {nombre}" for regle, nombre in sorted(compte.items()))
        lignes.append(f"  {tache} : {sum(compte.values())} ({detail})")
    if caches:
        detail = ", ".join(f"{regle} {nombre}" for regle, nombre in sorted(caches.items()))
        lignes.append(f"  tâches cachées : {sum(caches.values())} ({detail})")
    validations = validations_du_gardien(dossier)
    if (dossier / JOURNAL_GARDIEN).is_file():
        lignes.append(
            f"Validations demandées par le gardien : {sum(validations.values())} "
            f"({validations['accepter']} acceptée(s), {validations['refuser']} refusée(s))"
        )
    return lignes


def sonder(adresse: str) -> str:
    """Interroge le serveur d'un modèle local ; rend ce qu'il annonce, ou lève ConnectionError."""
    try:
        with urllib.request.urlopen(adresse, timeout=5) as reponse:
            texte = str(reponse.read().decode("utf-8"))
    except OSError as erreur:
        raise ConnectionError(f"le serveur du modèle ne répond pas sur {adresse} ({erreur})") from erreur
    try:
        donnees: object = json.loads(texte)
    except json.JSONDecodeError:
        return texte.strip()[:80]
    version = cast(dict[str, object], donnees).get("version") if isinstance(donnees, dict) else None
    return f"version {version}" if isinstance(version, str) else texte.strip()[:80]


def contexte_annonce(sonde: str) -> int:
    """Le contexte que le serveur d'un modèle local annonce, en jetons, lu dans /v1/models à côté de la
    sonde ; lève ConnectionError s'il ne le dit pas."""
    adresse = urllib.parse.urljoin(sonde, "/v1/models")
    try:
        with urllib.request.urlopen(adresse, timeout=5) as reponse:
            donnees: object = json.loads(reponse.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        raise ConnectionError(f"le serveur ne dit pas son contexte sur {adresse} ({erreur})") from erreur
    modeles = cast(dict[str, object], donnees).get("data") if isinstance(donnees, dict) else None
    contextes = [
        cast(dict[str, object], m).get("max_model_len")
        for m in cast(list[object], modeles or [])
        if isinstance(m, dict)
    ]
    entiers = [c for c in contextes if isinstance(c, int) and not isinstance(c, bool)]
    if len(entiers) != 1:
        raise ConnectionError(f"le serveur ne dit pas son contexte sur {adresse}")
    return entiers[0]


FOURNISSEURS_SANS_CACHEES = {"GMI Cloud", "OpenRouter, route gratuite"}
"""Fournisseurs à qui les tâches cachées ne vont jamais : ce qu'ils font des requêtes n'a pas été lu
(00_docs/sources/2026-10-05_reglages_des_modeles.md ; pour la route gratuite d'OpenRouter, JOURNAL,
deux-cent-vingt-quatrième entrée)."""


def refus_cachees(candidat: CandidatExterne) -> str | None:
    """La raison de ne pas passer les tâches cachées à ce candidat, ou None."""
    fournisseurs = {m.fournisseur for m in candidat.configuration.modeles} & FOURNISSEURS_SANS_CACHEES
    return f"les tâches cachées ne vont pas chez {', '.join(sorted(fournisseurs))}" if fournisseurs else None


def taches_du_run(prefixes: list[str], cachees: bool = False, seules: bool = False, jeu: str = "public") -> list[Tache]:
    """Les tâches publiques du jeu, plus ses cachées avec cachees ; ses cachées seules avec seules,
    pour un candidat déjà mesuré sur les publiques (JOURNAL, entrée 111) ; filtrées par préfixes. Le
    socle (public) et la tranche dure ont une part cachée (ease.cachees), les autres jeux non."""
    publiques = [] if seules else taches_du_jeu(jeu)
    toutes = publiques + (cachees_du_jeu(jeu) if cachees or seules else [])
    return [t for t in toutes if not prefixes or any(t.identifiant.startswith(p) for p in prefixes)]


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(prog="python -m ease.mesure", description="Mesure un candidat sur la PME.")
    analyse.add_argument("candidat", help=f"identifiant déclaré : {', '.join(declarations())}")
    analyse.add_argument("--taches", default="", help="préfixes séparés par des virgules, par exemple t01,t03")
    analyse.add_argument("--repetitions", type=int, default=5)
    analyse.add_argument("--gardien", action="store_true", help="le gardien entre l'agent et la PME")
    analyse.add_argument(
        "--cachees", action="store_true", help="ajoute les tâches cachées du jeu (dans 07_taches/prive/)"
    )
    analyse.add_argument("--cachees-seules", action="store_true", help="les tâches cachées seules, sans les publiques")
    analyse.add_argument(
        "--jeu",
        choices=JEUX,
        default="public",
        help="jeu de tâches : public, documents (EKE) ou dure (la tranche dure)",
    )
    options = analyse.parse_args(arguments)
    if dossier_cachees_du_jeu(options.jeu) is None and (options.cachees or options.cachees_seules):
        print(f"Run non lancé : le jeu {options.jeu} n'a pas de tâches cachées.", file=sys.stderr)
        return 2
    candidat = lire_candidat(options.candidat)
    prefixes = [p for p in options.taches.split(",") if p]
    if (options.cachees or options.cachees_seules) and (refus := refus_cachees(candidat)) is not None:
        print(f"Run non lancé : {refus}.", file=sys.stderr)
        return 2
    taches = taches_du_run(prefixes, options.cachees, options.cachees_seules, options.jeu)
    if not taches:
        quoi = f"ne commence par {options.taches}" if prefixes else f"dans le jeu {options.jeu}"
        print(f"Run non lancé : aucune tâche {quoi}.", file=sys.stderr)
        return 2
    try:
        societe = societe_des_taches(taches)
        version = etat_des_taches(taches)
    except ValueError as erreur:
        print(f"Run non lancé : {erreur}. Choisir avec TACHES= les tâches d'un seul état.", file=sys.stderr)
        return 2
    if candidat.lancement.sonde is not None:
        try:
            print(f"Serveur du modèle : {sonder(candidat.lancement.sonde)}")
            attendu = candidat.lancement.contexte_serveur
            if attendu is not None:
                annonce = contexte_annonce(candidat.lancement.sonde)
                if annonce != attendu:
                    print(
                        f"Run non lancé : le serveur annonce un contexte de {annonce} jetons, ce candidat en "
                        f"attend {attendu}. Relancer le serveur : make qwen CONTEXTE={attendu}.",
                        file=sys.stderr,
                    )
                    return 3
                print(f"Contexte du serveur : {annonce} jetons, celui qu'attend le candidat")
        except ConnectionError as erreur:
            print(f"Run non lancé : {erreur}.", file=sys.stderr)
            conseil = "Pour Qwen : make qwen dans un autre terminal, puis attendre « Application startup complete »."
            print(conseil, file=sys.stderr)
            return 3
    if candidat.lancement.creneau == "heures_creuses_deepseek":
        refus = refus_heures_creuses(maintenant())
        if refus is not None:
            print(f"Run non lancé : {refus}.", file=sys.stderr)
            return 4
    juge = None
    if demande_un_juge(taches):
        try:
            juge = juge_du_banc(racine_depot())
        except JugeIndisponible as erreur:
            print(f"Run non lancé : juge indisponible, {erreur}.", file=sys.stderr)
            return 2
    if (refus := refus_hors_poste(racine_depot())) is not None:
        print(f"Run non lancé : {refus}.", file=sys.stderr)
        return 6
    etat = dossier_pme(candidat.fiche.identifiant)
    verrou = verrouiller(etat.with_name(f"{etat.name}.verrou"))
    if verrou is None:
        print(f"Run non lancé : un run de {candidat.fiche.identifiant} tourne déjà.", file=sys.stderr)
        return 5
    gardien = regles_gardien(societe) if options.gardien else None
    environnement = EnvironnementPME(version, etat, gardien=gardien, societe=societe)
    avec = f", gardien règles {environnement.regles_gardien.version}" if environnement.regles_gardien else ""
    print(f"{candidat.fiche.nom} : {len(taches)} tâche(s), {options.repetitions} répétition(s){avec}", flush=True)
    with verrou:
        try:
            dossier = lancer_run(
                candidat=candidat,
                environnement=environnement,
                taches=taches,
                controleur=verifier if juge is None else functools.partial(verifier, juge=jugement(juge)),
                repetitions=options.repetitions,
                nom_jeu=f"{'pme' if options.jeu == 'public' else options.jeu}_{version}",
                juge=None if juge is None else DU_RUN,
            )
        except ArretDuRun as arret:
            raison = f"Run interrompu : {arret}. Les exécutions déjà faites restent dans 99_local/runs/."
            print(raison, file=sys.stderr)
            return 4
    if environnement.regles_gardien is not None and environnement.journal_gardien.is_file():
        shutil.copyfile(environnement.journal_gardien, dossier / JOURNAL_GARDIEN)
    resultats = [lire_resultat(chemin) for chemin in sorted((dossier / "resultats").glob("*.json"))]
    cachees: set[str] = (
        {t.identifiant for t in cachees_du_jeu(options.jeu)} if options.cachees or options.cachees_seules else set()
    )
    print("\n".join(resume_texte(resultats, cachees)))
    racine_taches = racine_depot() / "07_taches"
    # Le socle lit public/ et prive/ ; un autre jeu ajoute son dossier, puis celui de sa part cachée.
    cache = dossier_cachees_du_jeu(options.jeu)
    gravite = (
        lire_gravite()
        if options.jeu == "public"
        else lire_gravite(racine_taches / "public", dossier_du_jeu(options.jeu), *([cache] if cache else []))
    )
    print("\n".join(resume_graves(resultats, taches, gravite, cachees)))
    if options.gardien:
        print("\n".join(resume_gardien(dossier, resultats, cachees)))
    if juge is not None:
        print(f"Coût du juge, à part : {_virgule(juge.cout_dollars, 4)} $")
    relatif = Path(dossier).relative_to(racine_depot())
    publiques = [t for t in taches if t.identifiant not in cachees]
    trace = f" TACHE={publiques[0].identifiant}_r1" if publiques else ""
    print(f"\nRun : {relatif}\nTraces : make journal CHEMIN={relatif}{trace}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
