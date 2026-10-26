"""Mesure d'un candidat déclaré sur τ²-bench : make mesure-tau2 CANDIDAT=<identifiant>.

    python -m ease.mesure_tau2 reproduction_tau2_deepseek_flash [--jeu verified] \\
        [--taches 0,1,2] [--repetitions 5] [--simulateur gemini_2_5_flash]

Le contrôle de la règle 4 de l'étape 7 (journal τ², seizième entrée) : un candidat de
candidats_tau2/ passe les tâches d'airline de τ²-bench, face au simulateur d'utilisateur
choisi ; le run va dans 99_local/runs_tau2/, sa fiche nomme le banc, le jeu et le simulateur, avec
ses jetons et son coût (champ banc_public). Le résumé donne la réussite, pass^1 à pass^k, le coût
du candidat et celui du simulateur, à part.

Les candidats de τ²-bench sont déclarés à part de ceux de la PME (candidats_tau2/) : `make mesure`
ne les voit pas, et ceux-ci ne voient pas la PME. Le simulateur gemini-2.5-flash, celui des
scores d'OpenRouter (journal τ², cinquième entrée), passe par OpenRouter ; sa clé se lit dans la
variable OPENROUTER_API_KEY ou dans le fichier .env de la racine du dépôt, et ne va qu'au serveur
de τ²-bench. Chaque candidat a son dossier de travail du serveur
(99_local/travail/tau2_travail_<candidat>/) et son verrou : deux candidats différents peuvent tourner
en même temps. Le run ne part que d'un poste de mesure propre, sur un commit de main (ease.poste).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from typing import cast

from ease.candidat_externe import CandidatExterne
from ease.candidats import declarations, lire_candidat
from ease.chargement import racine_depot
from ease.contrats.fiche_de_run import Tarif
from ease.creneaux import refus_heures_creuses
from ease.executeur import ArretDuRun, maintenant
from ease.fiches import lire_fiche_de_run, lire_resultat
from ease.mesure import contexte_annonce, resume_texte, sonder, verrouiller
from ease.poste import refus_hors_poste
from ease.statistiques import resumer
from ease.terrain_tau2 import (
    JEUX,
    EnvironnementTau2,
    Jeu,
    Simulateur,
    fichier_taches,
    lancer_run,
    lire_taches,
)

DOSSIER = Path(__file__).parent / "candidats_tau2"

SIMULATEURS: dict[str, Simulateur] = {
    "gemini_2_5_flash": Simulateur(
        modele="openrouter/google/gemini-2.5-flash",
        fournisseur="OpenRouter",
        # Les réglages que le serveur envoie au simulateur : DEFAULT_LLM_ARGS_USER de τ²-bench
        # 1.0.1 (src/tau2/config.py), vérifiés par 02_ease/tests/test_mesure_tau2.py. Aucun
        # paramètre de réflexion : gemini-2.5-flash garde son réglage par défaut (décision
        # d'Alexandre du 2026-10-10, journal τ², dix-huitième entrée) ; ses jetons de réflexion se
        # comptent à part, dans la sortie.
        parametres={"temperature": 0.0},
        tarif=Tarif(
            entree_dollars_par_million=0.30,
            entree_en_cache_dollars_par_million=0.03,
            sortie_dollars_par_million=2.50,
            source="https://openrouter.ai/google/gemini-2.5-flash",
            releve_le=date(2026, 10, 10),
        ),
        cle_env="OPENROUTER_API_KEY",
    ),
    "ecrit_d_avance": Simulateur(),
}
"""Les simulateurs d'utilisateur permis ; ecrit_d_avance, sans modèle, pour les essais à blanc.
Prix de gemini-2.5-flash chez OpenRouter : 00_docs/sources/2026-10-10_estimation_tau2_regle4.md."""


def declarations_tau2() -> list[str]:
    """Identifiants des candidats déclarés pour τ²-bench."""
    return sorted(chemin.stem for chemin in DOSSIER.glob("*.yaml"))


def lire_candidat_tau2(identifiant: str) -> CandidatExterne:
    return lire_candidat(identifiant, DOSSIER)


def cle_du_simulateur(nom: str, racine: Path) -> str | None:
    """La clé lue dans la variable d'environnement nom, ou dans le fichier .env de la racine ;
    None si ni l'une ni l'autre ne la donne. Elle n'est jamais affichée."""
    if os.environ.get(nom):
        return os.environ[nom]
    fichier = racine / ".env"
    if fichier.is_file():
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            cle, egal, valeur = ligne.strip().partition("=")
            if egal and cle.strip() == nom and valeur.strip().strip("\"'"):
                return valeur.strip().strip("\"'")
    return None


def _virgule(valeur: float, decimales: int) -> str:
    return f"{valeur:.{decimales}f}".replace(".", ",")


def _pourcent(valeur: float) -> str:
    return f"{valeur * 100:.1f}".replace(".", ",").removesuffix(",0") + " %"


def _dollars(valeur: float | str | None) -> str:
    if valeur is None:
        return "sans objet"
    return "?" if isinstance(valeur, str) else _virgule(valeur, 4) + " $"


def resume_tau2(dossier: Path) -> list[str]:
    """Ce que le résumé de la PME ne dit pas : pass^k, et le simulateur, à part du candidat."""
    resultats = [lire_resultat(chemin) for chemin in sorted((dossier / "resultats").glob("*.json"))]
    lignes = resume_texte(resultats)
    resume = resumer(resultats)
    if resume.pass_k:
        lignes.append("pass^k : " + " ; ".join(f"pass^{k} {_pourcent(v)}" for k, v in sorted(resume.pass_k.items())))
    fiche = lire_fiche_de_run(dossier / "fiche_de_run.json")
    banc = fiche.banc_public
    if banc is not None:
        simulateur = banc.simulateur
        jetons = simulateur.jetons
        detail = (
            "aucun appel"
            if jetons is None
            else f"jetons en entrée {jetons.entree} (dont en cache {jetons.entree_en_cache}), "
            f"en sortie {jetons.sortie} (dont réflexion {jetons.dont_reflexion})"
        )
        lignes.append(
            f"Simulateur {simulateur.modele}, à part : coût {_dollars(simulateur.cout_dollars)} au tarif de la "
            f"fiche, {_dollars(simulateur.cout_annonce_dollars)} annoncé par le fournisseur ; {detail}"
        )
        lignes.append(f"Banc : {banc.nom} {banc.version}, {banc.domaine}, jeu {banc.jeu}")
    return lignes


def main(arguments: list[str] | None = None) -> int:
    analyse = argparse.ArgumentParser(
        prog="python -m ease.mesure_tau2", description="Mesure un candidat déclaré sur τ²-bench (airline)."
    )
    analyse.add_argument("candidat", help=f"identifiant déclaré : {', '.join(declarations_tau2())}")
    analyse.add_argument("--jeu", choices=JEUX, default="verified", help="jeu de tâches (verified par défaut)")
    analyse.add_argument("--taches", default="", help="numéros de τ²-bench séparés par des virgules (toutes sinon)")
    analyse.add_argument("--repetitions", type=int, default=5)
    analyse.add_argument("--simulateur", choices=sorted(SIMULATEURS), default="gemini_2_5_flash")
    options = analyse.parse_args(arguments)
    if options.candidat not in declarations_tau2():
        inconnu = options.candidat in declarations()
        aide = " (c'est un candidat de la PME : make mesure)" if inconnu else ""
        print(f"Candidat inconnu pour τ²-bench : {options.candidat}{aide}.", file=sys.stderr)
        return 2
    if options.repetitions < 1:
        print("--repetitions : au moins 1", file=sys.stderr)
        return 2
    candidat = lire_candidat_tau2(options.candidat)
    simulateur = SIMULATEURS[options.simulateur]
    jeu = cast(Jeu, options.jeu)
    racine = racine_depot()
    try:
        fichier_taches(jeu)
        numeros = [n.strip() for n in options.taches.split(",") if n.strip()] or None
        taches = lire_taches(jeu, numeros=numeros)
    except (FileNotFoundError, ValueError) as erreur:
        print(f"Run non lancé : {erreur}.", file=sys.stderr)
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
            conseil = "Pour Qwen : make qwen dans un autre terminal, puis attendre « Application startup complete »."
            print(conseil, file=sys.stderr)
            return 3
    if candidat.lancement.creneau == "heures_creuses_deepseek":
        refus = refus_heures_creuses(maintenant())
        if refus is not None:
            print(f"Run non lancé : {refus}.", file=sys.stderr)
            return 4
    variables: dict[str, str] | None = None
    if simulateur.cle_env is not None:
        cle = cle_du_simulateur(simulateur.cle_env, racine)
        if cle is None:
            print(
                f"Run non lancé : clé du simulateur introuvable ; ajouter la ligne {simulateur.cle_env}=<clé> "
                f"au fichier {racine / '.env'}.",
                file=sys.stderr,
            )
            return 2
        variables = {simulateur.cle_env: cle}
    if (refus := refus_hors_poste(racine)) is not None:
        print(f"Run non lancé : {refus}.", file=sys.stderr)
        return 6
    travail = racine / "99_local" / "travail" / f"tau2_travail_{candidat.fiche.identifiant}"
    verrou = verrouiller(travail.with_name(f"{travail.name}.verrou"))
    if verrou is None:
        print(f"Run non lancé : un run de {candidat.fiche.identifiant} sur τ²-bench tourne déjà.", file=sys.stderr)
        return 5
    executions = len(taches) * options.repetitions
    print(
        f"{candidat.fiche.nom} : τ²-bench airline, jeu {jeu}, {len(taches)} tâche(s), "
        f"{options.repetitions} répétition(s), {executions} exécution(s) ; simulateur {simulateur.modele}",
        flush=True,
    )
    environnement = EnvironnementTau2(jeu, travail=travail, utilisateur=simulateur.modele, variables=variables)
    with verrou:
        try:
            dossier = lancer_run(
                candidat=candidat,
                environnement=environnement,
                taches=taches,
                repetitions=options.repetitions,
                simulateur=simulateur,
            )
        except ArretDuRun as arret:
            print(
                f"Run interrompu : {arret}. Les exécutions déjà faites restent dans 99_local/runs_tau2/.",
                file=sys.stderr,
            )
            return 4
    print("\n".join(resume_tau2(dossier)))
    relatif = Path(dossier).relative_to(racine)
    premiere = f"{taches[0].identifiant}_r1"
    print(f"\nRun : {relatif}\nTraces : make journal CHEMIN={relatif} TACHE={premiere}")
    print(f"Conversations de τ²-bench : {travail.relative_to(racine)}/{dossier.name}_*/simulation.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
