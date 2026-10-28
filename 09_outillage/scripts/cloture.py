"""Clôt une campagne : écrit l'attestation de suppression, puis supprime le dossier de la campagne
et ses postes de mesure (cadrage des interventions, section 5 et annexe D ; JOURNAL, entrée 316).

    make cloture NOM=<nom>

Lancé depuis l'atelier, jamais depuis une campagne. Le script refuse tant qu'un run tourne dans la
campagne ou ses postes. Il liste ce qui va disparaître : le clone, ses postes, ses runs, ses
rapports de travail, son `.env`. Il écrit l'attestation de suppression à côté des campagnes, dans
<atelier>_campagnes/<date>_attestation_suppression_<nom>.md, qui survit à la suppression et
se remet à l'entreprise une fois signée. Il ne supprime qu'après que la personne a retapé le nom de
la campagne : une suppression ne se rattrape pas.

Codes de refus : 2 un nom invalide, 3 la campagne n'existe pas, 4 un run tourne, 5 lancé depuis une
campagne, 6 la confirmation refusée, 7 une attestation du même jour existe déjà. Bibliothèque
standard seule ; Linux (`/proc`) pour reconnaître un run en cours.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from campagne import NOM, CampagneImpossible, atelier_de, dossier_campagnes, est_campagne


@dataclass(frozen=True)
class Inventaire:
    """Ce que la clôture supprime, et ce que la fiche de la campagne en dit."""

    campagne: Path
    postes: Path | None
    fichiers: int
    runs: list[str]
    rapports: list[str]
    cles: bool
    entreprise: str
    ouverture: str
    commit: str


def inventaire(campagne: Path) -> Inventaire:
    postes = campagne.parent / f"{campagne.name}_postes"
    local = campagne / "99_local"
    runs = sorted(p.name for p in (local / "runs").glob("*") if p.is_dir()) if (local / "runs").is_dir() else []
    rapports = (
        sorted(p.name for p in (local / "rapports").glob("*") if p.is_file()) if (local / "rapports").is_dir() else []
    )
    fichiers = sum(1 for p in campagne.rglob("*") if p.is_file() and ".git" not in p.relative_to(campagne).parts)
    fiches = sorted((campagne / "00_docs" / "sources").glob(f"*_campagne_{campagne.name}.md"))
    texte = fiches[-1].read_text(encoding="utf-8") if fiches else ""
    entreprise = re.search(r"^\| Entreprise \| (.*?) \|$", texte, re.MULTILINE)
    ouverture = re.search(r"Ouverte le (\d{4}-\d{2}-\d{2}) par `make campagne`, depuis le commit `(\w+)`", texte)
    return Inventaire(
        campagne=campagne,
        postes=postes if postes.is_dir() else None,
        fichiers=fichiers,
        runs=runs,
        rapports=rapports,
        cles=(campagne / ".env").is_file(),
        entreprise=entreprise.group(1).strip() if entreprise else "[entreprise]",
        ouverture=ouverture.group(1) if ouverture else "[date]",
        commit=ouverture.group(2) if ouverture else "[commit]",
    )


def run_en_cours(dossiers: list[Path]) -> bool:
    """Vrai si un processus ease.mesure tourne dans l'un de ces dossiers (Linux, /proc)."""
    racines = [str(d.resolve()) for d in dossiers]
    for processus in Path("/proc").glob("[0-9]*"):
        try:
            commande = (processus / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            dossier = str((processus / "cwd").readlink())
        except OSError:
            continue
        if "ease.mesure" in commande and any(dossier == r or dossier.startswith(r + os.sep) for r in racines):
            return True
    return False


def attestation(nom: str, jour: datetime.date, inv: Inventaire) -> str:
    def liste(noms: list[str]) -> str:
        return ", ".join(f"`{n}`" for n in noms) if noms else "aucun"

    postes = f"`{inv.postes.name}/`" if inv.postes is not None else "aucun"
    return f"""# Attestation de suppression

Campagne `{nom}`, menée pour {inv.entreprise}. Ouverte le {inv.ouverture} depuis le commit `{inv.commit}`
de l'atelier d'Épreuve d'agent ; close le {jour.isoformat()}.

Ont été supprimés le {jour.isoformat()}, sans copie conservée :

- le dossier de la campagne, `{nom}/`, son code et ses données ({inv.fichiers} fichiers) ;
- ses postes de mesure : {postes} ;
- ses runs : {liste(inv.runs)} ;
- ses rapports de travail : {liste(inv.rapports)} ;
- son fichier de clés (`.env`) : {"supprimé" if inv.cles else "aucun"}.

Rien de ce que {inv.entreprise} a confié ni des résultats de la campagne ne reste chez Épreuve d'agent,
hormis cette attestation.

Remis à {inv.entreprise}, qui les garde : [le rapport du date, la présentation du date].

Fait le {jour.isoformat()}.

Alexandre Do, Épreuve d'agent

Signature :
"""


def clore(atelier: Path, nom: str, confirmer: Callable[[str], bool], jour: datetime.date | None = None) -> Path:
    """Écrit l'attestation, demande la confirmation, puis supprime ; rend le chemin de l'attestation."""
    if not NOM.match(nom):
        raise CampagneImpossible(f"nom invalide : {nom!r}", 2)
    if est_campagne(atelier):
        raise CampagneImpossible(f"{atelier} est une campagne ; une campagne se clôt depuis l'atelier", 5)
    campagne = dossier_campagnes(atelier) / nom
    if not campagne.is_dir():
        raise CampagneImpossible(f"la campagne n'existe pas : {campagne}", 3)
    inv = inventaire(campagne)
    dossiers = [campagne] + ([inv.postes] if inv.postes is not None else [])
    if run_en_cours(dossiers):
        raise CampagneImpossible("un run tourne dans la campagne ou ses postes ; attendre sa fin", 4)
    jour = jour or datetime.date.today()
    chemin = campagne.parent / f"{jour.isoformat()}_attestation_suppression_{nom}.md"
    if chemin.exists():
        raise CampagneImpossible(f"une attestation existe déjà : {chemin}", 7)
    print(f"La clôture de {nom} supprime, sans retour possible :")
    for dossier in dossiers:
        print(f"  {dossier}")
    print(f"  dont {len(inv.runs)} run(s), {len(inv.rapports)} rapport(s), {'un' if inv.cles else 'aucun'} .env")
    if not confirmer(nom):
        raise CampagneImpossible("confirmation refusée ; rien n'est supprimé", 6)
    chemin.write_text(attestation(nom, jour, inv), encoding="utf-8")
    for dossier in reversed(dossiers):
        shutil.rmtree(dossier)
    return chemin


def confirmer_au_clavier(nom: str) -> bool:
    return input(f"Pour supprimer, retape le nom de la campagne ({nom}) : ").strip() == nom


def main(arguments: list[str] | None = None) -> int:
    lecteur = argparse.ArgumentParser(description="Clôt une campagne : attestation, puis suppression.")
    lecteur.add_argument("--nom", required=True)
    args = lecteur.parse_args(arguments)
    try:
        atelier = atelier_de(Path(__file__).resolve().parents[2])
        chemin = clore(atelier, args.nom, confirmer_au_clavier)
    except CampagneImpossible as erreur:
        print(f"REFUS : {erreur}.", file=sys.stderr)
        return erreur.code
    print(f"Campagne {args.nom} supprimée. Attestation à compléter, signer et remettre : {chemin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
