"""Ouvre une campagne : le dossier d'une intervention pour une entreprise, hors de l'atelier
(cadrage des interventions, 00_docs/sources/2026-10-26_cadrage_interventions.md, section 5 ;
JOURNAL, entrée 311).

    make campagne NOM=<nom> [COMMIT=<commit>]

La campagne est un clone privé de l'atelier, à un commit de main, dans
<atelier>_campagnes/<nom>/ : git n'y copie que les fichiers suivis, ni les tâches cachées, ni le
.env, ni 99_local/ ; le clone perd son dépôt distant, donc rien ne s'en pousse. Le script y écrit
la fiche de la campagne (00_docs/sources/<date>_campagne_<nom>.md, avec les annexes du cadrage),
met tous les agents d'opencode sur un modèle qui ne garde ni n'entraîne sur les requêtes, et
commite l'ouverture dans le clone. Ses postes de mesure se font dans le clone, par
make poste-mesure, à côté de lui ; ses runs restent dans son 99_local/. Rien n'en revient dans
l'atelier ; à la clôture, le dossier et ses postes se suppriment, avec l'accord d'Alexandre.

Codes de refus : 2 un nom invalide, 3 la campagne existe déjà, 4 un commit hors de main, 5 lancé
depuis une campagne. Bibliothèque standard seule.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

NOM = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
CADRAGE = Path("00_docs") / "sources" / "2026-10-26_cadrage_interventions.md"
MODELE_ADMIS = "opencode-go/glm-5.3"
"""Le modèle de tous les agents d'opencode dans une campagne : ni rétention ni entraînement
(00_docs/sources/2026-10-26_politiques_de_donnees_opencode.md)."""
AGENTS = ("build", "plan", "general", "explore", "review", "hard", "secours", "title", "summary", "compaction")
"""Les agents qu'opencode charge sur le poste d'Alexandre (opencode debug agents, 2026-10-26)."""
IDENTITE = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")


class CampagneImpossible(Exception):
    """La campagne ne peut pas s'ouvrir ; le message dit pourquoi, le code dit le refus."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def git(*arguments: str, dans: Path) -> str:
    """git sans les variables qui viseraient un autre dépôt (celles d'un crochet), identité gardée."""
    environnement = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in IDENTITE}
    resultat = subprocess.run(
        ["git", *arguments],
        cwd=dans,
        capture_output=True,
        text=True,
        env=environnement | {"GIT_OPTIONAL_LOCKS": "0"},
        check=False,
    )
    if resultat.returncode != 0:
        raise CampagneImpossible(f"git {' '.join(arguments)} : {resultat.stderr.strip()}", 6)
    return resultat.stdout.strip()


def est_campagne(dossier: Path) -> bool:
    return dossier.resolve().parent.name.endswith("_campagnes")


def atelier_de(dossier: Path) -> Path:
    """Le dossier principal du dépôt, même lancé depuis un poste de mesure."""
    commun = git("rev-parse", "--path-format=absolute", "--git-common-dir", dans=dossier)
    return Path(commun).parent.resolve()


def dossier_campagnes(atelier: Path) -> Path:
    return atelier.parent / f"{atelier.name}_campagnes"


DEBUT_PROPOSITION = "[//]: # (proposition)"
FIN_PROPOSITION = "[//]: # (fin de la proposition)"


def proposition(cadrage: str) -> str:
    """Le modèle de la proposition, annexe E du cadrage, entre ses deux marques."""
    debut, fin = cadrage.find(DEBUT_PROPOSITION), cadrage.find(FIN_PROPOSITION)
    if debut < 0 or fin < debut:
        raise CampagneImpossible("le cadrage des interventions n'a pas le modèle de la proposition (annexe E)", 6)
    return cadrage[debut + len(DEBUT_PROPOSITION) : fin].strip() + "\n"


def annexes(cadrage: str) -> str:
    """Les annexes du cadrage, de « ## Annexe A » à la fin, titres descendus d'un niveau."""
    debut = cadrage.find("## Annexe A")
    if debut < 0:
        raise CampagneImpossible("le cadrage des interventions n'a pas ses annexes", 6)
    return re.sub(r"^## ", "### ", cadrage[debut:], flags=re.MULTILINE).rstrip() + "\n"


def fiche(nom: str, jour: datetime.date, commit: str, cadrage: str, atelier: Path) -> str:
    return f"""# Campagne {nom}

Ouverte le {jour.isoformat()} par `make campagne`, depuis le commit `{commit[:12]}` de l'atelier
(cadrage des interventions, `{CADRAGE.as_posix()}`). Ce dossier est un clone privé de
l'atelier, sans dépôt distant : rien ne s'en pousse. Tout ce qu'il contient de l'entreprise est
confidentiel (cadrage, section 6) et se supprime à la clôture.

| | |
|---|---|
| Entreprise | ? |
| Numéro au JOURNAL de l'atelier | ? |
| Contact | ? |
| Remise du rapport | ? |
| Suppression prévue | ? (au plus tard 30 jours après la remise du rapport) |

## Les règles de ce dossier

- Les modèles : seulement ceux qui ne gardent ni n'entraînent sur les requêtes
  (`00_docs/sources/2026-10-26_politiques_de_donnees_opencode.md`). `opencode.json` met tous les
  agents sur `{MODELE_ADMIS}` ; `opencode debug agents` le vérifie.
- Le juge du banc et la référence DeepSeek passent par l'API officielle de DeepSeek, qui entraîne
  par défaut : aucune vérification `juge_requis` dans les tâches de la campagne ; sur ses tâches,
  les références tournent sur le poste (Qwen 3.8 27B, Flash-Next) ; DeepSeek seulement sur le
  socle public de Calorelle.
- L'entreprise : des tâches fictives, inspirées de ce qu'elle décrit ; aucune donnée réelle, aucun
  accès à ses systèmes. Son agent tourne avec ses propres clés.
- `make publier`, `make exporter-public`, `make coffre` et `make sauvegarder` refusent ici ; un
  résultat dont l'entreprise accepte la publication se refait dans l'atelier.
- Les clés : un `.env` à part, avec les seules clés dont la campagne a besoin.
- Rien de ce dossier ne revient dans l'atelier ; une ligne au JOURNAL de l'atelier, sous un
  numéro, sans nom ni contenu.

## Les étapes (cadrage, section 3)

- [ ] 2. Premier échange : la fiche de demande, plus bas.
- [ ] 3. Faisabilité, oui ou non, avec ses raisons, par écrit.
- [ ] 4. Proposition : le périmètre, le délai, le devis ; le modèle, à compléter, est dans
  `00_docs/sources/{jour.isoformat()}_proposition_{nom}.md`.
- [ ] 5. Cadrage de la campagne, validé par l'entreprise.
- [ ] 6. Construction : les variables du gabarit, `make gabarit`, les tâches du métier ; témoins
  conformes (`make temoins TERRAIN=gabarit`).
- [ ] 7. Mesure, depuis un poste de ce dossier (`make poste-mesure POSTE=api` ou `POSTE=local`).
- [ ] 8. Rapport, avec ses limites, et sa présentation : `make rapport-campagne
  CANDIDATS=campagne_{nom}[,<référence>]`, depuis ce dossier, puis les passages « À écrire » ; la
  présentation suit le plan de l'annexe F.
- [ ] 9. Clôture, avec l'accord d'Alexandre : `make cloture NOM={nom}`, depuis l'atelier ;
  l'attestation de suppression s'écrit à côté des campagnes, puis le dossier et ses postes sont
  supprimés.

## Mettre la campagne à jour depuis l'atelier

Une correction de l'atelier (le gabarit, EASE, un service) se commite dans l'atelier, puis se tire
ici, par le chemin local, sans dépôt distant ; ensuite `make gabarit` régénère sur les variables de
la campagne, `make installer` si les dépendances ont changé :

    git pull --no-rebase --no-edit {atelier} main

`--no-rebase` : la campagne a ses propres commits, git refuse sinon de réunir les deux branches.

## Les documents de la campagne

{annexes(cadrage)}"""


def opencode_de_campagne(configuration: dict[str, Any]) -> dict[str, Any]:
    """La configuration d'opencode de l'atelier, tous les agents sur un modèle admis."""
    agents = cast(dict[str, dict[str, Any]], configuration.setdefault("agent", {}))
    for nom in AGENTS:
        agents.setdefault(nom, {})["model"] = MODELE_ADMIS
    configuration["model"] = MODELE_ADMIS
    return configuration


def ouvrir(atelier: Path, nom: str, commit: str = "HEAD", jour: datetime.date | None = None) -> Path:
    if not NOM.match(nom):
        raise CampagneImpossible(f"nom invalide : {nom!r} (minuscules, chiffres, « - » et « _ »)", 2)
    if est_campagne(atelier):
        raise CampagneImpossible(f"{atelier} est déjà une campagne ; une campagne s'ouvre depuis l'atelier", 5)
    destination = dossier_campagnes(atelier) / nom
    if destination.exists():
        raise CampagneImpossible(f"la campagne existe déjà : {destination}", 3)
    complet = git("rev-parse", f"{commit}^{{commit}}", dans=atelier)
    try:
        git("merge-base", "--is-ancestor", complet, "main", dans=atelier)
    except CampagneImpossible as erreur:
        raise CampagneImpossible(f"le commit {complet[:12]} n'est pas dans main", 4) from erreur
    destination.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "--quiet", "--branch", "main", str(atelier), str(destination), dans=destination.parent)
    git("reset", "--quiet", "--hard", complet, dans=destination)
    git("remote", "remove", "origin", dans=destination)
    jour = jour or datetime.date.today()
    cadrage = (destination / CADRAGE).read_text(encoding="utf-8")
    chemin_fiche = destination / "00_docs" / "sources" / f"{jour.isoformat()}_campagne_{nom}.md"
    chemin_fiche.write_text(fiche(nom, jour, complet, cadrage, atelier.resolve()), encoding="utf-8")
    chemin_proposition = destination / "00_docs" / "sources" / f"{jour.isoformat()}_proposition_{nom}.md"
    chemin_proposition.write_text(proposition(cadrage), encoding="utf-8")
    chemin_opencode = destination / "opencode.json"
    configuration = cast(dict[str, Any], json.loads(chemin_opencode.read_text(encoding="utf-8")))
    texte = json.dumps(opencode_de_campagne(configuration), ensure_ascii=False, indent=2) + "\n"
    chemin_opencode.write_text(texte, encoding="utf-8")
    git(
        "add",
        str(chemin_fiche.relative_to(destination)),
        str(chemin_proposition.relative_to(destination)),
        "opencode.json",
        dans=destination,
    )
    git("commit", "--quiet", "-m", f"Ouverture de la campagne {nom}", dans=destination)
    return destination


def main(arguments: list[str] | None = None) -> int:
    lecteur = argparse.ArgumentParser(description="Ouvre une campagne, hors de l'atelier.")
    lecteur.add_argument("--nom", required=True)
    lecteur.add_argument("--commit", default="HEAD")
    args = lecteur.parse_args(arguments)
    try:
        atelier = atelier_de(Path(__file__).resolve().parents[2])
        destination = ouvrir(atelier, args.nom, args.commit)
    except CampagneImpossible as erreur:
        print(f"REFUS : {erreur}.", file=sys.stderr)
        return erreur.code
    print(f"Campagne ouverte : {destination}")
    print(f"  la fiche : {destination}/00_docs/sources/ (campagne_{args.nom})")
    print(f"  ensuite : cd {destination} && make installer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
